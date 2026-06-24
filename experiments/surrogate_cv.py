"""auto_pilot kNN sürrogatının leave-one-out çapraz-validasyonu (CFD GEREKTİRMEZ).
İki çıktıyı ölçer: (1) tip-sınıflama doğruluğu (LOO majority-vote), (2) Cd-kestirim
hatası (LOO mesafe-ağırlıklı kNN, aynı-tip). Ayrıca belirsizlik-kalibrasyonu: kestirim
belirsizliği gerçek hatayı izliyor mu? auto_pilot._features + aynı kNN mantığını yansıtır.

Kullanım: python experiments/surrogate_cv.py   → surrogate_cv.json + figures/surrogate_cv.png
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import os

import auto_pilot as _ap  # noqa: E402
from auto_pilot import _features, _load_cases  # noqa: E402

if os.environ.get("CV_MEMORY"):                  # ayrı bellek dosyasını (ör. hq) değerlendir
    _ap.MEMORY = Path(os.environ["CV_MEMORY"])
_OUT_TAG = os.environ.get("CV_TAG", "")

K = 5
MIN_SUPPORT = 5


def _d2(fa, fb):
    return sum((a - b) ** 2 for a, b in zip(fa, fb))


def type_loocv(cases):
    """Her vakayı dışarda bırak, kalan kütüphaneden k-NN majority tip tahmini."""
    feats = [(_features(c["metrik"]), c["onayli_tip"]) for c in cases]
    confusion = defaultdict(Counter)
    correct = 0
    for i, (fi, true_t) in enumerate(feats):
        nbrs = sorted((j for j in range(len(feats)) if j != i),
                      key=lambda j: _d2(fi, feats[j][0]))[:K]
        pred = Counter(feats[j][1] for j in nbrs).most_common(1)[0][0]
        confusion[true_t][pred] += 1
        correct += (pred == true_t)
    per_type = {t: round(c[t] / sum(c.values()), 3) for t, c in confusion.items()}
    return {"genel_dogruluk": round(correct / len(feats), 3),
            "tip_basina_dogruluk": per_type,
            "confusion": {t: dict(c) for t, c in confusion.items()}}


def cd_loocv(cases):
    """Her Cd-çapasını dışarda bırak, aynı-tipten mesafe-ağırlıklı kNN ile Cd tahmin et."""
    by_type = defaultdict(list)
    for c in cases:
        if c.get("cd_toplam") is not None and c.get("onayli_tip"):
            by_type[c["onayli_tip"]].append(c)
    out = {}
    calib = []          # (rel_belirsizlik, rel_hata) — kalibrasyon
    flat = []           # tüm tiplerin birleşik rel-hataları (genel MAPE)
    for vtype, anchors in by_type.items():
        if len(anchors) < MIN_SUPPORT + 1:
            out[vtype] = {"n": len(anchors), "durum": "yetersiz destek (CV atlandı)"}
            continue
        errs = []
        for i, ci in enumerate(anchors):
            fi = _features(ci["metrik"])
            rest = [cj for j, cj in enumerate(anchors) if j != i]
            knn = sorted(rest, key=lambda c: _d2(fi, _features(c["metrik"])))[:K]
            w = [1.0 / (_d2(fi, _features(c["metrik"])) ** 0.5 + 1e-6) for c in knn]
            cds = [c["cd_toplam"] for c in knn]
            wsum = sum(w) or 1.0
            cd_hat = sum(wi * v for wi, v in zip(w, cds)) / wsum
            unc = (sum(wi * (v - cd_hat) ** 2 for wi, v in zip(w, cds)) / wsum) ** 0.5
            true = ci["cd_toplam"]
            rel_err = abs(cd_hat - true) / (abs(true) + 1e-9)
            errs.append(rel_err); flat.append(rel_err)
            calib.append((unc / (abs(cd_hat) + 1e-9), rel_err))
        out[vtype] = {"n": len(anchors), "mape_pct": round(100 * sum(errs) / len(errs), 1),
                      "medyan_hata_pct": round(100 * sorted(errs)[len(errs) // 2], 1),
                      "max_hata_pct": round(100 * max(errs), 1)}
    genel = round(100 * sum(flat) / len(flat), 1) if flat else None
    return {"genel_mape_pct": genel, "tip_basina": out, "_calib": calib}


def _figure(tip_res, cd_res, out_png):
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
    # 1: tip doğruluk
    pt = cd_res["tip_basina"]
    tt = tip_res["tip_basina_dogruluk"]
    ks = sorted(tt)
    ax[0].barh(ks, [tt[k] for k in ks], color="#1f4e79")
    ax[0].set_xlim(0, 1); ax[0].set_title(f"Tip-sınıflama LOO doğruluk\n(genel {tip_res['genel_dogruluk']})", fontsize=9)
    ax[0].axvline(0.9, ls="--", color="#c00000", lw=0.8)
    # 2: Cd MAPE
    mk = [k for k in pt if "mape_pct" in pt[k]]
    ax[1].barh(mk, [pt[k]["mape_pct"] for k in mk], color="#2e7d32")
    ax[1].set_title(f"Cd-kestirim LOO MAPE %\n(genel {cd_res['genel_mape_pct']}%)", fontsize=9)
    ax[1].axvline(15, ls="--", color="#c00000", lw=0.8)
    # 3: kalibrasyon
    cal = cd_res["_calib"]
    if cal:
        xs, ys = zip(*cal)
        ax[2].scatter([100 * x for x in xs], [100 * y for y in ys], s=10, alpha=0.5, color="#6a1b9a")
        lim = max(max(xs), max(ys)) * 100
        ax[2].plot([0, lim], [0, lim], ls="--", color="gray", lw=0.8)
    ax[2].set_xlabel("rapor edilen belirsizlik %"); ax[2].set_ylabel("gerçek hata %")
    ax[2].set_title("Belirsizlik kalibrasyonu", fontsize=9)
    fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)


def main():
    cases = _load_cases()
    anchors = [c for c in cases if c.get("cd_toplam") is not None]
    tip_res = type_loocv(cases)
    cd_res = cd_loocv(cases)
    calib = cd_res.pop("_calib")
    # kalibrasyon korelasyonu (Pearson)
    corr = None
    if len(calib) > 3:
        xs = [a for a, _ in calib]; ys = [b for _, b in calib]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        cov = sum((a - mx) * (b - my) for a, b in calib)
        sx = math.sqrt(sum((a - mx) ** 2 for a in xs)); sy = math.sqrt(sum((b - my) ** 2 for b in ys))
        corr = round(cov / (sx * sy), 3) if sx and sy else None
    rec = {"n_vaka": len(cases), "n_cd_capa": len(anchors),
           "tip_siniflama": tip_res, "cd_kestirim": cd_res,
           "belirsizlik_kalibrasyon_pearson": corr,
           "yorum": ("LOO: kütüphane kendi içinde ne kadar tutarlı. Cd-MAPE düşük + kalibrasyon "
                     "pozitif ise sürrogat öğreniyor. Bu MUTLAK doğruluk DEĞİL — etiketler "
                     "üreten CFD kalitesiyle (hizli→y⁺ yüksek) tavanlı; mutlak için validate_pipeline.")}
    suf = f"_{_OUT_TAG}" if _OUT_TAG else ""
    (ROOT / f"surrogate_cv{suf}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    figdir = ROOT / "figures"; figdir.mkdir(exist_ok=True)
    _figure(tip_res, {**cd_res, "_calib": calib}, figdir / f"surrogate_cv{suf}.png")
    print(json.dumps({k: v for k, v in rec.items() if k != "cd_kestirim"}, indent=2, ensure_ascii=False))
    print("Cd genel MAPE:", cd_res["genel_mape_pct"], "%  | kalibrasyon r:", corr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
