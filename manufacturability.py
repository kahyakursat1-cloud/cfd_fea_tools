"""3D-baskı üretilebilirlik değerlendirmesi (FDM/SLA destek-yapısız basılabilirlik).

TO sonucu (ya da herhangi bir tasarım STL'i) basılabilir mi? Bu modül ENFORCE etmez,
DEĞERLENDİRİR + DANIŞMANLIK eder (mesh_quality_gate / _stress_assessment ile aynı felsefe):
  • Overhang: build-yönüne göre destek gereken aşağı-bakan yüzey alanı oranı (45° kriteri).
  • Yön önerisi: 6 eksen-yönünden overhang'i en azaltanı.
  • Min-üye: TO duyarlılık-filtresi yarıçapı rmin, nozzle-basılabilir eşikle karşılaştırılır.

Overhang kriteri (standart): yukarı build-yönü b için, dışa-normali n olan sınır yüzeyi,
n·b < −cos(α_krit) ise (aşağı-bakan ve yataya α_krit'ten sığ) DESTEK ister. Build-plakasına
oturan en-alt yüzeyler (plaka desteği) hariç tutulur. α_krit=45° (FDM tipik).
"""
from __future__ import annotations

import numpy as np

# Yukarı build-yönü adayları (parça bu yönde katman-katman büyür)
BUILD_AXES = {"+z": (0, 0, 1.0), "-z": (0, 0, -1.0), "+x": (1.0, 0, 0),
              "-x": (-1.0, 0, 0), "+y": (0, 1.0, 0), "-y": (0, -1.0, 0)}


def _overhang_area_frac(normals, areas, centroids, build_dir,
                        crit_deg: float = 45.0, plate_tol_frac: float = 0.02) -> float:
    """Destek gerektiren aşağı-bakan yüzey alanının toplam yüzey alanına oranı.
    build_dir: yukarı build-yönü. Build-plakasına oturan en-alt yüzeyler hariç."""
    n = np.asarray(normals, float)
    a = np.asarray(areas, float)
    c = np.asarray(centroids, float)
    if len(a) == 0 or a.sum() <= 0:
        return 0.0
    b = np.asarray(build_dir, float)
    b = b / (np.linalg.norm(b) + 1e-30)
    ndotb = n @ b
    proj = c @ b                                   # build-ekseni boyunca yükseklik
    span = float(proj.max() - proj.min()) or 1.0
    on_plate = proj < proj.min() + plate_tol_frac * span   # plakaya oturanlar
    thr = -np.cos(np.radians(crit_deg))            # aşağı-bakan & sığ
    viol = (ndotb < thr) & ~on_plate
    return float(a[viol].sum() / a.sum())


def overhang_fraction(mesh, build_dir, crit_deg: float = 45.0) -> float:
    return _overhang_area_frac(mesh.face_normals, mesh.area_faces,
                               mesh.triangles_center, build_dir, crit_deg)


def recommend_orientation(mesh, crit_deg: float = 45.0) -> tuple[str, dict]:
    """6 eksen-yönünü tara, overhang alanını en azaltan build-yönünü döndür."""
    scores = {k: overhang_fraction(mesh, v, crit_deg) for k, v in BUILD_AXES.items()}
    best = min(scores, key=lambda k: scores[k])
    return best, {k: round(v, 4) for k, v in scores.items()}


def assess_manufacturability(mesh, rmin_m: float | None = None,
                             build_dir: str | None = None, crit_deg: float = 45.0,
                             nozzle_m: float = 4e-4, wall_mult: float = 2.0) -> dict:
    """Tasarım STL'i için üretilebilirlik özeti + verdict.

    mesh: trimesh.Trimesh (kapalı tasarım yüzeyi)
    rmin_m: TO duyarlılık-filtresi yarıçapı (min-üye ölçeği); None → atla
    build_dir: sabit build-yönü ("+z" vb.); None → en-iyi öneri kullanılır
    """
    best, scores = recommend_orientation(mesh, crit_deg)
    used = build_dir if build_dir in BUILD_AXES else best
    oh = scores[used]
    oh_verdict = ("✅ destek-yapısız basılabilir" if oh < 0.05 else
                  "⚠️ az destek gerek" if oh < 0.20 else
                  "❌ çok destek / yeniden yönlendir")

    out = {
        "overhang_orani": round(oh, 4),
        "build_yonu": used,
        "onerilen_yon": best,
        "yon_skorlari": scores,
        "overhang_verdict": oh_verdict,
        "kritik_aci_deg": crit_deg,
    }
    if build_dir and build_dir != best and scores[best] < oh - 0.02:
        out["yon_tavsiyesi"] = (f"'{best}' yönü overhang'i %{oh*100:.0f}→"
                                f"%{scores[best]*100:.0f} düşürür")

    if rmin_m is not None:
        min_print = wall_mult * nozzle_m
        feat_ok = rmin_m >= min_print
        out["min_uye_mm"] = round(rmin_m * 1e3, 3)
        out["min_basilabilir_mm"] = round(min_print * 1e3, 3)
        out["min_uye_verdict"] = (
            "✅ üye ölçeği basılabilir" if feat_ok else
            f"⚠️ ince üye: rmin {rmin_m*1e3:.2f}mm < {min_print*1e3:.2f}mm "
            f"(nozzle {nozzle_m*1e3:.1f}mm × {wall_mult:.0f}) — filtre yarıçapını büyüt")

    return out


if __name__ == "__main__":
    import sys

    import trimesh
    if len(sys.argv) < 2:
        print("Kullanım: python manufacturability.py <tasarim.stl> [rmin_mm]")
        sys.exit(1)
    m = trimesh.load(sys.argv[1], force="mesh")
    rmin = float(sys.argv[2]) / 1e3 if len(sys.argv) > 2 else None
    res = assess_manufacturability(m, rmin_m=rmin)
    for k, v in res.items():
        print(f"  {k}: {v}")
