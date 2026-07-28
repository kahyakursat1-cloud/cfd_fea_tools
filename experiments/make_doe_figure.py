"""DOE sonucundan (design_explore_cfd.json) 'güven-nicelenmiş tasarım keşfi' figürü:
parametre vs Cd, her nokta V&V/UQ bandı (hata-çubuğu), en-iyi vurgulu. Grant/paper için.
Kullanım: python experiments/make_doe_figure.py [json] [çıktı.png]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "design_explore_cfd.json"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "figures" / "doe_design_exploration.png"
    d = json.loads(src.read_text(encoding="utf-8"))
    pts = [p for p in d["tum_noktalar"] if p["gecerli"] and "cd" in p["objectives"]]
    if not pts:
        print("geçerli nokta yok"); return 1
    pkey = next(iter(d["parametre_uzayi"]))           # 1. parametre (x ekseni)
    xs = [p["params"][pkey] for p in pts]
    cds = [p["objectives"]["cd"] for p in pts]
    errs = [p["objectives"]["cd"] * (p["uncertainty"].get("cd_pct") or 0) / 100 for p in pts]

    out.parent.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    ax.errorbar(xs, cds, yerr=errs, fmt="o", color="#1f4e79", mfc="white", ms=7,
                capsize=4, lw=1, ecolor="#c00000", label="tasarım noktası ± V&V bandı")
    best = d.get("en_iyi")
    if best and "cd" in best["objectives"]:
        ax.plot(best["params"][pkey], best["objectives"]["cd"], "*", color="#2e7d32",
                ms=18, label=f"en iyi ({pkey}={best['params'][pkey]:.2f})")
    ax.set_xlabel(pkey); ax.set_ylabel("$C_D$ (Richardson/en-ince)")
    ax.set_title("Güven-nicelenmiş tasarım keşfi (DOE + 3-mesh GCI)", fontsize=10)
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out, dpi=150); plt.close(fig)
    print(f"YAZILDI {out}  ({len(pts)} geçerli nokta)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
