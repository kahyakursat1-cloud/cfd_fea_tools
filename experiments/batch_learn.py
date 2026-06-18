"""Toplu öğrenme kampanyası — çeşitli ETİKETLİ geometrileri otopilot akışıyla koşar,
record_case ile öğrenme kütüphanesini büyütür. Sentetik geometrilerin GERÇEK tipi bilinir
→ onayli_tip=ground-truth → temiz etiketli eğitim verisi (sınıflandırıcı yanlışsa bile öğrenir).

Akış/geometri: roket (dönel gövde, L/D 5–14), uçak (geniş ince kanat), multikopter (merkez+kol),
genel (küre/elipsoid/küt). Her geo: inspect → classify → CFD(hizli) → record_case. Robust
(geo başına try/except), devam-edebilir (yapılmışları atlar), ilerleme dosyaya.
Kullanım: python experiments/batch_learn.py [n_per_class]
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from auto_pilot import classify_vehicle, record_case  # noqa: E402
from vehicle_pipeline import inspect_geometry, prepare_geometry, run_vehicle_analysis  # noqa: E402

GEN_DIR = HERE.parent / "vehicle_runs" / "_batch_geo"
LOG = HERE.parent / "batch_learn.log"
DONE = HERE.parent / "batch_learn_done.json"


# ─────────── geometri üreticileri (gerçek tip etiketli) ───────────

def _revolve(profile, sections=64):
    """2B (yarıçap, eksen) profilini dönel katı yap (watertight)."""
    m = trimesh.creation.revolve(np.asarray(profile, float), sections=sections)
    m.merge_vertices(); m.fix_normals()
    return m


def gen_roket(L_D, nose_frac, R=0.04):
    L = L_D * 2 * R; Ln = nose_frac * L
    prof = [[0, 0], [R, 0], [R, L - Ln], [0, L]]      # kuyruk→silindir→konik burun
    return _revolve(prof), "roket"


def gen_kanatli_roket(L_D, R=0.04):
    body, _ = gen_roket(L_D, 0.25, R)
    fins = []
    for ang in (0, 90, 180, 270):
        f = trimesh.creation.box((R * 2.5, R * 0.15, L_D * 2 * R * 0.18))
        f.apply_translation((R * 0.9, 0, L_D * 2 * R * 0.09))
        f.apply_transform(trimesh.transformations.rotation_matrix(np.radians(ang), [0, 0, 1]))
        fins.append(f)
    return trimesh.util.concatenate([body, *fins]), "kanatli_roket"


def gen_ucak(span_frac, L=0.6):
    # ince fuzelaj + geniş kanat + kuyruk → uçak imzası (span_ratio≥0.35, ince-yassı)
    R = L * 0.045
    fus = trimesh.creation.cylinder(radius=R, height=L * 0.9)
    fus.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    span = span_frac * L
    wing = trimesh.creation.box((L * 0.16, span, L * 0.018))
    wing.apply_translation((L * 0.05, 0, 0))
    tail = trimesh.creation.box((L * 0.10, span * 0.4, L * 0.016))
    tail.apply_translation((-L * 0.4, 0, 0))
    return trimesh.util.concatenate([fus, wing, tail]), "ucak"


def gen_multikopter(arm, R=0.03):
    parts = [trimesh.creation.box((R * 2, R * 2, R * 1.2))]
    for ang in (45, 135, 225, 315):
        a = trimesh.creation.cylinder(radius=R * 0.25, height=arm)
        a.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        a.apply_translation((arm / 2, 0, 0))
        a.apply_transform(trimesh.transformations.rotation_matrix(np.radians(ang), [0, 0, 1]))
        parts.append(a)
    return trimesh.util.concatenate(parts), "multikopter"


def gen_genel(kind, S=0.2):
    if kind == "kure":
        return trimesh.creation.icosphere(subdivisions=3, radius=S / 2), "genel"
    if kind == "elipsoid":
        prof = [[0, 0]] + [[S / 2 * np.sin(t), S * (1 - np.cos(t)) / 2]
                           for t in np.linspace(0.01, np.pi - 0.01, 20)] + [[0, S]]
        return _revolve(prof), "genel"
    return trimesh.creation.box((S, S * 0.8, S * 0.7)), "genel"   # küt kutu


def build_catalog(n_per_class):
    """Etiketli geometri kataloğu (parametrik tarama)."""
    cat = []
    for ld in np.linspace(5, 14, n_per_class):
        cat.append((f"roket_LD{ld:.0f}", *gen_roket(ld, 0.3)))
    for ld in np.linspace(6, 12, max(2, n_per_class // 2)):
        cat.append((f"kanatliroket_LD{ld:.0f}", *gen_kanatli_roket(ld)))
    for sf in np.linspace(0.5, 0.95, n_per_class):
        cat.append((f"ucak_sf{sf*100:.0f}", *gen_ucak(sf)))
    for arm in np.linspace(0.18, 0.40, max(2, n_per_class // 2)):
        cat.append((f"multikopter_{arm*100:.0f}", *gen_multikopter(arm)))
    for i, k in enumerate(["kure", "elipsoid", "kut"] * n_per_class):
        if i >= n_per_class:
            break
        cat.append((f"genel_{k}{i}", *gen_genel(k)))
    return cat


def main():
    n_per = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    done = set(json.loads(DONE.read_text())) if DONE.exists() else set()

    def log(m):
        line = f"[{time.strftime('%H:%M:%S')}] {m}"
        print(line, flush=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    catalog = build_catalog(n_per)
    log(f"=== Toplu öğrenme: {len(catalog)} geometri (yapılmış: {len(done)}) ===")
    t0 = time.time(); ok = 0; dogru = 0
    for name, mesh, true_tip in catalog:
        if name in done:
            continue
        try:
            stl = GEN_DIR / f"{name}.stl"
            mesh.export(str(stl))
            prep, _ = prepare_geometry(stl, GEN_DIR / name)
            geo = inspect_geometry(prep)
            cls = classify_vehicle(geo)
            log(f"{name}: tip→{cls['tip']} (gerçek {true_tip}, güven {cls['guven']})")
            res = run_vehicle_analysis(prep, vehicle_type=cls["tip"], velocity=30.0,
                                       quality="hizli", out_root=str(GEN_DIR))
            drift = (res.convergence or {}).get("drift_pct")
            gate = record_case(cls["metrik"], cls["tip"], true_tip,
                               {"Cd_toplam": res.cd, "rejim": _regime(true_tip),
                                "Cd_drift_pct": drift}, dosya=f"batch:{name}")
            ok += 1
            dogru += int(cls["tip"] == true_tip)
            log(f"  → Cd={res.cd} güvenilir={gate['cd_guvenilir']} "
                f"({(time.time()-t0)/60:.0f} dk, {ok} tamam)")
            done.add(name); DONE.write_text(json.dumps(sorted(done)))
        except Exception as e:
            log(f"  !!! {name} BAŞARISIZ: {str(e)[:160]}")
    log(f"=== BİTTİ: {ok} koşu, sınıflandırma isabeti {dogru}/{ok} "
        f"({100*dogru/max(ok,1):.0f}%), {(time.time()-t0)/60:.0f} dk ===")
    return 0


def _regime(tip):
    return "supersonic" if tip in {"roket", "kanatli_roket", "kaldirici_govde"} else "subsonic"


if __name__ == "__main__":
    sys.exit(main())
