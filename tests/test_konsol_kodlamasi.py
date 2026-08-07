"""Türkçe konsolda (cp1254) Unicode çıktı veren CLI'ler çökmemeli.

`python zarf.py` doğru zarf tablosunu üretiyor, sonra ✅ karakterini yazarken
UnicodeEncodeError ile düşüyordu: hesap doğru, çıktı çöp. Windows konsolu
cp1254 olduğu sürece bu her ✅/⚠️/α içeren CLI için geçerli.

Repo deyimi: `__main__` içinde akışları utf-8'e çevir. Bu test deyimi SINIF
olarak bağlar — yeni bir CLI aynı tuzağa düşerse burada yakalanır.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

ATLA = ("tests/", ".venv", "build/", "__pycache__")


def _kaynaklar():
    for p in sorted(KOK.rglob("*.py")):
        s = p.relative_to(KOK).as_posix()
        if any(s.startswith(a) or a in s for a in ATLA):
            continue
        yield s, p.read_text(encoding="utf-8", errors="ignore")


def _ascii_disi_print(t: str) -> int:
    return len([m for m in re.findall(r"print\((.{0,300}?)\)\n", t, re.S)
                if any(ord(c) > 127 for c in m)])


def test_ASCII_disi_basan_CLI_akisi_utf8e_ceviriyor():
    kusurlu = []
    for s, t in _kaynaklar():
        if "__main__" not in t:
            continue
        if "reconfigure(encoding" in t:
            continue
        if _ascii_disi_print(t):
            kusurlu.append(s)
    assert not kusurlu, (
        "Bu CLI'ler ASCII-dışı basıyor ama akışı utf-8'e çevirmiyor; Türkçe "
        "konsolda UnicodeEncodeError ile düşerler:\n  " + "\n  ".join(kusurlu))


def test_zarf_CLI_gercekten_utf8_yaziyor():
    """Deyimin varlığı değil ETKİSİ: cp1254 akışa ✅ yazılabiliyor mu."""
    import io
    ham = io.BytesIO()
    akis = io.TextIOWrapper(ham, encoding="cp1254", errors="strict")
    if hasattr(akis, "reconfigure"):
        akis.reconfigure(encoding="utf-8", errors="replace")
    akis.write("✅ α=3° · y⁺=42\n")
    akis.flush()
    assert "✅" in ham.getvalue().decode("utf-8")
