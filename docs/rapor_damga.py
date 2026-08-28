"""Rapor kapagindaki damga ELLE TASINMAZ --- olculur.

NEDEN. Kapak "22 Agustos 2026 / 38.224 satir / 188 test dosyasi / 1.917
gecen test" diyordu. Tarih alti gun, test sayisi 354 test eskiydi; ikisi de
elle yazilmisti ve kimse yenilemiyordu. Bir dis hakem bunu yakaladi:
kapak tarihi raporun gercek revizyon tarihini temsil etmiyordu.

Bu betik damgayi olcup `rapor_damga.tex`e yazar; rapor onu `\\input` eder.
Sayilar UCUZ ve DURUST olanlardir:

  - satir sayisi ve test dosyasi sayisi: dosya sisteminden sayilir
  - test FONKSIYONU sayisi: sozdizimi agacindan sayilir --- "gecen test"
    DEGIL, cunku onu bilmek suiti kosmayi gerektirir ve kapak bir olcum
    yapmadan "gecti" diyemez
  - surum: git kisa ozeti (+ calisma agaci kirliyse isaret)
  - tarih: damganin uretildigi gun

    python docs/rapor_damga.py
Cikti: docs/rapor_damga.tex
"""
from __future__ import annotations

import ast
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
CIKTI = HERE / "rapor_damga.tex"

ATLA = (".venv", "build", "__pycache__", ".git")

AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
         "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def _yetkili_kod_satiri() -> int:
    """Kod satirini OLCEN yer `experiments/rapor_sayilari`dir; damga onu
    cagirir. Ayri bir sayim kurmak raporun icinde iki farkli "kod satiri"
    yaratirdi ve bu rapor tam da o ayrismalari avlayan bir sistemi
    anlatiyor."""
    import sys as _s
    _s.path.insert(0, str(KOK / "experiments"))
    from rapor_sayilari import kod_satiri
    return int(kod_satiri())


def _py_dosyalar():
    for p in KOK.rglob("*.py"):
        if any(a in p.parts for a in ATLA):
            continue
        yield p


def _binlik(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def olc() -> dict:
    # SATIR SAYISININ YETKILISI BU BETIK DEGIL. `experiments/rapor_sayilari`
    # zaten "kok + analysis/" tanimiyla olcuyor ve raporun kalite tablosu ona
    # bagli. Burada kendi tanimimi kurunca ikinci bir kaynak dogdu ve ayni
    # etikete uc kat buyuk bir sayi (her .py) yaziyordu; okur ikisini ayni
    # sey sanardi. Yetkili cagrilir, tekrar edilmez.
    satir_kod = _yetkili_kod_satiri()
    satir_toplam = 0
    test_dosya = 0
    test_fn = 0
    atlanan: list[str] = []
    for p in _py_dosyalar():
        try:
            src = p.read_text(encoding="utf-8")
        # sessiz-yutma: kabul — SESSIZ DEGIL: bu betigin amaci dogru sayi
        # vermek, o yuzden atlanan dosya ADIYLA kaydedilir ve cikti "sayilar
        # EKSIK" uyarisini basar
        except (OSError, UnicodeDecodeError) as e:
            atlanan.append(f"{p.name}: {type(e).__name__}")
            continue
        satir_toplam += src.count("\n") + 1
        if p.parent.name != "tests" or not p.name.startswith("test_"):
            continue
        test_dosya += 1
        try:
            agac = ast.parse(src)
        # sessiz-yutma: kabul — ayni gerekce: ayristirilamayan test dosyasi
        # ADIYLA kaydedilir, sayinin eksik oldugu ciktida yazar
        except SyntaxError as e:
            atlanan.append(f"{p.name}: SyntaxError satır {e.lineno}")
            continue
        test_fn += sum(
            1 for n in ast.walk(agac)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith("test_"))
    return {"satir_kod": satir_kod, "satir_toplam": satir_toplam,
            "test_dosya": test_dosya, "test_fn": test_fn,
            "atlanan": atlanan, "surum": _surum(), "tarih": _tarih()}


def _surum() -> str:
    def _git(*a) -> str | None:
        try:
            r = subprocess.run(("git", *a), cwd=KOK, capture_output=True,
                               text=True, timeout=20)
        # sessiz-yutma: kabul — sebep cagirana TASINIYOR: None donunce kapak
        # "surum bilinmiyor (git yok)" basar, yani okur eksigi GORUR
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout.strip() if r.returncode == 0 else None

    ozet = _git("rev-parse", "--short", "HEAD")
    if not ozet:
        return "sürüm bilinmiyor (git yok)"
    kirli = _git("status", "--porcelain")
    return ozet + (" + kayıtsız değişiklik" if kirli else "")


def _tarih() -> str:
    b = date.today()
    return f"{b.day} {AYLAR[b.month - 1]} {b.year}"


def yaz(d: dict) -> str:
    return (
        "% URETILMIS DOSYA --- ELLE DUZENLEME. Kaynak: docs/rapor_damga.py\n"
        "\\newcommand{\\raporSatirKod}{" + _binlik(d["satir_kod"]) + "}\n"
        "\\newcommand{\\raporSatirToplam}{" + _binlik(d["satir_toplam"])
        + "}\n"
        "\\newcommand{\\raporTestDosya}{" + str(d["test_dosya"]) + "}\n"
        "\\newcommand{\\raporTestFn}{" + _binlik(d["test_fn"]) + "}\n"
        "\\newcommand{\\raporSurum}{" + d["surum"] + "}\n"
        "\\newcommand{\\raporTarih}{" + d["tarih"] + "}\n")


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    d = olc()
    CIKTI.write_text(yaz(d), encoding="utf-8")
    print(f"{_binlik(d['satir_kod'])} satır çekirdek kod "
          f"({_binlik(d['satir_toplam'])} toplam) · "
          f"{d['test_dosya']} test dosyası · "
          f"{_binlik(d['test_fn'])} test fonksiyonu · {d['surum']} · "
          f"{d['tarih']}")
    if d["atlanan"]:
        print(f"UYARI: {len(d['atlanan'])} dosya okunamadı/ayrıştırılamadı, "
              f"sayılar EKSİK: {', '.join(d['atlanan'][:5])}")
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
