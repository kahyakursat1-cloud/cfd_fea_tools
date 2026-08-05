"""3B kanat poları — VLM taşıması + 2B kesit sürüklemesi + indüklenen direnç.

NEDEN BU YOL: ince kanatta 3B viskoz RANS mutlak taşımayı VEREMİYOR. Ölçüldü
(NACA0012 AR6 çapası, 2026-08-02): firar kenarı 1.3 hücre, hücre 20.6 KAT
artarken Cl yalnız %23 arttı (0.0572 → 0.0705, beklenen 0.329). Taşıma
sirkülasyondan, sirkülasyon Kutta koşulundan doğar; RANS o koşulu ağla kurar ve
bir hücrelik firar kenarında kuramaz. Hedef ≥6 hücre için yalnız yüzeyde
~775.000 yüz gerekir — bu donanımda çözülemez.

VLM/panel yöntemi Kutta koşulunu firar kenarında ANALİTİK dayatır; orada hücre
yoktur, dolayısıyla bu tıkanıklık VLM'de hiç oluşmaz. Havacılıkta ön-tasarımın
standart iş bölümü budur:

    Cl_3B(α)  ← VLM (sonlu-kanat düzeltmesi zaten içinde)
    Cd_3B(α)  = Cd_profil(Cl) [2B viskoz] + CDi [VLM] + Δ_entegrasyon [3B RANS]

BU MODÜL YENİ CFD KOŞMAZ; mevcut kanıtları birleştirir. Ama körlemesine
birleştirmez — birleştirme ancak parçalar UYUMLUYSA geçerlidir ve uyumsuzluğu
sessizce yutmak, bu depoda avlanan kusurun ta kendisidir. Kapılar:

  1. KESİT TİPİ    simetrik/kamburlu tutarlılığı (α_L0 kayması)
  2. REYNOLDS      kesit verisi kanadın Re'sinde mi (Cd0 ~ Re^-0.2 ile ölçeklenir)
  3. MESH-BAĞIMSIZ kesit Cd'si yakınsamış mı — değilse MUTLAK Cd üretilmez
  4. α ÖRTÜŞMESİ   ekstrapolasyon yok
  5. LİNEER BÖLGE  2B geçiş modeli α≥10°'de bozuluyor (ölçüldü: Cl hatası %45)

CLI:  python polar_birlestirme.py            (depodaki kanıtlarla dener)
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Kesit verisi kanadın Re'sinden bu katsayıdan fazla ayrılırsa MUTLAK sürükleme
# üretilmez. Türbülanslı sürtünme Cd ~ Re^-0.2; 2 kat Re farkı ~%15 Cd farkı
# demektir ve bu, kesit bandının kendisiyle aynı mertebeye çıkar.
RE_TOLERANS = 2.0
# 2B geçiş modelinin güvenilir olduğu üst sınır — ÖLÇÜLDÜ (transition_results):
# α=8°'de Cl hatası %7.8, α=10°'de %45. Aradaki fark model bozulmasıdır.
LINEER_ALFA_MAX = 8.0


def _re_olcek(re_hedef: float, re_kaynak: float) -> float:
    """Türbülanslı sürtünme sürüklemesinin Reynolds ölçeklemesi (Cf ~ Re^-0.2).

    Bu bir DÜZELTME DEĞİL, bir BÜYÜKLÜK KESTİRİMİdir: kesit verisi yanlış Re'de
    ise ne kadar yanıldığımızı söyler. Düzeltip kullanmak, ölçülmemiş bir modeli
    ölçüm gibi sunmak olurdu.
    """
    return (re_kaynak / max(re_hedef, 1.0)) ** 0.2


def kesit_polari(kayitlar: list[dict]) -> list[tuple[float, float]]:
    """(Cl, Cd) çiftleri — sürükleme poları. Cl'e göre sıralı."""
    return sorted(((float(k["Cl"]), float(k["Cd"])) for k in kayitlar),
                  key=lambda t: t[0])


def _ara_deger(polar: list[tuple[float, float]], cl: float) -> float | None:
    """Cl'de doğrusal ara değer. EKSTRAPOLASYON YOK — dışarıdaysa None."""
    if len(polar) < 2 or cl < polar[0][0] or cl > polar[-1][0]:
        return None
    for (c0, d0), (c1, d1) in zip(polar, polar[1:]):
        if c0 <= cl <= c1:
            if abs(c1 - c0) < 1e-12:
                return d0
            return d0 + (d1 - d0) * (cl - c0) / (c1 - c0)
    return None


def birlesik_polar(vlm_polar: list[dict], kesit: list[dict], *,
                   re_kanat: float, re_kesit: float,
                   kesit_cd_mesh_bagimsiz: bool,
                   kesit_cd_band_pct: float | None = None,
                   kesit_simetrik: bool = True, vlm_simetrik: bool = True,
                   delta_entegrasyon: float = 0.0,
                   vlm_band_pct: float | None = None,
                   vlm_band_kaynagi: str | None = None) -> dict:
    """VLM + 2B kesit → 3B polar. Kapılardan geçmeyen bileşen ÜRETİLMEZ.

    Döner: {"noktalar": [...], "engeller": [...], "uyarilar": [...], "verdikt"}
    Engel varsa `noktalar` yalnız TAŞIMA taşır; mutlak Cd yayınlanmaz.
    """
    engeller: list[str] = []
    uyarilar: list[str] = []

    if kesit_simetrik != vlm_simetrik:
        engeller.append(
            f"KESİT TİPİ UYUŞMUYOR: 2B veri {'simetrik' if kesit_simetrik else 'kamburlu'}, "
            f"VLM {'simetrik' if vlm_simetrik else 'kamburlu'} — α_L0 kayması "
            "birinde var birinde yok; polarlar aynı eğriye ait değil")

    oran = max(re_kanat, re_kesit) / max(min(re_kanat, re_kesit), 1.0)
    if oran > RE_TOLERANS:
        engeller.append(
            f"REYNOLDS UYUŞMUYOR: kanat Re={re_kanat:.2e}, kesit verisi Re={re_kesit:.2e} "
            f"({oran:.1f} kat). Türbülanslı sürtünme Cd~Re^-0.2 ile ölçeklenir; bu fark "
            f"profil sürüklemesinde ~{(_re_olcek(re_kanat, re_kesit) - 1) * 100:.0f}% "
            "sistematik sapma demektir. Kesit verisi kanadın Re'sinde koşulmalı")

    if not kesit_cd_mesh_bagimsiz:
        engeller.append(
            "KESİT Cd MESH-BAĞIMSIZ DEĞİL: bu veriden MUTLAK profil sürüklemesi "
            "üretilmez. (Taşıma etkilenmez — Cl mesh'e çok daha az duyarlıdır.)")

    polar2b = kesit_polari(kesit)
    noktalar = []
    for p in vlm_polar:
        a = float(p["alpha"])
        cl = float(p.get("Cl", 0.0))
        cdi = float(p.get("Cd_i", 0.0))
        n = {"alpha": a, "Cl": round(cl, 5), "CDi": round(cdi, 6)}
        if a > LINEER_ALFA_MAX:
            n["uyari"] = (f"α={a}° lineer bölge dışında (>{LINEER_ALFA_MAX}°); 2B geçiş "
                          "modeli burada bozuluyor — ÖLÇÜLDÜ: α=10°'de Cl hatası %45")
        if not engeller:
            cd0 = _ara_deger(polar2b, cl)
            if cd0 is None:
                n["Cd_notu"] = (f"Cl={cl:.3f} 2B veri aralığının "
                                f"[{polar2b[0][0]:.3f}, {polar2b[-1][0]:.3f}] DIŞINDA "
                                "— ekstrapolasyon yapılmaz")
            else:
                n["Cd_profil"] = round(cd0, 6)
                n["Cd_toplam"] = round(cd0 + cdi + delta_entegrasyon, 6)
                if kesit_cd_band_pct is not None and n["Cd_toplam"] > 0:
                    # Band YALNIZ profil bileşenine ait; CDi'nin kendi bandı VLM
                    # doğrulaması olmadan bilinmiyor ve uydurulmuyor.
                    n["Cd_band_pct"] = round(
                        kesit_cd_band_pct * cd0 / n["Cd_toplam"], 2)
        noktalar.append(n)

    if vlm_band_pct is None:
        uyarilar.append(
            "TAŞIMA BANDI ÖLÇÜLMEMİŞTİR: VLM bu geometride panel-yakınsaması "
            "ölçülmedi; Cl değerleri literatür-öncül statüsündedir. Ölçüm için: "
            "experiments/vlm_panel_yakinsamasi.py")
    else:
        for n in noktalar:
            n["Cl_band_pct"] = vlm_band_pct
        # METIN KANITTAN URETILIR, SABIT YAZILMAZ. Ilk surumde olculen seri
        # metne GOMULMUSTU; uc kumelemesi eklenip seri monotonlasinca metin
        # "dizi MONOTON DEGIL" demeye DEVAM ETTI — yani rapor, uzerinde
        # calistigi veriyle celisiyordu. Bu depoda avlanan kusurun rapor
        # katmanindaki hali.
        uyarilar.append(
            f"TAŞIMA BANDI ÖLÇÜLDÜ: ±%{vlm_band_pct} — bu bir DOĞRULAMA bandı "
            "DEĞİL, VLM'in bu geometrideki PANEL AYRIKLAŞTIRMA bandıdır"
            + (f" ({vlm_band_kaynagi})" if vlm_band_kaynagi else "")
            + ". Temiz dikdörtgen kanat çapasındaki doğrulama bandı buraya "
              "TAŞINAMAZ; taşınsaydı olmayan bir kesinlik yayınlanırdı. Ayrıntı: "
              "vlm_panel_yakinsamasi.json")

    verdikt = ("3B polar üretildi (Cl + Cd)" if not engeller else
               "YALNIZ TAŞIMA üretildi — mutlak sürükleme için engeller var: "
               + " | ".join(e.split(":")[0] for e in engeller))
    return {"noktalar": noktalar, "engeller": engeller, "uyarilar": uyarilar,
            "verdikt": verdikt,
            "yontem": ("Cl_3B ← VLM; Cd_3B = Cd_profil(Cl) [2B viskoz] + CDi [VLM]"
                       + (" + Δ_entegrasyon [3B RANS]" if delta_entegrasyon else ""))}


def _depo_verisi() -> dict:
    """Depodaki kanıtlarla dene — sayılar KANITTAN, elle yazılmaz.

    KESİT KAYNAĞI ÖNCELİĞİ: XFOIL kesiti kanadın kendi Re'sinde üretilmişse o
    kullanılır; yoksa eski RANS/O-grid verisine düşülür. Düşülürse engeller
    (Re uyuşmazlığı, mesh-bağımsızlık yok) zaten devreye girer ve mutlak
    sürükleme yayınlanmaz — sessiz bir geri düşüş DEĞİLDİR.
    """
    vlm = json.loads((HERE / "vspaero_polar.json").read_text(encoding="utf-8"))
    # VLM TASIMA BANDI: capadaki %1.22 TEMIZ kanata aittir ve gercek araca
    # tasinmaz. Bu geometrinin KENDI panel sacilmasi olculduyse o kullanilir.
    _pk = HERE / "vlm_panel_yakinsamasi.json"
    vlm_band = vlm_band_kaynagi = None
    if _pk.exists():
        _d = json.loads(_pk.read_text(encoding="utf-8"))
        vlm_band = _d.get("vlm_band_pct")
        _kb = _d.get("kanonik_band") or {}
        _y = _d.get("yakinsama") or {}
        vlm_band_kaynagi = (
            f"{_kb.get('kaynak', 'panel serisi')}; dizi "
            f"{'monoton' if _y.get('monoton') else 'MONOTON DEGIL'}, "
            f"paneller {_d.get('paneller')}, uc kumeleme "
            f"{(_d.get('kayitlar') or [{}])[-1].get('uc_kumeleme')}")
    from aircraft_geometry import AircraftLibrary
    ac = AircraftLibrary().get_template("mini_hawk")()
    kiris = ac.wing.root_chord()
    re_kanat = 15.0 * kiris / 1.5e-5

    xf = HERE / "kesit_re35e4.json"
    if xf.exists():
        d = json.loads(xf.read_text(encoding="utf-8"))
        pb = d.get("panel_bagimsizligi") or {}
        return {"vlm_polar": vlm["polar"], "kesit": d["polar"],
                "re_kanat": re_kanat, "re_kesit": float(d["re"]),
                # XFOIL'de mesh yok; AYRIKLASTIRMA parametresi PANEL SAYISIDIR ve
                # bandi OLCULDU. "Bagimsiz" iddiasi olcume dayanir, varsayima degil.
                "kesit_cd_mesh_bagimsiz": bool(pb) and pb["en_kotu_sapma_pct"] < 5.0,
                "kesit_cd_band_pct": pb.get("en_kotu_sapma_pct"),
                "kesit_kaynagi": f"XFOIL ({d.get('yontem', '')})",
                "vlm_band_pct": vlm_band,
                "vlm_band_kaynagi": vlm_band_kaynagi,
                "kiris": kiris}

    tr = json.loads((HERE / "transition_results.json").read_text(encoding="utf-8"))
    gci = json.loads((HERE / "gci_airfoil.json").read_text(encoding="utf-8"))
    kesit = [{"alpha": float(a), **v} for a, v in tr.items()
             if a.lstrip("-").isdigit() and isinstance(v, dict)]
    ref = (gci.get("reference") or {}).get("kaynak", "")
    re_kesit = 3.4e6 if "3.4e6" in ref else 0.0
    return {"vlm_polar": vlm["polar"], "kesit": kesit, "re_kanat": re_kanat,
            "re_kesit": re_kesit, "kesit_cd_mesh_bagimsiz": False,
            "kesit_cd_band_pct": None,
            "kesit_kaynagi": "RANS O-grid (Re=3.4e6 — kanadin Re'si DEGIL)",
                "vlm_band_pct": vlm_band,
                "vlm_band_kaynagi": vlm_band_kaynagi,
            "kiris": kiris}


def main() -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    d = _depo_verisi()
    out = birlesik_polar(d["vlm_polar"], d["kesit"],
                         re_kanat=d["re_kanat"], re_kesit=d["re_kesit"],
                         kesit_cd_mesh_bagimsiz=d["kesit_cd_mesh_bagimsiz"],
                         kesit_cd_band_pct=d.get("kesit_cd_band_pct"),
                         vlm_band_pct=d.get("vlm_band_pct"),
                         vlm_band_kaynagi=d.get("vlm_band_kaynagi"))
    print(f"MiniHawk kiris={d['kiris']:.3f} m, V=15 m/s → Re={d['re_kanat']:.2e}")
    print(f"2B kesit: {d.get('kesit_kaynagi', '?')}  Re={d['re_kesit']:.2e}"
          + (f"  ayrıklaştırma bandı %{d['kesit_cd_band_pct']}"
             if d.get("kesit_cd_band_pct") is not None else "") + "\n")
    for n in out["noktalar"]:
        s = f"  α={n['alpha']:>5.1f}°  Cl={n['Cl']:.4f}  CDi={n['CDi']:.5f}"
        if "Cd_toplam" in n:
            s += (f"  Cd_profil={n['Cd_profil']:.5f}  Cd={n['Cd_toplam']:.5f}"
                  + (f" ±%{n['Cd_band_pct']}" if "Cd_band_pct" in n else ""))
        print(s)
        for k in ("uyari", "Cd_notu"):
            if k in n:
                print(f"          ⚠ {n[k]}")
    print()
    for e in out["engeller"]:
        print("⛔ " + e)
    for u in out["uyarilar"]:
        print("⚠  " + u)
    print("\n" + out["verdikt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
