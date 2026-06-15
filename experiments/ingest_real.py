"""Gerçek-dünya CAD modellerini (internetten indirilen STL) otopilot
sınıflandırıcısıyla test eder = GENELLEME TESTİ.

Her model bilinen sınıfa göre uçuş-konvansiyonuna kanonikleştirilir
(rastgele yönelimi düzeltir), sonra mevcut kütüphaneyle sınıflandırılır.
Uyum oranı raporlanır; temiz/belirgin olanlar kütüphaneye eklenebilir.
"""
import json
import os
import sys
import tempfile
import warnings

import numpy as np
import trimesh

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import auto_pilot as ap  # noqa: E402
from vehicle_pipeline import inspect_geometry  # noqa: E402

GEO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "real_geo")
TMP = tempfile.mkdtemp()


def _canonical(mesh, mode):
    """Uçuş-konvansiyonuna yönlendir: z=en ince eksen; eksenel→x=en uzun,
    kanat→y=en uzun (açıklık). Sentetik seed konvansiyonuyla eşleşir."""
    m = mesh.copy()
    m.apply_translation(-m.centroid)
    ext = m.extents
    order = np.argsort(ext)            # küçük→büyük eksen indeksleri
    if mode == "wing":                 # x=orta(kiriş), y=büyük(açıklık), z=küçük
        perm = [order[1], order[2], order[0]]
    else:                              # axial: x=büyük(boy), y=orta, z=küçük
        perm = [order[2], order[1], order[0]]
    V = m.vertices[:, perm]
    return trimesh.Trimesh(vertices=V, faces=m.faces, process=False)


def _assemble(parts):
    ms = [trimesh.load(os.path.join(GEO, p), force="mesh") for p in parts]
    return trimesh.util.concatenate(ms)


# (ad, bilinen_tip, yönelim_modu, [parça dosyaları]) — parça>1 ise birleştir
MANIFEST = [
    ("rocket_tvc",   "roket",        "axial", ["rocket_tvc.stl"]),
    ("x15_rocketplane", "kanatli_roket", "axial", ["x15.stl"]),
    ("minihawk_vtol", "kanatli_vtol", "wing", ["minihawk_vtol.stl"]),
    ("su57_fighter", "ucak", "wing", ["su57.stl"]),
    ("f16_fighter",  "ucak", "wing",
     [f"f16_{p}.stl" for p in ("Aileron_A_F16", "Aileron_B_F16", "Body_F16",
      "Cockpit_F16", "LE_Slat_A_F16", "LE_Slat_B_F16", "Rudder_F16",
      "Stabilator_A_F16", "Stabilator_B_F16")]),
    ("a320_airliner", "ucak", "wing",
     [f"a320_{p}.stl" for p in ("Aileron_L_A320", "Aileron_R_A320", "Body_A320",
      "Elevator_L_A320", "Elevator_R_A320", "Engine_L_A320", "Engine_R_A320",
      "Rudder_A320")]),
    ("gripen_fighter", "ucak", "wing",
     [f"gripen_{p}.stl" for p in ("AB_Left", "AB_Right", "Body", "Canopy",
      "Canopy_Front", "Canopy_Rear", "Elevon_Left", "Elevon_Right", "FP_Left",
      "FP_Right", "LE_Left", "LE_Right", "Rudder")]),
]


def run():
    rows = []
    for name, known, mode, parts in MANIFEST:
        mesh = _assemble(parts)
        mesh = _canonical(mesh, mode)
        p = os.path.join(TMP, name + ".stl")
        mesh.export(p)
        geo = inspect_geometry(p)
        res = ap.classify_vehicle(geo)
        ok = res["tip"] == known
        rows.append({"ad": name, "bilinen": known, "tahmin": res["tip"],
                     "guven": res["guven"], "uyum": ok, "metrik": res["metrik"],
                     "ext": [round(float(e), 3) for e in mesh.extents],
                     "faces": int(len(mesh.faces))})
    return rows


if __name__ == "__main__":
    rows = run()
    n_ok = sum(r["uyum"] for r in rows)
    print(f"{'model':18s} {'bilinen':15s} {'tahmin':15s} guven uyum  ext / L_D,W_L,H_L,H_W")
    for r in rows:
        m = r["metrik"]
        flag = "OK " if r["uyum"] else "X  "
        print(f"{r['ad']:18s} {r['bilinen']:15s} {r['tahmin']:15s} "
              f"{r['guven']:.2f}  {flag} {r['ext']} / "
              f"{m['L_D']},{m['W_L']},{m['H_L']},{m['H_W']}")
    print(f"\nGenelleme (gercek-dunya): {n_ok}/{len(rows)} uyum")
    json.dump(rows, open(os.path.join(GEO, "_results.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # real_seed.jsonl: gerçek modellerin metriklerini hakem-etiketiyle yaz
    # (sadece türetilen 6 sayı; STL'ler üçüncü-taraf/lisanslı → commit edilmez)
    real = os.path.join(os.path.dirname(GEO), "..", "auto_pilot_real_seed.jsonl")
    real = os.path.normpath(real)
    with open(real, "w", encoding="utf-8") as fh:
        for r, (name, known, _m, _p) in zip(rows, MANIFEST):
            c = {"ts": "real", "kaynak": f"internet-CAD (hakem-etiket): {name}",
                 "metrik": r["metrik"], "onayli_tip": known, "otopilot_tip": r["tahmin"],
                 "dosya": f"real:{name}", "cd_toplam": None, "rejim": None}
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"real_seed yazıldı: {real}")
