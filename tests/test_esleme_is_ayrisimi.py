"""Arayüz işi: ÜRETİMDEKİ eşleme mi kaybediyor, terk edilmiş şema mı?

DIŞ HAKEM BU DEPONUN EN CİDDİ FSI PROBLEMİ OLARAK ``arayüz işi korunumu''nu
işaretledi ve haklı bir sayıya dayandı: kayıtta en kötü iş artığı %102,64.
Kayıt bunu ``izdüşüm kaymasına'' bağlıyordu.

ÖLÇÜLDÜ VE ATIF YANLIŞTI. `arayuz_isi_hatasi` iki tensörü kıyaslıyor:
düğüm momenti (ÜRETİMDEKİ korunumlu şema, CFD yüzlerinden) ve yüz momenti
(TERK EDİLMİŞ tutarlı şema, FEA yüzünde yeniden integre edilmiş). Yani
metrik şemaları kıyaslıyor, eşlemeyi ölçmüyor. Aynı vakada terk edilmiş
şemanın toplam kuvvetinin İŞARETİ bile ters çıkabiliyor.

Doğru referans CFD tarafıdır ve orada bir KİMLİK var. Baryentrik ağırlıklar
doğrusal alanları birebir ürettiği için:

    T_düğüm - T_cfd  ==  Σ_f dF_f ⊗ δ_f ,    δ_f = Σ_k w_k x_k - x_cfd,f

yani eşlemenin iş kaybı TAM OLARAK izdüşüm sapmasıdır. Turek--Hron FSI1'de
ölçüldü: eşleme payı %0,000000, yüzey payı %0,6457 --- toplamın tamamı
terk edilmiş şemadan geliyor.

BUNUN SONUCU BİR TASARIM KURALIDIR, ARAŞTIRMA KONUSU DEĞİL: eşlemenin iş
kaybını azaltmak için mortar/RBF'ye geçmek gerekmez; alıcı yüzeyin verici
yüzeyi çözmesi yeter. δ ölçülebilir ve kuplaj koşulmadan önce bakılabilir.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

VTK = KOK / "turek_hron_cfd1_case" / "VTK" / "bayrak" / "bayrak_445.vtk"


def _kos(stl: Path):
    from coupling_fsi import cfd_pressure_to_fea_loads
    return cfd_pressure_to_fea_loads(str(VTK), str(stl), rho=1000.0,
                                     p_is_kinematic=True)


@pytest.fixture(scope="module")
def ince(tmp_path_factory):
    """İNCE alıcı yüzey: CFD'yi rahatça çözüyor (9140 üçgen / 292 yüz)."""
    if not VTK.exists():
        pytest.skip("CFD1 VTK'sı yok (python experiments/turek_hron_cfd1.py)")
    from turek_hron_fsi1 import _bayrak_stl
    yol = tmp_path_factory.mktemp("ince") / "bayrak.stl"
    _bayrak_stl(yol, 160)
    return _kos(yol)


@pytest.fixture(scope="module")
def kaba(tmp_path_factory):
    """KABA alıcı yüzey: CFD'den çok daha az üçgen --- δ'nın büyümesi
    BEKLENİR ve ölçütün yanlış-negatif kapısı budur."""
    if not VTK.exists():
        pytest.skip("CFD1 VTK'sı yok")
    from turek_hron_fsi1 import _bayrak_stl
    yol = tmp_path_factory.mktemp("kaba") / "bayrak.stl"
    _bayrak_stl(yol, 2)
    return _kos(yol)


def test_KIMLIK_TUTUYOR(ince):
    """Açıklamanın kendisi sınanır. Kimlik tutmuyorsa 'iş kaybı izdüşüm
    sapmasıdır' cümlesi bir iddia olarak kalır ve kullanılamaz."""
    s = ince["esleme_sapmasi"]
    assert s is not None, "korunumlu şemada sapma kaydı üretilmemiş"
    assert s["kimlik_artigi"] < 1e-6, (
        f"kimlik artığı {s['kimlik_artigi']:.2e} --- 'iş kaybı = izdüşüm "
        "sapması' açıklaması bu veriyle desteklenmiyor")


def test_INCE_YUZEYDE_ESLEME_PAYI_IHMAL_EDILEBILIR(ince):
    """Asıl düzeltme. Kayıttaki iş artığının tamamı yüzey payından
    geliyorsa, üretimdeki eşleme suçlanamaz."""
    s = ince["esleme_sapmasi"]
    assert s["esleme_isi_artigi"] < 1e-4, (
        f"eşleme payı %{100 * s['esleme_isi_artigi']:.4f}")
    # Ve toplam artik GERCEKTEN sifir degil --- yoksa test hicbir sey
    # ayirt etmez; ayrisimin anlami toplamin BASKA bir yerden gelmesidir.
    assert ince["arayuz_isi_hatasi"] > 10 * s["esleme_isi_artigi"], (
        "toplam iş artığı da sıfıra yakın; bu vaka ayrışımı göstermiyor")
    assert s["yuzey_isi_artigi"] > 0.9 * ince["arayuz_isi_hatasi"]


def test_KABA_YUZEYDE_ESLEME_PAYI_BUYUYOR(kaba, ince):
    """YANLIŞ-NEGATİF KAPISI. 'Eşleme payı ihmal edilebilir' cümlesi
    KOŞULLUDUR: alıcı yüzey vericiyi çözdüğünde. Çözmediğinde δ büyür ve
    ölçüt bunu GÖRMELİDİR --- görmezse ölçüt kör demektir."""
    sk, si = kaba["esleme_sapmasi"], ince["esleme_sapmasi"]
    assert sk["en_buyuk_olcekli"] > si["en_buyuk_olcekli"], (
        "kaba yüzeyde izdüşüm sapması büyümüyor; ölçüt çözünürlüğe "
        "duyarsız")
    assert sk["esleme_isi_artigi"] > 100 * max(si["esleme_isi_artigi"], 1e-12)


def test_KIMLIK_KABA_YUZEYDE_de_TUTUYOR(kaba):
    """Kimlik bir cebirsel özdeşliktir; yalnız iyi vakada tutuyorsa
    tesadüftür."""
    assert kaba["esleme_sapmasi"]["kimlik_artigi"] < 1e-6


def test_DELTA_OLCEKLI_OLARAK_RAPORLANIYOR(ince):
    """Mutlak δ [m] geometri boyutuna bağlıdır ve vakalar arası
    kıyaslanamaz; FEA yüz ölçeğine bölünmüş hâli kıyaslanabilir."""
    s = ince["esleme_sapmasi"]
    for alan in ("ortalama_m", "en_buyuk_m", "fea_yuz_olcegi_m",
                 "ortalama_olcekli", "en_buyuk_olcekli"):
        assert alan in s
    assert s["fea_yuz_olcegi_m"] > 0
    assert s["en_buyuk_olcekli"] == pytest.approx(
        s["en_buyuk_m"] / s["fea_yuz_olcegi_m"], rel=1e-3, abs=1e-4)


def test_AYRISIM_KAYITTA_ACIKLANIYOR(ince):
    """Sayı doğru olsa bile, hangi payın üretimi ilgilendirdiği yazılı
    olmazsa okur yine toplamı üretime yazar --- hakemin yaptığı buydu."""
    s = ince["esleme_sapmasi"]
    assert "ESKI semanin" in s["_ayrisim"]
    assert "uretim yolunda" in s["_ayrisim"]
    assert "inceltmek" in s["_kimlik"]


def test_TOPLAM_ESLEME_ARTI_YUZEY_ile_TUTARLI(ince):
    """Ayrışım bir toplam iddiasıdır ve üçgen eşitsizliğine uymalı;
    uymuyorsa parçalar aynı büyüklüğün parçaları değildir."""
    s = ince["esleme_sapmasi"]
    toplam = ince["arayuz_isi_hatasi"]
    assert toplam <= s["esleme_isi_artigi"] + s["yuzey_isi_artigi"] + 1e-9
    assert np.isfinite(toplam)
