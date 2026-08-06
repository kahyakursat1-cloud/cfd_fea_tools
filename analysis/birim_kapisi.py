"""Birim kapısı — sayının BÜYÜKLÜĞÜNDEN birim hatasını yakalar.

NEDEN: bu depoda aynı alan adı iki farklı birimde yaşıyor. `material_database`
`youngs_modulus`'ü GPa (Al 6061 → 69), `fea_runner` aynı adı MPa (69000) tutuyor;
`analysis/calculix_writer` ise Pa istiyor. Üç katman arası her geçiş 10³'lük bir
hata fırsatıdır ve hiçbiri çalışma-zamanında kontrol edilmiyordu. 69 GPa yerine
69 Pa yazılırsa CalculiX şikâyet etmez — sehimi 10⁹ kat büyük, tamamen "geçerli
görünen" bir sonuç üretir.

YÖNTEM: birim etiketine GÜVENMEZ, fiziğe bakar. Katı mühendislik malzemelerinde
  E ∈ [1 MPa, 1.5 TPa]        (elastomer … elmas)
  E/σ_y ∈ [20, 3000]          (boyutsuz — birim hatasında 10³ kayar)
  E/ρ ∈ [1e4, 1e9] m²/s²      (özgül sertlik; Pa/(kg/m³))
Bu üçünün ikisi boyutsuz-benzeri olduğu için ölçek hatasını birim etiketinden
BAĞIMSIZ yakalar: E ve σ_y birlikte yanlış birimdeyse E/ρ, tek başına yanlışsa
E/σ_y patlar.

Kapı SESSİZ DÜZELTMEZ. Bir sayıyı "herhâlde GPa'ydı" diye 1e9 ile çarpmak, bu
deponun tüm reddettiği şeydir: tahmin edilen düzeltme, yanlış sonucu doğru
gösterir. Kapı yalnızca reddeder ve hangi birimin tutarlı olacağını söyler.
"""
from __future__ import annotations

E_PA_BANDI = (1e6, 1.5e12)
E_SIGMA_ORANI = (20.0, 3000.0)
E_RHO_ORANI = (1e4, 1e9)
RHO_BANDI = (10.0, 25000.0)          # köpük … tungsten
NU_BANDI = (-1.0, 0.5)

_CARPAN = {"Pa": 1.0, "kPa": 1e3, "MPa": 1e6, "GPa": 1e9}


def olasi_birim(e_deger: float, rho: float | None = None,
                sigma_y_pa: float | None = None) -> list[str]:
    """Bu SAYI hangi birimlerde fiziksel olurdu? Boş liste = hiçbirinde."""
    uygun = []
    for ad, k in _CARPAN.items():
        e_pa = e_deger * k
        if not (E_PA_BANDI[0] <= e_pa <= E_PA_BANDI[1]):
            continue
        if rho and not (E_RHO_ORANI[0] <= e_pa / rho <= E_RHO_ORANI[1]):
            continue
        if sigma_y_pa and not (E_SIGMA_ORANI[0] <= e_pa / sigma_y_pa
                               <= E_SIGMA_ORANI[1]):
            continue
        uygun.append(ad)
    return uygun


def malzeme_denetle(ad: str, e_deger: float, birim: str, rho: float,
                    sigma_y: float | None = None, birim_sigma: str = "MPa",
                    nu: float | None = None) -> list[str]:
    """Bir malzeme kaydının BEYAN EDİLEN birimiyle fiziksel tutarlılığı.

    Döner: ihlal metinleri (boş = tutarlı). Beyan edilen birim yanlışsa hangi
    birimin tutarlı olacağı da söylenir — düzeltme UYGULANMAZ, önerilir.
    """
    if birim not in _CARPAN:
        return [f"{ad}: birim '{birim}' tanınmıyor ({'/'.join(_CARPAN)})"]
    if birim_sigma not in _CARPAN:
        return [f"{ad}: σ_y birimi '{birim_sigma}' tanınmıyor ({'/'.join(_CARPAN)})"]
    ihlal: list[str] = []
    e_pa = e_deger * _CARPAN[birim]
    # E ve sigma_y AYNI birimde OLMAK ZORUNDA DEGIL: bu depoda materials.json
    # E'yi GPa, sigma_y'yi MPa tutar. Oran bu yuzden Pa'ya cevrilerek kurulur;
    # aksi halde kapi dogru semayi hatali sanar (ilk surumde tam bu oldu).
    sy_pa = sigma_y * _CARPAN[birim_sigma] if sigma_y else None
    if not (E_PA_BANDI[0] <= e_pa <= E_PA_BANDI[1]):
        alt = olasi_birim(e_deger, rho, sy_pa)
        ihlal.append(
            f"{ad}: E={e_deger} {birim} → {e_pa:.3g} Pa, fiziksel bantta DEĞİL "
            f"[{E_PA_BANDI[0]:.0e}, {E_PA_BANDI[1]:.0e}]"
            + (f" — sayı {'/'.join(alt)} olarak tutarlı olurdu" if alt
               else " — hiçbir birimde tutarlı değil, veri hatalı"))
    if not (RHO_BANDI[0] <= rho <= RHO_BANDI[1]):
        ihlal.append(f"{ad}: ρ={rho} kg/m³ bantta değil {RHO_BANDI} "
                     "(g/cm³ girilmiş olabilir — 1000× fark)")
    elif not (E_RHO_ORANI[0] <= e_pa / rho <= E_RHO_ORANI[1]):
        ihlal.append(f"{ad}: E/ρ={e_pa / rho:.3g} m²/s² özgül-sertlik bandı dışında "
                     f"{E_RHO_ORANI} — E ya da ρ birimi yanlış")
    if sy_pa:
        oran = e_pa / sy_pa
        if not (E_SIGMA_ORANI[0] <= oran <= E_SIGMA_ORANI[1]):
            ihlal.append(f"{ad}: E/σ_y={oran:.3g} bandı dışında {E_SIGMA_ORANI} — "
                         f"E={e_deger} {birim} ve σ_y={sigma_y} {birim_sigma} "
                         "birlikte fiziksel değil; biri 10³ kaymış")
    if nu is not None and not (NU_BANDI[0] < nu < NU_BANDI[1]):
        ihlal.append(f"{ad}: ν={nu} termodinamik sınır dışında {NU_BANDI}")
    return ihlal


def pa_dogrula(ad: str, e_pa: float, rho: float,
               sigma_y_pa: float | None = None) -> None:
    """Pa BEKLEYEN katmanın giriş kapısı — ihlalde ValueError.

    calculix_writer.FEAMaterial buradan geçer: GPa/MPa değeri Pa alanına
    yazıldığında çözücü şikâyet etmez, sehimi 10³–10⁹ kat kaydırır.
    """
    ihlal = malzeme_denetle(ad, e_pa, "Pa", rho,
                            sigma_y=sigma_y_pa if sigma_y_pa else None,
                            birim_sigma="Pa")
    if ihlal:
        raise ValueError(
            "BİRİM KAPISI — Pa bekleyen alana fiziksel olmayan değer: "
            + "; ".join(ihlal)
            + ". Değer TAHMİNLE düzeltilmez: doğru birimle yeniden verin "
              "(FEAMaterial.from_gpa GPa/MPa girdiyi kendisi çevirir).")
