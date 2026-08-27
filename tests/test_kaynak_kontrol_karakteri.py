"""Kaynak dosyalarında KONTROL KARAKTERİ olmamalı — sessiz regex bozucu.

BU KUSUR BİR OTURUMDA ÜÇ KEZ ÇIKTI ve her seferinde SESSİZDİ:

  1. `\\b` kelime-sınırı kaçışı 0x08 (backspace) olarak yazıldı; desen
     hiçbir şeye uymadı ve kapsam ölçümü kendi lehine bozuldu.
  2. `\\1` geri-referansı 0x01 (SOH) olarak yazıldı; `re.sub` yakalanan
     grubu ATTI ve OpenFOAM boundary dosyasında yama ADINI sildi ---
     `gmshToFoam` "Patch 0 gets name ya" dedi, ağ yamasız kaldı.
  3. Aynı sınıf bir üçüncü kez, aynı sebeple.

ORTAK MEKANİZMA: kaynak dosyası bir kabuk here-doc'u içinden yazıldığında
`\\b`, `\\1`, `\\n` gibi diziler bir kez fazla çözülüyor ve dosyaya
GÖRÜNMEZ bir bayt olarak düşüyor. `grep` onları göstermez, gözle okuma
yakalamaz, ruff sözdizimi hatası bulmaz --- kod ÇALIŞIR ve YANLIŞ davranır.

BU TEST O SINIFI KAPATIR. Ölçüt basit ve geneldir: metin dosyalarında
sekme/satırsonu dışında kontrol karakteri yoktur.
"""
from __future__ import annotations

from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
# Taranan yerler: kod ve kanit/belge metinleri. Uretilen ikili ciktilar
# (pdf, png, msh) DISARIDA --- onlarda kontrol karakteri normaldir.
DESENLER = ("*.py", "experiments/*.py", "analysis/*.py", "tests/*.py",
            "docs/*.tex", "*.json")
# Sekme, satirsonu ve satirbasi MESRU. Geri kalan her sey supheli.
IZINLI = {0x09, 0x0A, 0x0D}


def _tara(yol: Path) -> list[str]:
    try:
        t = yol.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return []          # ikili ya da okunamayan dosya: bu testin konusu degil
    return sorted({hex(ord(c)) for c in t if ord(c) < 32 and ord(c) not in IZINLI})


def test_KAYNAKTA_kontrol_karakteri_YOK():
    kirli = {}
    for desen in DESENLER:
        for yol in KOK.glob(desen):
            kotu = _tara(yol)
            if kotu:
                kirli[str(yol.relative_to(KOK))] = kotu
    assert not kirli, (
        f"kontrol karakteri taşıyan dosya(lar): {kirli}. Bu sessiz bir regex "
        "bozucudur: `\\b` 0x08'e, `\\1` 0x01'e dönüşür; desen hiçbir şeye "
        "uymaz ya da yakalanan grup atılır ve KOD ÇALIŞMAYA DEVAM EDER.")


def test_OLCUT_gercekten_YAKALIYOR(tmp_path):
    """Yanlış-negatif kapısı: tarama bozuk bir dosyayı GERÇEKTEN bulmalı.
    Bulmuyorsa yukarıdaki testin yeşil olması hiçbir şey söylemez."""
    kirli = tmp_path / "bozuk.py"
    kirli.write_text("desen = '\x08kelime\x08'\n", encoding="utf-8")
    assert _tara(kirli) == ["0x8"]
    temiz = tmp_path / "temiz.py"
    temiz.write_text("desen = r'\\bkelime\\b'\n\tsekme\n", encoding="utf-8")
    assert _tara(temiz) == []
