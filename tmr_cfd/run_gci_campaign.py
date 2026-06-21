"""TMR drag GCI kampanyası — 897 + 1793 koş, 449 ile birleştirip GCI hesapla.
449 önceden koşuldu (tmr_cfd/n0012_449). Bu sürücü 897 ve 1793'ü build_and_run ile
koşar, üç Cd'den Richardson GCI'ı çıkarır, tmr_gci_verdict.json'a yazar.
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
GRIDS = ROOT / "tmr_grids"
# (etiket, grid dosyası, case, hücre, endTime)
LEVELS = [
    ("449", GRIDS / "n0012_449-129.p3dfmt", HERE / "n0012_449", 57344, "6000"),
    ("897", GRIDS / "n0012_897-257.p3dfmt", HERE / "n0012_897", 229376, "7000"),
    ("1793", GRIDS / "n0012_1793-513.p3dfmt", HERE / "n0012_1793", 917504, "9000"),
]


def cd_of(case: Path):
    f = case / "postProcessing" / "forceCoeffs" / "0" / "forceCoeffs.dat"
    if not f.exists():
        return None
    rows = [ln for ln in f.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    return float(rows[-1].split()[2]) if rows else None


def main():
    # 897 ve 1793'ü koş (449 zaten var). 449 yoksa onu da koş.
    for lbl, grid, case, _, end in LEVELS:
        if lbl == "449" and cd_of(case) is not None:
            print(f"[{lbl}] mevcut, atlanıyor (Cd={cd_of(case):.5f})", flush=True)
            continue
        print(f"=== {lbl} koşuluyor ===", flush=True)
        subprocess.run([sys.executable, str(HERE / "build_and_run.py"),
                        str(grid), str(case), ALPHA, end, "8"], check=False)

    res = [(lbl, cells, cd_of(case)) for lbl, _, case, cells, _ in LEVELS]
    print("Sonuçlar:", res, flush=True)
    ok = [(lbl, c, cd) for lbl, c, cd in res if cd is not None]
    rec = {"vaka": f"TMR NACA0012 drag GCI (α={ALPHA}°, tam-türbülans SST)",
           "kaynak": "NASA TMR PLOT3D C-grid + plot3dToFoam + SST, Re=6e6",
           "seviyeler": [{"grid": lbl, "cells": c, "Cd": cd} for lbl, c, cd in res]}
    if len(ok) == 3:
        h = [1.0 / math.sqrt(c) for _, c, _ in ok]      # 449,897,1793 → h küçülür
        cd = [x[2] for x in ok]
        gci = compute_gci(h[0], h[1], h[2], cd[0], cd[1], cd[2])
        rec["gci"] = gci
        rec["strict_gci_verdict"] = gci_verdict(gci) if gci else "hesaplanamadı"
        if gci:
            rec["Cd_richardson"] = gci["f_exact"]
            rec["TMR_referans_SST_alpha0"] = 0.00809
            rec["sonuc"] = (f"Cd_richardson={gci['f_exact']:.5f} vs TMR≈0.00809. "
                            f"p={gci['p']}, GCI_ince={gci['gci_fine_pct']}%. "
                            "Asimptotik+TMR-uyum varsa mutlak Cd TASARIM-GRADE.")
    else:
        rec["sonuc"] = "3 seviye tamamlanamadı — kısmi sonuç."
    (ROOT / "tmr_gci_verdict.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    print("YAZILDI tmr_gci_verdict.json", flush=True)
    if rec.get("gci"):
        print(f"GCI: p={rec['gci']['p']} Cd*={rec['gci']['f_exact']:.5f} "
              f"GCI_ince={rec['gci']['gci_fine_pct']}%", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
