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
    # sessiz-yutma: kabul — kNN ÖNCÜLÜ kaydı; öncül UQ'ya girmez, hüküm etkilenmez
    except Exception:
        return None
    md = s.get("mesh_duyarlilik") or {}
    geo = s.get("geometry") or {}
    if s.get("status") != "ok" or not md or not geo.get("boyutlar_m"):
        return None
    import auto_pilot as ap
    try:
        cls = ap.classify_vehicle(geo)
    # sessiz-yutma: kabul — kNN ÖNCÜLÜ kaydı; öncül UQ'ya girmez, hüküm etkilenmez
    except Exception:
        return None
    metrik = cls["metrik"]
    gci = md.get("gci") or {}
    verdikt_ok = str(md.get("verdikt", "")).startswith("✅")
    unc = s.get("belirsizlik") or {}
    u_kayitli = unc.get("u_sayisal_pct")
    if u_kayitli is None:
        u_kayitli = gci.get("gci_fine_pct", md.get("fark_pct"))

    # KAYDEDİLEN SAYIYA GÜVENİLMEZ, SEVİYELERDEN YENİDEN TÜRETİLİR.
    # Belirsizlik kuralı bu oturumda beş kez değişti; jsonl kayıtları değişmedi.
    # Ölçüldü: doe_6.90_0.37 kaydı %1.40 diyordu (asimptotik OLMAYAN Richardson
    # sayısı — bugün reddedilir); aynı seviyelerden bugünün kuralı %15.2 verir.
    # Öncül, artık üretilmeyen ve on kat iyimser bir tanımla besleniyordu.
    seviyeler = md.get("seviyeler") or []
    from report_generator import band_from_levels
    band = band_from_levels([lv.get("cells") for lv in seviyeler],
                            [lv.get("Cd") for lv in seviyeler])

    import mentor
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M"), "kaynak": str(path),
           "dosya": geo.get("dosya", ""), **mentor._tip_alanlari(s, cls),
           "metrik": metrik, "cells_fine": (s.get("mesh") or {}).get("cells"),
           "p": gci.get("p"), "monotonic": gci.get("monotonic"),
           "asimptotik_ok": verdikt_ok, "n_seviye": len(seviyeler),
           "u_kayitli_pct": (round(float(u_kayitli), 2)
                             if u_kayitli is not None else None),
           "u_num_pct": band["u_pct"] if band else None,
           "u_kaynak": band["kaynak"] if band else None,
           "yontem": band["yontem"] if band else None}
    if band and u_kayitli:
        rec["sapma_kat"] = round(band["u_pct"] / max(abs(float(u_kayitli)), 1e-9), 2)

    # ÖĞRENİLEBİLİR Mİ? mesh_memory ile AYNI ölçüt: gövde gerçekten çözülmüş mü.
    # Çözülmemiş bir gövdenin GCI'si o gövdenin değil, onun 74-yüzlü gölgesinindir
    # (MiniHawk'ta %379 böyle çıkmıştı).
    gecerli = mentor._yuzey_gecerlilik(s.get("sinir_tabaka") or {})
    if band is None:
        rec.update(ogrenilebilir=False,
                   gecersizlik="seviye Cd/hucre YOK — band yeniden turetilemedi")
    else:
        rec.update(gecerli)
    return rec


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
    # SESSİZ DARALTMA YOK: kaç kayıt öğrenmeye girmiyor ve kaçının kaydedilen sayısı
    # bugünün kuralından SAPIYOR — ikisi de görünür olmalı. Sapma büyükse öncülün
    # eski tanımla beslendiği anlaşılır.
    sapan = [r for r in recs if (r.get("sapma_kat") or 1) >= 2 or
             (r.get("sapma_kat") or 1) <= 0.5]
    return {"n_kayit": len(recs), "dosya": str(GCI_MEMORY),
            "asimptotik": sum(1 for r in recs if r["asimptotik_ok"]),
            "n_ogrenilebilir": sum(1 for r in recs if r.get("ogrenilebilir")),
            "n_dislanan": sum(1 for r in recs if not r.get("ogrenilebilir")),
            "n_kayitli_sayi_SAPIYOR": len(sapan),
            "en_buyuk_sapma_kat": (max(r["sapma_kat"] for r in sapan) if sapan else None),
            "n_tip_celiskisi": sum(1 for r in recs if r.get("tip_celiskisi"))}


def _load(sadece_gecerli: bool = True) -> list[dict]:
    """Öğrenme havuzu. `sadece_gecerli`: gövdesi ÇÖZÜLMEMİŞ ya da bandı yeniden
    türetilemeyen koşular GİRMEZ — bkz. mentor._load, aynı ölçüt."""
    if not GCI_MEMORY.exists():
        return []
    out = []
    for line in GCI_MEMORY.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if sadece_gecerli and not r.get("ogrenilebilir"):
                continue
            if r.get("metrik") and r.get("u_num_pct") is not None:
                out.append(r)
        # sessiz-yutma: kabul — bozuk satır atlanır; öncül zayıflar, hüküm etkilenmez
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
    # GÜVEN, KAYIT SAYISINDAN DEĞİL AYRIK GEOMETRİ SAYISINDAN. Öğrenme havuzunda
    # ölçüldü: 16 kaydın 5'i AYNI gövde (minihawk, farklı ayarlarla). Ayar→sonuç
    # için o tekrarlar sinyaldir, ama "16 bağımsız vaka gördüm" demek değildir.
    n_geo = len({c.get("dosya") or c.get("kaynak") for c in pool})
    guven = round(min(1.0, n_geo / 12.0) * (1.0 if pool is same_tip else 0.6), 2)

    # AYIRT EDİCİ Mİ? Havuzdaki TÜM koşular aynı sonucu verdiyse "olasılık" bir
    # öğrenme değil, bir SABİTTİR: geometri ne olursa olsun aynı cevap çıkar.
    # Mentor'daki aynı kusur ölçülmüştü — iki kalite de %100 görünüyordu ve
    # sıralama beraberlik-bozucuya kalıp ÖLÇÜMLE ÇÜRÜTÜLMÜŞ bir öneri veriyordu.
    ayirt_edici = len({bool(c["asimptotik_ok"]) for c in knn}) > 1
    us = [c["u_num_pct"] for c in knn]
    genis = max(us) > 3.0 * max(min(us), 1e-9)

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
    if not ayirt_edici:
        oneri = ("[AYIRT EDİCİ DEĞİL: komşuların hepsi aynı sonucu verdi; bu cevap "
                 "geometriden değil havuzun tek-yönlülüğünden geliyor] " + oneri)
    if genis:
        oneri += (f" NOT: komşu bandları %{min(us):.1f}–%{max(us):.1f} arasında "
                  "saçılıyor; ortalama bir beklenti DEĞİL, yalnız büyüklük mertebesi.")
    return {"u_num_beklenen_pct": round(u_hat, 1),
            "u_komsu_araligi_pct": [round(min(us), 1), round(max(us), 1)],
            "asimptotik_olasilik": (round(p_asym, 2) if ayirt_edici else None),
            "ayirt_edici": ayirt_edici,
            "p_gozlenen_komsu": ([round(min(ps), 2), round(max(ps), 2)] if ps else None),
            "n_destek": len(pool), "n_ayrik_geometri": n_geo,
            "komsu": len(knn), "ayni_tip": pool is same_tip,
            "guven": (guven if ayirt_edici else 0.0), "oneri": oneri,
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
