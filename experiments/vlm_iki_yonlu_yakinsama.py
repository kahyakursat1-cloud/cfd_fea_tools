"""VLM panel yakınsaması — AÇIKLIK ve KİRİŞ BİRLİKTE inceltilir.

NEDEN AYRI BİR ÖLÇÜM: `vlm_panel_yakinsamasi` yalnız AÇIKLIK yönünü inceltiyor
(20→120) ve kiriş yönü sabit kalıyor. Gövde çapı düzeltildikten sonra o dizi
monotonlaştı ama gözlenen mertebe p<0.5 çıktı ve band %28.32'de kaldı.

NEDENİ ÖLÇÜLDÜ: kiriş yönü tek başına Cl(8)'i %1.9 oynatıyor ve monoton değil
(Tess_W 17/25/33/49 → 0.72920/0.72256/0.73630/0.73711). Açıklık serisinin ince
kademelerindeki adımlar %0.5–1.2, yani SABİT TUTULAN YÖNÜN GÜRÜLTÜSÜNÜN ALTINDA.
Tek yönde inceltmek bu durumda yakınsama gösteremez: band, sabit yönün
belirlediği tabanın altına inmez.

BU AİLEDE her kademede İKİ yön de aynı çarpanla (1.35) inceltilir. Paneller 2B
bir yüzeyi döşediği için temsili boyut h ~ N_toplam^(-1/2); band kanonik
kuraldan `band_from_levels(boyut=2)` ile alınır.

    conda run -n openvsp python experiments/vlm_iki_yonlu_yakinsama.py
Çıktı: vlm_iki_yonlu_yakinsama.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

# (açıklık paneli, kiriş paneli) — her kademe 1.35 kat, yani h 1.35 kat küçülür.
# Celik'in r ≥ 1.3 şartı h ORANINDA sağlanmalı: h ~ (Nsp·Nkr)^(-1/2) olduğundan
# iki yönü de 1.35 ile çarpmak h oranını 1.35 yapar (ölçüldü: 1.351/1.350/1.349).
KADEMELER = ((40, 17), (54, 23), (73, 31), (98, 42))
ALFALAR = (0.0, 4.0, 8.0)
REFERANS_ALFA = 8.0


def _kos(span_panel: int, kiris_panel: int) -> dict:
    import openvsp as vsp

    import openvsp_bridge as ob
    from aircraft_geometry import AircraftLibrary
    from openvsp_bridge import _ayar
    ac = AircraftLibrary().get_template("mini_hawk")()
    ob.aircraft_to_vsp(ac, kambur=ob.VLM_KAMBUR)
    uygulanan = ob._panel_yogunlugu_ata(span_panel)
    kiris_uygulanan = []
    for gid in vsp.FindGeoms():
        if vsp.GetGeomTypeName(gid) != "Wing":
            continue
        pid = vsp.FindParm(gid, "Tess_W", "Shape")
        if pid:
            vsp.SetParmValUpdate(pid, kiris_panel)
            kiris_uygulanan.append(vsp.GetGeomName(gid))
    vsp.Update()
    vsp.SetAnalysisInputDefaults("VSPAEROComputeGeometry")
    vsp.ExecAnalysis("VSPAEROComputeGeometry")
    a = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(a)
    _ayar(a, "AlphaStart", [min(ALFALAR)], "double")
    _ayar(a, "AlphaEnd", [max(ALFALAR)], "double")
    _ayar(a, "AlphaNpts", [len(ALFALAR)])
    _ayar(a, "MachStart", [0.05], "double")
    _ayar(a, "Sref", [ac.wing.area], "double")
    _ayar(a, "bref", [ac.wing.span], "double")
    _ayar(a, "cref", [ac.wing.root_chord()], "double")
    _ayar(a, "WakeNumIter", [5])
    vsp.ExecAnalysis(a)
    pol = vsp.FindResultsID("VSPAERO_Polar", 0)
    al = list(vsp.GetDoubleResults(pol, "Alpha"))
    cl = list(vsp.GetDoubleResults(pol, "CLwtot"))
    kayit = {"span_panel": span_panel, "kiris_panel": kiris_panel,
             "toplam_panel": span_panel * kiris_panel,
             "span_uygulanan": uygulanan, "kiris_uygulanan": kiris_uygulanan}
    for a_, c_ in zip(al, cl):
        kayit[f"Cl_{round(a_):g}"] = round(c_, 5)
    return kayit


def calistir() -> dict:
    from report_generator import band_from_levels
    kayitlar = [_kos(sp, kr) for sp, kr in KADEMELER]
    anahtar = f"Cl_{REFERANS_ALFA:g}"
    seri = [k[anahtar] for k in kayitlar]
    n = [k["toplam_panel"] for k in kayitlar]
    # PANEL 2B AYRIKLASTIRMA: h ~ N^(-1/2). boyut=3 gecmek bandi sisirir ve
    # r>=1.3 sartini YANLIS ihlal ettirir (bkz. TestIkiBoyutluBand).
    band = band_from_levels(n, seri, 1.0, boyut=2)
    h_oran = [(n[i + 1] / n[i]) ** 0.5 for i in range(len(n) - 1)]
    monoton = (all(x <= y for x, y in zip(seri, seri[1:]))
               or all(x >= y for x, y in zip(seri, seri[1:])))
    son_adim = abs(seri[-1] - seri[-2]) / abs(seri[-1]) * 100

    rec = {
        "vaka": "VLM panel yakınsaması — AÇIKLIK + KİRİŞ birlikte, mini_hawk",
        "_neden": ("Tek yonde inceltmek yakinsama gosteremiyordu: kiris yonu tek "
                   "basina Cl(8)'i %1.9 oynatiyor ve aciklik serisinin ince "
                   "adimlari (%0.5-1.2) o gurultunun ALTINDA kaliyordu."),
        "kademeler": [{"span": sp, "kiris": kr, "toplam": sp * kr}
                      for sp, kr in KADEMELER],
        "h_oranlari": [round(x, 3) for x in h_oran],
        "kayitlar": kayitlar,
        "referans": anahtar,
        "seri": seri,
        "monoton": monoton,
        "son_kademe_degisimi_pct": round(son_adim, 2),
        "kanonik_band": band,
        "tek_yonlu_band_pct": 28.32,
        "_kisit": ("Band panel AYRIKLASTIRMA bandidir, DOGRULAMA bandi DEGIL. "
                   "VLM'in kendi model-form payi ayri olculdu (ciplak kanatta "
                   "tasima egimi kurama gore -%10). Ayrica bu aile TAM ARAC "
                   "icindir; temiz kanat capasinin bandi buraya tasinmaz."),
        "_uretim": ("Üretim: conda run -n openvsp python "
                    "experiments/vlm_iki_yonlu_yakinsama.py"),
    }
    rec["vlm_band_pct"] = band["u_pct"]
    kazanc = rec["tek_yonlu_band_pct"] / band["u_pct"] if band["u_pct"] else None
    rec["verdikt"] = (
        f"{'✅' if monoton and band['u_pct'] < 10 else '⚠️'} İki yönlü aile: "
        f"{anahtar} = {' / '.join(f'{x:.5f}' for x in seri)}, "
        f"dizi {'monoton' if monoton else 'MONOTON DEGIL'}, son kademe "
        f"%{son_adim:.2f}. Kanonik band %{band['u_pct']} ({band['yontem']}). "
        f"Tek yonlu aile %{rec['tek_yonlu_band_pct']} vermisti"
        + (f" — band {kazanc:.1f} KAT daraldi." if kazanc and kazanc > 1
           else " — daralma YOK; sabit tutulan yon hipotezi bu veriyle "
                "DESTEKLENMIYOR."))
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    (KOK / "vlm_iki_yonlu_yakinsama.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    print(f"{'span':>6} {'kiris':>6} {'toplam':>8} {rec['referans']:>10}")
    for k in rec["kayitlar"]:
        print(f"{k['span_panel']:6d} {k['kiris_panel']:6d} "
              f"{k['toplam_panel']:8d} {k[rec['referans']]:10.5f}")
    print(f"\nh oranlari: {rec['h_oranlari']}")
    print("\n" + rec["verdikt"])
    print("-> vlm_iki_yonlu_yakinsama.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
