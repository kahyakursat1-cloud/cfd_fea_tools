"""band_from_levels — sayısal belirsizlik kuralının TEK KAYNAĞI.

NEDEN: aynı hiyerarşi (LSR > asimptotik Richardson > 3·Δ_M) boru hattında satır-içi
yazılıydı; öğrenme katmanı (gci_advisor) ise kuralı hiç uygulamıyor, koşunun kaydettiği
ESKİ sayıya güveniyordu. Kural bu oturumda beş kez değişti. Ölçülen sonuç: kayıtlı
GCI belleğindeki 10 kaydın 6'sı bugünün kuralından SAPIYOR, en büyüğü 274 kat.

Bu dosya kuralın kendisini, boru hattında ÖLÇÜLMÜŞ vakalarla çivi ler.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from report_generator import band_from_levels  # noqa: E402


def test_ASIMPTOTIK_OLMAYAN_richardson_sayisi_KULLANILMIYOR():
    """Küp çapasında ölçüldü: verdikt "mesh bağımsızlığı GÖSTERİLEMEDİ (p=5.56,
    monoton değil)" derken belirsizlik "%0.045" diyordu — rapor aynı anda hem
    "gösteremedim" hem "mükemmel yakınsak" anlamına geliyordu. Doğru kural
    Eça-Hoekstra U=3·Δ_M ve o dizide %12.3 verir.

    Sayılar UYDURULMADI: vehicle_runs/genel_kup800/sonuc.json'ın kendi seviyeleri.
    O koşunun kaydettiği kaynak etiketi zaten "GCI (asimptotik DEĞİL)" diyordu —
    etiket dürüsttü, yayınlanan sayı değildi."""
    cells = [67144, 241135, 905896]
    cds = [1.08044, 1.03769, 1.04166]           # işaretler değişiyor → salınımlı
    b = band_from_levels(cells, cds)
    assert b["yontem"] == "salinim"
    assert 12.0 <= b["u_pct"] <= 12.7, b
    assert "asimptotik DEĞİL" in b["kaynak"]


def test_4_seviyede_LSR_kullaniliyor():
    """Disk çapası: p=1.75, monotonik, iyi fit → LSR standart dal %2.27."""
    b = band_from_levels([70946, 317881, 867274, 1862301],
                         [1.1206, 1.18681, 1.21812, 1.21838])
    assert b["yontem"] == "lsr"
    assert 2.0 <= b["u_pct"] <= 2.6, b


def test_asimptotik_3_seviye_richardson_kabul():
    """Kural bir ŞEYİ reddetmekle kalmıyor; hak edildiğinde Richardson'ı veriyor.
    2. mertebe temiz dizi + r=1.5 → p≈2, band küçük."""
    h = [0.001 * 1.5 ** i for i in (2, 1, 0)]
    cells = [h_i ** -3 for h_i in h]
    cds = [1.0 + 0.5 * x ** 2 for x in h]
    b = band_from_levels(cells, cds)
    assert b["yontem"] == "richardson" and b["u_pct"] < 1.0, b


def test_ORAN_kapisi_asilamazsa_richardsona_dusulmuyor():
    """Celik 2008: r ≥ 1.3 ŞART. Sıkışık seviyelerde p patlar (ölçüldü: r=1.076'da
    p=-2.338 ve GCI=-%3.167 — negatif belirsizlik fiziksel değildir)."""
    cells = [1000000, 1150000, 1300000]          # r ≈ 1.05 — kapı kapalı
    cds = [1.00, 1.02, 1.021]
    b = band_from_levels(cells, cds)
    assert b["yontem"] == "salinim", "oran kapısı aşılamadan Richardson kullanıldı"


def test_iki_seviye_VEKIL_bant_olarak_isaretleniyor():
    b = band_from_levels([300000, 900000], [1.0, 1.1])
    assert b["yontem"] == "2-mesh" and "vekil" in b["kaynak"]


def test_seviye_yoksa_SAYI_uydurulmuyor():
    assert band_from_levels([], []) is None
    assert band_from_levels([None, None], [1.0, 1.1]) is None
    assert band_from_levels([300000], [1.0]) is None


def test_boru_hatti_kurali_KOPYALAMIYOR():
    """İki-hızlı ayrışmanın önlenmesi: boru hattı satır-içi 3·Δ hesabı yerine
    fonksiyonu ÇAĞIRMALI, yoksa kural altıncı kez değiştiğinde ayrışırlar."""
    src = (ROOT / "vehicle_pipeline.py").read_text(encoding="utf-8")
    assert "band_from_levels" in src
    assert "3.0 * _dm" not in src, "satır-içi kopya geri geldi"
