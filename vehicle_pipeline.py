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
import re
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
    m.process(validate=True)                    # tekil nokta birleştirme + dejenere üçgen temizliği
    if len(m.faces) != n_face0:
        info["onarimlar"].append(f"dejenere/yinelenen üçgen temizliği ({n_face0}→{len(m.faces)})")
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
    info["su_gecirmez_sonra"] = bool(m.is_watertight)

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
    }


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
    cl: float | None = None
    ld: float | None = None
    cda_m2: float | None = None
    drag_N: float | None = None
    mesh: dict | None = None
    convergence: dict | None = None
    uyarilar: list = None
    mesh_duyarlilik: dict | None = None
    case_dir: str = ""
    report: str = ""
    error: str = ""


def run_vehicle_analysis(stl_path, vehicle_type="ucak", velocity=30.0, alpha_deg=0.0,
                         quality="standart", out_root="vehicle_runs",
                         n_processors=0, rho=1.225,
                         nose_axis="+x", up_axis="+z",
                         mesh_sensitivity=False,
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
    case = CFDCase(
        name=stem,
        stl_path=stl_path,
        velocity=velocity,
        flow_direction=(math.cos(a), 0.0, math.sin(a)),
        rho=rho,
        domain_upstream=preset["domain"][0],
        domain_downstream=preset["domain"][1],
        domain_lateral=preset["domain"][2],
        refinement_min=max(1, rmin + bump),
        refinement_max=max(1, rmax + bump),
        end_time=q["end_time"],
        max_global_cells=q["max_cells"],
        bg_cell_size=geo["lmax_m"] / q["bg_div"],
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

    uyarilar = []
    mach = velocity / 340.0
    if mach > 0.3:
        uyarilar.append(f"Mach {mach:.2f} > 0.3 — sıkıştırılamaz çözücü varsayımı "
                        "ihlal; Cd sistematik hatalı olabilir (sıkışabilir çözücü gerekir)")
    if not geo["su_gecirmez"]:
        uyarilar.append("STL su geçirmez değil — snappyHexMesh toleranslı ama "
                        "kapalı yüzey önerilir")
    rw = resolution_warning(geo["lmax_m"], q["bg_div"], case.refinement_max,
                            min(geo["boyutlar_m"]))
    if rw:
        uyarilar.append(rw)
    base.uyarilar = uyarilar

    # Opsiyonel mesh duyarlılık kontrolü: ayni analiz kaba seviyede, fark = belirsizlik bandi
    if mesh_sensitivity:
        if progress_cb:
            progress_cb(80, "Mesh duyarlılık koşusu (kaba seviye)…")
        coarse = CFDCase(
            name=f"{stem}_kaba", stl_path=stl_path, velocity=velocity,
            flow_direction=(math.cos(a), 0.0, math.sin(a)), rho=rho,
            domain_upstream=preset["domain"][0],
            domain_downstream=preset["domain"][1],
            domain_lateral=preset["domain"][2],
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
    args = ap.parse_args()

    def _cb(pct, msg):
        print(f"[{pct:3d}%] {msg}", flush=True)

    r = run_vehicle_analysis(args.model, args.tip, args.hiz, args.aoa,
                             args.kalite, n_processors=args.islemci,
                             nose_axis=args.burun, up_axis=args.ust,
                             mesh_sensitivity=args.duyarlilik, progress_cb=_cb)
    if r.status == "ok":
        print(f"\nCd={r.cd}  CdA={r.cda_m2} m²  Drag={r.drag_N} N"
              + (f"  Cl={r.cl}  L/D={r.ld}" if r.cl is not None else ""))
        print(f"Rapor: {r.report}")
    else:
        print(f"\nBASARISIZ — {r.case_dir}\n{r.error[-500:]}")
