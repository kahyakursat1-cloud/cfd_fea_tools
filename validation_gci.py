"""
Mesh Independence (GCI) Study — NACA0012 @ alpha=4, Re=3e6
=========================================================
ASME V&V 20 / Roache Grid Convergence Index.
3 sistematik olarak inceltilmis O-grid mesh; Cd uzerinde Richardson
ekstrapolasyon + GCI (sayisal belirsizlik bandi).

Kullanim: python validation_gci.py
"""
import json
import math
import sys
from pathlib import Path

from validation_suite import NACA0012Validation


class NACA0012GCI(NACA0012Validation):
    """Cozunurlugu parametrik NACA0012 O-grid (validation_suite mesh'ini miras alir)."""
    def __init__(self, base_path, n_prof, n_norm, grading):
        super().__init__(base_path)
        self.n_prof  = n_prof    # _write_ogrid bu attribute'lari getattr ile okur
        self.n_norm  = n_norm
        self.grading = grading


def gci_richardson(f1, f2, f3, r):
    """ASME V&V 20 GCI — f1=ince, f2=orta, f3=kaba; r=sabit inceltme orani.
    Donduru: p (gozlemlenen mertebe), f_ext (Richardson), gci_fine_pct, gci_med_pct, monotonik?
    """
    e32 = f3 - f2
    e21 = f2 - f1
    ratio = e32 / e21 if e21 != 0 else float("inf")
    monotonic = ratio > 0
    # Sabit r icin q(p)=0 -> p = ln|e32/e21| / ln(r)
    p = math.log(abs(ratio)) / math.log(r) if (monotonic and abs(ratio) > 0) else float("nan")
    f_ext = (r**p * f1 - f2) / (r**p - 1) if p == p else float("nan")  # NaN guard
    Fs = 1.25
    ea21 = abs((f1 - f2) / f1)
    ea32 = abs((f2 - f3) / f2)
    gci_fine = Fs * ea21 / (r**p - 1) if p == p else float("nan")
    gci_med  = Fs * ea32 / (r**p - 1) if p == p else float("nan")
    return {
        "p_order": round(p, 3) if p == p else None,
        "f_extrapolated": round(f_ext, 6) if f_ext == f_ext else None,
        "gci_fine_pct": round(gci_fine * 100, 3) if gci_fine == gci_fine else None,
        "gci_med_pct":  round(gci_med * 100, 3) if gci_med == gci_med else None,
        "monotonic": monotonic,
        "refinement_ratio": r,
    }


# 3 mesh — sabit inceltme orani r ~ 1.30 (toplam hucre = n_prof*n_norm, h ~ 1/sqrt(N))
MESHES = {
    "coarse": {"n_prof": 150, "n_norm": 60,  "grading": 500},
    "medium": {"n_prof": 195, "n_norm": 78,  "grading": 500},
    "fine":   {"n_prof": 254, "n_norm": 101, "grading": 500},
}
ALPHA = 4   # tasarim noktasi (iyi yakinsayan, Ladson ref mevcut)


def main():
    base = Path("./validation/gci")
    base.mkdir(parents=True, exist_ok=True)
    cd = {}
    raw = {}
    for level, m in MESHES.items():
        ncells = m["n_prof"] * m["n_norm"]
        print(f"\n=== {level.upper()}  cells={ncells}  (n_prof={m['n_prof']}, n_norm={m['n_norm']}) ===")
        v = NACA0012GCI(str(base / level), **m)
        r = v.run(alpha_deg=ALPHA)
        raw[level] = {**m, "ncells": ncells, **r}
        if r.get("status") in ("PASS", "FAIL", "NO_REF") and "Cd_sim" in r:
            cd[level] = r["Cd_sim"]
            print(f"  Cd={r['Cd_sim']}  Cl={r.get('Cl_sim')}  (vs Ladson Cd_err={r.get('Cd_err_pct')}%)")
        else:
            print(f"  KOSU BASARISIZ: {r}")

    out = {"alpha": ALPHA, "meshes": raw}
    if len(cd) == 3:
        # h ~ 1/sqrt(ncells); sabit r = sqrt(N_fine/N_med)
        Nf = MESHES["fine"]["n_prof"] * MESHES["fine"]["n_norm"]
        Nm = MESHES["medium"]["n_prof"] * MESHES["medium"]["n_norm"]
        Nc = MESHES["coarse"]["n_prof"] * MESHES["coarse"]["n_norm"]
        r21 = math.sqrt(Nf / Nm)
        r32 = math.sqrt(Nm / Nc)
        r = (r21 + r32) / 2
        g = gci_richardson(cd["fine"], cd["medium"], cd["coarse"], r)
        out["gci"] = g
        print("\n" + "=" * 56)
        print("  MESH-BAGIMSIZLIK (GCI) — Cd @ alpha=4")
        print("=" * 56)
        print(f"  Cd  kaba={cd['coarse']}  orta={cd['medium']}  ince={cd['fine']}")
        print(f"  Inceltme orani r        : {r:.3f}")
        print(f"  Gozlemlenen mertebe p   : {g['p_order']}")
        print(f"  Richardson Cd (h->0)    : {g['f_extrapolated']}")
        print(f"  GCI (ince mesh)         : {g['gci_fine_pct']}%")
        print(f"  Monotonik yakinsama     : {g['monotonic']}")

    (base / "gci_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nKaydedildi: {base / 'gci_results.json'}")


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    main()
