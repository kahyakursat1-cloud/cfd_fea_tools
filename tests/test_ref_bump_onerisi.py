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


# 12-geometrilik taramada OLCULEN 11 gecerli nokta:
#   (ad, secilen_bump, o kosuda OLCULEN y+)
OLCULEN = [
    ("minihawk_vtol", 0, 116.86), ("multikopter", 1, 38.6), ("gripen", 1, 58.62),
    ("kup800", 1, 65.16), ("ciftkuyruk", 2, 74.29), ("kaldirici", 2, 60.49),
    ("izgara", 2, 48.06), ("kapsul", 2, 101.17), ("a320", 3, 57.53),
    ("okkanat", 3, 60.53), ("gondol", 4, 65.26),
]


def test_OLCULEN_y_arti_HEPSI_BANDDA():
    """Oto kademe ile 11 geometrinin 11'i de duvar-fonksiyonu bandina girdi."""
    for ad, _b, y in OLCULEN:
        assert YPLUS_BANDI[0] <= y <= YPLUS_BANDI[1], f"{ad}: y+={y} band disi"


def test_kalibrasyon_ORTALAMAYA_FIT_EDILMEDI():
    """Az tahmin TEHLIKELI (kucuk kademe -> y+ bant USTU), fazla tahmin yalnizca
    PAHALI. Asimetrik risk: katsayi medyana cekilmez, bant KISITIYLA secilir.
    Olculen tahmin/olcum medyani 1.82 idi; katsayi ona bolunseydi (1.2/1.82=0.66)
    tutuculuk tamamen kaybolurdu."""
    from vehicle_pipeline import YPLUS_KALIBRASYON
    assert 0.85 <= YPLUS_KALIBRASYON <= 1.0, "medyana fit edilmis olabilir"


def test_secilen_katsayi_HICBIRINI_BAND_DISINA_CIKARMIYOR():
    """Kalibrasyon degisikliginin ASIL kisiti: 11 olculen noktanin hicbiri
    bandin disina dusmemeli. Kademe basina y+ yarilanir."""
    from vehicle_pipeline import YPLUS_KALIBRASYON as K
    for ad, b, y in OLCULEN:
        # bu geometri icin yeni katsayida secilecek kademe
        yb = y * (2 ** b) / (K / 1.2)      # bump=0'daki TAHMIN (eski katsayi tabanli olcum)
        nb = 0
        while nb <= 4 and not (40.0 <= yb / (2 ** nb) <= 150.0):
            nb += 1
        nb = min(nb, 4)
        yeni_y = y * (2 ** (b - nb))
        assert YPLUS_BANDI[0] <= yeni_y <= YPLUS_BANDI[1], (
            f"{ad}: kademe {b}->{nb}, y+ {y:.0f}->{yeni_y:.0f} BANT DISI")


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


class TestOtoRefBump:
    """ref_bump="oto": geometri-BAŞINA hesapla.

    Sabit bir sayı tüm geometrilere uymuyor — ÖLÇÜLDÜ: `--ref-bump 2` çoğunda y⁺'ı
    banda soktu ama `multikopter_kucuk`ta y⁺=25 verdi, bandın (30-300) ALTINDA.
    Ters problem: o geometride mesh duvar fonksiyonu için fazla ince kalmış.
    Doğru kademe gövde boyutuna ve hıza bağlıdır.

    Bu SESSİZ EZME DEĞİL: çağıran açıkça "oto" diyerek devrediyor. Sayı verirse
    o sayı aynen kullanılır ve yalnız ÖNERİ raporlanır.
    """
    @staticmethod
    def _src():
        import inspect

        import vehicle_pipeline as vp
        return inspect.getsource(vp.run_vehicle_analysis)

    def test_oto_destekleniyor(self):
        assert '"oto"' in self._src() or "'oto'" in self._src()

    def test_oneri_CFDCase_KURULMADAN_ONCE_uygulaniyor(self):
        """Sonradan uygulanırsa mesh yine eski bump ile üretilir."""
        s = self._src()
        assert s.index("_oto and _oneri") < s.index("case = CFDCase(")

    def test_SAYI_verilince_EZILMIYOR(self):
        """Açık sayı = çağıranın kararı; öneri yalnız raporlanır."""
        s = self._src()
        i = s.index("_oto = ")
        blok = s[i:i + 400]
        assert "isinstance(ref_bump, str)" in blok      # yalniz "oto" tetikler

    def test_uygulandi_KAYDA_giriyor(self):
        assert '"uygulandi"' in self._src()

    def test_tarama_varsayilani_OTO(self):
        import inspect

        import experiments.guvenilirlik_taramasi as gt
        src = inspect.getsource(gt.main)
        assert '"--ref-bump", default="oto"' in src
