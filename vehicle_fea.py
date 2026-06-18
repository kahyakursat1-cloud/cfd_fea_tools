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


def resolve_cp_vtk(run_dir: Path, sonuc: dict) -> str | None:
    """sonuc.json'daki cp_vtk'yı döndürür; yoksa çözülmüş case'ten çıkarır ve
    sonuc.json'a kalıcı yazar (eski koşulara geriye-dönük uyumluluk)."""
    run_dir = Path(run_dir)
    cp = sonuc.get("cp_vtk")
    if cp and Path(cp).exists():
        return cp
    case_dirs = [d for d in run_dir.iterdir() if d.is_dir() and (d / "system").exists()]
    if not case_dirs:
        return None
    case_dir = case_dirs[0]
    yb = case_dir / "postProcessing" / "yuzeyBasinc"
    hits = sorted(yb.rglob("*.vtk")) if yb.exists() else []
    if not hits:
        from vehicle_pipeline import export_surface_vtk
        tris = list((case_dir / "constant" / "triSurface").glob("*.stl"))
        if not tris:
            return None
        hit = export_surface_vtk(case_dir, tris[0].stem.replace(" ", "_"))
        if not hit:
            return None
        hits = [hit]
    sonuc["cp_vtk"] = str(hits[-1])
    (run_dir / "sonuc.json").write_text(json.dumps(sonuc, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    return sonuc["cp_vtk"]


def _parse_eigenfrequencies(dat_path: Path, max_modes=10) -> list[float]:
    """ccx .dat EIGENVALUE OUTPUT bölümünden frekanslar (Hz)."""
    freqs = []
    if not dat_path.exists():
        return freqs
    in_block = False
    for line in dat_path.read_text(errors="ignore").splitlines():
        if "E I G E N V A L U E" in line:
            in_block = True
            continue
        if in_block:
            parts = line.split()
            if len(parts) >= 4:
                try:
                    int(parts[0])
                    freqs.append(float(parts[3]))   # CYCLES/TIME sütunu
                    if len(freqs) >= max_modes:
                        break
                    continue
                except ValueError:
                    pass
            if freqs and line.strip() and not line.strip()[0].isdigit():
                break
    return freqs


def _mechanism_check(max_disp_mm, lmax_m, fixed_n, total_n) -> str | None:
    """Mekanizma/yetersiz-mesnet imzası: devasa sehim + ufak gerilme tipiktir.
    Lineer çözücü mekanizmada km-ölçekli yer değiştirme döndürebilir."""
    if max_disp_mm is None:
        return None
    if max_disp_mm > 0.05 * lmax_m * 1000:
        return (f"Sehim ({max_disp_mm:.0f} mm) model boyutunun %5'ini aşıyor — "
                f"mesnet muhtemelen yetersiz/mekanizma ({fixed_n}/{total_n} düğüm "
                "sabit). Sonuç GEÇERSİZ; farklı mesnet preseti veya oryantasyon seçin.")
    return None


def _stress_assessment(vm_field, yield_mpa: float) -> dict | None:
    """Tekillik-dayanıklı gerilme özeti. Sivri iç köşede tepe von Mises bir
    TEKİLLİK'tir (mesh inceldikçe ıraksar) → SF'yi yapay düşürüp yanlış 'güvensiz'
    verdicti verir. Tepeyle birlikte 99. yüzdelik 'temsili' değeri + oranı raporla;
    yüksek oran = lokalize tekillik/konsantrasyon (fillet veya mesh-yakınsamayla teyit)."""
    if vm_field is None or len(vm_field) == 0:
        return None
    vm = np.asarray(vm_field, float) / 1e6                 # Pa → MPa
    peak = float(vm.max())
    repr_ = float(np.percentile(vm, 99.0))                 # tekillik-robust temsili
    ratio = peak / repr_ if repr_ > 0 else None
    singular = bool(ratio and ratio > 2.5)                 # tepe » kütle → hotspot

    def _sf(s):
        return round(yield_mpa / s, 2) if (s and s > 0 and yield_mpa > 0) else None
    note = ("Gerilme alanı düzgün; lokalize tekillik yok (tepe ≈ temsili)."
            if not singular else
            f"⚠ Lokalize gerilme tepesi (tepe/temsili≈{ratio:.1f}×): sivri-köşe TEKİLLİĞİ "
            "(sahte, mesh inceldikçe ıraksar) VEYA gerçek konsantrasyon (delik/fillet) "
            "olabilir — tek-mesh ayıramaz. Karar muhafazakâr tepe-SF'de kalır; sivri köşe "
            "ise fillet ekleyip ya da mesh-yakınsamayla teyit edin (gerçek SF temsiliye yakın).")
    return {"max_von_mises_MPa": round(peak, 3),
            "temsili_von_mises_MPa": round(repr_, 3),
            "tepe_temsili_orani": round(ratio, 2) if ratio else None,
            "tekillik_suphesi": singular,
            "emniyet_faktoru": _sf(peak),                  # muhafazakâr (tepe)
            "emniyet_faktoru_temsili": _sf(repr_),         # tekillik-robust
            "_gerilme_notu": note}


# Termal genleşme katsayıları (1/K) — malzeme adından sezgi (CTE literatür değerleri)
_CTE = {"alum": 23e-6, "alüm": 23e-6, "steel": 12e-6, "çelik": 12e-6,
        "titan": 8.6e-6, "carbon": 2e-6, "karbon": 2e-6}


def _material(key: str) -> FEAMaterial:
    m = MATERIAL_LIBRARY[key]   # youngs_modulus MPa, yield MPa
    alpha = next((v for k, v in _CTE.items() if k in key.lower() or k in m.name.lower()),
                 12e-6)         # bilinmeyen → çelik benzeri varsayılan
    return FEAMaterial.from_gpa(m.name, m.youngs_modulus / 1000.0,
                                m.poisson_ratio, m.density, m.yield_strength,
                                alpha_per_k=alpha)


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


def _map_pressure_to_shell(vtk_patch, m: trimesh.Trimesh, rho=1.225) -> dict:
    """CFD basıncını kabuk (yüzey) mesh'inin düğüm kuvvetlerine eşler."""
    points, polys, p_arr, p_loc = _parse_legacy_vtk(Path(vtk_patch))
    if len(polys) == 0 or len(p_arr) == 0:
        return {"status": "FAILED", "error": "VTK parse: poligon/basınç yok"}
    if p_loc == "POINT" or len(p_arr) == len(points):
        p_poly = np.array([p_arr[list(poly)].mean() for poly in polys])
    else:
        p_poly = np.asarray(p_arr)
    cfd_centers = np.array([points[list(poly)].mean(axis=0) for poly in polys])
    p_pa = p_poly * rho
    _, nearest = cKDTree(cfd_centers).query(m.triangles_center, k=1)
    dF = (-p_pa[nearest][:, None]) * m.face_normals * m.area_faces[:, None]
    node_forces = np.zeros_like(m.vertices)
    for fi, f in enumerate(m.faces):
        share = dF[fi] / 3.0
        for nid in f:
            node_forces[nid] += share
    forces = {int(i + 1): tuple(node_forces[i]) for i in range(len(m.vertices))
              if np.linalg.norm(node_forces[i]) > 1e-9}
    return {"status": "SUCCESS", "node_forces": forces,
            "toplam_kuvvet_N": [round(float(x), 3) for x in dF.sum(axis=0)]}


def _write_shell_inp(path: Path, m: trimesh.Trimesh, mat: FEAMaterial,
                     thickness_m: float, fixed_nodes, cload: str,
                     frequency_modes: int = 0) -> Path:
    L = ["*HEADING", "Kabuk (S3) yapisal kontrol", "*NODE"]
    for i, (x, y, z) in enumerate(m.vertices, start=1):
        L.append(f"{i}, {x:.9e}, {y:.9e}, {z:.9e}")
    L.append("*ELEMENT, TYPE=S3, ELSET=KABUK")
    for i, f in enumerate(m.faces, start=1):
        L.append(f"{i}, {f[0]+1}, {f[1]+1}, {f[2]+1}")
    L.append("*NSET, NSET=SABIT")
    for k in range(0, len(fixed_nodes), 8):
        L.append(", ".join(str(int(n)) for n in fixed_nodes[k:k+8]))
    L.append(f"*MATERIAL, NAME={mat.name.replace(' ', '_')[:60]}")
    L.append("*ELASTIC")
    L.append(f"{mat.youngs_modulus_pa:.6e}, {mat.poisson_ratio}")
    L.append("*DENSITY")
    L.append(f"{mat.density_kg_m3}")
    L.append(f"*SHELL SECTION, ELSET=KABUK, MATERIAL={mat.name.replace(' ', '_')[:60]}")
    L.append(f"{thickness_m:.6e}")
    L.append("*STEP")
    if frequency_modes > 0:
        L.append("*FREQUENCY")
        L.append(str(frequency_modes))
        L.append("*BOUNDARY")
        L.append("SABIT, 1, 6, 0.0")
        L.append("*NODE FILE")
        L.append("U")
    else:
        L.append("*STATIC")
        L.append("*BOUNDARY")
        L.append("SABIT, 1, 6, 0.0")   # kabukta dönme DOF'ları da bağlanır
        L.append(cload)
        L.append("*NODE FILE")
        L.append("U")
        L.append("*EL FILE")
        L.append("S")
    L.append("*END STEP")
    path.write_text("\n".join(L), encoding="utf-8")
    return path


def _cload_lines(node_forces: dict) -> str:
    out = ["*CLOAD"]
    for nid, (fx, fy, fz) in sorted(node_forces.items()):
        for dof, val in ((1, fx), (2, fy), (3, fz)):
            if abs(val) > 1e-9:
                out.append(f"{nid}, {dof}, {val:.6e}")
    return "\n".join(out)


def run_structural_check(run_dir, material="aluminum_6061", constraint="y_min",
                         rho=1.225, model="dolu", shell_thickness_mm=2.0,
                         analysis="statik", n_modes=8, g_yuk=0.0, itki_n=0.0,
                         delta_t=0.0, progress_cb=None) -> dict:
    """g_yuk: manevra yük faktörü n (≠0 → CFD basıncına ek n·g eylemsizlik gövde-
    kuvveti, -z; FlightEnvelope.n_max ile beslenebilir). 0 = sadece aero-basınç.
    itki_n: motor itkisi (N); ≠0 → aft (kuyruk, min-x) patch'ine +x dağıtık nokta-yük.
    delta_t: üniform sıcaklık değişimi (K); ≠0 → termal genleşme gerilmesi (α malzemeden)."""
    run_dir = Path(run_dir)

    def cb(p, m):
        if progress_cb:
            progress_cb(p, m)

    sonuc = json.loads((run_dir / "sonuc.json").read_text(encoding="utf-8"))
    if sonuc.get("status") != "ok":
        return {"status": "FAILED", "error": "Önce başarılı bir CFD koşusu gerekli"}
    cp_vtk = None
    if analysis == "statik":   # frekans analizi yük gerektirmez
        cp_vtk = resolve_cp_vtk(run_dir, sonuc)
        if not cp_vtk:
            return {"status": "FAILED", "error": "Yüzey basınç VTK'sı bulunamadı/çıkarılamadı"}
    stl_candidates = sorted(run_dir.glob("*_oriented.stl")) or sorted(run_dir.glob("*_prep.stl"))
    if not stl_candidates:
        return {"status": "FAILED", "error": "Hazırlanmış STL bulunamadı"}
    stl = stl_candidates[0]

    m = trimesh.load(str(stl), force="mesh")

    # ── KABUK modeli: yüzey mesh'i doğrudan S3 eleman — tet gerekmez,
    # ince-OML/tam-araç derisi için doğru araç (dolu model parça ister) ──
    if model == "kabuk":
        # Kaba STL kabuk için yetersizdir (küp prep'i 8 düğüm!): hedef kenar
        # boyutuna kadar incelt — hem statik hem modal doğruluk için şart
        lmax0 = float((m.bounds[1] - m.bounds[0]).max())
        max_edge = lmax0 / 25.0
        try:
            if len(m.faces) < 50000:
                m = m.subdivide_to_size(max_edge, max_iter=6)
        except Exception:
            pass
        cb(10, f"Kabuk modeli: {len(m.faces):,} S3 eleman, t={shell_thickness_mm} mm")
        if analysis == "statik":
            mp = _map_pressure_to_shell(cp_vtk, m, rho=rho)
            if mp["status"] != "SUCCESS":
                return mp
        desc, axis, side = CONSTRAINT_PRESETS[constraint]
        coord = m.vertices[:, axis]
        plane = coord.min() if side == "min" else coord.max()
        ext = float(coord.max() - coord.min()) or 1.0
        tol = 0.02 * ext
        fixed = np.where(np.abs(coord - plane) < tol)[0] + 1
        while len(fixed) < 6 and tol < 0.2 * ext:
            tol *= 2
            fixed = np.where(np.abs(coord - plane) < tol)[0] + 1
        mat = _material(material)
        fea_dir = run_dir / "fea"
        fea_dir.mkdir(exist_ok=True)
        if analysis == "frekans":
            inp = _write_shell_inp(fea_dir / "kabuk_frekans.inp", m, mat,
                                   shell_thickness_mm / 1000.0, fixed, "",
                                   frequency_modes=n_modes)
            cb(40, f"CalculiX modal çözüm ({len(m.vertices):,} düğüm)...")
            ccx = run_ccx(inp, timeout=3600)
            if not ccx.success:
                return {"status": "FAILED", "error": f"ccx: {ccx.stderr[-400:]}"}
            freqs = _parse_eigenfrequencies(ccx.dat_path, n_modes)
            out = {"status": "ok", "analiz": "doğal frekans",
                   "model": f"kabuk (t={shell_thickness_mm} mm)", "malzeme": mat.name,
                   "mesnet": desc, "dugum": int(len(m.vertices)),
                   "dogal_frekanslar_hz": [round(f, 2) for f in freqs],
                   "_not": ("Yakıt/donanım/motor kütleleri ve iç yapı yok — frekanslar "
                            "yapısal-deri üst sınırıdır; flutter taraması için 1. mod "
                            "uçuş zarfı uyarım frekanslarıyla kıyaslanır.")}
            (run_dir / "fea_frekans.json").write_text(
                json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
            _append_freq_report(run_dir, out)
            cb(100, "Modal analiz tamamlandı")
            return out
        inp = _write_shell_inp(fea_dir / "kabuk_kontrol.inp", m, mat,
                               shell_thickness_mm / 1000.0, fixed,
                               _cload_lines(mp["node_forces"]))
        cb(40, f"CalculiX kabuk çözümü ({len(m.vertices):,} düğüm)...")
        ccx = run_ccx(inp, timeout=3600)
        if not ccx.success:
            return {"status": "FAILED", "error": f"ccx başarısız: {ccx.stderr[-400:]}"}
        cb(90, "Sonuçlar ayrıştırılıyor...")
        frd = parse_frd(ccx.frd_path)
        disp = frd.displacement_magnitude()
        vm = frd.von_mises()
        max_disp_mm = float(disp.max()) * 1000 if disp is not None else None
        lmax = float((m.bounds[1] - m.bounds[0]).max())
        mech = _mechanism_check(max_disp_mm, lmax, len(fixed), len(m.vertices))
        sa = _stress_assessment(vm, mat.yield_strength_pa / 1e6) or {}
        if mech:   # mekanizma → emniyet faktörü anlamsız
            sa = {**sa, "emniyet_faktoru": None, "emniyet_faktoru_temsili": None}
        out = {"status": "ok", "model": f"kabuk (t={shell_thickness_mm} mm)",
               "malzeme": mat.name, "mesnet": desc,
               "dugum": int(len(m.vertices)), "eleman": int(len(m.faces)),
               "sabit_dugum": int(len(fixed)),
               "toplam_kuvvet_N": mp["toplam_kuvvet_N"],
               "max_sehim_mm": round(max_disp_mm, 4) if max_disp_mm else None,
               **sa,
               "gecersiz": mech,
               "_not": ("Üniform kalınlıklı kabuk: spar/kaburga/iç yapı yok — "
                        "gerçek yapıdan ESNEK taraftadır (sehim üst-sınır eğilimli); "
                        "dolu-katı modelin tamamlayıcısı.")}
        (run_dir / "fea_sonuc.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        _append_report(run_dir, out)
        cb(100, "Kabuk yapısal kontrol tamamlandı")
        return out

    cb(5, "Tet mesh üretiliyor (gmsh)...")
    lmax = float((m.bounds[1] - m.bounds[0]).max())
    thin = sonuc.get("geometry", {}).get("ince_kalinlik_m") or lmax / 30
    target = float(np.clip(thin / 2.0, lmax / 80, lmax / 20))
    tet = generate_tet_mesh(m, target_size=target, output_dir=run_dir / "fea",
                            second_order=False,
                            progress_callback=lambda p, s: cb(5 + p // 5, s))

    if analysis == "statik":
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

    mat = _material(material)
    if analysis == "frekans":
        cb(40, f"CalculiX modal çözüm ({tet.num_nodes:,} düğüm)...")
        case = FEACase(name="dolu_frekans", mesh=tet, material=mat,
                       fixed_bcs=[FixedBC(node_ids=fixed)],
                       analysis_type="FREQUENCY", num_modes=n_modes)
        inp = write_inp(case, run_dir / "fea")
        ccx = run_ccx(inp, timeout=3600)
        if not ccx.success:
            return {"status": "FAILED", "error": f"ccx: {ccx.stderr[-400:]}"}
        freqs = _parse_eigenfrequencies(ccx.dat_path, n_modes)
        out = {"status": "ok", "analiz": "doğal frekans", "model": "dolu katı",
               "malzeme": mat.name, "mesnet": desc, "dugum": tet.num_nodes,
               "dogal_frekanslar_hz": [round(f, 2) for f in freqs],
               "_not": ("Dolu-katı: gerçek (kabuk) yapıdan RİJİT — frekanslar üst "
                        "sınır eğilimli; kütle dağılımı idealize.")}
        (run_dir / "fea_frekans.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        _append_freq_report(run_dir, out)
        cb(100, "Modal analiz tamamlandı")
        return out

    cb(40, f"CalculiX statik çözüm ({tet.num_nodes:,} düğüm)...")
    case = FEACase(name="yapisal_kontrol", mesh=tet, material=mat,
                   fixed_bcs=[FixedBC(node_ids=fixed)], analysis_type="STATIC",
                   delta_t=delta_t)
    inp = write_inp(case, run_dir / "fea")
    txt = inp.read_text(encoding="utf-8")
    inject = _cload_lines(mp["node_forces"])
    if g_yuk:                                   # manevra g-yükü: n·g eylemsizlik (-z)
        dz = -1.0 if g_yuk >= 0 else 1.0
        inject += (f"\n*DLOAD\nEALL, GRAV, {abs(g_yuk) * 9.81:.6e}, "
                   f"0.0, 0.0, {dz:.1f}")
    if itki_n:                                  # motor itkisi: aft (min-x) patch'e +x dağıtık
        xc = tet.points[:, 0]
        aft = np.where(xc < xc.min() + 0.03 * (xc.max() - xc.min()))[0] + 1
        if len(aft):
            fper = itki_n / len(aft)
            inject += "\n*CLOAD\n" + "\n".join(f"{int(n)}, 1, {fper:.6e}" for n in aft)
    txt = txt.replace("*STATIC", "*STATIC\n" + inject, 1)
    inp.write_text(txt, encoding="utf-8")
    ccx = run_ccx(inp, timeout=3600)
    if not ccx.success:
        return {"status": "FAILED", "error": f"ccx başarısız: {ccx.stderr[-400:]}"}

    cb(90, "Sonuçlar ayrıştırılıyor...")
    frd = parse_frd(ccx.frd_path)
    disp = frd.displacement_magnitude()
    vm = frd.von_mises()
    max_disp_mm = float(disp.max()) * 1000 if disp is not None else None
    mech = _mechanism_check(max_disp_mm, lmax, len(fixed), tet.num_nodes)
    sa = _stress_assessment(vm, mat.yield_strength_pa / 1e6) or {}
    if mech:
        sa = {**sa, "emniyet_faktoru": None, "emniyet_faktoru_temsili": None}
    out = {"status": "ok", "model": "dolu katı", "malzeme": mat.name, "mesnet": desc,
           "dugum": tet.num_nodes, "eleman": tet.num_tets,
           "sabit_dugum": int(len(fixed)),
           "toplam_kuvvet_N": mp["toplam_kuvvet_N"],
           "g_yuk_n": g_yuk or None,
           "itki_n": itki_n or None,
           "delta_t_k": delta_t or None,
           "max_sehim_mm": round(max_disp_mm, 4) if max_disp_mm else None,
           **sa,
           "gecersiz": mech,
           "_not": ("Dolu-katı varsayımı: sehim alt-sınır, gerilme yük-yolu "
                    "göstergesi; kabuk/iç yapı modellenmedi."
                    + (f" Yük: aero-basınç + {g_yuk:g}g eylemsizlik." if g_yuk
                       else " Yük: yalnız aero-basınç."))}
    (run_dir / "fea_sonuc.json").write_text(json.dumps(out, indent=2, ensure_ascii=False),
                                            encoding="utf-8")
    _append_report(run_dir, out)
    cb(100, "Yapısal kontrol tamamlandı")
    return out


def _append_freq_report(run_dir: Path, out: dict):
    rapor = run_dir / "rapor" / "RAPOR.md"
    if not rapor.exists():
        return
    md = ["\n## 8. Doğal Frekanslar (flutter/titreşim taraması)\n",
          f"- Model: **{out['model']}** — {out['malzeme']}, mesnet: {out['mesnet']}  ",
          "\n| Mod | Frekans (Hz) |", "|-----|--------------|"]
    for i, f in enumerate(out["dogal_frekanslar_hz"], start=1):
        md.append(f"| {i} | {f} |")
    md.append(f"\n> ⚠️ *{out['_not']}*\n")
    txt = rapor.read_text(encoding="utf-8")
    anchor = "\n---\n*Otomatik üretildi"
    if "## 8. Doğal Frekanslar" in txt:
        txt = txt.split("\n## 8. Doğal Frekanslar")[0] + "\n".join(md) + \
              anchor + " — vehicle_pipeline (CFD/FEA Tools)*\n"
    else:
        txt = txt.replace(anchor, "\n".join(md) + anchor, 1)
    rapor.write_text(txt, encoding="utf-8")


def _append_report(run_dir: Path, out: dict):
    rapor = run_dir / "rapor" / "RAPOR.md"
    if not rapor.exists():
        return
    sf = out.get("emniyet_faktoru")                  # tepe (muhafazakâr)
    sf_t = out.get("emniyet_faktoru_temsili")        # temsili (tekillik-robust)
    singular = out.get("tekillik_suphesi")
    sf_s = (">1000" if sf and sf > 1000 else str(sf))
    if out.get("gecersiz"):
        verdict = "❌ GEÇERSİZ (mekanizma)"
    else:
        # Verdict MUHAFAZAKÂR (tepe-SF). Tekillik şüphesinde temsili-SF BİLGİ olarak
        # gösterilir ama karar tepeye dayanır: tek-mesh tekilliği (sivri köşe, sahte)
        # gerçek konsantrasyondan (delik/fillet, Kt gerçek) AYIRAMAZ; temsiliye geçmek
        # gerçek konsantrasyonda SAHTE-GÜVENLİ olurdu. Güvenli taraf = tepe.
        verdict = ("✅ güvenli" if sf and sf >= 1.5 else
                   "⚠️ marjinal (SF<1.5)" if sf and sf >= 1.0 else
                   "❌ yetersiz (SF<1)" if sf else "—")
        if singular and sf_t:
            verdict += (f" — ⚠ tepe tekillik OLABİLİR (sivri köşeyse gerçek SF≈{sf_t}; "
                        "fillet ya da mesh-yakınsamayla teyit edin)")
    vm_line = f"- Max von Mises: **{out['max_von_mises_MPa']} MPa** (tepe)"
    if singular:
        vm_line += (f", temsili %99: **{out['temsili_von_mises_MPa']} MPa** "
                    f"(tepe/temsili {out['tepe_temsili_orani']}×)")
    sf_line = f"- Emniyet faktörü: tepe **{sf_s}**"
    if singular and sf_t:
        sf_line += f", temsili **{sf_t}**"
    sf_line += f" → {verdict}"
    md = ["\n## 7. Yapısal Kontrol (FEA — CFD basınçlarıyla)\n",
          f"- Model: **{out.get('model', 'dolu katı')}**  ",
          f"- Malzeme: **{out['malzeme']}**, mesnet: {out['mesnet']}  ",
          f"- Mesh: {out['dugum']:,} düğüm / {out['eleman']:,} tet "
          f"({out['sabit_dugum']} sabit düğüm)  ",
          f"- Aktarılan toplam kuvvet: {out['toplam_kuvvet_N']} N  ",
          (f"- Yük durumu: aero-basınç + **{out['g_yuk_n']:g}g** manevra eylemsizliği  "
           if out.get("g_yuk_n") else "- Yük durumu: yalnız aero-basınç  "),
          (f"- Motor itkisi (aft): **{out['itki_n']:g} N** (+x)  " if out.get("itki_n") else ""),
          (f"- Termal: **ΔT={out['delta_t_k']:g} K** (α·ΔT genleşme gerilmesi)  "
           if out.get("delta_t_k") else ""),
          f"- Max sehim: **{out['max_sehim_mm']} mm**  ",
          vm_line + "  ", sf_line + "\n",
          (f"> ⚠️ *{out['_gerilme_notu']}*\n" if singular and not out.get("gecersiz") else ""),
          (f"> ❌ *{out['gecersiz']}*\n" if out.get("gecersiz") else
           f"> ⚠️ *{out['_not']}*\n")]
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
    ap.add_argument("--model", default="dolu", choices=["dolu", "kabuk"],
                    help="dolu katı (parça) / kabuk S3 (tam araç derisi)")
    ap.add_argument("--kalinlik", type=float, default=2.0,
                    help="kabuk et kalınlığı (mm)")
    ap.add_argument("--analiz", default="statik", choices=["statik", "frekans"],
                    help="statik (CFD yükü) / frekans (modal, yük gerekmez)")
    ap.add_argument("--modlar", type=int, default=8, help="mod sayısı")
    args = ap.parse_args()

    def _cb(p, m):
        print(f"[{p:3d}%] {m}", flush=True)

    r = run_structural_check(args.run_dir, args.malzeme, args.mesnet,
                             model=args.model, shell_thickness_mm=args.kalinlik,
                             analysis=args.analiz, n_modes=args.modlar,
                             progress_cb=_cb)
    if r["status"] == "ok" and r.get("analiz") == "doğal frekans":
        print("\nDogal frekanslar (Hz):", r["dogal_frekanslar_hz"])
    elif r["status"] == "ok":
        print(f"\nSehim={r['max_sehim_mm']} mm  vonMises={r['max_von_mises_MPa']} MPa  "
              f"SF={r['emniyet_faktoru']}")
    else:
        print("BASARISIZ:", r.get("error", ""))
