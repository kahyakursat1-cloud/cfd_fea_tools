"""GCI danışmanı — ML katmanının mesh-yakınsama ayağı (instance-based, auto_pilot deseniyle).

İki iş:
1. harvest(): geçmiş koşuların GCI sonuçlarını (vehicle_runs / validation_anchors_runs
   sonuc.json'larındaki mesh_duyarlilik) geometri-metrikleriyle birlikte GCI_MEMORY'ye
   toplar — kütüphane her kampanyayla kendiliğinden büyür.
2. advise(): yeni bir geometri için koşu-ÖNCESİ öğrenilen-öncül döner: beklenen sayısal
   belirsizlik bandı, asimptotik-çıkma olasılığı, seviye/yöntem önerisi (3-seviye GCI mi,
   4+ seviye + LSR mi — bkz. report_generator.least_squares_gci).

DÜRÜSTLÜK: çıktı ÖĞRENİLEN-ÖNCÜL'dür, ölçülen band DEĞİL — rapora/UQ'ya girmez, yalnız
plan katmanına (auto_pilot öner+onayla) uyarı olarak gider. Veri ince (n<min_support)
ise şeffaf REDDEDER (None). CV dersi (surrogate_cv_hq): instance-based kestirim sanity-
check priori'dir, doğrulama ikamesi değil.

CLI: python gci_advisor.py harvest | python gci_advisor.py advise <stl> [--tip roket]
"""
from __future__ import annotations

import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GCI_MEMORY = HERE / "gci_memory.jsonl"
_SCAN_ROOTS = ("vehicle_runs", "validation_anchors_runs", "_doe_runs")
MIN_SUPPORT = 4


def _record_from_sonuc(path: Path) -> dict | None:
    try:
        s = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    md = s.get("mesh_duyarlilik") or {}
    geo = s.get("geometry") or {}
    if s.get("status") != "ok" or not md or not geo.get("boyutlar_m"):
        return None
    import auto_pilot as ap
    try:
        metrik = ap.classify_vehicle(geo)["metrik"]
    except Exception:
        return None
    gci = md.get("gci") or {}
    verdikt_ok = str(md.get("verdikt", "")).startswith("✅")
    unc = s.get("belirsizlik") or {}
    u_num = unc.get("u_sayisal_pct")
    if u_num is None:
        u_num = gci.get("gci_fine_pct", md.get("fark_pct"))
    if u_num is None:
        return None
    return {"ts": time.strftime("%Y-%m-%d %H:%M"), "kaynak": str(path),
            "dosya": geo.get("dosya", ""), "tip": s.get("vehicle_type", "genel"),
            "metrik": metrik, "cells_fine": (s.get("mesh") or {}).get("cells"),
            "p": gci.get("p"), "u_num_pct": round(float(u_num), 2),
            "monotonic": gci.get("monotonic"), "asimptotik_ok": verdikt_ok,
            "n_seviye": len(md.get("seviyeler", []))}


def harvest(roots=_SCAN_ROOTS) -> dict:
    """Depodaki sonuc.json'lardan GCI kayıtlarını topla; GCI_MEMORY'yi YENİDEN yazar
    (kaynak-dosya bazlı — aynı koşu iki kez girmez, silinen koşu düşer)."""
    recs = []
    for root in roots:
        for p in sorted((HERE / root).rglob("sonuc.json")):
            r = _record_from_sonuc(p)
            if r:
                recs.append(r)
    GCI_MEMORY.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs),
                          encoding="utf-8")
    return {"n_kayit": len(recs), "dosya": str(GCI_MEMORY),
            "asimptotik": sum(1 for r in recs if r["asimptotik_ok"])}


def _load() -> list[dict]:
    if not GCI_MEMORY.exists():
        return []
    out = []
    for line in GCI_MEMORY.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if r.get("metrik") and r.get("u_num_pct") is not None:
                out.append(r)
        except Exception:
            pass
    return out


def advise(metrik: dict, tip: str = "", k: int = 5,
           min_support: int = MIN_SUPPORT) -> dict | None:
    """Geometri-metriğinden öğrenilen GCI-öncülü. Komşuluk auto_pilot._features
    uzayında (kütüphane kayıtlarıyla AYNI tanım). Döner: dict | None (veri ince)."""
    import auto_pilot as ap
    cases = _load()
    same_tip = [c for c in cases if c.get("tip") == tip]
    pool = same_tip if len(same_tip) >= min_support else cases
    if len(pool) < min_support:
        return None
    fv = ap._features(metrik)

    def d2(c):
        return sum((a - b) ** 2 for a, b in zip(fv, ap._features(c["metrik"])))
    knn = sorted(pool, key=d2)[:min(k, len(pool))]
    w = [1.0 / (d2(c) ** 0.5 + 1e-6) for c in knn]
    ws = sum(w) or 1.0
    u_hat = sum(wi * c["u_num_pct"] for wi, c in zip(w, knn)) / ws
    p_asym = sum(wi * (1.0 if c["asimptotik_ok"] else 0.0) for wi, c in zip(w, knn)) / ws
    ps = [c["p"] for c in knn if c.get("p") is not None]
    guven = round(min(1.0, len(pool) / 12.0) * (1.0 if pool is same_tip else 0.6), 2)

    if p_asym < 0.5:
        oneri = ("Benzer koşularda 3-seviye GCI çoğunlukla asimptotik ÇIKMADI → "
                 "4+ seviye koşup LSR (least_squares_gci, Eça-Hoekstra) kullanın; "
                 "3-seviye Richardson'a zaman harcamayın.")
    elif u_hat > 10.0:
        oneri = ("Asimptotik çıksa da band geniş görünüyor (öncül ~%"
                 f"{u_hat:.0f}) — mesh yoğunluğunu artırın ya da bandı raporlayıp "
                 "A/B-karşılaştırmalı kullanın.")
    else:
        oneri = "Standart 3-seviye GCI bu geometri sınıfında yeterli görünüyor."
    return {"u_num_beklenen_pct": round(u_hat, 1),
            "asimptotik_olasilik": round(p_asym, 2),
            "p_gozlenen_komsu": ([round(min(ps), 2), round(max(ps), 2)] if ps else None),
            "n_destek": len(pool), "komsu": len(knn), "ayni_tip": pool is same_tip,
            "guven": guven, "oneri": oneri,
            "etiket": "ÖĞRENİLEN-ÖNCÜL — ölçülen band değil, UQ'ya girmez"}


if __name__ == "__main__":
    import argparse
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cli = argparse.ArgumentParser()
    cli.add_argument("komut", choices=["harvest", "advise"])
    cli.add_argument("stl", nargs="?")
    cli.add_argument("--tip", default="")
    args = cli.parse_args()
    if args.komut == "harvest":
        print(json.dumps(harvest(), indent=2, ensure_ascii=False))
    else:
        if not args.stl:
            sys.exit("advise için STL yolu gerekli")
        import auto_pilot as ap
        from vehicle_pipeline import inspect_geometry
        cls = ap.classify_vehicle(inspect_geometry(args.stl))
        out = advise(cls["metrik"], args.tip or cls["tip"])
        print(json.dumps(out or {"durum": f"veri ince (<{MIN_SUPPORT} kayıt) — öncül verilmez"},
                         indent=2, ensure_ascii=False))
