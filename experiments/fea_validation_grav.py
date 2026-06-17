"""FEA doğrulama #4 — öz-ağırlık (gravity body-force), kapalı-forma karşı.
Üstten ankastre prizmatik çubuk, kendi ağırlığı altında: tepe (kök) ekseni gerilmesi
sigma_max = rho*g*L, uzama delta = rho*g*L^2/(2E). ÜRETİMin GÖVDE-KUVVETİ yolunu doğrular:
GravityLoad → *DLOAD GRAV (calculix_writer). Kuvvet (CLOAD) ve basınç (DLOAD P) yollarından
sonra ÜÇÜNCÜ yük-tipi → yük-uygulama üçlüsü (kuvvet/basınç/gövde) tamamlanır.
Kullanım: python experiments/fea_validation_grav.py
"""
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
    GravityLoad,
    write_inp,
)
from analysis.ccx_runner import run_ccx  # noqa: E402
from analysis.frd_parser import parse_frd  # noqa: E402
from analysis.tet_mesher import TetMesh  # noqa: E402

AX, LZ = 0.02, 1.0                              # kesit kenarı, boy (m)
E, NU, RHO, G = 210e9, 0.30, 7850.0, 9.81       # çelik
SIG_MAX_AN = RHO * G * LZ                        # Pa — kök ekseni gerilmesi
DELTA_AN = RHO * G * LZ ** 2 / (2 * E)           # m — toplam uzama


def build_mesh(work: Path) -> TetMesh:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.addBox(0, 0, 0, AX, AX, LZ)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMin", AX / 2)
        gmsh.option.setNumber("Mesh.MeshSizeMax", AX)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        msh = work / "bar.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    m = meshio.read(str(msh))
    tet = next(c for c in m.cells if c.type == "tetra10")
    return TetMesh(points=m.points.astype(np.float64), tets=tet.data.astype(np.int64),
                   surface_tris=np.zeros((0, 6), np.int64), msh_path=msh,
                   element_type="C3D10")


def main():
    work = HERE.parent / "_fea_val_grav"
    work.mkdir(exist_ok=True)
    print(f"Analitik: sigma_max=rho*g*L={SIG_MAX_AN / 1e6:.4f} MPa, "
          f"delta=rho*g*L^2/2E={DELTA_AN * 1e6:.4f} um", flush=True)
    mesh = build_mesh(work)
    print(f"Mesh: {mesh.num_nodes:,} dugum, {mesh.num_tets:,} C3D10", flush=True)

    pts = mesh.points
    top = np.where(np.abs(pts[:, 2] - LZ) < 1e-7)[0] + 1     # ust yuzey ankastre
    mat = FEAMaterial("CELIK", E, NU, RHO)
    case = FEACase(name="bar", mesh=mesh, material=mat,
                   fixed_bcs=[FixedBC(top, "FIX", 1, 3)],
                   gravity_loads=[GravityLoad(G, (0, 0, -1.0))],
                   analysis_type="STATIC")
    inp = write_inp(case, work)
    ccx = run_ccx(inp, timeout=600)
    if not ccx.success:
        print("CCX FAILED:", (ccx.stderr or ccx.stdout or "")[-400:]); return 1

    frd = parse_frd(ccx.frd_path)
    vm, disp = frd.von_mises(), frd.displacement_magnitude()
    s_peak = float(vm.max()) / 1e6 if vm is not None else None
    d_fem = float(disp.max()) if disp is not None else None
    es = abs(s_peak - SIG_MAX_AN / 1e6) / (SIG_MAX_AN / 1e6) * 100
    ed = abs(d_fem - DELTA_AN) / DELTA_AN * 100
    print(f"FEM: sigma_tepe={s_peak:.4f} MPa (hata %{es:.1f}); "
          f"delta={d_fem * 1e6:.4f} um (hata %{ed:.1f})", flush=True)
    ok = es < 15 and ed < 15
    print("SONUC:", "GECTI (oz-agirlik analitik ile uyumlu)" if ok else "tolerans disi",
          flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
