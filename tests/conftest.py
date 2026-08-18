"""Pytest yapilandirmasi.

Modüller su an depo kökünde flat (Faz 4'te src/ paketine tasinacak). Testlerin
`import structural_loads` gibi çalışabilmesi için kökü sys.path'e ekliyoruz.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


@pytest.fixture
def bellek_kapisi_acik(monkeypatch):
    """Bellek kapısını bu test için aç --- kapıyı SINAMAYAN kuyruk testleri için.

    NEDEN GEREKLİ (ölçüldü 2026-08-18): kuyruk sözleşmesini sınayan dört test,
    geliştirme makinesinde RAM %85 dolu olduğu için düşüyordu. Kuyruk işi doğru
    davranıp BEKLETİYOR, dolayısıyla `sonuc` hiç yazılmıyor ve testler
    `KeyError: 'sonuc'` ile patlıyordu. Yani kırmızı, üretim kodunun değil
    makinenin boş belleğinin fonksiyonuydu; üstelik hata mesajı nedeni
    söylemiyordu.

    Kapının KENDİSİ `test_bellek_kapisi.py`'de sınanır ve orada eşik açıkça
    0,5 GB'a çekilir; bu fixture onu zayıflatmaz --- yalnız konusu bellek
    olmayan testleri makinenin o anki yükünden ayırır.

    OTOMATİK (autouse) DEĞİL: bir üretim kapısını tüm pakette sessizce açmak,
    başka bir yerde gerçek bir kusuru gizleyebilirdi. Kullanan test onu adıyla
    ister.
    """
    import bellek_kapisi
    monkeypatch.setattr(bellek_kapisi, "bos_bellek_gb", lambda: 999.0)
