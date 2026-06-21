"""TMR GCI kampanyası — 449/897/1793, verilen α'da Cl & Cd GCI + TMR-referans kıyas.
α=0 drag-doğrulama (Cd), α=10 lift-doğrulama (Cl, asıl aero niceliği). α≠0'da case
dizinleri α-eki alır (α=0 sonuçları korunur); çıktı tmr_gci_verdict[_aNN].json.
Kullanım (arka plan): python tmr_cfd/run_gci_campaign.py [alpha]
"""
import json
import math
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from report_generator import compute_gci, gci_verdict  # noqa: E402

ALPHA = sys.argv[1] if len(sys.argv) > 1 else "0"
SUF = "" if ALPHA in ("0", "0.0") else f"_a{ALPHA}"
GRIDS = ROOT / "tmr_grids"
# TMR/CFL3D referans (SST, M=0.15, Re=6e6): α → (Cl_ref, Cd_ref)
TMR_REF = {"0": (0.0, 0.00809), "10": (1.0778, 0.01236)}
# (etiket, grid, case, hücre, endTime)
LEVELS = [
    ("449", GRIDS / "n0012_449-129.p3dfmt", HERE / f"n0012_449{SUF}", 57344, "6000"),
    ("897", GRIDS / "n0012_897-257.p3dfmt", HERE / f"n0012_897{SUF}", 229376, "7000"),
    ("1793", GRIDS / "n0012_1793-513.p3dfmt", HERE / f"n0012_1793{SUF}", 917504, "9000"),
]


def _force(case: Path, col: int):
    f = case / "postProcessing" / "forceCoeffs" / "0" / "forceCoeffs.dat"
    if not f.exists():
        return None
    rows = [ln for ln in f.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    return float(rows[-1].split()[col]) if rows else None


def cd_of(case):
    return _force(case, 2)


def cl_of(case):
    return _force(case, 3)


def main():
    for lbl, grid, case, _, end in LEVELS:
        if cd_of(case) is not None:                 # zaten çözülmüş seviyeyi atla
            print(f"[{lbl}] mevcut, atlanıyor (Cd={cd_of(case):.5f})", flush=True)
            continue
        print(f"=== {lbl} (α={ALPHA}) koşuluyor ===", flush=True)
        subprocess.run([sys.executable, str(HERE / "build_and_run.py"),
                        str(grid), str(case), ALPHA, end, "8"], check=False)

    res = [(lbl, cells, cd_of(case), cl_of(case)) for lbl, _, case, cells, _ in LEVELS]
    print("Sonuçlar (Cd,Cl):", [(l, cd, cl) for l, _, cd, cl in res], flush=True)
    cl_ref, cd_ref = TMR_REF.get(ALPHA, (None, None))
    # α=0 birincil nicelik Cd (Cl≈0); α≠0 birincil Cl
    primary = "Cl" if ALPHA not in ("0", "0.0") else "Cd"
    getp = (lambda r: r[3]) if primary == "Cl" else (lambda r: r[2])
    ref = cl_ref if primary == "Cl" else cd_ref
    rec = {"vaka": f"TMR NACA0012 {primary} GCI (α={ALPHA}°, tam-türbülans SST)",
           "kaynak": "NASA TMR PLOT3D C-grid + plot3dToFoam + SST, Re=6e6",
           "birincil_nicelik": primary, "TMR_referans": {"Cl": cl_ref, "Cd": cd_ref},
           "seviyeler": [{"grid": l, "cells": c, "Cd": cd, "Cl": cl} for l, c, cd, cl in res]}
    ok = [r for r in res if getp(r) is not None]
    if len(ok) == 3:
        h = [1.0 / math.sqrt(r[1]) for r in ok]
        fq = [getp(r) for r in ok]
        gci = compute_gci(h[0], h[1], h[2], fq[0], fq[1], fq[2])
        rec["gci"] = gci
        rec["strict_gci_verdict"] = gci_verdict(gci) if gci else "hesaplanamadı"
        if gci and ref:
            err = abs(gci["f_exact"] - ref) / abs(ref) * 100 if ref else None
            rec[f"{primary}_richardson"] = gci["f_exact"]
            rec["sonuc"] = (f"{primary}_richardson={gci['f_exact']:.5f} vs TMR {ref} "
                            f"(%{err:.1f}). p={gci['p']}, GCI_ince={gci['gci_fine_pct']}%, "
                            f"asimptotik={gci.get('asymptotic')}. "
                            "Asimptotik+TMR-uyumu varsa TASARIM-GRADE.")
    else:
        rec["sonuc"] = "3 seviye tamamlanamadı — kısmi sonuç."
    out = ROOT / f"tmr_gci_verdict{SUF}.json"
    out.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"YAZILDI {out.name}", flush=True)
    if rec.get("gci"):
        print(f"GCI ({primary}): p={rec['gci']['p']} f*={rec['gci']['f_exact']:.5f} "
              f"GCI_ince={rec['gci']['gci_fine_pct']}% asimptotik={rec['gci'].get('asymptotic')}",
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
