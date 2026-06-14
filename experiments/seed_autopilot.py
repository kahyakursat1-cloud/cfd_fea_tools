"""Otopilot öğrenme kütüphanesi tohumlayıcı — uzman(hakem)-etiketli kanonik
geometriler üretir, metriklerini çıkarır ve auto_pilot_seed.jsonl'a yazar.
Çalıştır: python experiments/seed_autopilot.py
Reprodüsibl: aynı şekiller → aynı seed. Etiketler kanonik şekiller için kesin.
"""
import json
import os
import sys
import tempfile

import numpy as np
import trimesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import auto_pilot as ap  # noqa: E402
from vehicle_pipeline import inspect_geometry  # noqa: E402

TMP = tempfile.mkdtemp()


def _x_axis(m):
    """uzun ekseni +x yap (silindir/koni z'de üretilir)."""
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    return m


def _metrik(mesh, name):
    p = os.path.join(TMP, f"{name}.stl")
    mesh.export(p)
    return ap.classify_vehicle(inspect_geometry(p))["metrik"]


def _fins(body, r, x_tail, span, n=4):
    """gövdeye kuyruk kanatçıkları ekle (ince kutular), tek mesh döndür."""
    parts = [body]
    for k in range(n):
        a = 2 * np.pi * k / n
        fin = trimesh.creation.box(extents=(0.12 * span, 0.01, span))
        fin.apply_transform(trimesh.transformations.rotation_matrix(a, [1, 0, 0]))
        fin.apply_translation((x_tail, 0, 0))
        parts.append(fin)
    return trimesh.util.concatenate(parts)


def _rotor(arm, n=4, arm_w=0.07):
    """n-kollu multikopter (merkez + ayrık kollar)."""
    parts = [trimesh.creation.box(extents=(0.14, 0.14, 0.10))]
    for k in range(n):
        a = 2 * np.pi * k / n
        b = trimesh.creation.box(extents=(arm_w, arm_w, 0.05))
        b.apply_translation((arm * np.cos(a), arm * np.sin(a), 0))
        parts.append(b)
    return trimesh.util.concatenate(parts)


cases = []


def add(mesh, name, tip):
    cases.append({"ts": "seed", "kaynak": "uzman-etiket (hakem)",
                  "metrik": _metrik(mesh, name), "onayli_tip": tip,
                  "otopilot_tip": tip, "dosya": f"seed:{name}",
                  "cd_toplam": None, "rejim": None})


# ── ROKET: ince, yuvarlak kesit; çeşitli L/D, burun, kanatçık, boattail ──────
add(_x_axis(trimesh.creation.cylinder(radius=0.06, height=1.0)), "rok_LD8", "roket")
add(_x_axis(trimesh.creation.cylinder(radius=0.05, height=1.6)), "rok_LD16", "roket")
add(_x_axis(trimesh.creation.cylinder(radius=0.08, height=2.7)), "rok_LD17", "roket")
add(_x_axis(trimesh.creation.cylinder(radius=0.04, height=1.8)), "rok_LD22", "roket")
add(_x_axis(trimesh.creation.cone(radius=0.10, height=1.4)), "rok_koni", "roket")
add(_x_axis(trimesh.creation.capsule(radius=0.06, height=1.4)), "rok_ogive", "roket")
add(_x_axis(trimesh.creation.box(extents=(0.12, 0.12, 2.0)).apply_translation((0, 0, 0))),
    "rok_kare", "roket")
add(_fins(_x_axis(trimesh.creation.cylinder(radius=0.06, height=1.5)), 0.06, -0.6, 0.10),
    "rok_finli1", "roket")
add(_fins(_x_axis(trimesh.creation.cylinder(radius=0.07, height=2.0)), 0.07, -0.85, 0.13),
    "rok_finli2", "roket")
# boattail: gövde + daralan kuyruk koni
_bt = trimesh.util.concatenate([
    _x_axis(trimesh.creation.cylinder(radius=0.07, height=1.5)),
    _x_axis(trimesh.creation.cone(radius=0.07, height=0.25)).apply_translation((0.85, 0, 0))])
add(_bt, "rok_boattail", "roket")

# ── UÇAK/KANAT: yassı (H küçük), geniş; dikdörtgen/sivri/delta/süpürme/gövdeli ─
add(trimesh.creation.box(extents=(0.9, 1.8, 0.06)), "uca_AR2", "ucak")
add(trimesh.creation.box(extents=(0.5, 2.0, 0.05)), "uca_AR4", "ucak")
add(trimesh.creation.box(extents=(0.4, 2.4, 0.04)), "uca_AR6", "ucak")
add(trimesh.creation.box(extents=(1.1, 2.2, 0.07)), "uca_genis", "ucak")
# delta (üçgen prizma, yassı) — shapeysiz, elle vertex/yüz
_dv = np.array([[0, 0, -.025], [1.6, .8, -.025], [1.6, -.8, -.025],
                [0, 0, .025], [1.6, .8, .025], [1.6, -.8, .025]])
_df = [[0, 2, 1], [3, 4, 5], [0, 1, 4], [0, 4, 3], [1, 2, 5], [1, 5, 4],
       [2, 0, 3], [2, 3, 5]]
add(trimesh.Trimesh(vertices=_dv, faces=_df), "uca_delta", "ucak")
# kanat + gövde: geniş yassı plaka + ince eksenel gövde
_wb = trimesh.util.concatenate([
    trimesh.creation.box(extents=(0.6, 2.0, 0.05)),
    _x_axis(trimesh.creation.cylinder(radius=0.06, height=1.2))])
add(_wb, "uca_govdeli", "ucak")
# süpürme kanat (paralelkenar yassı)
_sw = trimesh.creation.box(extents=(0.7, 1.8, 0.05))
_sw.apply_transform(trimesh.transformations.rotation_matrix(np.deg2rad(20), [0, 0, 1]))
add(_sw, "uca_supurme", "ucak")
# 2. delta (daha keskin) — düşük-açıklıklı kanat kümesini güçlendir (W/L~1)
_dv2 = np.array([[0, 0, -.02], [1.4, .6, -.02], [1.4, -.6, -.02],
                 [0, 0, .02], [1.4, .6, .02], [1.4, -.6, .02]])
add(trimesh.Trimesh(vertices=_dv2, faces=_df), "uca_delta2", "ucak")
# düşük-açıklık trapez kanat (yassı, W/L~1.3)
add(trimesh.creation.box(extents=(1.0, 1.3, 0.05)), "uca_trapez", "ucak")

# ── MULTIKOPTER: kompakt + çok kollu (quad/hexa/octo, X ve +) ────────────────
add(_rotor(0.25, 4), "mlt_quad1", "multikopter")
add(_rotor(0.30, 4), "mlt_quad2", "multikopter")
add(_rotor(0.22, 4, arm_w=0.05), "mlt_quad_ince", "multikopter")
add(_rotor(0.28, 6), "mlt_hexa", "multikopter")
add(_rotor(0.32, 8), "mlt_octo", "multikopter")

# ── GENEL: küt/bluff (küre/küp/elipsoid/kısa silindir) ───────────────────────
add(trimesh.creation.box(extents=(0.5, 0.5, 0.5)), "gen_kup", "genel")
add(trimesh.creation.icosphere(subdivisions=3, radius=0.25), "gen_kure", "genel")
add(trimesh.creation.cylinder(radius=0.20, height=0.30), "gen_silindir", "genel")
_elip = trimesh.creation.icosphere(subdivisions=3, radius=0.25)
_elip.apply_scale([1.8, 1.0, 1.0])           # prolat ama L/D~1.8 (slender değil)
add(_elip, "gen_elipsoid", "genel")
add(trimesh.creation.box(extents=(0.6, 0.5, 0.4)), "gen_kutu", "genel")

ap.SEED.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n",
                   encoding="utf-8")
from collections import Counter  # noqa: E402

print(f"SEED yazıldı: {len(cases)} vaka, dağılım:",
      dict(Counter(c["onayli_tip"] for c in cases)))
