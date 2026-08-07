"""Hücre başına bellek katsayısı — KOŞU ARŞİVİNDEN ölçülür, uydurulmaz.

NEDEN: bellek kapısının ihtiyacı olan tek sayı "hücre başına kaç kB". Bu sayı
çözücüye, türbülans modeline ve katman sayısına bağlıdır; literatürden alınan
tek bir değer bu makinede yanlış olur. Çözücü artık koşu boyunca sistem
belleğini örnekliyor (`bellek.artis_gb`), yani sayı ÖLÇÜLEBİLİR.

NE ÖLÇÜLÜR: bellek telemetrisi taşıyan her koşu için artis_gb / cells. Doğrusal
bir uyum değil, ROBUST bir merkez (medyan) alınır — tek bir koşu arka planda
başka bir iş varken ölçülmüş olabilir.

NE ÖLÇÜLMEZ: WSL2 VM'i ayrı bir süreç olmadığı için tek koşunun RSS'i
görülemez; ölçülen, sistem geneli kullanımın koşu boyunca ARTIŞIDIR. Makinede
başka bir şey çalışıyorsa sayı yukarı kayar ve bu bir ÜST SINIRDIR.

    python experiments/bellek_katsayisi.py
Çıktı: bellek_katsayisi.json  (bellek_kapisi.py bunu okur)
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))


# GURULTU ESIKLERI. Kucuk kosularda cozucunun kendi bellegi (~0.05 GB) sistem
# geneli olcumun gurultusunun ALTINDA kalir; medyan almak gurultuye katsayi
# demektir. Olculdu (basarim matrisi, 18k-96k hucre): kB/hucre 0.9 ile 9.75
# arasinda sacildi — 10 KAT. Ayni geometri, ayni cozucu, tek degisen cekirdek
# sayisi. Yani sinyal yok.
EN_AZ_ARTIS_GB = 0.5       # bunun altindaki artis sistem gurultusuyle karisir
EN_COK_SACILMA = 3.0       # max/min bundan buyukse dagilim tutarli degil


def topla() -> list[dict]:
    kayit = []
    for p in sorted((KOK / "vehicle_runs").glob("*/sonuc.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        b = d.get("bellek") or {}
        cells = (d.get("mesh") or {}).get("cells")
        artis = b.get("artis_gb")
        if not cells or not isinstance(artis, (int, float)) or artis <= 0:
            continue
        kayit.append({"kosu": p.parent.name, "cells": cells,
                      "artis_gb": artis, "toplam_gb": b.get("toplam_gb"),
                      "kb_hucre": round(artis * 1e6 / cells, 3)})
    # BASARIM MATRISI de bellek olcumu tasir ve kendi calisma dizinine yazar
    # (vehicle_runs altinda degil). Onu disarida birakmak, elimizdeki en
    # kontrollu olcum setini gormezden gelmek olurdu.
    bm = KOK / "basarim_matrisi.json"
    if bm.exists():
        for r in json.loads(bm.read_text(encoding="utf-8")).get("satirlar", []):
            b2 = r.get("bellek") or {}
            artis, cells = b2.get("artis_gb"), r.get("cells")
            if not cells or not isinstance(artis, (int, float)) or artis <= 0:
                continue
            kayit.append({"kosu": f"basarim/{r['etiket']}", "cells": cells,
                          "artis_gb": artis, "toplam_gb": b2.get("toplam_gb"),
                          "kb_hucre": round(artis * 1e6 / cells, 3)})
    return kayit


def calistir() -> dict:
    kayit = topla()
    rec = {
        "vaka": "Hücre başına bellek katsayısı — koşu arşivinden",
        "_neden": ("Bellek kapisinin ihtiyaci olan tek sayi. Literaturden alinan "
                   "tek bir deger bu makinede yanlis olur; cozucu artik kosu "
                   "boyunca sistem bellegini ornekliyor."),
        "kosular": kayit,
        "_kisit": ("WSL2 VM ayri bir surec olmadigi icin tek kosunun RSS'i "
                   "gorulemez; olculen, sistem geneli kullanimin kosu boyunca "
                   "ARTISIDIR. Makinede baska is varsa sayi yukari kayar — "
                   "yani bu bir UST SINIRDIR."),
        "_uretim": "Üretim: python experiments/bellek_katsayisi.py",
    }
    if not kayit:
        rec["verdikt"] = ("Bellek telemetrisi tasiyan kosu YOK — katsayi "
                          "OLCULEMEDI. bellek_kapisi ONCUL ile calisir ve bunu "
                          "her ciktisinda soyler. Telemetri bu surumde eklendi; "
                          "bundan sonraki kosular olcum uretir.")
        rec["kb_hucre"] = None
        return rec
    d = [k["kb_hucre"] for k in kayit]
    medyan = round(statistics.median(d), 3)
    sacilma = max(d) / min(d) if min(d) > 0 else float("inf")
    zayif = [k for k in kayit if k["artis_gb"] < EN_AZ_ARTIS_GB]
    rec["dagilim"] = {"min": min(d), "max": max(d), "medyan": medyan,
                      "sacilma_katı": round(sacilma, 1),
                      "gurultu_alti_kosu": len(zayif), "n_kosu": len(d)}
    # GURULTUYE KATSAYI DENMEZ. Sacilma buyukse ya da olculen artis gurultu
    # esiginin altindaysa medyan bir merkez DEGILDIR; sayi YAZILMAZ ve kapi
    # onculle calismaya devam eder. Bu, "elimizde veri var" diye gecersiz bir
    # sayi yayimlamaktan iyidir.
    yeterli = sacilma <= EN_COK_SACILMA and len(zayif) < len(kayit)
    if not yeterli:
        rec["kb_hucre"] = None
        rec["n_kosu"] = len(d)
        rec["verdikt"] = (
            f"{len(d)} kosu var ama katsayi OLCULEMEDI: kB/hucre {min(d)}-{max(d)} "
            f"arasinda sacildi ({sacilma:.1f} kat, esik {EN_COK_SACILMA}) ve "
            f"{len(zayif)}/{len(kayit)} kosunun bellek artisi gurultu esiginin "
            f"({EN_AZ_ARTIS_GB} GB) altinda. Kucuk kosularda cozucunun kendi "
            "bellegi sistem geneli olcumun gurultusune gomuluyor. Medyani "
            "katsayi diye yazmak gurultuye katsayi demek olurdu — bellek kapisi "
            "ONCULLE calismaya devam ediyor.")
        return rec
    rec["kb_hucre"] = medyan
    rec["n_kosu"] = len(d)
    rec["verdikt"] = (f"{len(d)} kosudan medyan {medyan} kB/hucre "
                      f"(min {min(d)}, max {max(d)}, sacilma {sacilma:.1f} kat). "
                      "Bellek kapisi artik OLCULEN katsayiyla calisir.")
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    (KOK / "bellek_katsayisi.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    for k in rec["kosular"]:
        print(f"  {k['kosu']:<26}{k['cells']:>10,} hücre  "
              f"{k['artis_gb']:>6.2f} GB  →  {k['kb_hucre']:>6.3f} kB/hücre")
    print("\n" + rec["verdikt"])
    print("-> bellek_katsayisi.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
