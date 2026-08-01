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


class TestButceKisiti:
    """Öneri BÜTÇEYİ de kısıt almalı — yoksa tractable OLMAYAN mesh ister.

    ÖLÇÜLDÜ (su57: 20.8 m, 600 m² yüzey, Re 2.1e7, hücre tavanı 2.5M):
        bump  beklenen y+   yüzey yüzü    tractable
          0       3094.5        14.856       ✓
          1       1547.3        59.424       ✓
          2        773.6       237.699       ✓
          3        386.8       950.799       ✓
          4        193.4     3.803.197       ✗   <- y+ bandda AMA butce disi
    Eski hâl yalnız y⁺'a bakıp bump=4'ü seçiyordu → snappyHexMesh TIMEOUT,
    DÖRT koşu boyunca. Saatlerce koşup düşmek yerine baştan söylenmeli.

    Yüzey yüz sayısı İNDİRGENEMEZ: A alanını h boyunda örtmek A/h² yüz eder.
    Domaini daraltmak, bütçeyi dağıtmak, bölgesel iyileştirme — hiçbiri değiştirmez.
    """
    import numpy as _np
    SU57 = {"d": _np.array([20.8126, 4.915, 15.0647]), "A": 600.075}

    @staticmethod
    def _oneri(d, A, butce=2_500_000, V=15.0):
        import numpy as np

        from analysis.openfoam_runner import arka_plan_hucre_boyu
        from vehicle_pipeline import onerilen_ref_bump
        L = float(np.max(d)); dom = (5., 15., 5.)
        dmin = np.array([-dom[0]*L, -dom[2]*L, -dom[2]*L])
        dmax = np.array([d[0]+dom[1]*L, d[1]+dom[2]*L, d[2]+dom[2]*L])
        bg, bi = arka_plan_hucre_boyu(dmin, dmax, L/9, butce)
        return onerilen_ref_bump(bg, 4, V, L, yuzey_alani_m2=A,
                                 hucre_butcesi=butce,
                                 arka_plan_hucre=bi["arka_plan_hucre"])

    def test_TRACTABLE_OLMAYAN_kademe_SECILMIYOR(self):
        o = self._oneri(**self.SU57)
        assert o["bump"] == 3, "butceyi asan bump=4 secilmis"
        secilen = next(d for d in o["denemeler"] if d["bump"] == o["bump"])
        assert secilen["tractable"] is True

    def test_BUTCE_ENGELI_ayri_bir_hukum(self):
        """'Banda hic girilemiyor' ile 'girilebiliyor ama sigmiyor' AYRI seylerdir."""
        o = self._oneri(**self.SU57)
        assert o["butce_engeli"] is True
        assert "BÜTÇESİNE SIĞMIYOR" in o["neden"]
        assert "BASINÇ-BASKIN" in o["neden"]      # ne YAPILABILECEGI de yazili

    def test_GECERLILIK_bandiyla_olculuyor_secim_bandiyla_DEGIL(self):
        """su57'de bump=4 y+=193: secim bandinin (40-150) DISI ama gecerlilik
        bandinin (30-300) ICI. Dar bantla bakilsaydi butce engeli GORULMEZDI."""
        from vehicle_pipeline import YPLUS_BANDI, YPLUS_SECIM_BANDI
        o = self._oneri(**self.SU57)
        d4 = next(d for d in o["denemeler"] if d["bump"] == 4)
        y = d4["beklenen_yplus"]
        assert not (YPLUS_SECIM_BANDI[0] <= y <= YPLUS_SECIM_BANDI[1])
        assert YPLUS_BANDI[0] <= y <= YPLUS_BANDI[1]

    def test_BUTCE_BUYURSE_hukum_DEGISIYOR(self):
        """Kisit gercekten butce mi? Tavani buyut, ulasilan y+ duzelmeli.

        OLCULDU (su57): 2.5M -> y+ 387 (gecerlilik bandi DISI)
                        8M   -> y+ 278 (gecerlilik bandi ICI, savunulabilir)
                        20M  -> y+ 139 (secim bandi ICI)
        Yalnizca dar secim bandina bakan bir hukum 8M'de "uretilemez" diyerek
        YANLIS olurdu — sinir bir esik degil, SUREKLI bir takas."""
        k = self._oneri(**self.SU57)
        o8 = self._oneri(**self.SU57, butce=8_000_000)
        o20 = self._oneri(**self.SU57, butce=20_000_000)
        assert k["beklenen_yplus"] > o8["beklenen_yplus"] > o20["beklenen_yplus"]
        assert k.get("gecerlilik_bandinda") is False       # 387 -> band disi
        assert o8.get("gecerlilik_bandinda") is True       # 278 -> band ici
        assert o20["bandda"] is True                       # 139 -> secim bandi ici

    def test_GECERLILIK_bandindaysa_URETILEMEZ_DEMIYOR(self):
        """8M'de y+=278 savunulabilir; 'sürtünme çözülemez' demek yanlis olurdu."""
        o = self._oneri(**self.SU57, butce=8_000_000)
        assert "ÜRETİLEMEZ" not in o["neden"]
        assert "savunulabilir" in o["neden"]

    def test_kucuk_geometri_ETKILENMIYOR(self):
        import numpy as np
        o = self._oneri(np.array([0.704, 1.5, 0.08]), 2.1)
        assert o["bandda"] is True

    def test_yuzey_alani_YOKSA_kisit_uygulanmiyor(self):
        """Olcum yoksa uydurma bir kisitla kademe kirpilmaz."""
        import numpy as np

        from analysis.openfoam_runner import arka_plan_hucre_boyu
        from vehicle_pipeline import onerilen_ref_bump
        d = self.SU57["d"]
        L = float(np.max(d))
        bg, _ = arka_plan_hucre_boyu(np.array([-5*L, -5*L, -5*L]),
                                     np.array([16*L, 5*L, 5*L]), L/9, 2_500_000)
        o = onerilen_ref_bump(bg, 4, 15.0, L)
        assert all(x["tractable"] for x in o["denemeler"])


def test_yuzey_yuz_tahmini_INDIRGENEMEZ():
    """A/h² — alanı o çözünürlükte örtmenin maliyeti."""
    from vehicle_pipeline import yuzey_yuz_tahmini
    n = yuzey_yuz_tahmini(600.075, 3.21565, 8)      # su57 bump=4
    assert 3.7e6 < n < 3.9e6
    assert yuzey_yuz_tahmini(600.075, 3.21565, 7) == pytest.approx(n / 4, rel=0.01)
