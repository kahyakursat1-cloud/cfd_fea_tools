"""Girdi belirsizliği yayılımı — MiniHawk kanat sürüklemesi.

ASME V&V 20'nin sekiz adımından biri eksikti: girdi belirsizliği yayılımı.
Bu deney onu KANAT BİRLEŞTİRME yolunda kapatır, çünkü o yol ucuz ve
türevlenebilir: 2B kesit poları (XFOIL, önceden hesaplanmış) + taşıyıcı-çizgi
indüklenen direnci. Duyarlılıklar merkezi sonlu farkla ÖLÇÜLÜR.

RANS YOLUNDA YAPILMAZ ve nedeni yazılır: girdi başına iki koşu gerekir, her
koşu saatler sürer. Kestirim uydurmak yerine "bu yolda yayılmadı" denir.

Yayılan girdiler ve beyan edilen belirsizlikleri:
    hız        ±%2    pitot/anemometre tipik (kalibrasyonsuz)
    viskozite  ±%3    sıcaklık ±5 °C
    hücum açısı ±0.5° montaj/ölçüm toleransı
    kiriş      ±%1    STL/CAD ölçek ve imalat toleransı

    python experiments/girdi_uq_kanat.py
Çıktı: girdi_uq_kanat.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

from girdi_belirsizligi import (  # noqa: E402
    VARSAYILAN_KAYNAK,
    GirdiBelirsizligi,
    birlestir,
    yay,
)

ALFA_HEDEF = 4.0


def _kesit_polari() -> list[tuple[float, float, float]]:
    """(alpha, Cl, Cd) — XFOIL kesitinden, ARACIN Re'sinde üretilmiş."""
    d = json.loads((KOK / "kesit_re35e4.json").read_text(encoding="utf-8"))
    return [(float(n["alpha"]), float(n["Cl"]), float(n["Cd"]))
            for n in d["polar"]], float(d["re"])


def _ara(x: float, xs: list[float], ys: list[float]) -> float | None:
    """Doğrusal ara değer; EKSTRAPOLASYON YOK (dışarıdaysa None)."""
    if x < xs[0] or x > xs[-1]:
        return None
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if x0 <= x <= x1:
            return y0 if abs(x1 - x0) < 1e-12 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return None


def kur_model():
    """Cd_toplam(hiz, nu, alfa, kiris) — ucuz, türevlenebilir kanat modeli."""
    import lifting_line as ll
    from aircraft_geometry import AircraftLibrary
    polar, re_kesit = _kesit_polari()
    polar.sort(key=lambda t: t[0])
    a_ler = [p[0] for p in polar]
    cl_ler = [p[1] for p in polar]
    cd_ler = [p[2] for p in polar]

    ac = AircraftLibrary().get_template("mini_hawk")()
    ar = ac.wing.span ** 2 / ac.wing.area
    taper = ac.wing.taper_ratio
    e = ll.span_verimi(ar, taper)

    # ZINCIR BIRLESTIRICIYLE AYNI OLMALI, yoksa BASKA BIR BUYUKLUGUN
    # belirsizligi hesaplanmis olur. Birlestirici: Cl 3B VLM'den gelir, kesit
    # Cd'si O Cl'de aranir, induklenen direnc yine 3B Cl'den. Ilk surumde 2B Cl
    # kullanilmisti ve Cd_nominal 0.0414 cikiyordu — yayimlanan 0.0197 degil.
    vlm = json.loads((KOK / "vspaero_polar.json").read_text(encoding="utf-8"))["polar"]
    vlm = sorted(((float(p["alpha"]), float(p["Cl"])) for p in vlm
                  if p.get("Cl") is not None), key=lambda t: t[0])
    v_a = [t[0] for t in vlm]
    v_cl = [t[1] for t in vlm]
    # Kesit Cd'si Cl'e gore aranir (birlestiricideki `_ara_deger` ile ayni tanim).
    cl_sirali = sorted(zip(cl_ler, cd_ler), key=lambda t: t[0])
    kesit_cl = [t[0] for t in cl_sirali]
    kesit_cd = [t[1] for t in cl_sirali]

    def cd_toplam(hiz: float, nu: float, alfa: float, kiris: float) -> float | None:
        cl = _ara(alfa, v_a, v_cl)                 # 3B taşıma (VLM)
        if cl is None:
            return None
        cd0 = _ara(cl, kesit_cl, kesit_cd)         # profil sürüklemesi, Cl'de
        if cd0 is None:
            return None
        # REYNOLDS DÜZELTMESİ: kesit verisi tek bir Re'de üretildi. Sürtünme
        # bileşeni Cf ~ Re^-0.2 ile ölçeklenir — bu bir MODEL, ölçüm değil;
        # yayılımda yalnız hız/viskozite/kiriş DUYARLILIĞINI taşımak için var.
        re = hiz * kiris / nu
        olcek = (re_kesit / max(re, 1.0)) ** 0.2
        cdi = cl ** 2 / (math.pi * ar * e)
        return cd0 * olcek + cdi

    return cd_toplam, {"AR": round(ar, 4), "taper": taper,
                       "e_tasiyici_cizgi": round(e, 5), "re_kesit": re_kesit}


def calistir() -> dict:
    model, bilgi = kur_model()
    from aircraft_geometry import AircraftLibrary
    kiris = AircraftLibrary().get_template("mini_hawk")().wing.root_chord()

    girdiler = [
        GirdiBelirsizligi("hiz", 15.0, 0.02, True, VARSAYILAN_KAYNAK["hiz"]),
        GirdiBelirsizligi("nu", 1.5e-5, 0.03, True, VARSAYILAN_KAYNAK["nu"]),
        GirdiBelirsizligi("alfa", ALFA_HEDEF, 0.5, False, VARSAYILAN_KAYNAK["alfa"]),
        GirdiBelirsizligi("kiris", kiris, 0.01, True, VARSAYILAN_KAYNAK["olcek"]),
    ]
    s = yay(model, girdiler)

    # DİĞER BİLEŞENLER kanıt dosyalarından; ölçülmeyen None kalır.
    _pk = KOK / "vlm_iki_yonlu_yakinsama.json"
    u_ayriklastirma = (json.loads(_pk.read_text(encoding="utf-8")).get("vlm_band_pct")
                       if _pk.exists() else None)
    toplam = birlestir({
        "girdi": s.u_pct,
        "ayriklastirma_panel": u_ayriklastirma,
        "model_form": None,          # hat-özgü validasyon YOK (literatür-öncül sayılmaz)
    })

    rec = {
        "vaka": (f"Girdi belirsizliği yayılımı — MiniHawk kanat Cd, "
                 f"alpha={ALFA_HEDEF:g}°, V=15 m/s"),
        "_neden": ("ASME V&V 20'nin sekiz adimindan biri EKSIKTI. Bu yol ucuz ve "
                   "turevlenebilir oldugu icin duyarliliklar MERKEZI SONLU FARKLA "
                   "olculebiliyor."),
        "model": bilgi,
        "girdiler": [{"ad": g.ad, "nominal": g.nominal,
                      "u": g.u, "bagil": g.bagil,
                      "u_mutlak": round(g.u_mutlak, 8), "kaynak": g.kaynak}
                     for g in girdiler],
        "Cd_nominal": round(s.deger, 6),
        "u_girdi_mutlak": round(s.u_toplam, 6),
        "u_girdi_pct": round(s.u_pct, 3) if s.u_pct else None,
        "paylar": {k: (round(v, 8) if isinstance(v, float) else v)
                   for k, v in s.paylar.items()},
        "baskin_girdi": s.baskin,
        "toplam_belirsizlik": toplam,
        "_kisit": (s._kisit + " RANS YOLUNDA YAYILMADI: girdi basina iki kosu "
                   "gerekir ve her kosu saatler surer; bu donanimda tractable "
                   "degil. Model-form bileseni de OLCULMEDI (hat-ozgu validasyon "
                   "yok) — toplam bu yuzden ALT SINIRDIR."),
        "_uretim": "Üretim: python experiments/girdi_uq_kanat.py",
    }
    rec["verdikt"] = (
        f"Cd = {rec['Cd_nominal']:.5f} ± {rec['u_girdi_mutlak']:.5f} "
        f"(girdi kaynakli %{rec['u_girdi_pct']:.2f}); baskin girdi: "
        f"{s.baskin}. Ayriklastirma ile birlesince "
        f"%{toplam['u_toplam_pct']} — ve bu bir ALT SINIRDIR "
        f"(olculmeyen: {', '.join(toplam['olculmeyen_bilesenler']) or 'yok'}).")
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    (KOK / "girdi_uq_kanat.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    print(f"{'girdi':>8} {'nominal':>12} {'u':>10} {'Cd katkisi':>13}")
    for g in rec["girdiler"]:
        pay = rec["paylar"].get(g["ad"])
        pay_s = f"{pay:.3e}" if isinstance(pay, float) else str(pay)
        print(f"{g['ad']:>8} {g['nominal']:>12.6g} {g['u_mutlak']:>10.4g} {pay_s:>13}")
    print("\n" + rec["verdikt"])
    print("-> girdi_uq_kanat.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
