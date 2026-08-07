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
    rec["kb_hucre"] = round(statistics.median(d), 3)
    rec["n_kosu"] = len(d)
    rec["dagilim"] = {"min": min(d), "max": max(d),
                      "medyan": rec["kb_hucre"],
                      "_anlam": ("TEK OLCUM — dagilim iddia edilmez" if len(d) == 1
                                 else f"{len(d)} kosunun medyani")}
    rec["verdikt"] = (f"{len(d)} kosudan medyan {rec['kb_hucre']} kB/hucre "
                      f"(min {min(d)}, max {max(d)}). Bellek kapisi artik "
                      "OLCULEN katsayiyla calisir.")
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
