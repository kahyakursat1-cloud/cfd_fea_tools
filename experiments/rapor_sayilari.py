"""Raporun KENDİ HAKKINDA yazdığı sayılar — tek kaynak.

Teknik rapor kendi kod tabanını anlatan sayılar taşır: satır, modül, test
dosyası, geçen test, kapsam. Bunlar iki ayrı yerde (kapak ve kalite tablosu)
elle yazılıydı ve kaçınılmaz olarak ayrıştı — hakem incelemesi kapakta 31.322,
tabloda 31.307 buldu. On beş satırlık fark önemli değil; ayrışmanın KENDİSİ
önemli, çünkü rapor tam da bunu avlayan bir sistemi anlatıyor.

Betik sayıları ölçer ve JSON'a yazar; `test_rapor_sayilari` hem tex'teki
tekrarların birbirini tuttuğunu hem de ölçümden makul sapmada olduğunu bağlar.
Tolerans var çünkü rapor her commit'te yeniden derlenmiyor — ama sapma
büyürse test söyler.

    python experiments/rapor_sayilari.py
Çıktı: rapor_sayilari.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent


def kod_satiri() -> int:
    """Kök + analysis/ Python satırı — raporun kapakta yazdığı sayı."""
    n = 0
    for p in list(KOK.glob("*.py")) + list((KOK / "analysis").glob("*.py")):
        n += len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
    return n


def olc(pytest_calistir: bool = False) -> dict:
    d = {
        "kod_satiri": kod_satiri(),
        "kok_modul": len(list(KOK.glob("*.py"))),
        "deney_betigi": len(list((KOK / "experiments").glob("*.py"))),
        "test_dosyasi": len(list((KOK / "tests").glob("test_*.py"))),
    }
    cov = KOK / "cov.json"
    if cov.exists():
        t = json.loads(cov.read_text(encoding="utf-8"))["totals"]
        d["ifade"] = t["num_statements"]
        d["kapsanmamis"] = t["missing_lines"]
        d["kapsam_pct"] = int(t["percent_covered"])
    if pytest_calistir:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header"],
                           cwd=KOK, capture_output=True, text=True)
        for satir in (r.stdout or "").splitlines()[::-1]:
            if " passed" in satir:
                d["gecen_test"] = int(satir.split(" passed")[0].split()[-1])
                break
    return d


def main() -> int:
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    d = olc(pytest_calistir="--test" in sys.argv)
    d["_neden"] = ("Rapor kendi hakkinda yazdigi sayilari iki ayri yerde elle "
                   "tasiyordu ve ayrismisti (kapak 31.322, tablo 31.307). "
                   "Sayilar artik olculur ve tekrarlari testle baglanir.")
    d["_uretim"] = "Üretim: python experiments/rapor_sayilari.py"
    (KOK / "rapor_sayilari.json").write_text(
        json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    for k, v in d.items():
        if not k.startswith("_"):
            print(f"  {k:<16} {v}")
    print("-> rapor_sayilari.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
