"""VLM İNDÜKLENEN DİRENCİ — taper ile Munk sınırını ihlal ediyor.

NEDEN: `vlm_capa.py` VLM'i SADE DİKDÖRTGEN kanatta doğruladı (taşıma eğimi
lifting-line ile R²=0.99983). Birleştirici ise taşımanın yanında CDi'yi de
VLM'den alıyor — ve gerçek araçların kanadı sivriltilmiş. Dikdörtgen çapası
CDi hakkında hiçbir şey söylemiyordu.

ÖLÇÜM: alan, açıklık ve AR SABİT (inşa edilen geometriden doğrulanır); yalnız
taper değişir. Span verimi e = Cl²/(π·AR·CDi) düzlemsel kanatta e ≤ 1'dir
(Munk). Teorik beklenti: taper 1.0 → 0.5 arasında CDi ~%1-2 DÜŞER.

ELENEN ADAYLAR (hepsi ayrı ayrı ölçüldü, hiçbiri açıklamıyor):
  kamburluk    açık/kapalı — ihlal İKİSİNDE de var
  gövde+kuyruk çıkarıldı   — izole kanatta da var
  uç kümelemesi 1.00/0.25  — dikdörtgende fark %0.04
  iz gevşetmesi WakeNumIter 1..10 — e 1.0323 → 1.0289, etkisiz
  panel sayısı 28→80       — e 1.100 → 1.032, azalıyor ama sıfırlanmıyor
  ince/kalın yüzey         — ThinGeomSet ayarı BİREBİR AYNI sonucu verdi

Geriye taper kalıyor ve etki tek başına ihlalin tamamını taşıyor.

    python experiments/vlm_taper_capa.py
Çıktı: vlm_taper_capa.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

SPAN, ALAN = 1.5, 0.45          # MiniHawk kanadı — taper hariç sabit tutulur
AR = SPAN ** 2 / ALAN
ALFA = 4.0
MACH = 0.05
PANEL = 80
TAPERLER = (1.0, 0.85, 0.7, 0.5)


def _kos(taper: float) -> dict:
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
    # ALAN/ACIKLIK GERCEKTEN SABIT MI: normalizasyon kaymasi ihlali TAKLIT
    # edebilirdi, o yuzden dataclass'a degil INSA EDILEN geometriye bakilir.
    insa = {p: vsp.GetParmVal(vsp.FindParm(wid, p, "WingGeom"))
            for p in ("TotalSpan", "TotalArea", "TotalAR")}
    vsp.SetAnalysisInputDefaults("VSPAEROComputeGeometry")
    vsp.ExecAnalysis("VSPAEROComputeGeometry")
    a = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(a)
    _ayar(a, "AlphaStart", [ALFA], "double")
    _ayar(a, "AlphaEnd", [ALFA], "double")
    _ayar(a, "AlphaNpts", [1])
    _ayar(a, "MachStart", [MACH], "double")
    _ayar(a, "Sref", [ALAN], "double")
    _ayar(a, "bref", [SPAN], "double")
    _ayar(a, "cref", [kok], "double")
    _ayar(a, "WakeNumIter", [5])
    vsp.ExecAnalysis(a)
    pol = vsp.FindResultsID("VSPAERO_Polar", 0)
    cl = vsp.GetDoubleResults(pol, "CLwtot")[0]
    cdi = vsp.GetDoubleResults(pol, "CDiw")[0]
    return {"taper": taper, "Cl": round(cl, 6), "CDi": round(cdi, 7),
            "span_verimi_e": round(cl ** 2 / (math.pi * AR * cdi), 4),
            "insa_edilen": {k: round(v, 5) for k, v in insa.items()}}


def calistir() -> dict:
    from polar_birlestirme import E_ENGEL_ESIGI, E_UST_SINIR
    kayit = [_kos(t) for t in TAPERLER]
    e_ler = {k["taper"]: k["span_verimi_e"] for k in kayit}
    e_max = max(e_ler.values())
    sapan = [f"taper={t}: e={e}" for t, e in e_ler.items() if e > E_ENGEL_ESIGI]
    rec = {
        "vaka": (f"VLM induklenen direnci — taper suurmesi, AR={AR:g}, "
                 f"alpha={ALFA:g}, panel={PANEL}"),
        "_neden": ("vlm_capa dikdortgen kanatta TASIMA egimini dogruladi; CDi'yi "
                   "DOGRULAMADI. Birlestirici CDi'yi de VLM'den aliyor ve gercek "
                   "kanatlar sivriltilmis."),
        "olcum": kayit,
        "span_verimi": e_ler,
        "e_max": e_max,
        "sinir": {"munk_duzlemsel": E_UST_SINIR, "engel_esigi": E_ENGEL_ESIGI},
        "elenen_adaylar": ["kamburluk", "govde+kuyruk", "uc kumelemesi",
                           "iz gevsetmesi (WakeNumIter 1..10)",
                           "ince/kalin yuzey (ThinGeomSet etkisiz)"],
        "_kisit": ("KOK NEDEN BULUNMADI — bulunan sey ETKININ TAPER'A BAGLI "
                   "oldugudur. Panel inceltmesi ihlali azaltiyor (28 panelde "
                   "e=1.100, 80 panelde 1.032 dikdortgende) ama sifirlamiyor; "
                   "taper etkisi ayri bir mertebede ve inceltmeyle kapanmiyor. "
                   "Bu olcum alpha=4'te tek noktadir; alpha bagimligi olculmedi."),
        "_uretim": "Üretim: python experiments/vlm_taper_capa.py",
    }
    rec["verdikt"] = (
        f"{'⛔' if sapan else '✅'} span verimi e: "
        + ", ".join(f"taper {t}→{e}" for t, e in e_ler.items())
        + f". Duzlemsel kanatta e≤{E_UST_SINIR} MATEMATIKSEL SINIRDIR (Munk). "
        + (f"IHLAL: {'; '.join(sapan)} — bu kurulumda VLM'in CDi'si sivriltilmis "
           f"kanatta MUTLAK SURUKLEMEYE KATILAMAZ."
           if sapan else "Sinir icinde."))
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    (KOK / "vlm_taper_capa.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    print(f"{'taper':>7} {'Cl':>10} {'CDi':>11} {'e':>8}")
    for k in rec["olcum"]:
        print(f"{k['taper']:7.2f} {k['Cl']:10.6f} {k['CDi']:11.7f} "
              f"{k['span_verimi_e']:8.4f}")
    print("\n" + rec["verdikt"])
    print("-> vlm_taper_capa.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
