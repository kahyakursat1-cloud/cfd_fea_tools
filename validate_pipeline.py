"""Pipeline validasyon koşusu: bilinen-doğru çapaları (validation_anchors.ANCHORS)
run_vehicle_analysis'ten geçirip ÖLÇÜLEN hata bandını üretir → validation_band.json.
Bu dosya yazıldığında model_uncertainty_pct literatür-öncülü bırakıp ölçülen bandı kullanır.

CFD GEREKTİRİR (her çapa 3-mesh GCI ile dakikalar). Koşu meşgulken çalıştırma.
Kullanım: python validate_pipeline.py [--hiz 30] [--anchor sphere]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from validation_anchors import _BAND_FILE, ANCHORS  # noqa: E402
from vehicle_pipeline import run_vehicle_analysis  # noqa: E402

# çapa → (geometri üreteci, pipeline araç-tipi). NACA0012 2B → TMR yolu kapsar (atlanır).
_GEOM = {
    "sphere": (lambda: trimesh.creation.icosphere(subdivisions=4, radius=0.05), "genel"),
}


def _run_anchor(name: str, velocity: float, out_root: str) -> dict | None:
    spec = ANCHORS[name]
    if name not in _GEOM:
        return {"atlandi": "geometri üreteci yok (ör. 2B airfoil → TMR yolu)"}
    gen, vtype = _GEOM[name]
    stl = HERE / out_root / f"_anchor_{name}.stl"
    stl.parent.mkdir(parents=True, exist_ok=True)
    gen().export(stl)
    r = run_vehicle_analysis(str(stl), vehicle_type=vtype, velocity=velocity,
                             quality="hassas", mesh_sensitivity=True, out_root=out_root)
    if r.status != "ok" or r.cd is None:
        return {"durum": "koşu başarısız", "hata": r.error[:300]}
    cd_pred = r.cd_richardson or r.cd
    err = abs(cd_pred - spec["Cd"]) / spec["Cd"] * 100
    return {"regime": spec["regime"], "Cd_ref": spec["Cd"], "Cd_pipeline": round(cd_pred, 5),
            "hata_pct": round(err, 2), "u_sayisal_pct": (r.belirsizlik or {}).get("u_sayisal_pct"),
            "kaynak_ref": spec["ref"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hiz", type=float, default=30.0)
    ap.add_argument("--anchor", default="all")
    ap.add_argument("--out", default="validation_anchors_runs")
    args = ap.parse_args()
    names = list(ANCHORS) if args.anchor == "all" else [args.anchor]
    results = {n: _run_anchor(n, args.hiz, args.out) for n in names}

    # rejim-başına en kötü ölçülen hatayı duvar-çözünür band olarak yaz (muhafazakâr)
    by_regime = defaultdict(list)
    for n, res in results.items():
        if res and res.get("hata_pct") is not None:
            by_regime[res["regime"]].append(res["hata_pct"])
    band = {}
    if _BAND_FILE.exists():
        try:
            band = json.loads(_BAND_FILE.read_text(encoding="utf-8"))
        except Exception:
            band = {}
    for regime, errs in by_regime.items():
        band.setdefault(regime, {})["wall_resolved"] = round(max(errs), 2)
    if by_regime:
        _BAND_FILE.write_text(json.dumps(band, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"sonuclar": results, "yazilan_band": band}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
