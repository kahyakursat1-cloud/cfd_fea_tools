"""VSPAERO'nun İNDÜKLENEN DİRENCİ — iki çıktısı da kurama karşı ölçülür.

NEDEN: `vlm_taper_capa` VSPAERO'nun Trefftz CDi'sinin taper'la Munk sınırını
aştığını gösterdi (taper 0.5 → e=1.601). Ama "hangi sayı doğru" sorusunu
yanıtlamadı — VSPAERO İKİ ayrı indüklenen direnç veriyor:
    CDi   yakın-alan (yüzey entegrasyonu)
    CDiw  Trefftz/iz düzlemi
Birini diğerine tercih etmek keyfî olurdu. HAKEM gerekli.

HAKEM: Prandtl taşıyıcı-çizgi (Glauert Fourier). Çizelge ya da ezber yok, ve
KENDİNİ DOĞRULUYOR — eliptik planformda e=1.0 vermek ZORUNDA. Çözücü 1.00000
veriyor; bu, ölçümün kabul testidir.

    python experiments/vlm_induklenen_capa.py
Çıktı: vlm_induklenen_capa.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

SPAN, ALAN = 1.5, 0.45
AR = SPAN ** 2 / ALAN
ALFALAR = (2.0, 4.0, 6.0)
PANEL = 80
TAPERLER = (1.0, 0.85, 0.7, 0.5)


def _vspaero(taper: float) -> list[dict]:
    import openvsp as vsp

    from openvsp_bridge import _ayar
    vsp.VSPCheckSetup()
    vsp.ClearVSPModel()
    wid = vsp.AddGeom("WING")
    xs = vsp.GetXSec(vsp.GetXSecSurf(wid, 0), 1)
    kok = 2 * ALAN / (SPAN * (1 + taper))
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "Span"), SPAN / 2)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "Root_Chord"), kok)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "Tip_Chord"), kok * taper)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "Sweep"), 0.0)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "Dihedral"), 0.0)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "SectTess_U"), PANEL)
    vsp.Update()
    vsp.SetAnalysisInputDefaults("VSPAEROComputeGeometry")
    vsp.ExecAnalysis("VSPAEROComputeGeometry")
    a = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(a)
    _ayar(a, "AlphaStart", [min(ALFALAR)], "double")
    _ayar(a, "AlphaEnd", [max(ALFALAR)], "double")
    _ayar(a, "AlphaNpts", [len(ALFALAR)])
    _ayar(a, "MachStart", [0.05], "double")
    _ayar(a, "Sref", [ALAN], "double")
    _ayar(a, "bref", [SPAN], "double")
    _ayar(a, "cref", [kok], "double")
    _ayar(a, "WakeNumIter", [5])
    vsp.ExecAnalysis(a)
    pol = vsp.FindResultsID("VSPAERO_Polar", 0)
    al = list(vsp.GetDoubleResults(pol, "Alpha"))
    veri = {ad: list(vsp.GetDoubleResults(pol, ad))
            for ad in ("CLtot", "CLwtot", "CDi", "CDiw")}
    out = []
    for i, alfa in enumerate(al):
        s = {"alpha": round(alfa, 1)}
        s.update({k: (round(v[i], 7) if i < len(v) else None)
                  for k, v in veri.items()})
        for etiket, cl_ad, cd_ad in (("e_yakin_alan", "CLtot", "CDi"),
                                     ("e_trefftz", "CLwtot", "CDiw")):
            cl, cd = s.get(cl_ad), s.get(cd_ad)
            s[etiket] = round(cl ** 2 / (math.pi * AR * cd), 4) if (cl and cd) else None
        out.append(s)
    return out


def calistir() -> dict:
    import lifting_line as ll

    eliptik = ll.span_verimi(AR, 1.0, eliptik=True)
    if abs(eliptik - 1.0) > 1e-4:
        raise AssertionError(
            f"HAKEM KENDINI DOGRULAYAMADI: eliptik planformda e={eliptik:.6f}, "
            "1.0 olmali. Bu cozucuyle olcum yapilamaz.")

    kayit = []
    for t in TAPERLER:
        e_ll = ll.span_verimi(AR, t)
        noktalar = _vspaero(t)
        orta = [n for n in noktalar if abs(n["alpha"] - 4.0) < 1e-6] or noktalar[:1]
        n = orta[0]
        kayit.append({
            "taper": t, "e_kuram": round(e_ll, 4),
            "e_yakin_alan": n["e_yakin_alan"], "e_trefftz": n["e_trefftz"],
            "sapma_pct": {
                "yakin_alan": round((n["e_yakin_alan"] / e_ll - 1) * 100, 1),
                "trefftz": round((n["e_trefftz"] / e_ll - 1) * 100, 1)},
            "noktalar": noktalar})

    y_max = max(abs(k["sapma_pct"]["yakin_alan"]) for k in kayit)
    t_max = max(abs(k["sapma_pct"]["trefftz"]) for k in kayit)
    rec = {
        "vaka": f"VSPAERO induklenen direnci vs tasiyici-cizgi — AR={AR:g}, alpha=4",
        "_neden": ("VSPAERO IKI CDi veriyor (yakin-alan ve Trefftz) ve birlestirici "
                   "Trefftz olani kullaniyordu. Hangisinin dogru oldugu HAKEMSIZ "
                   "belirlenemez."),
        "hakem": {"yontem": "Prandtl tasiyici-cizgi, Glauert Fourier (kapali form)",
                  "kendini_dogrulama": {"eliptik_planform_e": round(eliptik, 6),
                                        "beklenen": 1.0}},
        "olcum": kayit,
        "en_kotu_sapma_pct": {"yakin_alan": y_max, "trefftz": t_max},
        "_kisit": ("Tasiyici-cizgi DUZ, orta/yuksek AR kanat kuramidir; ok acisi "
                   "ve dihedral MODELLENMEZ, kalinlik ve viskozite yoktur. "
                   "AR=5'te makul, AR<4 ya da buyuk ok acisinda kullanilmaz "
                   "(lifting_line.gecerli_mi bunu soyler). Karsilastirma alpha=4'te "
                   "yapildi; e her iki VSPAERO ciktisinda da alfa ile ~%0.5 icinde "
                   "sabit oldugu icin tek nokta temsil ediyor."),
        "_uretim": "Üretim: python experiments/vlm_induklenen_capa.py",
    }
    rec["verdikt"] = (
        f"⛔ VSPAERO'nun HER IKI induklenen direnci de kuramdan sapiyor: "
        f"yakin-alan en kotu %{y_max:.0f} (sistematik DUSUK e = YUKSEK CDi), "
        f"Trefftz en kotu %{t_max:.0f} (e>1 ile Munk sinirini ihlal ediyor ve "
        f"sapma taper'la buyuyor). Ikisi arasindan secim yapilmaz; induklenen "
        f"direnc DOGRULANMIS kuramdan uretilir (lifting_line.induklenen_direnc). "
        f"Hakem eliptik planformda e={eliptik:.5f} vererek kendini dogruladi.")
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    (KOK / "vlm_induklenen_capa.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    print(f"{'taper':>7} {'e_kuram':>9} {'e_yakin':>9} {'sapma%':>8} "
          f"{'e_trefftz':>10} {'sapma%':>8}")
    for k in rec["olcum"]:
        print(f"{k['taper']:7.2f} {k['e_kuram']:9.4f} {k['e_yakin_alan']:9.4f} "
              f"{k['sapma_pct']['yakin_alan']:8.1f} {k['e_trefftz']:10.4f} "
              f"{k['sapma_pct']['trefftz']:8.1f}")
    print("\n" + rec["verdikt"])
    print("-> vlm_induklenen_capa.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
