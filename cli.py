"""Başsız komut satırı — JSON döndürür, GUI gerektirmez.

Konteynerde çalışan giriş noktası budur: `docker run ... python cli.py --stl ...`
Çıktı stdout'a tek bir JSON nesnesidir; ilerleme iletileri stderr'e gider ki
stdout borulanabilsin.

    python cli.py --stl model.stl --tip ucak --hiz 30 --alpha 4 --duzeltici
    python cli.py --stl model.stl --tip roket --hiz 50 | jq .gecerlilik.genel

Çıkış kodu: 0 analiz tamamlandı, 1 çözücü hatası, 2 kullanım hatası.
Not: çıkış kodu 0, "sonuç tasarım kararında kullanılabilir" DEMEK DEĞİLDİR;
onu `gecerlilik.genel` söyler.
"""
from __future__ import annotations

import argparse
import json
import sys

from hizmet import SURUM, analiz_et


def _ayristir(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cli.py", description="Araç aerodinamik analizi (başsız, JSON çıktı)")
    p.add_argument("--stl", required=True, help="geometri dosyası (.stl)")
    p.add_argument("--tip", default="ucak", help="araç tipi (ucak/roket/multikopter/…)")
    p.add_argument("--hiz", type=float, default=30.0, help="serbest akış hızı [m/s]")
    p.add_argument("--alpha", type=float, default=0.0, help="hücum açısı [°]")
    p.add_argument("--kalite", default="standart", help="mesh kalite preset'i")
    p.add_argument("--cekirdek", type=int, default=0, help="işlemci sayısı (0=oto)")
    p.add_argument("--duzeltici", action="store_true",
                   help="kusur bulunursa kurulumu onar ve yeniden koş")
    p.add_argument("--referans-cd", type=float, default=None,
                   help="düzeltmenin işe yarayıp yaramadığı BUNA göre ölçülür; "
                        "verilmezse etki 'ölçülemedi' diye raporlanır")
    p.add_argument("--surum", action="version", version=f"hizmet {SURUM}")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = _ayristir(argv)
    try:
        o = analiz_et(a.stl, vehicle_type=a.tip, velocity=a.hiz,
                      alpha_deg=a.alpha, quality=a.kalite,
                      n_processors=a.cekirdek, duzeltici=a.duzeltici,
                      referans_cd=a.referans_cd,
                      progress_cb=lambda p, m: print(f"[{p:3d}%] {m}", file=sys.stderr))
    except Exception as e:                                        # noqa: BLE001
        # SESSİZ YUTMA YOK: hata JSON olarak stdout'a da yazılır ki borulayan
        # taraf onu ayrıştırabilsin; yalnız stderr'e yazmak istemciyi kör bırakır.
        json.dump({"surum": SURUM, "durum": "hata", "hata": f"{type(e).__name__}: {e}"},
                  sys.stdout, ensure_ascii=False)
        print()
        return 1
    json.dump(o, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0 if o.get("durum") == "ok" else 1


if __name__ == "__main__":
    for _a in (sys.stdout, sys.stderr):
        if hasattr(_a, "reconfigure"):
            _a.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
