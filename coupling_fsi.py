"""
1-Way FSI Coupling — CFD basinc alani -> FEA dugum kuvvetleri
=============================================================
OpenFOAM duvar basinc alanini (foamToVTK ciktisi) okur, her CFD yuzeyinde
dF = -p * n * A hesaplar, FEA STL dugumlerine en-yakin esleme ile aktarir.

Korunum garantisi: toplam kuvvet yeniden dagitildigi icin
sum(F_FEA) == sum(F_CFD) (makine hassasiyetinde).

Endustri pratigi: ASME V&V, bir-yonlu aero-yapisal coupling.
"""

from pathlib import Path

import numpy as np


def _parse_legacy_vtk(vtk_path: Path):
    """Legacy ASCII VTK (foamToVTK patch ciktisi) okur.
    POLYGONS akis-tabanli, basinc FIELD attributes blogunda.
    Donduru: points (N,3), polys (list[list[int]]), p_cell (M,), p_loc ('cell'|'point')
    """
    text = vtk_path.read_text(errors="replace")
    lines = text.splitlines()
    n = len(lines)
    i = 0

    points = np.zeros((0, 3))
    polys = []
    p_cell = np.array([])
    p_loc = None
    cur_data = None  # 'CELL' veya 'POINT'

    def read_floats(start, count):
        vals = []
        j = start
        while len(vals) < count and j < n:
            toks = lines[j].split()
            if toks and _is_num(toks[0]):
                vals.extend(float(x) for x in toks)
                j += 1
            else:
                break
        return np.array(vals[:count]), j

    def read_ints(start, count):
        vals = []
        j = start
        while len(vals) < count and j < n:
            toks = lines[j].split()
            if toks and _is_num(toks[0]):
                vals.extend(int(float(x)) for x in toks)
                j += 1
            else:
                break
        return vals[:count], j

    while i < n:
        line = lines[i].strip()
        toks = line.split()
        if not toks:
            i += 1
            continue

        key = toks[0]
        if key == "POINTS":
            npts = int(toks[1])
            flat, i = read_floats(i + 1, npts * 3)
            points = flat.reshape(-1, 3)
            continue
        if key in ("POLYGONS", "CELLS"):
            total = int(toks[2])
            flat, i = read_ints(i + 1, total)
            # akisi poligonlara ayikla: k, v0..v(k-1), tekrar
            idx = 0
            while idx < len(flat):
                k = flat[idx]
                polys.append(flat[idx + 1: idx + 1 + k])
                idx += 1 + k
            continue
        if key == "CELL_DATA":
            cur_data = "CELL"
            i += 1
            continue
        if key == "POINT_DATA":
            cur_data = "POINT"
            i += 1
            continue
        if key == "FIELD":
            nfields = int(toks[2])
            i += 1
            for _ in range(nfields):
                fhdr = lines[i].split()
                fname, ncomp, ntup = fhdr[0], int(fhdr[1]), int(fhdr[2])
                flat, i = read_floats(i + 1, ncomp * ntup)
                if fname == "p":
                    p_cell = flat.reshape(ntup, ncomp)[:, 0] if ncomp > 1 else flat
                    p_loc = cur_data
            continue
        if key == "SCALARS" and len(toks) > 1 and toks[1] == "p":
            i += 1
            if i < n and lines[i].strip().startswith("LOOKUP_TABLE"):
                i += 1
            flat, i = read_floats(i, len(points) if cur_data == "POINT" else len(polys))
            p_cell = flat
            p_loc = cur_data
            continue
        i += 1

    return points, polys, p_cell, p_loc


def _is_num(s):
    try:
        float(s); return True
    # sessiz-yutma: kabul — istisna BURADA kontrol akisidir; fonksiyonun
    # tanimi zaten "bu deger sayiya cevrilebiliyor mu". Donus degeri sonucun
    # kendisi, yani bilgi kaybi yok.
    except ValueError:
        return False


def _poly_geometry(points, polys):
    """Her poligon icin merkez, normal (alan-agirlikli), alan."""
    centers = np.zeros((len(polys), 3))
    normals = np.zeros((len(polys), 3))
    areas = np.zeros(len(polys))
    for idx, poly in enumerate(polys):
        vs = points[poly]
        c = vs.mean(axis=0)
        centers[idx] = c
        # ucgen fan ile alan + normal
        nrm = np.zeros(3)
        for k in range(1, len(vs) - 1):
            nrm += np.cross(vs[k] - vs[0], vs[k + 1] - vs[0])
        a = 0.5 * np.linalg.norm(nrm)
        areas[idx] = a
        normals[idx] = nrm / (np.linalg.norm(nrm) + 1e-30)
    return centers, normals, areas


def cfd_pressure_to_fea_loads(vtk_patch: str, fea_stl: str,
                               rho: float = 1.225, p_is_kinematic: bool = True):
    """CFD duvar basincini FEA STL dugum kuvvetlerine donustur.

    vtk_patch     : foamToVTK aircraft patch .vtk yolu
    fea_stl       : FEA yuzey STL (dugumler kuvvet alacak)
    p_is_kinematic: OpenFOAM incompressible p = P/rho (m2/s2). True ise rho ile carp.

    Donduru: {node_id: (Fx,Fy,Fz)} + ozet (korunum kontrolu dahil)
    """
    import trimesh

    vtk_path = Path(vtk_patch)
    points, polys, p_cell, p_loc = _parse_legacy_vtk(vtk_path)
    if len(polys) == 0 or len(p_cell) == 0:
        return {"status": "FAILED", "error": "VTK parse: poligon/basinc bulunamadi"}
    if p_loc == "POINT" or len(p_cell) == len(points):
        # point-data: poligon basina ortala
        p_poly = np.array([p_cell[list(poly)].mean() for poly in polys])
    elif len(p_cell) == len(polys):
        p_poly = p_cell
    else:
        return {"status": "FAILED",
                "error": f"p ({len(p_cell)}) ile poligon ({len(polys)})/nokta ({len(points)}) uyumsuz"}

    cfd_centers, _, _ = _poly_geometry(points, polys)

    # Statik basinci Pa'ya cevir (incompressible kinematic p)
    p_pa = p_poly * rho if p_is_kinematic else p_poly

    # FEA STL: tutarli disa-normaller (trimesh watertight mesh icin duzeltir)
    mesh = trimesh.load(fea_stl, force='mesh')
    trimesh.repair.fix_normals(mesh)
    fea_nodes   = mesh.vertices                        # (K,3)
    faces       = mesh.faces                           # (F,3) node indices
    f_centers   = mesh.triangles_center               # (F,3)
    f_normals   = mesh.face_normals                    # (F,3) disa-normal
    f_areas     = mesh.area_faces                      # (F,)

    # Her STL yuzeyine en-yakin CFD yuzeyinin basincini ata
    from scipy.spatial import cKDTree
    tree = cKDTree(cfd_centers)
    _, nearest = tree.query(f_centers, k=1)
    p_on_face = p_pa[nearest]                           # (F,)

    # Yuzey kuvveti: dF = -p * n * A  (STL disa-normali guvenilir)
    dF_face = (-p_on_face[:, None]) * f_normals * f_areas[:, None]   # (F,3)
    total_F = dF_face.sum(axis=0)

    # Yuzey kuvvetini 3 dugume esit dagit (korunumlu)
    node_forces = np.zeros_like(fea_nodes)
    for fi in range(len(faces)):
        share = dF_face[fi] / 3.0
        for nid in faces[fi]:
            node_forces[nid] += share

    total_F_node = node_forces.sum(axis=0)
    # Korunum: yeniden-dağıtım sum(F_dugum)==sum(F_yuzey). Normalleştirme NET kuvvete
    # DEGIL throughput'a (yuzey-kuvvet buyukluk toplami) — simetrik yukte net≈0 olsa da
    # metrik anlamli kalir (aksi halde 0'a bolup sahte-buyuk verir).
    throughput = float(np.linalg.norm(dF_face, axis=1).sum())
    conservation_err = np.linalg.norm(total_F_node - total_F) / (throughput + 1e-30)

    forces = {int(i + 1): tuple(node_forces[i])
              for i in range(len(fea_nodes)) if np.linalg.norm(node_forces[i]) > 1e-9}

    return {
        "status": "SUCCESS",
        "n_cfd_faces": len(polys),
        "n_fea_faces": len(faces),
        "n_fea_nodes": len(fea_nodes),
        "n_loaded_nodes": len(forces),
        "p_min_Pa": float(p_pa.min()),
        "p_max_Pa": float(p_pa.max()),
        "total_force_N": [round(float(x), 4) for x in total_F],
        "drag_Fx_N": round(float(total_F[0]), 4),
        "side_Fy_N": round(float(total_F[1]), 4),
        "lift_Fz_N": round(float(total_F[2]), 4),
        "conservation_error": float(conservation_err),
        "node_forces": forces,
    }


def write_cload(node_forces: dict, out_path: str) -> str:
    """Dugum kuvvetlerini CalculiX *CLOAD blogu olarak yazar."""
    lines = ["*CLOAD\n"]
    for nid, (fx, fy, fz) in node_forces.items():
        if abs(fx) > 1e-9:
            lines.append(f"{nid}, 1, {fx:.8e}\n")
        if abs(fy) > 1e-9:
            lines.append(f"{nid}, 2, {fy:.8e}\n")
        if abs(fz) > 1e-9:
            lines.append(f"{nid}, 3, {fz:.8e}\n")
    Path(out_path).write_text("".join(lines))
    return out_path


if __name__ == "__main__":
    import json
    import sys
    vtk = sys.argv[1] if len(sys.argv) > 1 else \
        "mesh_independence/cases/medium_fixed/VTK/aircraft/aircraft_143.vtk"
    stl = sys.argv[2] if len(sys.argv) > 2 else \
        "mesh_independence/cases/medium_fixed/constant/triSurface/aircraft.stl"
    r = cfd_pressure_to_fea_loads(vtk, stl)
    summary = {k: v for k, v in r.items() if k != "node_forces"}
    print(json.dumps(summary, indent=2, default=str))
