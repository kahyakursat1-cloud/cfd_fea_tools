"""FEA doğrulama #6 — eksenel-basınçlı kolon BURKULMASI, Euler kapalı-formuna karşı.
Havacılık-kanonik STABİLİTE modu: ince-cidar panel/spar-başlığı/lüle gövdesi göçmesi
deri burkulmasıyla yönetilir; statik dörtlü (kuvvet/basınç/gövde/termal) bunu kapsamaz.
ÜRETİMin BUCKLE yolunu doğrular: *BUCKLE adımı + referans *CLOAD → özdeğer λ; kritik
yük = λ·P_ref. Ankastre-serbest kolon (K=2): P_cr = π²EI/(KL)², I = b⁴/12.
Kullanım: python experiments/fea_validation_buckling.py
"""
import re
import sys
from pathlib import Path

import gmsh
import meshio
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from analysis.calculix_writer import (  # noqa: E402
    FEACase,
    FEAMaterial,
    FixedBC,
    ForceLoad,
    write_inp,
)
from analysis.ccx_runner import run_ccx  # noqa: E402
from analysis.tet_mesher import TetMesh  # noqa: E402

L, B = 0.50, 0.020                      # m — kolon boyu, kare kesit kenarı (narinlik 25)
E, NU, RHO = 70e9, 0.33, 2700.0         # alüminyum
P_REF = 1000.0                          # N — eksenel referans basınç yükü
K_EFF = 2.0                             # ankastre-serbest etkin-boy faktörü
I_SEC = B ** 4 / 12.0
P_CR_AN = np.pi ** 2 * E * I_SEC / (K_EFF * L) ** 2     # Euler kritik yük (N)


def build_mesh(work: Path) -> TetMesh:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.addBox(-B / 2, -B / 2, 0, B, B, L)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMin", B / 2.5)
        gmsh.option.setNumber("Mesh.MeshSizeMax", B / 2.0)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.HighOrderOptimize", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        msh = work / "col.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    m = meshio.read(str(msh))
    tet = next(c for c in m.cells if c.type == "tetra10")
    tri = next((c for c in m.cells if c.type == "triangle6"), None)
    tris = tri.data.astype(np.int64) if tri is not None else np.zeros((0, 6), np.int64)
    return TetMesh(points=m.points.astype(np.float64), tets=tet.data.astype(np.int64),
                   surface_tris=tris, msh_path=msh, element_type="C3D10")


def parse_buckling_factors(dat_path: Path) -> list[float]:
    """CalculiX .dat'tan burkulma faktörlerini (özdeğer λ) çıkar."""
    if not Path(dat_path).exists():
        return []
    txt = Path(dat_path).read_text(errors="ignore").splitlines()
    factors: list[float] = []
    in_sec = False
    for ln in txt:
        flat = ln.upper().replace(" ", "")
        if "BUCKLINGFACTOR" in flat:          # bölüm başlığı (harfler aralıklı yazılır)
            in_sec = True
            continue
        if in_sec:
            mt = re.match(r"\s*\d+\s+([-+]?[0-9.]+(?:[eEdD][-+]?[0-9]+)?)\s*$", ln)
            if mt:
                factors.append(float(mt.group(1).replace("D", "E").replace("d", "e")))
            elif factors:                      # sayısal blok bitti
                break
    return factors


def main():
    work = HERE.parent / "_fea_val_buckling"
    work.mkdir(exist_ok=True)
    print(f"Analitik (Euler ankastre-serbest, K={K_EFF}): I={I_SEC:.3e} m⁴, "
          f"P_cr={P_CR_AN:.1f} N", flush=True)
    mesh = build_mesh(work)
    print(f"Mesh: {mesh.num_nodes:,} düğüm, {mesh.num_tets:,} C3D10", flush=True)

    pts = mesh.points
    tol = 1e-7
    base = np.where(np.abs(pts[:, 2] - 0.0) < tol)[0] + 1     # z=0 ankastre
    top = np.where(np.abs(pts[:, 2] - L) < tol)[0] + 1        # z=L eksenel yük
    print(f"Ankastre düğüm: {len(base)}, tepe-yük düğüm: {len(top)}", flush=True)

    mat = FEAMaterial("AL", E, NU, RHO)
    case = FEACase(
        name="col", mesh=mesh, material=mat,
        fixed_bcs=[FixedBC(base, "BASE", 1, 3)],
        force_loads=[ForceLoad(top, (0.0, 0.0, -1.0), P_REF, "AXIAL")],
        analysis_type="BUCKLE", num_modes=4)
    inp = write_inp(case, work)
    ccx = run_ccx(inp, timeout=1800)
    if not ccx.success:
        print("CCX FAILED:", (ccx.stderr or ccx.stdout or "")[-500:])
        return 1

    factors = parse_buckling_factors(ccx.dat_path)
    if not factors:
        print("Burkulma faktörü okunamadı:", ccx.dat_path)
        return 1
    lam = abs(factors[0])
    p_cr_fem = lam * P_REF
    err = abs(p_cr_fem - P_CR_AN) / P_CR_AN * 100
    print(f"FEM: λ₁={lam:.4f} → P_cr={p_cr_fem:.1f} N (hata %{err:.1f}); "
          f"ilk-4 λ={[round(f, 3) for f in factors[:4]]}", flush=True)
    ok = err < 8
    print("SONUC:", "✅ GECTI (Euler ile uyumlu)" if ok else "⚠ tolerans disi", flush=True)

    import json
    (HERE.parent / "fea_validation_buckling.json").write_text(json.dumps({
        "vaka": "Eksenel kolon burkulması — Euler kapalı-form (ankastre-serbest, K=2)",
        "yontem": "ÜRETİM BUCKLE yolu: *BUCKLE + referans *CLOAD → özdeğer λ; P_cr=λ·P_ref. "
                  "Lineer-elastik stabilite (geometrik-rijitlik özdeğer problemi).",
        "geometri": {"L_m": L, "kesit_m": B, "narinlik_L_b": L / B,
                     "E_Pa": E, "I_m4": I_SEC, "K_eff": K_EFF, "P_ref_N": P_REF},
        "analitik": {"P_cr_N": round(P_CR_AN, 1), "formul": "P_cr=π²EI/(KL)²"},
        "fem": {"lambda_1": round(lam, 4), "P_cr_N": round(p_cr_fem, 1),
                "hata_pct": round(err, 1), "ilk4_lambda": [round(f, 4) for f in factors[:4]]},
        "sonuc": f"{'GECTI' if ok else 'TOLERANS-DISI'} — %{err:.1f}. Doğrular: ÜRETİMin "
                 "STABİLİTE (burkulma) yolu — statik dörtlüye ek 5. mekanizma. Havacılık "
                 "karşılığı: deri-paneli/spar-başlığı/lüle-gövdesi göçmesi.",
        "_not": "Üretim: python experiments/fea_validation_buckling.py. "
                "Suite: fea_validation*.json (artık 6 kanonik V&V).",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
