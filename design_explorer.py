"""Tasarım-alanı keşfi (MDAO/DOE): parametre uzayını örnekle → her noktayı değerlendir →
sırala + Pareto cephesi + rapor. Simcenter Motion-DOE muadili AMA her nokta bizim V&V/UQ
bandını taşır ("güven-nicelenmiş tasarım keşfi").

Ayırt edici: değerlendirici PLUGGABLE.
- evaluate_surrogate: kNN ön-kestirim (anında, CFD'siz ÖNİZLEME — güvenilmez prior, taramada işe yarar)
- evaluate_cfd: run_vehicle_analysis + mesh_sensitivity (DOĞRULANMIŞ, Cd±GCI bandlı, yavaş)

Engine evaluate_fn'den bağımsız → analitik mock ile CFD'siz test edilebilir.
CLI: python design_explorer.py --n 12 --mode surrogate
"""
from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent


@dataclass
class DesignPoint:
    params: dict
    objectives: dict           # {"cd": .., "ld": ..} (minimize edilir; maks için negatifle)
    uncertainty: dict = field(default_factory=dict)   # {"cd_pct": ..} V&V bandı
    source: str = ""           # "surrogate" | "cfd" | "mock"
    gecerli: bool = True
    not_: str = ""


def lhs_sample(space: dict, n: int, seed: int = 0) -> list[dict]:
    """Latin Hypercube örnekleme — grid'den daha iyi uzay-doldurma (saf-python, numpy opsiyonel)."""
    import random
    rng = random.Random(seed)
    keys = list(space)
    cols = []
    for k in keys:
        lo, hi = space[k]
        # her boyutu n dilime böl, dilim-içi rastgele, sonra karıştır (LHS)
        col = [lo + (i + rng.random()) * (hi - lo) / n for i in range(n)]
        rng.shuffle(col)
        cols.append(col)
    return [{k: cols[j][i] for j, k in enumerate(keys)} for i in range(n)]


def pareto_front(points: list[DesignPoint], objectives: list[str]) -> list[DesignPoint]:
    """Çok-amaçlı Pareto cephesi (hepsi minimize). Bir nokta, kendisini TÜM amaçlarda zayıf
    domine eden + en az birinde kesin domine eden başka nokta yoksa cephededir."""
    ok = [p for p in points if p.gecerli and all(o in p.objectives for o in objectives)]
    front = []
    for p in ok:
        dominated = False
        for q in ok:
            if q is p:
                continue
            le = all(q.objectives[o] <= p.objectives[o] for o in objectives)
            lt = any(q.objectives[o] < p.objectives[o] for o in objectives)
            if le and lt:
                dominated = True
                break
        if not dominated:
            front.append(p)
    return front


def explore(space: dict, evaluate_fn: Callable[[dict], DesignPoint], n: int,
            objectives: list[str], seed: int = 0) -> dict:
    """DOE çalıştır: örnekle → değerlendir → sırala (1. amaca göre) + Pareto. Sonuç sözlüğü döner."""
    samples = lhs_sample(space, n, seed)
    pts = [evaluate_fn(s) for s in samples]
    valid = [p for p in pts if p.gecerli]
    ranked = sorted(valid, key=lambda p: p.objectives.get(objectives[0], math.inf))
    front = pareto_front(valid, objectives) if len(objectives) > 1 else ranked[:1]
    return {
        "parametre_uzayi": {k: list(v) for k, v in space.items()},
        "n_ornek": n, "n_gecerli": len(valid), "amaclar": objectives,
        "en_iyi": _pt_dict(ranked[0]) if ranked else None,
        "pareto": [_pt_dict(p) for p in front],
        "tum_noktalar": [_pt_dict(p) for p in pts],
        "not": ("Surrogat modu = ÖNİZLEME (güvenilmez prior); mutlak karar için CFD modu "
                "(her nokta Cd±GCI bandlı). V&V bandı 'uncertainty' alanında."),
    }


def _pt_dict(p: DesignPoint) -> dict:
    return {"params": {k: round(v, 5) for k, v in p.params.items()},
            "objectives": {k: round(v, 5) for k, v in p.objectives.items()},
            "uncertainty": p.uncertainty, "source": p.source,
            "gecerli": p.gecerli, "not": p.not_}


# ───────────────── değerlendiriciler (pluggable) ─────────────────

def make_revolve_stl(params: dict, out: Path):
    """Örnek parametrik geometri: eksen-simetrik gövde (L/D ve burun-oranı). trimesh revolve."""
    import numpy as np
    import trimesh
    R = 0.04
    L_D = params["L_D"]; nose = params["nose_frac"]
    L = L_D * 2 * R; Ln = nose * L
    xs = np.linspace(0, Ln, 8)
    ogive = [[R * math.sqrt(max(1 - (x / Ln) ** 2, 0)), L - Ln + x] for x in xs]
    prof = [[0, 0], [R, 0], [R, L - Ln], *ogive]
    m = trimesh.creation.revolve(np.asarray(prof, float), sections=48)
    m.merge_vertices(); m.fix_normals()
    out.parent.mkdir(parents=True, exist_ok=True); m.export(out)
    return out


def evaluate_surrogate(params: dict) -> DesignPoint:
    """Hızlı önizleme: geometri → metrik → kNN cd_predict (CFD'siz, güvenilmez prior).
    Metrik, kNN kütüphanesinin (seed/memory) kayıt formatıyla AYNI tanımdan
    (classify_vehicle) üretilir — farklı tanım feature-uzayını kaydırır."""
    import auto_pilot as ap
    from vehicle_pipeline import inspect_geometry
    stl = HERE / "_doe_tmp" / "cand.stl"
    make_revolve_stl(params, stl)
    metrik = ap.classify_vehicle(inspect_geometry(str(stl)))["metrik"]
    pred = ap.cd_predict(metrik, "roket") if metrik else None
    if not pred:
        return DesignPoint(params, {}, source="surrogate", gecerli=False, not_="surrogat desteği yok")
    return DesignPoint(params, {"cd": pred["cd_tahmin"]},
                       {"cd_pct": round((1 - pred["guven"]) * 100, 1)},
                       source="surrogate")


def evaluate_cfd(params: dict, velocity: float = 30.0) -> DesignPoint:
    """Doğrulanmış: run_vehicle_analysis + 3-mesh GCI → Cd ± GCI bandı (yavaş)."""
    from vehicle_pipeline import run_vehicle_analysis
    stl = HERE / "_doe_runs" / f"doe_{params['L_D']:.2f}_{params['nose_frac']:.2f}.stl"
    make_revolve_stl(params, stl)
    r = run_vehicle_analysis(str(stl), vehicle_type="roket", velocity=velocity,
                             quality="hassas", mesh_sensitivity=True, out_root=str(HERE / "_doe_runs"))
    if r.status != "ok" or r.cd is None:
        return DesignPoint(params, {}, source="cfd", gecerli=False, not_="CFD başarısız")
    unc = r.belirsizlik or {}
    return DesignPoint(params, {"cd": r.cd, "ld": -(r.ld or 0)},   # ld maks → negatifle
                       {"cd_pct": unc.get("u_toplam_pct")}, source="cfd")


if __name__ == "__main__":
    import argparse
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--n", type=int, default=12)
    ap_.add_argument("--mode", choices=["surrogate", "cfd"], default="surrogate")
    args = ap_.parse_args()
    SPACE = {"L_D": (5.0, 14.0), "nose_frac": (0.15, 0.45)}
    fn = evaluate_surrogate if args.mode == "surrogate" else evaluate_cfd
    res = explore(SPACE, fn, args.n, objectives=["cd"])
    out = HERE / f"design_explore_{args.mode}.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"en_iyi": res["en_iyi"], "n_gecerli": res["n_gecerli"]},
                     indent=2, ensure_ascii=False))
    print("YAZILDI", out.name)
