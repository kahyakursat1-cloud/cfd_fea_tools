"""`bluff.wall_resolved` hücresi neden boş — FİZİKSEL gerekçe + hesap kestirimi.

NEDEN: model-form tablosunun bu hücresi "yapılacaklar" listesinde duruyordu ve
gerekçesi "pahalı" idi. Bu yetersiz bir gerekçedir: bir hücrenin kapanmaması
maliyet meselesi mi, yoksa vakanın kendisi mi uygun değil --- ikisi farklı
şeylerdir ve okuyucu hangisi olduğunu bilmelidir.

BULGU: elde olan üç künt çapanın hiçbiri bu hücreye UYGUN DEĞİL, ve neden
maliyet değil FİZİK:

  küp, disk   → çapa tanımında "keskin-kenar, Re-duyarsız" yazılı. Ayrılma
                noktası geometriktir (kenar); sınır tabaka durumu C_d'yi
                belirlemez. y⁺'ı düşürmek model-form hatasını değiştirmez.
  küre        → çapa aralığı "1e3-2e5 (subkritik)". Bu aralıkta yüzey sınır
                tabakası LAMİNERDİR; ayrılma laminer ayrılmadır. y⁺<5 ağ
                laminer bir tabakayı çözer --- "duvar-çözünür TÜRBÜLANSLI
                sınır tabaka" değildir. Model hatası duvardan değil İZ
                modellemesinden gelir.
  Ahmed 25°   → Re~1e6; gövde üzerinde türbülanslı sınır tabaka VAR ve arka
                eğimdeki ayrılma ona duyarlıdır. TEK uygun aday budur.

Yani hücre, künt cisim ailesinin geniş bir kısmında ilkece tanımsızdır; yalnız
yüksek-Re, eğimli-yüzeyli gövdelerde anlamlıdır.

Betik ayrıca Ahmed vakası için hesap bütçesini ÖLÇÜLMÜŞ katsayılarla kestirir
(bellek: 0,779 kB/hücre; süre: 3B koşudan) --- "pahalı" demek yerine ne kadar.

    python experiments/bluff_duvar_cozunur_fizibilite.py
Çıktı: bluff_duvar_cozunur_fizibilite.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

NU = 1.5e-5          # m²/s, hava
YPLUS_HEDEF = 1.0
BUYUME = 1.2         # katman büyüme oranı
KATMAN_SONU_M = 5e-3  # katman yığınının bittiği hücre boyu


def ilk_hucre(u_inf: float, l_ref: float) -> tuple[float, float]:
    """Hedef y⁺ için ilk hücre yüksekliği (m) ve u_tau.

    Cf için 1/7-kuvvet yasası (Schlichting) kullanılır; künt gövdede yerel
    değer değişir ama mertebe doğrudur. y⁺ hücre MERKEZİNDE tanımlı olduğundan
    ilk hücre yüksekliği iki katıdır (bu çarpan düz levha çapasında ölçülerek
    doğrulandı: çarpansız sürüm hedefin yarısını veriyordu).
    """
    re_l = u_inf * l_ref / NU
    cf = 0.0592 * re_l ** -0.2
    u_tau = u_inf * math.sqrt(cf / 2.0)
    return 2.0 * YPLUS_HEDEF * NU / u_tau, u_tau


def katman_sayisi(ilk: float) -> int:
    """İlk hücreden KATMAN_SONU_M'ye geometrik büyümeyle kaç katman."""
    return max(1, math.ceil(math.log(KATMAN_SONU_M / ilk) / math.log(BUYUME)))


def ahmed_kestirimi() -> dict:
    """Ahmed gövdesi (L=1,044 m, Re~1e6) için duvar-çözünür ağ bütçesi."""
    l_ref, u_inf = 1.044, 15.0
    yuzey_alani = 1.5          # m², gövde ıslak alanı (kaba)
    ilk, u_tau = ilk_hucre(u_inf, l_ref)
    n_katman = katman_sayisi(ilk)
    # Yuzey hucre boyu: katman yiginin bittigi olcek mertebesinde
    yuzey_hucre = KATMAN_SONU_M
    n_yuzey = yuzey_alani / yuzey_hucre ** 2
    n_prizma = n_yuzey * n_katman
    # Dis alan: prizma tabakasinin ~2-3 kati (snappy deneyiminden)
    n_toplam = n_prizma * 3.0

    import bellek_kapisi
    bel = bellek_kapisi.tahmini_gb(int(n_toplam))
    bos = bellek_kapisi.bos_bellek_gb()

    # Sure: 3B URANS olcumu 403.200 hucre / 3300 adim / 2 saat (4 cekirdek).
    # Kararli RANS ~2000 iterasyon; hucre basina maliyet dogrusal varsayilir.
    ref_hucre, ref_adim, ref_saat = 403_200, 3300, 2.0
    saat = ref_saat * (n_toplam / ref_hucre) * (2000 / ref_adim)

    return {
        "vaka": "Ahmed gövdesi 25°, duvar-çözünür (y⁺≈1)",
        "L_m": l_ref, "U_ms": u_inf, "Re_L": u_inf * l_ref / NU,
        "ilk_hucre_um": round(ilk * 1e6, 2),
        "u_tau_ms": round(u_tau, 4),
        "katman_sayisi": n_katman,
        "yuzey_hucre_mm": KATMAN_SONU_M * 1e3,
        "hucre_kestirimi": int(n_toplam),
        "bellek_gb": round(bel["gereken_gb"], 2),
        "bellek_kaynagi": bel["kaynak"],
        "bos_bellek_gb": round(bos, 2) if bos else None,
        "bellege_sigar_mi": (bos is not None and bel["gereken_gb"] < bos),
        "sure_saat_kestirim": round(saat, 1),
        "_sure_dayanagi": (f"3B URANS ölçümü: {ref_hucre:,} hücre / {ref_adim} "
                           f"adım / {ref_saat} saat (4 çekirdek); hücre başına "
                           "maliyet doğrusal varsayıldı"),
    }


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")

    import validation_anchors as va
    kunt = {k: v for k, v in va.ANCHORS.items() if v.get("regime") == "bluff"}
    uygunluk = []
    for ad, spec in kunt.items():
        re_notu = str(spec.get("Re", ""))
        if "keskin-kenar" in re_notu:
            hukum, neden = "UYGUN DEĞİL", ("ayrılma noktası geometrik (keskin "
                                           "kenar); duvar işlemi C_d'yi "
                                           "belirlemez")
        elif "subkritik" in re_notu:
            hukum, neden = "UYGUN DEĞİL", ("subkritik Re'de yüzey sınır tabakası "
                                           "LAMİNER; y⁺<5 ağ türbülanslı değil "
                                           "laminer tabaka çözer")
        else:
            hukum, neden = "UYGUN", ("yüksek Re, türbülanslı sınır tabaka ve "
                                     "ayrılma ona duyarlı")
        uygunluk.append({"capa": ad, "Re": re_notu, "hukum": hukum,
                         "neden": neden, "referans": spec.get("ref")})

    ahmed = ahmed_kestirimi()
    uygun = [u for u in uygunluk if u["hukum"] == "UYGUN"]

    rec = {
        "vaka": "bluff.wall_resolved — hücrenin boş kalma nedeni (fizik + bütçe)",
        "_neden": ("Hucrenin gerekcesi 'pahali' idi. Bir hucrenin kapanmamasi "
                   "maliyet meselesi mi yoksa vaka mi uygun degil — ikisi "
                   "farklidir ve okuyucu hangisi oldugunu bilmelidir."),
        "capa_uygunlugu": uygunluk,
        "uygun_capa_sayisi": len(uygun),
        "ahmed_butcesi": ahmed,
        "_uretim": "Üretim: python experiments/bluff_duvar_cozunur_fizibilite.py",
    }
    rec["verdikt"] = (
        f"Künt çapaların {len(kunt) - len(uygun)}/{len(kunt)}'i bu hücreye "
        "FİZİKSEL olarak uygun değil: keskin kenarlı cisimlerde ayrılma "
        "geometriktir, subkritik kürede sınır tabaka laminerdir. Tek uygun aday "
        f"Ahmed gövdesi ve duvar-çözünür bütçesi ≈{ahmed['hucre_kestirimi']:,} "
        f"hücre, {ahmed['bellek_gb']} GB, ~{ahmed['sure_saat_kestirim']:.0f} saat "
        + ("— bu makinede belleğe SIĞMIYOR"
           if not ahmed["bellege_sigar_mi"] else
           "— bellek sınırında ama sığıyor") + ". Hücre bu yüzden öncülle "
        "kalıyor; gerekçe artık 'pahalı' değil, ÖLÇÜLMÜŞ.")

    import ortam
    ortam.damgala(rec)
    (KOK / "bluff_duvar_cozunur_fizibilite.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(rec["vaka"] + "\n" + "=" * 74)
    for u in uygunluk:
        im = "✅" if u["hukum"] == "UYGUN" else "❌"
        print(f"{im} {u['capa']:<12} Re={u['Re']:<28} {u['neden'][:60]}")
    print("\nAHMED DUVAR-ÇÖZÜNÜR BÜTÇESİ (ölçülmüş katsayılarla)")
    for k in ("ilk_hucre_um", "katman_sayisi", "hucre_kestirimi", "bellek_gb",
              "bos_bellek_gb", "sure_saat_kestirim"):
        print(f"  {k:<22} {ahmed[k]}")
    print("\n" + rec["verdikt"])
    print("-> bluff_duvar_cozunur_fizibilite.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
