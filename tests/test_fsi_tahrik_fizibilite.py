"""Sürülen FSI kıyası neden ulaşılamıyor — çelişki NİCELLEŞTİRİLDİ.

Çözünürlük ve esneklik AYNI büyüklüğe (t/L) ZIT yönde basar:

    çözünürlük:  t/L ≥ 6/D            (kalınlık en az 6 hücre)
    esneklik  :  t/L ≤ (k·q/(hedef·E))^(1/3)

İkisi birleşince D ≥ 6·(hedef·E/(k·q))^(1/3). D'nin E ve q'ya KÜP-KÖK bağlı
olması sonucu belirler: malzemeyi 100 kat yumuşatmak ağı yalnız 4,6 kat
ucuzlatır. Yani bu bir DONANIM sorunundan çok bir GEOMETRİ-AİLESİ sorunudur.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from fsi_tahrik_fizibilite import gereken_D, kalibre_k  # noqa: E402


def test_k_OLCULEN_kosuya_oturuyor():
    """Kalibrasyon kendi girdisini geri vermeli; vermezse cebir yanlıştır."""
    E, q, r = 69e9, 296.5, 300.0
    k = kalibre_k(0.0247, E, q, r)
    geri = k * (q / E) * r ** 3
    assert geri == pytest.approx(0.0247, rel=1e-9)


def test_D_malzemeye_KUP_KOK_bagli():
    """Yumuşak malzeme ucuz ağ DEMEK DEĞİL: 100 kat yumuşama 4,64 kat kazanç.

    Bu, "daha yumuşak malzeme seç, sorun çözülür" beklentisini çürütür ve
    fizibilite hükmünün neden malzeme değişimiyle kurtarılamadığını açıklar.
    """
    k, q = 0.213, 296.5
    d1 = gereken_D(69e9, q, k)
    d2 = gereken_D(0.69e9, q, k)          # 100 kat yumusak
    assert d1 / d2 == pytest.approx(100 ** (1 / 3), rel=1e-6)
    assert d1 / d2 < 5.0, "kazanç küp-kök; 100 kat yumuşama 100 kat ucuz DEĞİL"


def test_D_hiza_da_KUP_KOK_bagli():
    """q ~ V², D ~ q^(-1/3) → D ~ V^(-2/3). Hızı katlamak da ucuz kurtarmaz."""
    k, E = 0.213, 69e9
    d1 = gereken_D(E, 0.5 * 1.225 * 22 ** 2, k)
    d2 = gereken_D(E, 0.5 * 1.225 * 44 ** 2, k)
    assert d1 / d2 == pytest.approx(4 ** (1 / 3), rel=1e-6)


def test_KANIT_bu_makinede_ULASILAMAZ_diyor():
    p = KOK / "fsi_tahrik_fizibilite.json"
    if not p.exists():
        pytest.skip("fsi_tahrik_fizibilite.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["bu_makinede_uygun"] == 0
    assert "ULASILAMAZ" in d["verdikt"]
    assert d["senaryolar"], "senaryo listesi boş"


def test_KANIT_yalniz_IYIMSER_ucu_alintilamiyor():
    """Hücre kestirimi bir BAND (D² ile D³ arası); tek sayı yayımlamak
    ölçülmemiş bir kesinlik yayımlamak olurdu."""
    p = KOK / "fsi_tahrik_fizibilite.json"
    if not p.exists():
        pytest.skip("fsi_tahrik_fizibilite.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    if not d.get("en_ucuz_ulasilabilir"):
        pytest.skip("iş istasyonunda da uygun senaryo yok")
    assert d.get("en_ucuzun_kotumser_ucu"), "bandın kötümser ucu kayıtta yok"
    assert d["en_ucuzun_kotumser_ucu"]["bellek_GB"] > \
        d["en_ucuz_ulasilabilir"]["bellek_GB"]
    assert "BAND" in d["verdikt"] and "ÖLÇÜLMEDİ" in d["verdikt"]


def test_k_AYNI_AILE_disinda_kullanilmaz_UYARISI_yazili():
    """Tek noktadan kalibre edilen katsayı genellenirse sessizce yanlış olur."""
    p = KOK / "fsi_tahrik_fizibilite.json"
    if not p.exists():
        pytest.skip("fsi_tahrik_fizibilite.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "AYNI ailede" in d["kalibrasyon"]["_not"]
    assert "KIRIS KURAMINDAN turetilmedi" in d["kalibrasyon"]["_not"]


def test_MALZEME_modulu_materials_jsondan():
    """İkinci kaynak yaratmamak için modül veritabanından okunur."""
    src = (KOK / "experiments" / "fsi_tahrik_fizibilite.py").read_text(encoding="utf-8")
    assert "materials.json" in src
    assert "youngs_modulus" in src
    # Sabit bir GPa degeri gomulmemeli
    import re
    assert not re.search(r"=\s*(69|4\.5|45)e9\b", src.replace("E_al = 69e9", "")), \
        "malzeme modülü koda gömülmüş — materials.json ikinci kaynak olur"
