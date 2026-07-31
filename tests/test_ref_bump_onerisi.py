"""ref_bump ML eylem uzayına girmeli — kazanan kaldıraç oydu.

`auto_pilot` yalnız hizli/standart/hassas seçiyordu; ref_bump preset'in SABİT bir
alanıydı. Ama ölçüldü ki y⁺'ı duvar-fonksiyonu bandına sokan tek kaldıraç budur:
kök-sebep düzeltmesinden SONRA bile varsayılan y⁺=340 veriyordu, +2 ise 112.
Sınıflandırıcı %95 doğrulukla seçim yapıyordu ama seçtiği üç seçeneğin ÜÇÜ DE
bandın dışındaydı — kazanan kaldıraç eylem uzayında YOKTU.

ÖLÇÜLEN ÇAPA (MiniHawk, lmax 1.5 m, V=15 m/s, katmansız, bg=0.3072 m):
    cagiran=1 -> ref_max 5 -> y+ 340   (yuzey 3060 yuz  — iyilestirme TAM DEGIL)
    cagiran=2 -> ref_max 6 -> y+ 112   (yuzey 32588 yuz)
    cagiran=3 -> ref_max 7 -> y+  61   (yuzey 99652 yuz)
"""
import math

import pytest

from vehicle_pipeline import (
    YPLUS_BANDI,
    YPLUS_SECIM_BANDI,
    beklenen_yplus,
    onerilen_ref_bump,
)

BG = 0.3072          # MiniHawk arka plan hucresi (arka_plan_hucre_boyu ile olculdu)
V, LREF = 15.0, 1.5


@pytest.mark.parametrize("ref_max,olculen", [(6, 112.3), (7, 61.4)])
def test_formul_OLCULEN_noktalari_yakaliyor(ref_max, olculen):
    """Iyilestirmenin GERCEKTEN uygulandigi iki nokta; %15 icinde olmali."""
    t = beklenen_yplus(BG, ref_max, V, LREF)
    assert abs(t - olculen) / olculen < 0.15, f"tahmin {t:.1f} vs olcum {olculen}"


def test_kalibrasyon_UYDURULMAMIS():
    """Kalibrasyon iki olculen noktadan geliyor; degisirse test kirilsin."""
    from vehicle_pipeline import YPLUS_KALIBRASYON
    assert 1.1 <= YPLUS_KALIBRASYON <= 1.3


def test_MINIHAWK_icin_OLCULEN_calisan_ayari_oneriyor():
    o = onerilen_ref_bump(BG, 4, V, LREF)
    assert o["bump"] == 2 and o["bandda"] is True


def test_SECIM_bandi_GECERLILIK_bandindan_DAR():
    """bump=1'de tahmin 238 (gecerlilik bandi ICI) iken OLCULEN 340 (DISI) cikti —
    cunku iyilestirme tam uygulanmadi. Secimde pay birakilmali."""
    assert YPLUS_SECIM_BANDI[0] >= YPLUS_BANDI[0]
    assert YPLUS_SECIM_BANDI[1] < YPLUS_BANDI[1]
    t1 = beklenen_yplus(BG, 5, V, LREF)          # bump=1
    assert YPLUS_BANDI[0] <= t1 <= YPLUS_BANDI[1]        # genis bantta gecerdi
    assert t1 > YPLUS_SECIM_BANDI[1]                      # dar bantta GECMIYOR


def test_en_UCUZ_kademe_seciliyor():
    """Her kademe hucre sayisini ~8x artirir; banda giren ILK kademe alinmali."""
    o = onerilen_ref_bump(BG, 4, V, LREF)
    onceki = beklenen_yplus(BG, 4 + o["bump"] - 1, V, LREF)
    assert onceki > YPLUS_SECIM_BANDI[1]


def test_bandda_degilse_ACIKCA_soyluyor():
    """Cok dusuk hizda hicbir kademe bandi tutturamaz — sessizce en iyiyi vermek yanlis."""
    o = onerilen_ref_bump(BG, 4, 0.5, LREF, tavan=2)
    assert o["bandda"] is False and "neden" in o
    assert "denemeler" in o and len(o["denemeler"]) == 3


def test_y_arti_kademe_basina_YARILANIYOR():
    a = beklenen_yplus(BG, 5, V, LREF)
    b = beklenen_yplus(BG, 6, V, LREF)
    assert math.isclose(a / b, 2.0, rel_tol=1e-9)
