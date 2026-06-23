"""FEA knob-taraması — silent-failure assay'in FEA tarafı (Path A, tam matris).
İç-basınçlı silindir (Lamé truth) üzerinde naive-kullanıcı knob'larını tara:
  element-order {C3D4 lineer, C3D10 kuadratik} × mesh-density {kaba, orta, ince}.
Her config → ccx → tepe vM → Lamé hatası + tekillik-bekçisi (truth-bağımsız guard).
Çıktı: assay hücreleri (case,knob,naive,truth,flagged) → fea_knob_sweep.jsonl.

C3D4 lineer tet stress'i fazla-rijit → AZ-tahmin (klasik under-integration); bu, run-time
guard'ların (watchdog tek-mesh; GCI 3-mesh) yakalayıp yakalayamadığını ölçen gerçek bir knob.
Kullanım: python experiments/fea_knob_sweep.py
"""
import json
import sys
from pathlib import Path

import gmsh
import meshio
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from fea_validation_cyl import (  # noqa: E402  (cylinder geometri + sabitler + truth)
    LZ,
    NU,
    R_IN,
    R_OUT,
    RHO,
    SIG_VM_AN,
    SY,
    E,
    P,
)

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

# (etiket, gmsh ElementOrder, mesh-size böleni: büyük=ince)
KNOBS = [
    ("C3D4-coarse", 1, 1.5), ("C3D4-mid", 1, 2.5), ("C3D4-fine", 1, 4.0),
    ("C3D10-coarse", 2, 1.5), ("C3D10-mid", 2, 2.5), ("C3D10-fine", 2, 4.0),
]


def build_mesh(work: Path, order: int, size_div: float) -> TetMesh:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        outer = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, LZ, R_OUT)
        inner = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, LZ, R_IN)
        tube, _ = gmsh.model.occ.cut([(3, outer)], [(3, inner)])
        qbox = gmsh.model.occ.addBox(0, 0, 0, R_OUT, R_OUT, LZ)
        gmsh.model.occ.intersect(tube, [(3, qbox)])
        gmsh.model.occ.synchronize()
        t = R_OUT - R_IN
        gmsh.option.setNumber("Mesh.MeshSizeMin", t / (size_div + 0.5))
        gmsh.option.setNumber("Mesh.MeshSizeMax", t / size_div)
        gmsh.option.setNumber("Mesh.ElementOrder", order)
        if order == 2:
            gmsh.option.setNumber("Mesh.HighOrderOptimize", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        msh = work / f"cyl_o{order}_{size_div}.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    m = meshio.read(str(msh))
    if order == 2:
        tet = next(c for c in m.cells if c.type == "tetra10")
        tri = next((c for c in m.cells if c.type == "triangle6"), None)
        nt = 6
        etype = "C3D10"
    else:
        tet = next(c for c in m.cells if c.type == "tetra")
        tri = next((c for c in m.cells if c.type == "triangle"), None)
        nt = 3
        etype = "C3D4"
    tris = tri.data.astype(np.int64) if tri is not None else np.zeros((0, nt), np.int64)
    return TetMesh(points=m.points.astype(np.float64), tets=tet.data.astype(np.int64),
                  surface_tris=tris, msh_path=msh, element_type=etype)


def pressure_tris(mesh: TetMesh) -> np.ndarray:
    """İç yüzey üçgenleri, 1-indexed, normal eksene (katı-dışı basınç). T3 (C3D4) ve
    T6 (C3D10) ikisini de işler — fea_validation_cyl'in T6-hardcoded versiyonunun aksine.
    Köşeleri çevirerek normal yönlendir; kenar-orta düğümler (varsa) yük için sıra-bağımsız."""
    pts = mesh.points
    tol = 0.3 * (R_OUT - R_IN)
    out = []
    for tri in mesh.surface_tris:
        p1, p2, p3 = pts[tri[0]], pts[tri[1]], pts[tri[2]]
        c = (p1 + p2 + p3) / 3.0
        if abs((c[0] ** 2 + c[1] ** 2) ** 0.5 - R_IN) > tol:
            continue
        n = np.cross(p2 - p1, p3 - p1)
        t1 = (tri + 1).tolist()
        if np.dot(n, np.array([c[0], c[1], 0.0])) > 0:        # köşe 1↔2 çevir (kenar-orta yerinde)
            t1 = [t1[0], t1[2], t1[1]] + t1[3:]
        out.append(t1)
    return np.array(out, dtype=np.int64) if out else np.zeros((0, mesh.surface_tris.shape[1]), np.int64)


def run_one(work: Path, label: str, order: int, size_div: float) -> dict | None:
    mesh = build_mesh(work, order, size_div)
    pts = mesh.points
    def plane(ax):
        return np.where(np.abs(pts[:, ax]) < 1e-7)[0] + 1
    ptris = pressure_tris(mesh)
    if len(ptris) == 0:
        return None
    case = FEACase(name=label, mesh=mesh, material=FEAMaterial("AL", E, NU, RHO, yield_strength_pa=SY),
                   fixed_bcs=[FixedBC(plane(0), "SYMX", 1, 1), FixedBC(plane(1), "SYMY", 2, 2),
                              FixedBC(plane(2), "SYMZ", 3, 3)],
                   pressure_loads=[PressureLoad(ptris, P, "PINT")], analysis_type="STATIC")
    ccx = run_ccx(write_inp(case, work), timeout=900)
    if not ccx.success:
        return {"label": label, "error": (ccx.stderr or ccx.stdout or "")[-200:]}
    vm = parse_frd(ccx.frd_path).von_mises()
    if vm is None:
        return {"label": label, "error": "vM yok"}
    peak = float(vm.max()) / 1e6
    truth = SIG_VM_AN / 1e6
    err = abs(peak - truth) / truth * 100
    sa = _stress_assessment(vm, SY / 1e6)
    return {"label": label, "etype": mesh.element_type, "nodes": mesh.num_nodes,
            "peak_vM_MPa": round(peak, 2), "truth_MPa": round(truth, 2), "err_pct": round(err, 1),
            "watchdog_ratio": sa["tepe_temsili_orani"]}


def main():
    work = HERE.parent / "_fea_knob_sweep"
    work.mkdir(exist_ok=True)
    truth = SIG_VM_AN / 1e6
    print(f"Lamé truth vM = {truth:.2f} MPa | knob taraması ({len(KNOBS)} config)", flush=True)
    rows = []
    out = HERE.parent / "fea_knob_sweep.jsonl"
    out.write_text("", encoding="utf-8")
    for label, order, sd in KNOBS:
        print(f"  [{label}] koşuluyor...", flush=True)
        r = run_one(work, label, order, sd)
        if r is None:
            print(f"  [{label}] basınç-üçgeni yok, atlandı"); continue
        rows.append(r)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if "error" in r:
            print(f"  [{label}] HATA: {r['error']}")
        else:
            print(f"  [{label}] {r['etype']} n={r['nodes']:,} vM={r['peak_vM_MPa']} "
                  f"err=%{r['err_pct']} watchdog={r['watchdog_ratio']}×", flush=True)
    print(f"\nYAZILDI {out.name} ({len(rows)} config)", flush=True)
    print("Yorum: C3D4 (lineer) under-integration → AZ-tahmin bekleniyor; C3D10 ~Lamé. "
          "Bunlar assay korpusuna FEA element-order hücreleri olarak eklenir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
