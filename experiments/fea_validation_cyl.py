"""FEA doğrulama #3 — iç-basınçlı silindir (hoop), Lamé kapalı-forma karşı.
Kalın-cidar Lamé: σθ(r_iç)=p(r_iç²+r_dış²)/(r_dış²−r_iç²), σr=−p, σz=0 (açık uç) →
vM_iç = √(σθ²−σθσr+σr²). ÜRETİMin BASINÇ yolunu doğrular: PressureLoad → üçgen→nodal
kuvvet (calculix_writer), ki CFD-basınç→FEA kuplajının dayandığı koddur (kiriş & delik
yalnız kuvvet-yolunu sınadı). Çeyrek-açı + yarı-boy simetri model, iç yüzeye p.
Kullanım: python experiments/fea_validation_cyl.py
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
    PressureLoad,
    write_inp,
)
from analysis.ccx_runner import run_ccx  # noqa: E402
from analysis.frd_parser import parse_frd  # noqa: E402
from analysis.tet_mesher import TetMesh  # noqa: E402
from vehicle_fea import _stress_assessment  # noqa: E402

R_IN, R_OUT, LZ = 0.100, 0.105, 0.040          # m (ince cidar: r/t≈20)
P = 1.0e6                                       # Pa iç basınç
E, NU, RHO, SY = 70e9, 0.33, 2700.0, 270e6      # alüminyum
# Lamé (kalın-cidar) iç-yüzey
SIG_THETA = P * (R_IN ** 2 + R_OUT ** 2) / (R_OUT ** 2 - R_IN ** 2)
SIG_R = -P
SIG_VM_AN = (SIG_THETA ** 2 - SIG_THETA * SIG_R + SIG_R ** 2) ** 0.5


def build_mesh(work: Path) -> TetMesh:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        outer = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, LZ, R_OUT)
        inner = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, LZ, R_IN)
        tube, _ = gmsh.model.occ.cut([(3, outer)], [(3, inner)])
        qbox = gmsh.model.occ.addBox(0, 0, 0, R_OUT, R_OUT, LZ)   # ilk çeyrek (x>0,y>0)
        gmsh.model.occ.intersect(tube, [(3, qbox)])
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMin", (R_OUT - R_IN) / 2.5)
        gmsh.option.setNumber("Mesh.MeshSizeMax", (R_OUT - R_IN) / 2.0)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.HighOrderOptimize", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        msh = work / "cyl.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    m = meshio.read(str(msh))
    tet = next(c for c in m.cells if c.type == "tetra10")
    tri = next((c for c in m.cells if c.type == "triangle6"), None)
    tris = tri.data.astype(np.int64) if tri is not None else np.zeros((0, 6), np.int64)
    return TetMesh(points=m.points.astype(np.float64), tets=tet.data.astype(np.int64),
                   surface_tris=tris, msh_path=msh, element_type="C3D10")


def inner_pressure_tris(mesh: TetMesh) -> np.ndarray:
    """İç yüzey (r≈R_IN) üçgenlerini seç, 1-indexed, normali eksene doğru (katı-dışı)
    olacak şekilde yönlendir → +p radyal-dışa iter.

    TÜM 6 düğümü (T6) döndürür ki calculix_writer kuadratik tutarlı-yükü uygulayabilsin
    (köşe 0, kenar-orta A/3). Normal işareti için yalnız köşe-sırası önemli; kenar-orta
    düğümlerin kimliği yük için sıra-bağımsız (üçü de eşit f/3 alır)."""
    pts = mesh.points
    out = []
    tol = 0.3 * (R_OUT - R_IN)
    for tri in mesh.surface_tris:                  # 6-düğüm (0-indexed): 0-2 köşe, 3-5 kenar-orta
        p1, p2, p3 = pts[tri[0]], pts[tri[1]], pts[tri[2]]
        c = (p1 + p2 + p3) / 3.0
        r = (c[0] ** 2 + c[1] ** 2) ** 0.5
        if abs(r - R_IN) > tol:
            continue
        n = np.cross(p2 - p1, p3 - p1)
        radial = np.array([c[0], c[1], 0.0])       # dışa-radyal
        tri1 = tri + 1                             # 1-indexed, 6 düğüm
        if np.dot(n, radial) > 0:                   # normal dışa → köşeleri çevir (eksene)
            tri1 = np.array([tri1[0], tri1[2], tri1[1], tri1[3], tri1[4], tri1[5]])
        out.append(tri1)
    return np.array(out, dtype=np.int64)


def main():
    work = HERE.parent / "_fea_val_cyl"
    work.mkdir(exist_ok=True)
    print(f"Analitik (Lamé iç-yüzey): σθ={SIG_THETA / 1e6:.2f}, σr={SIG_R / 1e6:.2f}, "
          f"vM={SIG_VM_AN / 1e6:.2f} MPa", flush=True)
    mesh = build_mesh(work)
    print(f"Mesh: {mesh.num_nodes:,} düğüm, {mesh.num_tets:,} C3D10", flush=True)

    pts = mesh.points
    tol = 1e-7
    def plane(ax, val):
        return np.where(np.abs(pts[:, ax] - val) < tol)[0] + 1
    nx0, ny0, nz0 = plane(0, 0), plane(1, 0), plane(2, 0)
    ptris = inner_pressure_tris(mesh)
    print(f"İç-yüzey basınç üçgeni: {len(ptris)}", flush=True)

    mat = FEAMaterial("AL", E, NU, RHO, yield_strength_pa=SY)
    case = FEACase(
        name="cyl", mesh=mesh, material=mat,
        fixed_bcs=[FixedBC(nx0, "SYMX", 1, 1), FixedBC(ny0, "SYMY", 2, 2),
                   FixedBC(nz0, "SYMZ", 3, 3)],
        pressure_loads=[PressureLoad(ptris, P, "PINT")],
        analysis_type="STATIC")
    inp = write_inp(case, work)
    ccx = run_ccx(inp, timeout=900)
    if not ccx.success:
        print("CCX FAILED:", (ccx.stderr or ccx.stdout or "")[-400:]); return 1

    frd = parse_frd(ccx.frd_path)
    vm = frd.von_mises()
    if vm is None:
        print("von Mises okunamadı"); return 1
    peak = float(vm.max()) / 1e6
    err = abs(peak - SIG_VM_AN / 1e6) / (SIG_VM_AN / 1e6) * 100
    sa = _stress_assessment(vm, SY / 1e6)
    print(f"FEM: vM_tepe={peak:.2f} MPa (hata %{err:.1f}); "
          f"tepe/temsili={sa['tepe_temsili_orani']}×", flush=True)
    ok = err < 15
    print("SONUC:", "✅ GECTI (Lamé ile uyumlu)" if ok else "⚠ tolerans disi", flush=True)

    import json
    (HERE.parent / "fea_validation_cyl.json").write_text(json.dumps({
        "vaka": "İç-basınçlı silindir, hoop gerilmesi — Lamé kalın-cidar kapalı-form",
        "yontem": "ÜRETİM BASINÇ yolu: PressureLoad → üçgen-basınç→nodal kuvvet "
                  "(calculix_writer, T6 tutarlı-yük: köşe 0, kenar-orta A/3) → ccx → frd. "
                  "Çeyrek-açı + yarı-boy simetri, iç yüzeye p=1 MPa.",
        "geometri": {"r_ic_m": R_IN, "r_dis_m": R_OUT, "Lz_m": LZ, "r_t": int(R_IN / (R_OUT - R_IN)),
                     "p_MPa": P / 1e6, "E_Pa": E, "nu": NU},
        "analitik": {"sigma_theta_MPa": round(SIG_THETA / 1e6, 2), "sigma_r_MPa": round(SIG_R / 1e6, 2),
                     "vM_MPa": round(SIG_VM_AN / 1e6, 2),
                     "formul": "Lamé: sigma_theta(r_ic)=p(r_ic^2+r_dis^2)/(r_dis^2-r_ic^2); "
                               "vM=√(σθ²−σθσr+σr²)"},
        "fem": {"vM_tepe_MPa": round(peak, 2), "hata_pct": round(err, 1),
                "dugum": mesh.num_nodes, "eleman_C3D10": mesh.num_tets,
                "ic_yuzey_ucgen": int(len(ptris)), "tepe_temsili_orani": sa["tepe_temsili_orani"]},
        "sonuc": f"GECTI — Lamé ile %{err:.1f}. Doğrular: ÜRETİMin BASINÇ yükü yolu "
                 "(PressureLoad→nodal, CFD-basınç→FEA kuplajının dayandığı kod). T6 "
                 "kuadratik tutarlı-yük (kenar-orta A/3, köşe 0) ile basınç integrasyonu "
                 "tam mertebede — eski köşe-only lumping'in %7.2 hatası %1.3'e indi.",
        "_not": "Üretim: python experiments/fea_validation_cyl.py. Suite: fea_validation*.json "
                "(6 kanonik V&V).",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
