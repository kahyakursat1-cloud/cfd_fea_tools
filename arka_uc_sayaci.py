"""Arka uç katmanını atlayan çağrıların sayacı — artmasın diye.

NEDEN: `analysis/backend.py` çözücünün nerede koşacağını tek yerden seçer
(WSL ya da Docker konteyneri, `CFD_BACKEND`). Ama kök dizindeki birçok betik
`wsl bash -c` çağrısını ELLE kuruyor ve o katmanı atlıyor. Sonuç sessizdir ve
tehlikelidir: `CFD_BACKEND=docker` ayarlandığında araç hattı konteynere
giderken bu betikler WSL'de kalır — aynı kampanyanın iki yarısı FARKLI
çözücülerde koşabilir ve kanıt dosyaları bunu söylemez. WSL distro seçimi de
atlanır.

NEDEN HEPSİ BİRDEN TAŞINMIYOR: 24 dosya, bir kısmı yarış-durumu ve zaman-aşımı
inceliklerine sahip (`construct2d_bridge` süreç ağacını elle yokluyor). Toplu
yeniden yazım, ölçülmemiş bir riski tek commit'e sıkıştırmak olurdu; depo
kuralı da bunu söylüyor ("çalışan koda dokunma, cerrahi değişiklik").

BU YÜZDEN SAYAÇ: mevcut durum ölçülür ve TABAN'a bağlanır. Yeni kod bu sayıyı
ARTIRAMAZ; taşınan her modül tabanı düşürür. `sessiz_yutma` sayacıyla aynı
desen — depo bu mekanizmayı zaten kullanıyor.

    python arka_uc_sayaci.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent

# Tasima katmanini MESRU olarak kuran tek yer; sayilmaz.
MUAF = {"analysis/backend.py", "arka_uc_sayaci.py"}
DESEN = re.compile(r"""wsl["'\s]*bash\s+-c|\[\s*["']wsl["']\s*,""")


def _kaynak_dosyalari() -> list[Path]:
    out = []
    for p in sorted(KOK.rglob("*.py")):
        r = p.relative_to(KOK).as_posix()
        if r.startswith(("tests/", ".venv/", "_")) or "site-packages" in r:
            continue
        out.append(p)
    return out


def tara() -> list[dict]:
    """Arka uç katmanını atlayan her satır (yorum satırları HARİÇ)."""
    bulgu = []
    for p in _kaynak_dosyalari():
        rel = p.relative_to(KOK).as_posix()
        if rel in MUAF:
            continue
        for i, satir in enumerate(p.read_text(encoding="utf-8",
                                              errors="replace").splitlines(), 1):
            if satir.lstrip().startswith("#"):
                continue          # gerekçe yazan yorum sayılmaz
            if DESEN.search(satir):
                bulgu.append({"dosya": rel, "satir": i,
                              "kod": satir.strip()[:100]})
    return bulgu


def ozet() -> dict:
    b = tara()
    dosyalar: dict[str, int] = {}
    for x in b:
        dosyalar[x["dosya"]] = dosyalar.get(x["dosya"], 0) + 1
    return {"toplam": len(b), "dosya_sayisi": len(dosyalar),
            "dosyalar": dict(sorted(dosyalar.items())), "bulgular": b}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    o = ozet()
    print(f"Arka uç katmanını atlayan çağrı: {o['toplam']} satır, "
          f"{o['dosya_sayisi']} dosya\n")
    for d, n in o["dosyalar"].items():
        print(f"  {n:>3}  {d}")
    print("\nTaşıma: yerel `wsl bash -c` kurulumunu analysis.backend.linux_run "
          "ile değiştirin; bash gövdesi AYNEN kalır, değişen yalnız taşımadır.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
