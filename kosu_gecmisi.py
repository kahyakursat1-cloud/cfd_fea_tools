"""Koşu geçmişi — tüm analiz koşularını tek tablodan tara + iki koşuyu karşılaştır.

Mühendis iş-akışının ilk isteği: 'vehicle_runs doluyor, iki koşunun Cd'sini yan yana
görmek için JSON açıyorum'. Veri zaten sonuc.json'larda; bu modül yalnız görünüm katmanı.
Karşılaştırma A/B-dürüst: iki koşunun kalite/mesh ailesi farklıysa uyarır (farklı aile
karşılaştırması sistematik-hata kırpmaz).

CLI: python kosu_gecmisi.py listele [--tip roket]
     python kosu_gecmisi.py karsilastir <kosu_adi_A> <kosu_adi_B>
GUI: app_analyzer '📂 Koşular' → KosularDialog (bu modülü kullanır).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_ROOTS = ("vehicle_runs", "validation_anchors_runs", "_doe_runs")

_ALANLAR = [("ad", "Koşu"), ("tip", "Tip"), ("kalite", "Kalite"), ("hiz", "V (m/s)"),
            ("alpha", "α (°)"), ("cd", "Cd"), ("u_pct", "±U%"), ("cl", "Cl"),
            ("cells", "Hücre"), ("verdikt", "Mesh-bağımsızlık"), ("status", "Durum")]


def tara(roots=_ROOTS) -> list[dict]:
    """Tüm koşu dizinlerini tara → tablo-hazır kayıt listesi (yeni→eski, mtime)."""
    out = []
    for root in roots:
        base = HERE / root
        if not base.exists():
            continue
        for p in sorted(base.rglob("sonuc.json"), key=lambda x: -x.stat().st_mtime):
            try:
                s = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            unc = s.get("belirsizlik") or {}
            md = s.get("mesh_duyarlilik") or {}
            out.append({
                "ad": p.parent.name, "yol": str(p.parent),
                "tip": s.get("vehicle_type", "?"), "kalite": s.get("kalite", ""),
                "hiz": s.get("velocity"), "alpha": s.get("alpha_deg"),
                "cd": s.get("cd"), "cl": s.get("cl"), "ld": s.get("ld"),
                "drag_N": s.get("drag_N"),
                "u_pct": unc.get("u_toplam_pct"),
                "u_kaynak": unc.get("u_sayisal_kaynak"),
                "cells": (s.get("mesh") or {}).get("cells"),
                "yplus": ((s.get("sinir_tabaka") or {}).get("yplus") or {}).get("ort"),
                "verdikt": (md.get("verdikt") or "")[:60],
                "status": s.get("status", "?"),
                "rapor": s.get("report", ""),
            })
    return out


def bul(ad: str, kayitlar: list[dict] | None = None) -> dict | None:
    for k in (kayitlar if kayitlar is not None else tara()):
        if k["ad"] == ad:
            return k
    return None


def karsilastir(a: str | dict, b: str | dict) -> dict:
    """İki koşunun metrik-yanyana karşılaştırması + Δ%. Uyarılar: farklı kalite/tip/hız
    (A/B karşılaştırmasının güvenilirlik önkoşulları)."""
    ka = a if isinstance(a, dict) else bul(a)
    kb = b if isinstance(b, dict) else bul(b)
    if not ka or not kb:
        raise ValueError(f"koşu bulunamadı: {a if not ka else b}")

    def d_pct(x, y):
        if x is None or y is None or not x:
            return None
        return round((y - x) / abs(x) * 100, 2)
    satirlar = []
    for key, etiket in (("cd", "Cd"), ("cl", "Cl"), ("ld", "L/D"),
                        ("drag_N", "Sürükleme (N)"), ("cells", "Hücre"),
                        ("yplus", "y⁺ (gövde)")):
        satirlar.append({"metrik": etiket, "A": ka.get(key), "B": kb.get(key),
                         "delta_pct": d_pct(ka.get(key), kb.get(key))})
    uyarilar = []
    for key, mesaj in (("kalite", "mesh kalitesi farklı — Δ mesh-etkisi içerir"),
                       ("tip", "araç tipi/referans-alan modu farklı"),
                       ("hiz", "hız (Re) farklı — katsayılar aynı rejimde değil")):
        if ka.get(key) != kb.get(key):
            uyarilar.append(f"{key}: {ka.get(key)} ↔ {kb.get(key)} ({mesaj})")
    ua, ub = ka.get("u_pct"), kb.get("u_pct")
    ayirt = None
    if None not in (ua, ub, ka.get("cd"), kb.get("cd")) and ka["cd"]:
        dcd = abs(kb["cd"] - ka["cd"]) / abs(ka["cd"]) * 100
        band = (ua ** 2 + ub ** 2) ** 0.5
        ayirt = {"dCd_pct": round(dcd, 2), "band_rss_pct": round(band, 2),
                 "hukum": ("Fark belirsizlik bandının DIŞINDA — gerçek tasarım farkı"
                           if dcd > band else
                           "Fark belirsizlik bandının İÇİNDE — A/B ayırt edilemez")}
    return {"A": ka["ad"], "B": kb["ad"], "satirlar": satirlar,
            "uyarilar": uyarilar, "ayirt_edilebilirlik": ayirt}


def tablo_metni(kayitlar: list[dict], tip: str = "") -> str:
    rows = [k for k in kayitlar if not tip or k["tip"] == tip]
    if not rows:
        return "(koşu yok)"
    basliklar = [b for _, b in _ALANLAR]
    hucre = [[("" if k.get(a) is None else str(k.get(a))) for a, _ in _ALANLAR] for k in rows]
    gen = [max(len(basliklar[i]), *(len(h[i]) for h in hucre)) for i in range(len(basliklar))]
    cizgi = "  ".join("-" * g for g in gen)
    out = ["  ".join(b.ljust(g) for b, g in zip(basliklar, gen)), cizgi]
    out += ["  ".join(c.ljust(g) for c, g in zip(h, gen)) for h in hucre]
    return "\n".join(out)


if __name__ == "__main__":
    import argparse
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cli = argparse.ArgumentParser()
    cli.add_argument("komut", choices=["listele", "karsilastir"])
    cli.add_argument("a", nargs="?")
    cli.add_argument("b", nargs="?")
    cli.add_argument("--tip", default="")
    args = cli.parse_args()
    if args.komut == "listele":
        print(tablo_metni(tara(), tip=args.tip))
    else:
        if not (args.a and args.b):
            sys.exit("karsilastir için iki koşu adı gerekli")
        print(json.dumps(karsilastir(args.a, args.b), indent=2, ensure_ascii=False))
