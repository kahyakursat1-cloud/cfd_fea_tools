"""
Araç yapısal kontrolü: CFD yüzey basınçları → tet mesh → CalculiX statik çözüm.
================================================================================
Stüdyo CFD koşusunun çıktılarından (oriented STL + yuzey.vtk) çalışır:
1) gmsh tet mesh (et-kalınlığına göre boyut), 2) basınçlar tet yüzeyine
KDTree ile eşlenir (korunum kontrolü), 3) mesnet preseti ankastre, 4) ccx
statik → max sehim, von Mises, emniyet faktörü; RAPOR.md'ye bölüm eklenir.

DÜRÜSTLÜK: araç DOLU katı varsayılır (kabuk/iç yapı modellenmez) — gerçek
uçak yapısından ÇOK daha rijit. Sehim alt-sınır niteliğindedir; gerilme
dağılımı yük yolu fikri verir, sertifikasyon değeri taşımaz.

CLI: python vehicle_fea.py vehicle_runs/<model> --malzeme aluminum_6061 --mesnet y_min
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from analysis.calculix_writer import FEACase, FEAMaterial, FixedBC, write_inp
from analysis.ccx_runner import run_ccx
from analysis.frd_parser import parse_frd
from analysis.tet_mesher import generate_tet_mesh
from coupling_fsi import _parse_legacy_vtk
from fea_runner import MATERIAL_LIBRARY

CONSTRAINT_PRESETS = {
    "y_min": ("Kök ankastre (y-min düzlemi) — kanat kökü / yarım-model", 1, "min"),
    "y_max": ("Kök ankastre (y-max düzlemi)", 1, "max"),
    "x_min": ("Burun ankastre (x-min düzlemi)", 0, "min"),
    "z_min": ("Taban ankastre (z-min düzlemi) — sehpa/gövde altı", 2, "min"),
}


def _material(key: str) -> FEAMaterial:
    m = MATERIAL_LIBRARY[key]   # youngs_modulus MPa, yield MPa
    return FEAMaterial.from_gpa(m.name, m.youngs_modulus / 1000.0,
                                m.poisson_ratio, m.density, m.yield_strength)


def _map_pressure_to_tet(vtk_patch, tet, rho=1.225) -> dict:
    """CFD yüzey basıncını (kinematik p) tet yüzey düğüm kuvvetlerine eşler."""
    points, polys, p_arr, p_loc = _parse_legacy_vtk(Path(vtk_patch))
    if len(polys) == 0 or len(p_arr) == 0:
        return {"status": "FAILED", "error": "VTK parse: poligon/basınç yok"}
    if p_loc == "POINT" or len(p_arr) == len(points):
        p_poly = np.array([p_arr[list(poly)].mean() for poly in polys])
    else:
        p_poly = np.asarray(p_arr)
    cfd_centers = np.array([points[list(poly)].mean(axis=0) for poly in polys])
    p_pa = p_poly * rho

    tris = tet.surface_tris[:, :3]              # C3D10'da ilk 3 = köşe
    P = tet.points
    v1 = P[tris[:, 1]] - P[tris[:, 0]]
    v2 = P[tris[:, 2]] - P[tris[:, 0]]
    cross = np.cross(v1, v2)
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    normals = cross / (2 * areas[:, None] + 1e-30)
    centers = P[tris].mean(axis=1)
    # Dışa-normal garantisi: hacim merkezinden dışarı bakmalı
    cg = P.mean(axis=0)
    flip = np.einsum("ij,ij->i", normals, centers - cg) < 0
    normals[flip] *= -1

    _, nearest = cKDTree(cfd_centers).query(centers, k=1)
    dF = (-p_pa[nearest][:, None]) * normals * areas[:, None]
    total = dF.sum(axis=0)

    node_forces = np.zeros_like(P)
    for fi in range(len(tris)):
        share = dF[fi] / 3.0
        for nid in tris[fi]:
            node_forces[nid] += share
    forces = {int(i + 1): tuple(node_forces[i]) for i in range(len(P))
              if np.linalg.norm(node_forces[i]) > 1e-9}
    return {"status": "SUCCESS", "node_forces": forces,
            "toplam_kuvvet_N": [round(float(x), 3) for x in total],
            "n_yuklu_dugum": len(forces)}


def _cload_lines(node_forces: dict) -> str:
    out = ["*CLOAD"]
    for nid, (fx, fy, fz) in sorted(node_forces.items()):
        for dof, val in ((1, fx), (2, fy), (3, fz)):
            if abs(val) > 1e-9:
                out.append(f"{nid}, {dof}, {val:.6e}")
    return "\n".join(out)


def run_structural_check(run_dir, material="aluminum_6061", constraint="y_min",
                         rho=1.225, progress_cb=None) -> dict:
    run_dir = Path(run_dir)

    def cb(p, m):
        if progress_cb:
            progress_cb(p, m)

    sonuc = json.loads((run_dir / "sonuc.json").read_text(encoding="utf-8"))
    if sonuc.get("status") != "ok":
        return {"status": "FAILED", "error": "Önce başarılı bir CFD koşusu gerekli"}
    cp_vtk = sonuc.get("cp_vtk")
    if not cp_vtk or not Path(cp_vtk).exists():
        # Eski koşu: yüzey VTK'sını şimdi çıkar (cozum diskte duruyor)
        case_dirs = [d for d in run_dir.iterdir()
                     if d.is_dir() and (d / "system").exists()]
        if not case_dirs:
            return {"status": "FAILED", "error": "Çözülmüş case dizini bulunamadı"}
        case_dir = case_dirs[0]
        hits = sorted((case_dir / "postProcessing" / "yuzeyBasinc").rglob("*.vtk")) \
            if (case_dir / "postProcessing" / "yuzeyBasinc").exists() else []
        if not hits:
            from vehicle_pipeline import export_surface_vtk
            tris = list((case_dir / "constant" / "triSurface").glob("*.stl"))
            if not tris:
                return {"status": "FAILED", "error": "triSurface STL yok"}
            hit = export_surface_vtk(case_dir, tris[0].stem.replace(" ", "_"))
            if not hit:
                return {"status": "FAILED", "error": "Yüzey VTK çıkarılamadı"}
            hits = [hit]
        cp_vtk = str(hits[-1])
    sonuc["cp_vtk"] = cp_vtk
    stl_candidates = sorted(run_dir.glob("*_oriented.stl")) or sorted(run_dir.glob("*_prep.stl"))
    if not stl_candidates:
        return {"status": "FAILED", "error": "Hazırlanmış STL bulunamadı"}
    stl = stl_candidates[0]

    cb(5, "Tet mesh üretiliyor (gmsh)...")
    m = trimesh.load(str(stl), force="mesh")
    lmax = float((m.bounds[1] - m.bounds[0]).max())
    thin = sonuc.get("geometry", {}).get("ince_kalinlik_m") or lmax / 30
    target = float(np.clip(thin / 2.0, lmax / 80, lmax / 20))
    tet = generate_tet_mesh(m, target_size=target, output_dir=run_dir / "fea",
                            second_order=False,
                            progress_callback=lambda p, s: cb(5 + p // 5, s))

    cb(30, "CFD basınçları tet yüzeyine eşleniyor...")
    mp = _map_pressure_to_tet(cp_vtk, tet, rho=rho)
    if mp["status"] != "SUCCESS":
        return mp

    desc, axis, side = CONSTRAINT_PRESETS[constraint]
    coord = tet.points[:, axis]
    plane = coord.min() if side == "min" else coord.max()
    extent = float(coord.max() - coord.min()) or 1.0
    tol = 0.02 * extent
    fixed = np.where(np.abs(coord - plane) < tol)[0] + 1
    while len(fixed) < 6 and tol < 0.2 * extent:
        tol *= 2
        fixed = np.where(np.abs(coord - plane) < tol)[0] + 1

    cb(40, f"CalculiX statik çözüm ({tet.num_nodes:,} düğüm)...")
    mat = _material(material)
    case = FEACase(name="yapisal_kontrol", mesh=tet, material=mat,
                   fixed_bcs=[FixedBC(node_ids=fixed)], analysis_type="STATIC")
    inp = write_inp(case, run_dir / "fea")
    txt = inp.read_text(encoding="utf-8")
    txt = txt.replace("*STATIC", "*STATIC\n" + _cload_lines(mp["node_forces"]), 1)
    inp.write_text(txt, encoding="utf-8")
    ccx = run_ccx(inp, timeout=3600)
    if not ccx.success:
        return {"status": "FAILED", "error": f"ccx başarısız: {ccx.stderr[-400:]}"}

    cb(90, "Sonuçlar ayrıştırılıyor...")
    frd = parse_frd(ccx.frd_path)
    disp = frd.displacement_magnitude()
    vm = frd.von_mises()
    max_disp_mm = float(disp.max()) * 1000 if disp is not None else None
    max_vm_mpa = float(vm.max()) / 1e6 if vm is not None else None
    sf = (mat.yield_strength_pa / 1e6 / max_vm_mpa) if (max_vm_mpa and
          mat.yield_strength_pa > 0) else None

    out = {"status": "ok", "malzeme": mat.name, "mesnet": desc,
           "dugum": tet.num_nodes, "eleman": tet.num_tets,
           "sabit_dugum": int(len(fixed)),
           "toplam_kuvvet_N": mp["toplam_kuvvet_N"],
           "max_sehim_mm": round(max_disp_mm, 4) if max_disp_mm else None,
           "max_von_mises_MPa": round(max_vm_mpa, 3) if max_vm_mpa else None,
           "emniyet_faktoru": round(sf, 2) if sf else None,
           "_not": "Dolu-katı varsayımı: sehim alt-sınır, gerilme yük-yolu "
                   "göstergesi; kabuk/iç yapı modellenmedi."}
    (run_dir / "fea_sonuc.json").write_text(json.dumps(out, indent=2, ensure_ascii=False),
                                            encoding="utf-8")
    _append_report(run_dir, out)
    cb(100, "Yapısal kontrol tamamlandı")
    return out


def _append_report(run_dir: Path, out: dict):
    rapor = run_dir / "rapor" / "RAPOR.md"
    if not rapor.exists():
        return
    sf = out.get("emniyet_faktoru")
    sf_s = (">1000" if sf and sf > 1000 else str(sf))
    verdict = ("✅ güvenli" if sf and sf >= 1.5 else
               "⚠️ marjinal (SF<1.5)" if sf and sf >= 1.0 else
               "❌ yetersiz (SF<1)" if sf else "—")
    md = ["\n## 7. Yapısal Kontrol (FEA — CFD basınçlarıyla)\n",
          f"- Malzeme: **{out['malzeme']}**, mesnet: {out['mesnet']}  ",
          f"- Mesh: {out['dugum']:,} düğüm / {out['eleman']:,} tet "
          f"({out['sabit_dugum']} sabit düğüm)  ",
          f"- Aktarılan toplam kuvvet: {out['toplam_kuvvet_N']} N  ",
          f"- Max sehim: **{out['max_sehim_mm']} mm**  ",
          f"- Max von Mises: **{out['max_von_mises_MPa']} MPa** → "
          f"Emniyet faktörü: **{sf_s}** {verdict}\n",
          f"> ⚠️ *{out['_not']}*\n"]
    txt = rapor.read_text(encoding="utf-8")
    anchor = "\n---\n*Otomatik üretildi"
    if "## 7. Yapısal Kontrol" in txt:
        txt = txt.split("\n## 7. Yapısal Kontrol")[0]
        txt += "\n".join(md) + anchor + " — vehicle_pipeline (CFD/FEA Tools)*\n"
    else:
        txt = txt.replace(anchor, "\n".join(md) + anchor, 1)
    rapor.write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="CFD basınçlarıyla yapısal kontrol")
    ap.add_argument("run_dir", help="vehicle_runs/<model> dizini")
    ap.add_argument("--malzeme", default="aluminum_6061", choices=list(MATERIAL_LIBRARY))
    ap.add_argument("--mesnet", default="y_min", choices=list(CONSTRAINT_PRESETS))
    args = ap.parse_args()

    def _cb(p, m):
        print(f"[{p:3d}%] {m}", flush=True)

    r = run_structural_check(args.run_dir, args.malzeme, args.mesnet, progress_cb=_cb)
    if r["status"] == "ok":
        print(f"\nSehim={r['max_sehim_mm']} mm  vonMises={r['max_von_mises_MPa']} MPa  "
              f"SF={r['emniyet_faktoru']}")
    else:
        print("BASARISIZ:", r.get("error", ""))
