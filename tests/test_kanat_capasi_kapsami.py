"""Kanat çapası YALNIZ Cd doğrular — taşıma bu yolla çözülemiyor (ÖLÇÜLDÜ).

ref_bump="oto" düzeltmesinden sonra sürükleme sağlıklı: y⁺ 407→134 (bant içi),
yüzey yüzü 2.142→30.321, Cd 0.050→0.0236, Richardson 0.0211 (beklenen 0.0204).

Taşıma ise ölçülerek kapatıldı:
  hücre 20.6 KAT artarken Cl yalnız %23 arttı (0.0572 → 0.0705); beklenen 0.329.
  Sebep firar kenarı: kalınlık 3.6 mm, yüzey hücresi 2.8 mm → TE 1.3 HÜCRE.
  Kutta koşulu bir hücrelik firar kenarında kurulamaz → sirkülasyon doğmaz.
  Projenin ≥6 hücre hedefi 0.60 mm hücre, yani yalnız yüzeyde ~775.000 yüz ister
  (şu anki TÜM mesh 803 bin hücre) — bu donanımda çözülemez.
"""
import inspect

import validate_pipeline as vp
from validation_anchors import ANCHORS


def test_kanat_capasi_YALNIZ_Cd_referansi_tasiyor():
    """Taşıma iddiası hiç kurulmamış olmalı; kurulsaydı yanlış olurdu."""
    a = ANCHORS["naca0012_wing_ar6"]
    assert "Cd" in a
    assert "Cl" not in a and "CL" not in a


def test_kanat_capasi_YETERLI_bump_kullaniyor():
    """Kanat GERÇEKTEN çözülmeli — bump=0'da kirişte 13 hücre, CL 18 kat düşüktü.

    2026-08-19: ölçüt "oto" DEĞERİNDEN çözünürlük SONUCUNA bağlandı. Çapa
    Re=6e6'ya taşınınca (kiriş 0,15 -> 3,0 m) "oto" yetmedi ve koşu düştü:
    aracın kendi uyarısı "en ince özellik 11,34 mm, yüzey hücresi 125,0 mm —
    özellik hücrenin 0,09 katı" dedi; 12 katman istendi 0 örüldü, Cl 0,067
    (beklenen 0,33), Cd hatası %163. Aynı uyarı çareyi de yazıyordu:
    "ref_bump=4 ile hedefe ulaşılır ve bütçeye sığar".

    Yani "oto" bu ölçekte doğru seçimi yapamadı. Test artık DEĞERİ değil
    NİYETİ bağlıyor: bump ya otomatik ya da açıkça yeterince yüksek olmalı.
    """
    _gen, _tip, kw = vp._GEOM["naca0012_wing_ar6"]
    bump = kw.get("ref_bump")
    assert bump == "oto" or (isinstance(bump, int) and bump >= 2), (
        f"ref_bump={bump!r} — kanat çözülmez (bump=0'da kirişte 13 hücre)")


def test_TE_cozunurluk_limiti_KAYITLI():
    """Ölçüm koda yazılmazsa aynı arama tekrarlanır."""
    src = inspect.getsource(vp)
    i = src.index('"naca0012_wing_ar6"')
    blok = src[max(0, i - 3000):i + 200]
    for parca in ("1.3 HÜCRE", "Kutta", "775.000", "20.6 KAT"):
        assert parca in blok, parca


def test_TE_hucre_sayisi_aritmetigi():
    """Kayıttaki sayılar tutarlı mı — yazarken yanılmış olmayalım."""
    A, n_yuz, te_m = 0.279, 30321, 0.0036
    h = (A / n_yuz) ** 0.5
    assert 0.0027 < h < 0.0031                      # ~2.8 mm yüzey hücresi
    assert 1.1 < te_m / h < 1.5                     # TE ≈ 1.3 hücre
    h6 = te_m / 6
    assert 700_000 < A / h6 ** 2 < 850_000          # ≥6 hücre için ~775 bin yüz
