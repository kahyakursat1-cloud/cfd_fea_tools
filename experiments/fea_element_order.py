"""FEA eleman-mertebesi etkisi — C3D4 (linear tet) vs C3D10 (quadratic tet) BÜKÜLMEDE.
Üretim araç-FEA'sı second_order=False (C3D4) kullanır; V&V ise C3D10. Linear tet bükülmede
shear-locking'le AŞIRI KATI → sehimi düşük tahmin (güvensiz: gerçek sehim daha büyük).
Bu script ankastre kirişi (Euler-Bernoulli δ=PL³/3EI analitik) her iki elemanla, birkaç
mesh-inceliğinde koşup C3D4'ün hata payını NİCELER → "üretimi C3D10'a geçirelim mi"yi
veriye bağlar. Kanonik V&V'ye (fea_validation.json, C3D8I hex %1) ek: tet-mertebe ekseni.
Kullanım: python experiments/fea_element_order.py
"""
import json
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

L, B, H = 1.0, 0.05, 0.05                  # m — kiriş boyu, kesit (narinlik L/H=20)
E, NU, RHO, P = 70e9, 0.33, 2700.0, 1000.0  # alüminyum, uç yük (N), -z
I_SEC = B * H ** 3 / 12.0
DELTA_AN_MM = P * L ** 3 / (3 * E * I_SEC) * 1e3      # Euler-Bernoulli uç sehim (mm)


def build_mesh(work: Path, size: float, order: int) -> TetMesh:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.addBox(0, 0, 0, L, B, H)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMin", size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.ElementOrder", order)
        if order == 2:
            gmsh.option.setNumber("Mesh.HighOrderOptimize", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        msh = work / f"beam_o{order}_{size:.4f}.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    m = meshio.read(str(msh))
    ctype = "tetra10" if order == 2 else "tetra"
    etype = "C3D10" if order == 2 else "C3D4"
    tet = next(c for c in m.cells if c.type == ctype)
    ncol = 6 if order == 2 else 3
    return TetMesh(points=m.points.astype(np.float64), tets=tet.data.astype(np.int64),
                   surface_tris=np.zeros((0, ncol), np.int64), msh_path=msh, element_type=etype)


def run_case(work: Path, size: float, order: int) -> dict | None:
    mesh = build_mesh(work, size, order)
    pts = mesh.points
    tol = 1e-7
    root = np.where(np.abs(pts[:, 0] - 0.0) < tol)[0] + 1      # x=0 ankastre
    tip = np.where(np.abs(pts[:, 0] - L) < tol)[0] + 1          # x=L uç yük
    mat = FEAMaterial("AL", E, NU, RHO)
    case = FEACase(name=f"beam_o{order}", mesh=mesh, material=mat,
                   fixed_bcs=[FixedBC(root, "FIX", 1, 3)],
                   force_loads=[ForceLoad(tip, (0.0, 0.0, -1.0), P, "TIP")],
                   analysis_type="STATIC")
    inp = write_inp(case, work)
    ccx = run_ccx(inp, timeout=1200)
    if not ccx.success:
        return None
    disp = parse_frd(ccx.frd_path).displacement_magnitude()
    if disp is None:
        return None
    delta_mm = float(disp.max()) * 1e3                          # uç en çok sehir
    err = (delta_mm - DELTA_AN_MM) / DELTA_AN_MM * 100          # işaretli: <0 = çok katı
    return {"eleman": mesh.element_type, "h_m": size, "dugum": mesh.num_nodes,
            "eleman_sayisi": mesh.num_tets, "delta_mm": round(delta_mm, 4),
            "hata_pct": round(err, 1)}


def main():
    work = HERE.parent / "_fea_elem_order"
    work.mkdir(exist_ok=True)
    print(f"Analitik (Euler-Bernoulli): δ=PL³/3EI = {DELTA_AN_MM:.3f} mm "
          f"(I={I_SEC:.3e} m⁴, narinlik L/H={L / H:.0f})", flush=True)
    sizes = [H, H / 1.5, H / 2.0]                               # kaba→ince (kesit-bölme ~1,1.5,2)
    rows = []
    for order in (1, 2):
        for s in sizes:
            r = run_case(work, s, order)
            if r is None:
                print(f"  CCX FAIL eleman-order={order} h={s:.4f}"); continue
            rows.append(r)
            print(f"  {r['eleman']:5s} h={s:.4f} ({r['dugum']:>6,} düğüm, "
                  f"{r['eleman_sayisi']:>6,} elm): δ={r['delta_mm']:.3f} mm "
                  f"(hata %{r['hata_pct']:+.1f})", flush=True)

    c3d4 = [r for r in rows if r["eleman"] == "C3D4"]
    c3d10 = [r for r in rows if r["eleman"] == "C3D10"]
    worst_c3d4 = min((r["hata_pct"] for r in c3d4), default=None)   # en negatif = en katı
    best_c3d10 = min((abs(r["hata_pct"]) for r in c3d10), default=None)
    rec = {
        "vaka": "Eleman-mertebesi: C3D4 vs C3D10 ankastre kiriş bükülmesi (Euler-Bernoulli)",
        "analitik_delta_mm": round(DELTA_AN_MM, 3),
        "geometri": {"L_m": L, "kesit_m": B, "narinlik": L / H, "E_Pa": E, "P_N": P},
        "kosular": rows,
        "ozet": {
            "C3D4_en_kati_hata_pct": worst_c3d4,
            "C3D10_en_iyi_hata_pct": best_c3d10,
            "yorum": (f"C3D4 (linear, ÜRETİM default) sehimi %{abs(worst_c3d4):.0f}'a kadar "
                      f"DÜŞÜK tahmin (shear-locking → aşırı katı); C3D10 (V&V) analitiğe "
                      f"%{best_c3d10:.1f}. Düşük sehim GÜVENSİZ yöndedir (gerçek deformasyon "
                      "daha büyük). Sonuç: üretim FEA'sı bükülme-baskın yüklerde C3D10 "
                      "kullanmalı — özellikle ince kabuk/kanat-spar gibi narin yapılarda."
                      if worst_c3d4 is not None else "koşu eksik"),
        },
        "_not": "Üretim: python experiments/fea_element_order.py. Bağlam: vehicle_fea "
                "generate_tet_mesh(second_order=False) → C3D4; bu script C3D10'a geçiş gerekçesi.",
    }
    (HERE.parent / "fea_element_order.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nÖZET: C3D4 en katı %{worst_c3d4}, C3D10 en iyi %{best_c3d10} "
          "→ fea_element_order.json", flush=True)
    return 0


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
