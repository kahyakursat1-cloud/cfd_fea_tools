"""FEA doğrulama #2 — delikli plaka (gerilme konsantrasyonu Kt), kapalı-forma karşı.
Tek-eksenli çekmede merkez delikli plakanın tepe gerilmesini analitik Kt ile karşılaştırır.
ÜRETİM hattını doğrular: gmsh C3D10 (tet10 node-ordering) → calculix_writer.write_inp →
ccx → frd. Ayrıca _stress_assessment'ı GERÇEK konsantrasyonda sınar (tekillik DEĞİL:
delik kenarı düzgün eğri → sonlu/yakınsak tepe; sivri-köşe tekilliğiyle karıştırılmamalı).

Çeyrek-simetri model: delik orijinde, çekme +x. Analitik (Heywood, net-kesit):
  Kt_net = 2 + (1 - d/W)³,  σ_net = σ_brüt/(1 - d/W),  σ_tepe = Kt_net·σ_net = Kt_brüt·σ_brüt
Kullanım: python experiments/fea_validation_hole.py
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
    ForceLoad,
    write_inp,
)
from analysis.ccx_runner import run_ccx  # noqa: E402
from analysis.frd_parser import parse_frd  # noqa: E402
from analysis.tet_mesher import TetMesh  # noqa: E402
from vehicle_fea import _stress_assessment  # noqa: E402

# Geometri (çeyrek): x∈[0,A] çekme yönü, y∈[0,B] yarı-genişlik, z∈[0,T] yarı-kalınlık
A, B, T, R = 0.20, 0.05, 0.004, 0.010          # m
SIG_GROSS = 50e6                                # Pa — uzak-alan brüt gerilme (elastik)
E, NU, RHO, SY = 70e9, 0.33, 2700.0, 270e6     # alüminyum
DW = (2 * R) / (2 * B)                          # delik/genişlik oranı = 0.2
KT_NET = 2 + (1 - DW) ** 3                       # Heywood net-kesit konsantrasyonu
SIG_NET = SIG_GROSS / (1 - DW)
SIG_MAX_AN = KT_NET * SIG_NET                    # analitik tepe gerilme
KT_GROSS = SIG_MAX_AN / SIG_GROSS                # brüt-kesit Kt (~Peterson)


def build_mesh(work: Path, vin_div: float = 6.0, tag: str = "plate_hole") -> TetMesh:
    """Delikli-plaka mesh'i. vin_div: delik-çevresi eleman boyu = R/vin_div
    (büyük → ince mesh). GCI için bu yerel boyut h-temsilcisidir."""
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        box = gmsh.model.occ.addBox(0, 0, 0, A, B, T)
        cyl = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, T, R)
        gmsh.model.occ.cut([(3, box)], [(3, cyl)])
        gmsh.model.occ.synchronize()
        fld = gmsh.model.mesh.field.add("Ball")              # delik çevresini sıklaştır
        gmsh.model.mesh.field.setNumber(fld, "Radius", 4 * R)
        gmsh.model.mesh.field.setNumber(fld, "Thickness", 3 * R)
        gmsh.model.mesh.field.setNumber(fld, "XCenter", 0.0)
        gmsh.model.mesh.field.setNumber(fld, "YCenter", 0.0)
        gmsh.model.mesh.field.setNumber(fld, "ZCenter", T / 2)
        gmsh.model.mesh.field.setNumber(fld, "VIn", R / vin_div)
        gmsh.model.mesh.field.setNumber(fld, "VOut", R * 1.2)
        gmsh.model.mesh.field.setAsBackgroundMesh(fld)
        for opt in ("MeshSizeExtendFromBoundary", "MeshSizeFromPoints",
                    "MeshSizeFromCurvature"):
            gmsh.option.setNumber(f"Mesh.{opt}", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", R * 1.5)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.HighOrderOptimize", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        msh = work / f"{tag}.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    m = meshio.read(str(msh))
    tet = next(c for c in m.cells if c.type == "tetra10")
    return TetMesh(points=m.points.astype(np.float64),
                   tets=tet.data.astype(np.int64),
                   surface_tris=np.zeros((0, 6), dtype=np.int64),
                   msh_path=msh, element_type="C3D10")


def run_case(work: Path, vin_div: float = 6.0) -> dict | None:
    """Verilen mesh-inceliğinde delikli-plakayı koş; tepe vM + meta döndür.
    GCI scripti farklı vin_div'lerle çağırır."""
    tag = f"ph{int(round(vin_div))}"
    mesh = build_mesh(work, vin_div, tag)
    pts = mesh.points
    tol = 1e-7
    def plane(ax, val):
        return np.where(np.abs(pts[:, ax] - val) < tol)[0] + 1   # 1-indexed
    nx0, ny0, nz0, nxa = plane(0, 0), plane(1, 0), plane(2, 0), plane(0, A)
    mat = FEAMaterial("AL", E, NU, RHO, yield_strength_pa=SY)
    case = FEACase(
        name=tag, mesh=mesh, material=mat,
        fixed_bcs=[FixedBC(nx0, "SYMX", 1, 1), FixedBC(ny0, "SYMY", 2, 2),
                   FixedBC(nz0, "SYMZ", 3, 3)],
        force_loads=[ForceLoad(nxa, (1.0, 0.0, 0.0), SIG_GROSS * B * T, "TENS")],
        analysis_type="STATIC")
    inp = write_inp(case, work)
    ccx = run_ccx(inp, timeout=900)
    if not ccx.success:
        return None
    frd = parse_frd(ccx.frd_path)
    vm = frd.von_mises()
    if vm is None:
        return None
    loc = pts[int(np.argmax(vm))]
    return {"h": R / vin_div, "peak_MPa": float(vm.max()) / 1e6,
            "nodes": mesh.num_nodes, "sa": _stress_assessment(vm, SY / 1e6),
            "loc_mm": (loc * 1e3).tolist()}


def main():
    work = HERE.parent / "_fea_val_hole"
    work.mkdir(exist_ok=True)
    print(f"Analitik: Kt_net={KT_NET:.3f}, Kt_brüt={KT_GROSS:.3f}, "
          f"σ_tepe={SIG_MAX_AN / 1e6:.1f} MPa (σ_brüt={SIG_GROSS / 1e6:.0f})", flush=True)
    r = run_case(work, 6.0)
    if r is None:
        print("CCX FAILED"); return 1
    peak, sa, loc = r["peak_MPa"], r["sa"], r["loc_mm"]
    err = abs(peak - SIG_MAX_AN / 1e6) / (SIG_MAX_AN / 1e6) * 100
    print(f"Mesh: {r['nodes']:,} düğüm", flush=True)
    print(f"FEM: σ_tepe={peak:.1f} MPa (hata %{err:.1f}); konum (x,y,z)="
          f"({loc[0]:.1f},{loc[1]:.1f},{loc[2]:.1f}) mm", flush=True)
    print(f"_stress_assessment: tepe/temsili={sa['tepe_temsili_orani']}× , "
          f"tekillik_süphesi={sa['tekillik_suphesi']} (delik düzgün eğri → False beklenir)",
          flush=True)
    ok = err < 15
    print("SONUC:", "✅ GECTI (Kt analitik ile uyumlu)" if ok else "⚠ tolerans disi",
          flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
