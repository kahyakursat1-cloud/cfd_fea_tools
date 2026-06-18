"""
Araç analiz hattı: katı model (STL/OBJ) → araca uygun mesh → CFD → mühendis raporu.
===================================================================================
Tek giriş noktası: run_vehicle_analysis(). GUI (app_analyzer) ve CLI bunu çağırır.
Mesh/çözüm motoru analysis.openfoam_runner (snappyHexMesh + foamRun/kOmegaSST);
bu modül araç-tipi presetleri, referans alan hesabı, yakınsama/kalite teşhisi ve
rapor üretimini ekler.

CLI: python vehicle_pipeline.py model.stl --tip ucak --hiz 30 --aoa 4
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import ConvexHull

from analysis.openfoam_runner import CFDCase, run_cfd

VEHICLE_PRESETS = {
    "ucak": {
        "ad": "Sabit Kanatlı Uçak / İHA",
        "refinement": (2, 3), "domain": (5.0, 15.0, 5.0),
        "aref_mode": "planform", "lift_relevant": True,
    },
    "roket": {
        "ad": "Roket / Füze Gövdesi",
        "refinement": (2, 3), "domain": (5.0, 20.0, 5.0),
        "aref_mode": "frontal", "lift_relevant": False,
    },
    "multikopter": {
        "ad": "Multikopter / Drone Gövdesi",
        "refinement": (2, 3), "domain": (5.0, 12.0, 5.0),
        "aref_mode": "frontal", "lift_relevant": False,
    },
    "genel": {
        "ad": "Genel Cisim (küt gövde)",
        "refinement": (1, 2), "domain": (5.0, 15.0, 5.0),
        "aref_mode": "frontal", "lift_relevant": False,
    },
}

# bg_div: arka-plan hucresi = L/bg_div. maxGlobalCells yalniz refinement'i
# sinirlar; domain ~21Lx11Lx11L oldugundan taban mesh = 2541*bg_div^3 hucre —
# tavani asil delen buydu (L/8 otomatigi tek basina ~1.3M taban uretiyordu).
MESH_QUALITY = {
    "hizli":    {"end_time": 200, "ref_bump": -1, "max_cells": 400_000,   "bg_div": 5},
    "standart": {"end_time": 400, "ref_bump": 0,  "max_cells": 1_200_000, "bg_div": 7},
    "hassas":   {"end_time": 800, "ref_bump": 1,  "max_cells": 2_500_000, "bg_div": 9},
}

def farfield_domain(preset: dict, alpha_deg: float = 0.0) -> tuple[float, float, float]:
    """Far-field domain çarpanları (upstream, downstream, lateral) — rejim/geometri-bilinçli.

    Taşıyıcı (lift_relevant) cisimde sirkülasyon-kaynaklı basınç alanı yanal/yukarı YAVAŞ
    söner; yakın sınır basınç-drag'i orantısız bozar (bu oturumun far-field dersi; literatür:
    ses-altı RANS best-practice ≥ büyük domain). Bu yüzden lifting cisimde domain ölçülü
    büyütülür; yüksek |α|'da (daha çok lift) yanal biraz daha. Küt/eksenel cisim değişmez.

    MALİYET: lifting domain ~%50-100 daha çok taban hücre (hacim ∝ up·lat²). max_cells +
    bg_div sınırlar; yine de aircraft koşusu bir kademe ağırlaşır — doğruluk/maliyet takası.
    """
    up, down, lat = preset["domain"]
    if preset.get("lift_relevant"):
        up, down, lat = max(up, 7.0), max(down, 18.0), max(lat, 7.0)
        if abs(alpha_deg) >= 8.0:          # güçlü lift → daha geniş yan/üst
            lat = max(lat, 9.0)
    return (up, down, lat)


RESIDUAL_TARGET = 1e-4   # proje kuralı: yakınsama kriteri
NONORTHO_LIMIT = 70.0
SKEW_LIMIT = 4.0
DRIFT_LIMIT_PCT = 2.0    # son %20 pencerede |dCd|/Cd


CAD_EXTS = {".step", ".stp", ".iges", ".igs"}


def convert_cad_to_stl(cad_path: Path, out_stl: Path) -> Path:
    """STEP/IGES → STL (gmsh yüzey mesh'i; çekirdek bağımlılık, ek kurulum yok)."""
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(cad_path))
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
        L = max(xmax - xmin, ymax - ymin, zmax - zmin)
        gmsh.option.setNumber("Mesh.MeshSizeMin", L / 200)
        gmsh.option.setNumber("Mesh.MeshSizeMax", L / 60)
        gmsh.model.mesh.generate(2)
        gmsh.write(str(out_stl))
    finally:
        gmsh.finalize()
    return out_stl


def canonicalize_axial(m: trimesh.Trimesh):
    """Belirgin EKSENEL cismi (roket/füze: bir uzun eksen + YUVARLAK kesit)
    uçuş yönüne hizalar — uzun eksen→+x, ince eksen→+z. run_supersonic uzun-ekseni
    ≈+x ve frontal'i +x izdüşümü varsayar; dikey/yan modellenen roketi düzeltir.

    Yassı/kanat (kesit yuvarlak değil) ve küt cisimlere DOKUNMAZ — onlar zaten
    doğru sınıflanır ve ses-altı yolu nose_axis parametresini kullanır (çift-dönme
    riski yok). Döner: (mesh, açıklama|None)."""
    ext = (m.bounds[1] - m.bounds[0]).astype(float)
    order = np.argsort(ext)                       # küçük→büyük eksen indeksi
    e_thin, e_mid, e_long = ext[order[0]], ext[order[1]], ext[order[2]]
    # eksenel imza: belirgin uzun eksen (e_long»e_mid) + yuvarlak kesit (e_mid≈e_thin)
    if not (e_long >= 2.0 * e_mid and e_mid <= 1.7 * e_thin):
        return m, None
    long_axis = int(order[2])
    if long_axis == 0:
        return m, None                            # zaten +x hizalı
    axis = [0, 1, 0] if long_axis == 2 else [0, 0, 1]   # z→x: y-ekseni; y→x: z-ekseni
    out = m.copy()
    out.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, axis))
    return out, f"eksenel hizalama: uzun eksen {'xyz'[long_axis]}→x (uçuş yönü)"


def weld_axial_segments(m: trimesh.Trimesh):
    """KOPUK ama EŞ-EKSENLİ (aynı kesit, tek eksen boyunca dizili, aralarında BOŞLUK)
    gövdeleri tek watertight cisme birleştirir — konveks-zarf köprüleme. Roket/füze
    exploded/kopuk-ihraç artefaktını onarır (akış boşluklardan geçip Cd'yi bozuyordu).

    MUHAFAZAKÂR GUARD — yalnız EŞ-MERKEZLİ + BENZER-KESİT (koaksiyel silindir) segmentlere
    uygular. Yanal-yayılı çok-gövde (kanat/kontrol-yüzeyi montajı: a320/f16) ya da finli
    roket (yanal çıkıntı) GUARD'ı geçemez → DOKUNULMAZ (konveks-zarf onları bozardı).
    Döner: (mesh, açıklama|None)."""
    try:
        parts = m.split(only_watertight=False)
    except Exception:
        return m, None
    if len(parts) < 2:
        return m, None
    ext = (m.bounds[1] - m.bounds[0]).astype(float)
    long_ax = int(np.argmax(ext))
    minor = [a for a in range(3) if a != long_ax]
    ref = max(parts, key=lambda p: len(p.faces))            # ana gövde referans
    for p in parts:
        for ax in minor:
            rc = (ref.bounds[0][ax] + ref.bounds[1][ax]) / 2
            pc = (p.bounds[0][ax] + p.bounds[1][ax]) / 2
            rext = ref.bounds[1][ax] - ref.bounds[0][ax]
            pext = p.bounds[1][ax] - p.bounds[0][ax]
            # eş-merkez (merkez kayması < %25 çap) + benzer kesit (extent oranı < 1.6)
            if abs(pc - rc) > 0.25 * rext or not (1 / 1.6 < pext / max(rext, 1e-9) < 1.6):
                return m, None
    welded = m.convex_hull                                   # boşlukları köprüler
    if not welded.is_watertight:
        return m, None
    welded = welded.subdivide().subdivide()                 # CFD-dostu yüzey
    try:
        trimesh.smoothing.filter_taubin(welded, iterations=2)
        welded.fix_normals()
    except Exception:
        pass
    return welded, (f"{len(parts)} kopuk eş-eksenli segment → tek watertight cisme "
                    "kaynatıldı (konveks-zarf köprüleme; exploded/kopuk-ihraç onarımı)")


def prepare_geometry(path, out_dir: Path, progress_cb=None) -> tuple[Path, dict]:
    """Her formatı analiz-hazır tek STL'e indirger: CAD dönüşümü, çok-gövde
    birleştirme, normal/sarım onarımı, delik kapatma. Onarım kaydı döner."""
    path = Path(path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    info = {"kaynak": path.name, "onarimlar": []}

    if path.suffix.lower() in CAD_EXTS:
        if progress_cb:
            progress_cb(1, f"CAD dönüşümü (gmsh): {path.name}")
        path = convert_cad_to_stl(path, out_dir / f"{path.stem}_cad.stl")
        info["onarimlar"].append("CAD→STL dönüşümü (gmsh yüzey mesh)")

    m = trimesh.load(str(path), force="mesh")   # Scene ise gövdeler birleştirilir
    if not isinstance(m, trimesh.Trimesh) or len(m.faces) == 0:
        raise ValueError(f"Model okunamadı veya boş: {path}")

    try:
        info["govde_sayisi"] = len(m.split(only_watertight=False))
    except Exception:
        info["govde_sayisi"] = 1

    before_wt = bool(m.is_watertight)
    n_face0 = len(m.faces)
    try:
        m.process(validate=True)                # tekil nokta birleştirme + dejenere üçgen temizliği
        if len(m.faces) != n_face0:
            info["onarimlar"].append(f"dejenere/yinelenen üçgen temizliği ({n_face0}→{len(m.faces)})")
    except Exception:
        # trimesh fix_winding bazı çok-parçalı/tutarsız sarımlı mesh'lerde çöker;
        # onarımı atla, ham mesh ile devam et (analiz yine de koşar).
        info["onarimlar"].append("uyarı: tam topoloji onarımı atlandı (sarım tutarsız)")
    try:
        trimesh.repair.fix_normals(m)
        info["onarimlar"].append("normal/sarım onarımı")
    except Exception:
        pass
    if not m.is_watertight:
        try:
            if trimesh.repair.fill_holes(m) and m.is_watertight:
                info["onarimlar"].append("delik kapatma (su geçirmez hale getirildi)")
        except Exception:
            pass
    info["su_gecirmez_once"] = before_wt

    # Kopuk eş-eksenli segmentleri kaynat (roket exploded/kopuk-ihraç → tek cisim).
    # Akış boşluklardan geçip Cd'yi bozuyordu; muhafazakâr guard montajlara dokunmaz.
    m, _weld = weld_axial_segments(m)
    if _weld:
        info["onarimlar"].append(_weld)
        info["kaynak_birlestirme"] = _weld
    info["su_gecirmez_sonra"] = bool(m.is_watertight)

    # Yönelim: eksenel cismi (roket/füze) uçuş yönüne hizala (uzun eksen→+x).
    m, _orient = canonicalize_axial(m)
    if _orient:
        info["onarimlar"].append(_orient)
        info["yonelim"] = _orient

    # Birim sezgisi: CAD (STEP/IGES) konvansiyonel mm; çözücü metre bekler.
    # BİLSEM araçları (roket/İHA/dron) 0.05–10 m; >50 birim => mm, ÷1000.
    lmax = float((m.bounds[1] - m.bounds[0]).max())
    if lmax > 50.0:
        m.apply_scale(0.001)
        info["onarimlar"].append(f"birim ölçek mm→m (÷1000; ham Lmax={lmax:.0f})")
        info["birim_olcek"] = "mm→m"

    prepared = out_dir / f"{Path(info['kaynak']).stem}_prep.stl"
    m.export(str(prepared))
    return prepared, info


AXIS_VECTORS = {
    "+x": np.array([1.0, 0, 0]), "-x": np.array([-1.0, 0, 0]),
    "+y": np.array([0, 1.0, 0]), "-y": np.array([0, -1.0, 0]),
    "+z": np.array([0, 0, 1.0]), "-z": np.array([0, 0, -1.0]),
}


def orientation_matrix(nose_axis: str, up_axis: str) -> np.ndarray:
    """Modeli burun→+x, üst→+z olacak şekilde döndüren 3x3 matris.
    nose ve up dik olmalı (aynı/karşıt eksen kabul edilmez)."""
    nose = AXIS_VECTORS[nose_axis]
    up = AXIS_VECTORS[up_axis]
    if abs(float(nose @ up)) > 1e-9:
        raise ValueError(f"Burun ({nose_axis}) ve üst ({up_axis}) eksenleri dik olmalı")
    side = np.cross(up, nose)            # sağ-el: y = z × x
    return np.vstack([nose, side, up])   # satırlar: hedef eksenlerin kaynak ifadesi


def orient_mesh(stl_path: Path, nose_axis: str, up_axis: str, out_path: Path) -> Path:
    """STL'i akış çerçevesine (+x burun, +z üst) döndürüp out_path'e yazar."""
    if nose_axis == "+x" and up_axis == "+z":
        return Path(stl_path)
    m = trimesh.load(str(stl_path), force="mesh")
    T = np.eye(4)
    T[:3, :3] = orientation_matrix(nose_axis, up_axis)
    m.apply_transform(T)
    m.export(str(out_path))
    return out_path


def _hull_projected_area(vertices: np.ndarray, drop_axis: int) -> float:
    """Konveks-zarf izdüşüm alanı (üst sınır kestirimi)."""
    pts2 = np.delete(vertices, drop_axis, axis=1)
    try:
        return float(ConvexHull(pts2).volume)   # 2D'de volume = alan
    except Exception:
        mn, mx = pts2.min(0), pts2.max(0)
        return float((mx[0]-mn[0]) * (mx[1]-mn[1]))


def _thin_flatness(m: trimesh.Trimesh, nb: int = 12) -> float:
    """Açıklık (en-uzun eksen) boyunca yerel yassılık profilinin alt-yüzdeliği:
    her dilimde kalınlık(en-ince eksen)/kiriş(orta eksen). İnce kaldırma yüzeyi
    (kanat) düşük (~0.1), kalın harmanlanmış/küt gövde yüksek (~0.4–1.0) verir.
    Yönelimden bağımsız (eksenler ekstent'e göre sıralanır)."""
    mm = m
    while len(mm.vertices) < 400:          # düşük-poligon (box) → yoğunlaştır
        mm = mm.subdivide()
    V = np.asarray(mm.vertices, float)
    V = V - V.mean(0)
    order = np.argsort(V.max(0) - V.min(0))           # küçük→büyük eksen
    a_long, a_mid, a_thin = order[2], order[1], order[0]
    y = V[:, a_long]
    edges = np.linspace(y.min(), y.max(), nb + 1)
    flat = []
    for i in range(nb):
        sel = (y >= edges[i]) & (y < edges[i + 1])
        if int(sel.sum()) < 5:
            continue
        chord = float(np.ptp(V[sel, a_mid]))
        thick = float(np.ptp(V[sel, a_thin]))
        if chord > 1e-9:
            flat.append(thick / chord)
    return float(np.percentile(flat, 20)) if flat else 1.0


def _radial_solidity(m: trimesh.Trimesh) -> float:
    """Üst-görünüm (en-ince eksene dik) DOLULUK: siluet-alanı / konveks-zarf-alanı.
    Radyal-kollu cisim (multikopter: gövde+ince kollar, aralarda boşluk) DÜŞÜK (~0.2);
    sürekli yüzey (kanat/küt gövde) YÜKSEK (~0.5–1.0). 'Radyal-simetri/spoke' ayırt edici —
    multikopter↔kanat bbox-örtüşmesini çözer (govde dejenere olduğunda bile çalışır)."""
    ext = m.bounds[1] - m.bounds[0]
    keep = [i for i in range(3) if i != int(np.argmin(ext))]
    V2 = np.asarray(m.vertices, float)[:, keep]
    tris = V2[m.faces]
    a, b = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    sil = 0.5 * float(np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum()) * 0.5  # ~2-katman
    try:
        hull = float(ConvexHull(V2).volume)              # 2B'de volume = alan
    except Exception:
        return 1.0
    return round(min(sil / hull, 1.0), 4) if hull > 1e-12 else 1.0


def inspect_geometry(stl_path: Path) -> dict:
    m = trimesh.load(str(stl_path), force="mesh")
    if not isinstance(m, trimesh.Trimesh):
        raise ValueError(f"Model yüklenemedi: {stl_path}")
    dims = (m.bounds[1] - m.bounds[0]).astype(float)
    return {
        "dosya": Path(stl_path).name,
        "boyutlar_m": [round(float(d), 4) for d in dims],
        "lmax_m": round(float(dims.max()), 4),
        "ucgen_sayisi": int(len(m.faces)),
        "su_gecirmez": bool(m.is_watertight),
        "yuzey_alani_m2": round(float(m.area), 5),
        "on_alan_m2": round(_hull_projected_area(m.vertices, 0), 5),     # akış +x
        "planform_alan_m2": round(_hull_projected_area(m.vertices, 2), 5),  # üstten
        "ince_kalinlik_m": (lambda t: round(t, 5) if t else None)(estimate_thin_thickness(m)),
        "ince_yassilik": round(_thin_flatness(m), 4),    # kanat-inceliği (bbox-üstü)
        "radyal_doluluk": _radial_solidity(m),           # spoke↔sürekli (multikopter ayrımı)
    }


def estimate_thin_thickness(m: trimesh.Trimesh, samples: int = 200,
                            percentile: float = 10.0) -> float | None:
    """Yüzeyden örneklenmiş yerel et-kalınlığı kestirimi (normal boyunca ray).
    Kanat/fin gibi ince özellikleri bbox'tan çok daha iyi temsil eder; alt
    persentil alınır ki gövde kalınlığı inceyi maskelemesin. (max_sphere
    kenar yakınında sistematik küçük verir — ray doğru semantik.)

    Ray backend (rtree/embree) yoksa ya da ince plaka gibi durumlarda geçerli
    örnek yetersiz kalırsa bbox en-ince-boyutuna düşülür — kaba ama güvenli."""
    extents = (m.bounds[1] - m.bounds[0]).astype(float)
    bbox_min = float(extents[extents > 0].min()) if np.any(extents > 0) else None
    try:
        pts, face_idx = trimesh.sample.sample_surface(m, samples)
        normals = m.face_normals[face_idx]
        th = trimesh.proximity.thickness(m, pts, normals=normals,
                                         method="ray")
        th = th[np.isfinite(th) & (th > 0)]
        if len(th) >= samples // 4:
            return float(np.percentile(th, percentile))
    except Exception:
        pass
    return bbox_min


def resolution_warning(lmax_m: float, bg_div: int, ref_max: int, min_dim_m: float,
                       min_cells_across: int = 6) -> str | None:
    """En ince bbox boyutunun en ince yüzey hücresine oranı — kanat/fin gibi
    ince özelliklerin çözünürlük bekçisi. Yetersizse uyarı metni döner."""
    surf_cell = (lmax_m / bg_div) / (2 ** ref_max)
    n_across = min_dim_m / surf_cell
    if n_across >= min_cells_across:
        return None
    return (f"En ince boyut ({min_dim_m:.3g} m) en ince yüzey hücresinin "
            f"~{n_across:.1f} katı (hedef ≥{min_cells_across}) — kanat/fin gibi ince "
            "özellikler yeterince çözülmüyor olabilir; Cl/Cd güvenilirliği için "
            "'hassas' kalite önerilir")


def parse_checkmesh(log: Path) -> dict:
    out = {"cells": None, "non_ortho_max": None, "skew_max": None, "mesh_ok": None}
    if not log.exists():
        return out
    txt = log.read_text(errors="ignore")
    m = re.search(r"cells:\s+(\d+)", txt)
    if m: out["cells"] = int(m.group(1))
    m = re.search(r"non-orthogonality Max:\s*([\d.]+)", txt)
    if m: out["non_ortho_max"] = float(m.group(1))
    m = re.search(r"Max skewness =\s*([\d.]+)", txt)
    if m: out["skew_max"] = float(m.group(1))
    out["mesh_ok"] = "Mesh OK" in txt
    return out


def propeller_params(thrust_n: float, cap_m: float, velocity: float,
                     rho: float = 1.225) -> dict:
    """Froude aktüatör diski: hedef itkiden indüksiyon faktörü.
    OF11 actuationDiskSource T = 2A·U₀²·a(1−a); diskDir akış yönünde (+x)
    seçilince kaynak akışkanı İTER (pervane). Froude sınırı τ ≤ 0.25."""
    area = math.pi * (cap_m / 2) ** 2
    tau = thrust_n / (2 * rho * area * velocity ** 2)
    uyari = None
    if tau > 0.24:
        uyari = (f"İtki Froude sınırını aşıyor (τ={tau:.2f}>0.25; bu hız/çapta "
                 f"max ~{0.24 * 2 * rho * area * velocity**2:.1f} N) — sınıra kapatıldı")
        tau = 0.24
    a = (1 - math.sqrt(1 - 4 * tau)) / 2
    ct = 0.7
    return {"itki_N": thrust_n, "cap_m": cap_m, "area": area,
            "a": round(a, 4), "Cp": round(ct * (1 - a), 4), "Ct": ct,
            "tau": round(tau, 4), "uyari": uyari}


def first_layer_height(velocity, lref, yplus_target, nu=1.5e-5):
    """Hedef y⁺ için ilk prizma katmanı YÜKSEKLİĞİ (m).
    Düz-plaka türbülanslı korelasyon: Cf=0.026·Re⁻¹ᐟ⁷, u*=V√(Cf/2),
    y₁=y⁺·ν/u* hücre MERKEZİ olduğundan yükseklik = 2·y₁."""
    re = max(velocity * lref / nu, 1e3)
    cf = 0.026 / re ** (1 / 7)
    utau = velocity * math.sqrt(cf / 2)
    return 2.0 * yplus_target * nu / utau


def measure_yplus(case_dir, timeout=600) -> dict | None:
    """Çözülmüş alanda duvar y⁺'ını ÖLÇER (varsayım değil; foamPostProcess)."""
    p = str(Path(case_dir).resolve())
    wsl = "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")
    try:
        r = subprocess.run(
            f'wsl bash -c "source /opt/openfoam11/etc/bashrc && unset FOAM_SIGFPE && '
            f"cd {wsl} && foamPostProcess -solver incompressibleFluid -func yPlus -latestTime 2>&1"
            f'"',
            shell=True, capture_output=True, text=True, timeout=timeout)
        m = re.search(r"y\+ : min = ([\d.eE+-]+), max = ([\d.eE+-]+), average = ([\d.eE+-]+)",
                      r.stdout)
        if m:
            return {"min": round(float(m.group(1)), 2), "max": round(float(m.group(2)), 2),
                    "ort": round(float(m.group(3)), 2)}
    except Exception:
        pass
    return None


def export_surface_vtk(case_dir, patch_name: str, timeout=600) -> Path | None:
    """Çözülmüş alandan araç yüzeyini p alanıyla VTK olarak çıkarır
    (foamPostProcess, solver yeniden koşmaz — eski case'lere de uygulanabilir)."""
    case_dir = Path(case_dir)
    func = (
        'type surfaces; libs ("libsampling.so");\n'
        "surfaceFormat vtk; fields (p);\n"
        "interpolationScheme cellPoint;\n"
        f"surfaces ( yuzey {{ type patch; patches ({patch_name}); }} );\n"
    )
    (case_dir / "system" / "yuzeyBasinc").write_text(
        "FoamFile{version 2.0; format ascii; class dictionary; object yuzeyBasinc;}\n" + func)
    p = str(case_dir.resolve())
    wsl = "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")
    try:
        subprocess.run(
            f'wsl bash -c "source /opt/openfoam11/etc/bashrc && unset FOAM_SIGFPE && '
            f'cd {wsl} && foamPostProcess -solver incompressibleFluid -func yuzeyBasinc '
            f'-latestTime > log.yuzeyBasinc 2>&1"',
            shell=True, capture_output=True, text=True, timeout=timeout)
        cands = sorted((case_dir / "postProcessing" / "yuzeyBasinc").rglob("*.vtk")) + \
                sorted((case_dir / "postProcessing" / "yuzeyBasinc").rglob("*.vtp"))
        return cands[-1] if cands else None
    except Exception:
        return None


def export_cutplane_vtk(case_dir, center, timeout=600) -> Path | None:
    """Simetri düzleminden (y=merkez) hız kesiti VTK'sı çıkarır (foamPostProcess)."""
    case_dir = Path(case_dir)
    cx, cy, cz = center
    func = (
        'type surfaces; libs ("libsampling.so");\n'
        "surfaceFormat vtk; fields (U p);\n"
        "interpolationScheme cellPoint;\n"
        "surfaces ( kesit { type cutPlane; planeType pointAndNormal; "
        f"pointAndNormalDict {{ point ({cx} {cy} {cz}); normal (0 1 0); }} "
        "interpolate true; } );\n"
    )
    (case_dir / "system" / "hizKesiti").write_text(
        "FoamFile{version 2.0; format ascii; class dictionary; object hizKesiti;}\n" + func)
    p = str(case_dir.resolve())
    wsl = "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")
    try:
        subprocess.run(
            f'wsl bash -c "source /opt/openfoam11/etc/bashrc && unset FOAM_SIGFPE && '
            f'cd {wsl} && foamPostProcess -solver incompressibleFluid -func hizKesiti '
            f'-latestTime > log.hizKesiti 2>&1"',
            shell=True, capture_output=True, text=True, timeout=timeout)
        cands = sorted((case_dir / "postProcessing" / "hizKesiti").rglob("kesit.vtk"))
        return cands[-1] if cands else None
    except Exception:
        return None


def parse_residuals(log: Path) -> dict:
    """foamRun logundan alan bazlı initial-residual tarihçesi."""
    hist: dict[str, list[float]] = {}
    if not log.exists():
        return hist
    pat = re.compile(r"Solving for (\w+), Initial residual = ([\d.eE+-]+)")
    seen_this_iter: set[str] = set()
    for line in log.read_text(errors="ignore").splitlines():
        if line.startswith("Time ="):
            seen_this_iter = set()
            continue
        m = pat.search(line)
        if m and m.group(1) not in seen_this_iter:   # PIMPLE iç döngülerinde ilkini al
            seen_this_iter.add(m.group(1))
            hist.setdefault(m.group(1), []).append(float(m.group(2)))
    return hist


@dataclass
class VehicleAnalysisResult:
    status: str
    vehicle_type: str
    stl: str
    velocity: float
    alpha_deg: float
    geometry: dict
    aref_m2: float | None = None
    aref_mode: str = ""
    cd: float | None = None
    cd_wake: float | None = None        # far-field iz-momentum Cd (2.-mertebe çapraz-kontrol)
    cl: float | None = None
    ld: float | None = None
    cda_m2: float | None = None
    drag_N: float | None = None
    mesh: dict | None = None
    convergence: dict | None = None
    uyarilar: list = None
    sinir_tabaka: dict | None = None
    pervane: dict | None = None
    cp_vtk: str = ""
    kesit_vtk: str = ""
    mesh_duyarlilik: dict | None = None
    case_dir: str = ""
    report: str = ""
    error: str = ""


def run_vehicle_analysis(stl_path, vehicle_type="ucak", velocity=30.0, alpha_deg=0.0,
                         quality="standart", out_root="vehicle_runs",
                         n_processors=0, rho=1.225,
                         nose_axis="+x", up_axis="+z",
                         mesh_sensitivity=False, n_layers=0, yplus_target=30.0,
                         pervane_itki_n=0.0, pervane_cap_m=0.0,
                         progress_cb=None) -> VehicleAnalysisResult:
    stl_path = Path(stl_path)
    stem = stl_path.stem
    preset = VEHICLE_PRESETS[vehicle_type]
    q = MESH_QUALITY[quality]

    run_dir = Path(out_root) / stem
    run_dir.mkdir(parents=True, exist_ok=True)
    stl_path, prep = prepare_geometry(stl_path, run_dir, progress_cb)
    stl_path = orient_mesh(stl_path, nose_axis, up_axis,
                           run_dir / f"{stem}_oriented.stl")
    geo = inspect_geometry(stl_path)
    geo["hazirlik"] = prep
    geo["oryantasyon"] = f"burun={nose_axis} üst={up_axis} → akış çerçevesi (+x, +z)"
    if progress_cb:
        progress_cb(2, f"Geometri: {geo['lmax_m']} m, {geo['ucgen_sayisi']} üçgen")

    a = math.radians(alpha_deg)
    rmin, rmax = preset["refinement"]
    bump = q["ref_bump"]
    _dom = farfield_domain(preset, alpha_deg)   # lift-bilinçli far-field
    prop = None
    if pervane_itki_n > 0 and pervane_cap_m > 0:
        prop = propeller_params(pervane_itki_n, pervane_cap_m, velocity, rho)

    # Mach>0.3: sıkışabilir çözücü altyapısı mevcut (foamRun -solver fluid:
    # thermo + T/p/rho/alphat alanları + akı şemaları) ama soğuk-başlangıç
    # kararlılığı tuning gerektiriyor — DENEYSEL, varsayılan KAPALI.
    mach = velocity / 340.0
    compressible = mach > 0.3 and os.environ.get("CFD_COMPRESSIBLE") == "1"
    if compressible:
        rho = 101325.0 / (287.058 * 288.15)
        if progress_cb:
            progress_cb(3, f"Mach {mach:.2f} — DENEYSEL sıkışabilir çözücü (fluid)")
    case = CFDCase(
        name=stem,
        stl_path=stl_path,
        velocity=velocity,
        flow_direction=(math.cos(a), 0.0, math.sin(a)),
        rho=rho,
        domain_upstream=_dom[0],
        domain_downstream=_dom[1],
        domain_lateral=_dom[2],
        refinement_min=max(1, rmin + bump),
        refinement_max=max(1, rmax + bump),
        end_time=q["end_time"],
        max_global_cells=q["max_cells"],
        bg_cell_size=geo["lmax_m"] / q["bg_div"],
        n_layers=n_layers,
        first_layer_thickness=(first_layer_height(velocity, geo["lmax_m"], yplus_target)
                               if n_layers > 0 else None),
        propeller=prop,
        compressible=compressible,
        n_processors=n_processors,
    )
    res = run_cfd(case, run_dir, progress_callback=progress_cb)
    case_dir = res.case_dir

    base = VehicleAnalysisResult(
        status="failed", vehicle_type=vehicle_type, stl=str(stl_path),
        velocity=velocity, alpha_deg=alpha_deg, geometry=geo,
        case_dir=str(case_dir),
    )
    if not res.success or res.cd is None:
        base.error = (res.stderr or res.stdout)[-2000:]
        (run_dir / "sonuc.json").write_text(json.dumps(asdict(base), indent=2, ensure_ascii=False), encoding="utf-8")
        return base

    # Katsayıları gerçek referans alana ölçekle (forceCoeffs Aref = lref^2 kullanır)
    lref = case.lref
    aref_of = lref * lref
    aref_mode = preset["aref_mode"]
    aref = geo["planform_alan_m2"] if aref_mode == "planform" else geo["on_alan_m2"]
    if aref <= 0:
        aref, aref_mode = aref_of, "lref^2 (fallback)"
    scale = aref_of / aref
    cd = res.cd * scale
    cl = res.cl * scale if res.cl is not None and math.isfinite(res.cl) else None
    q_dyn = 0.5 * rho * velocity**2

    history = [(t, c * scale, (lc * scale if math.isfinite(lc) else float("nan")))
               for t, c, lc, _ in res.forces_history]
    residuals = parse_residuals(case_dir / "log.foamRun")
    meshq = parse_checkmesh(case_dir / "log.checkMesh")

    # Yakınsama teşhisi: son %20 pencerede Cd drifti + son rezidüeller
    n = len(history)
    drift_pct = None
    if n >= 10:
        w = max(2, n // 5)
        drift_pct = abs(history[-1][1] - history[-w][1]) / (abs(history[-1][1]) + 1e-12) * 100
    final_res = {f: (v[-1] if v else None) for f, v in residuals.items()}
    res_ok = all(v is not None and v < RESIDUAL_TARGET for f, v in final_res.items()
                 if f.startswith(("Ux", "Uy", "Uz", "p")))
    conv = {
        "iterasyon": n,
        "cd_drift_son20pct": round(drift_pct, 3) if drift_pct is not None else None,
        "drift_ok": drift_pct is not None and drift_pct < DRIFT_LIMIT_PCT,
        "son_rezidualler": {k: (f"{v:.2e}" if v is not None else None) for k, v in final_res.items()},
        "rezidual_ok": res_ok,
    }

    base.status = "ok"
    base.aref_m2 = round(aref, 6)
    base.aref_mode = aref_mode
    base.cd = round(cd, 5)
    base.cl = round(cl, 5) if cl is not None else None
    base.ld = round(cl / cd, 2) if (cl is not None and cd) else None
    base.cda_m2 = round(cd * aref, 6)
    base.drag_N = round(cd * aref * q_dyn, 3)
    base.mesh = meshq
    base.convergence = conv

    # Far-field iz-momentum Cd (2.-mertebe). Tek mesh'te yüzey-Cd ile UYUŞMASI yakınsama
    # göstergesi (3-mesh GCI'nin ucuz vekili); AYRIŞMASI az-çözünürlük flag'i.
    cd_wake = None
    try:
        from farfield_drag import compute_case_wake_drag
        w = compute_case_wake_drag(case_dir, U_inf=velocity, A_ref=aref, rho=rho)
        if w and w.get("Cd") is not None:
            cd_wake = round(w["Cd"], 5)
            base.cd_wake = cd_wake
    except Exception:
        pass

    uyarilar = []
    if cd_wake is not None and cd:
        fark = abs(cd - cd_wake) / abs(cd) * 100
        if fark > 12:
            uyarilar.append(f"Yüzey-Cd ({cd:.3f}) ile iz-momentum Cd ({cd_wake:.3f}) "
                            f"%{fark:.0f} ayrışıyor → mesh az-çözünür/yakınsamamış olabilir "
                            "(çapraz-kontrol; uyum yakınsama göstergesi)")
    if compressible:
        uyarilar.append(f"Mach {mach:.2f} > 0.3 — DENEYSEL sıkışabilir çözücü "
                        "(soğuk-başlangıç kararlılığı tuning gerektirir)")
    elif mach > 0.3:
        uyarilar.append(f"Mach {mach:.2f} > 0.3 — sıkıştırılamaz çözücü varsayımı "
                        "İHLAL; Cd sistematik hatalı. Sıkışabilir yol deneysel "
                        "(CFD_COMPRESSIBLE=1 ile açılır, kararlılık garantisiz)")
    if not geo["su_gecirmez"]:
        uyarilar.append("STL su geçirmez değil — snappyHexMesh toleranslı ama "
                        "kapalı yüzey önerilir")
    thin = geo.get("ince_kalinlik_m") or min(geo["boyutlar_m"])
    rw = resolution_warning(geo["lmax_m"], q["bg_div"], case.refinement_max, thin)
    if rw:
        uyarilar.append(rw)
    # Mesh-kalite uyarısı (reject zaten run_cfd'de elendi; warn-seviyesini yüzeye çıkar)
    no_max, sk_max = meshq.get("non_ortho_max"), meshq.get("skew_max")
    if no_max is not None and no_max > NONORTHO_LIMIT:
        uyarilar.append(f"Mesh non-ortogonallik {no_max:.0f}° > {NONORTHO_LIMIT:.0f} eşiği "
                        "— gradyan/Cd doğruluğu sınırda (mesh iyileştir)")
    if sk_max is not None and sk_max > SKEW_LIMIT:
        uyarilar.append(f"Mesh skewness {sk_max:.1f} > {SKEW_LIMIT:.0f} eşiği "
                        "— yerel hata kaynağı (mesh iyileştir)")
    if prop:
        base.pervane = prop
        if prop.get("uyari"):
            uyarilar.append(prop["uyari"])

    if progress_cb:
        progress_cb(78, "y+ olcumu...")
    yp = measure_yplus(case_dir)
    base.sinir_tabaka = {"katman_sayisi": n_layers, "yplus": yp,
                         "yplus_hedef": yplus_target if n_layers > 0 else None,
                         "ilk_katman_m": (round(case.first_layer_thickness, 8)
                                          if case.first_layer_thickness else None)}
    if progress_cb:
        progress_cb(82, "Yuzey basinc alani cikariliyor...")
    vtk_path = export_surface_vtk(case_dir, Path(stl_path).stem.replace(" ", "_"))
    base.cp_vtk = str(vtk_path) if vtk_path else ""
    bb = trimesh.load(str(stl_path), force="mesh").bounds
    center = [(bb[0][i] + bb[1][i]) / 2 for i in range(3)]
    kesit = export_cutplane_vtk(case_dir, center)
    base.kesit_vtk = str(kesit) if kesit else ""
    if yp and yp["ort"] > 30 and n_layers == 0:
        uyarilar.append(f"Ölçülen y⁺ ort={yp['ort']} (log bölgesi üstü) — sürtünme "
                        "sürüklemesi duvar fonksiyonu sınırında; katman sayısını artırın")
    base.uyarilar = uyarilar

    # Opsiyonel mesh duyarlılık kontrolü: ayni analiz kaba seviyede, fark = belirsizlik bandi
    if mesh_sensitivity:
        if progress_cb:
            progress_cb(80, "Mesh duyarlılık koşusu (kaba seviye)…")
        coarse = CFDCase(
            name=f"{stem}_kaba", stl_path=stl_path, velocity=velocity,
            flow_direction=(math.cos(a), 0.0, math.sin(a)), rho=rho,
            domain_upstream=_dom[0],
            domain_downstream=_dom[1],
            domain_lateral=_dom[2],
            refinement_min=max(1, rmin + bump - 1),
            refinement_max=max(1, rmax + bump - 1),
            end_time=MESH_QUALITY["hizli"]["end_time"],
            max_global_cells=q["max_cells"],
            bg_cell_size=geo["lmax_m"] / max(3, q["bg_div"] - 2),
            n_processors=n_processors,
        )
        res2 = run_cfd(coarse, run_dir, progress_callback=None)
        if res2.success and res2.cd is not None:
            cd2 = res2.cd * scale
            delta_pct = abs(cd - cd2) / (abs(cd) + 1e-12) * 100
            base.mesh_duyarlilik = {
                "kaba_cd": round(cd2, 5),
                "fark_pct": round(delta_pct, 1),
                "yorum": ("iki-seviye farkı sayısal belirsizlik bandı olarak kullanılır; "
                          "GCI yerine geçmez ama tek-mesh iddiasını niceler"),
            }
        else:
            base.mesh_duyarlilik = {"durum": "kaba koşu başarısız — bant hesaplanamadı"}

    (run_dir / "sonuc.json").write_text(json.dumps(asdict(base), indent=2, ensure_ascii=False), encoding="utf-8")

    from vehicle_report import build_vehicle_report
    report_path = build_vehicle_report(base, history, residuals, run_dir / "rapor")
    base.report = str(report_path)
    (run_dir / "sonuc.json").write_text(json.dumps(asdict(base), indent=2, ensure_ascii=False), encoding="utf-8")
    return base


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Katı model → CFD → mühendis raporu")
    ap.add_argument("model", help="STL/OBJ/STEP/IGES dosyası")
    ap.add_argument("--tip", default="ucak", choices=list(VEHICLE_PRESETS))
    ap.add_argument("--hiz", type=float, default=30.0, help="m/s")
    ap.add_argument("--aoa", type=float, default=0.0, help="hücum açısı (derece)")
    ap.add_argument("--kalite", default="standart", choices=list(MESH_QUALITY))
    ap.add_argument("--islemci", type=int, default=0, help="0 = otomatik")
    ap.add_argument("--burun", default="+x", choices=list(AXIS_VECTORS),
                    help="modelin burun/akış ekseni")
    ap.add_argument("--ust", default="+z", choices=list(AXIS_VECTORS),
                    help="modelin üst ekseni")
    ap.add_argument("--duyarlilik", action="store_true",
                    help="ikinci (kaba) koşuyla mesh duyarlılık bandı hesapla")
    ap.add_argument("--katman", type=int, default=0,
                    help="prizma sınır-tabaka katman sayısı (0=kapalı)")
    ap.add_argument("--yplus", type=float, default=30.0,
                    help="hedef y+ (ilk katman kalınlığı buna göre hesaplanır)")
    ap.add_argument("--itki", type=float, default=0.0,
                    help="pervane itkisi (N) — aktüatör disk modeli")
    ap.add_argument("--cap", type=float, default=0.0,
                    help="pervane çapı (m)")
    args = ap.parse_args()

    def _cb(pct, msg):
        print(f"[{pct:3d}%] {msg}", flush=True)

    r = run_vehicle_analysis(args.model, args.tip, args.hiz, args.aoa,
                             args.kalite, n_processors=args.islemci,
                             nose_axis=args.burun, up_axis=args.ust,
                             mesh_sensitivity=args.duyarlilik, n_layers=args.katman,
                             yplus_target=args.yplus,
                             pervane_itki_n=args.itki, pervane_cap_m=args.cap,
                             progress_cb=_cb)
    if r.status == "ok":
        print(f"\nCd={r.cd}  CdA={r.cda_m2} m²  Drag={r.drag_N} N"
              + (f"  Cl={r.cl}  L/D={r.ld}" if r.cl is not None else ""))
        print(f"Rapor: {r.report}")
    else:
        print(f"\nBASARISIZ — {r.case_dir}\n{r.error[-500:]}")
