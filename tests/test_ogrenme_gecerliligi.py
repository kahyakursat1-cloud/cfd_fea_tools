"""Öğrenme havuzu: gövdesi ÇÖZÜLMEMİŞ koşulardan öğrenilmez.

2026-07-29'a kadarki TÜM araç koşularında arka plan mesh'i hücre bütçesini tek
başına yiyordu; snappy hiç yüzey iyileştirmesi yapamıyor ve gövde 74 yüzle temsil
ediliyordu (ölçüldü). O koşulardan öğrenilen her örüntü, çözülmemiş bir geometrinin
örüntüsüdür.

VE ÖĞRENMİŞTİ: mentor "katman-çökmesi imzası — katmansız 'hassas_nl' düşünün"
diyordu. ÖLÇÜLDÜ ki `hassas_nl` ile `hassas` BİREBİR aynı mesh'i veriyor (660862
hücre; iki preset de ref_bump=+1). Bozuk veriden tutarlı ama YANLIŞ bir kural.

AYRAÇ TARİH DEĞİL ÖLÇÜM: eski bir koşuda geometri tesadüfen çözülmüş olabilir,
yeni bir koşuda çözülmemiş olabilir. Tarihe göre kesmek ikisini de yanlış sınıflar.
"""
import pytest

from mentor import _yuzey_gecerlilik


def test_olculmemis_kosu_OGRENILEBILIR_DEGIL():
    """Düzeltme öncesi koşularda `yuzey_cozunurlugu` alanı YOK."""
    r = _yuzey_gecerlilik({"katman_sayisi": 12})
    assert r["ogrenilebilir"] is False
    assert r["yuzey_cozuldu"] is None          # 'bilinmiyor', 'kotu' DEGIL
    assert "OLCULMEMIS" in r["gecersizlik"]


def test_cozulmus_kosu_ogrenilebilir():
    r = _yuzey_gecerlilik({"yuzey_cozunurlugu": {"cozuldu": True, "gerekce": [],
                                                 "yuzey_yuz": 32588}})
    assert r["ogrenilebilir"] is True and r["yuzey_cozuldu"] is True
    assert "gecersizlik" not in r


def test_COZULMEMIS_kosu_GEREKCESIYLE_dislanir():
    r = _yuzey_gecerlilik({"yuzey_cozunurlugu": {
        "cozuldu": False, "yuzey_yuz": 74,
        "gerekce": ["govde yamasi yalnizca 74 yuz — bu cozunurlukte kamburluk/egrilik "
                    "temsil EDILEMEZ"]}})
    assert r["ogrenilebilir"] is False and r["yuzey_cozuldu"] is False
    assert "74 yuz" in r["gecersizlik"]


def test_bozuk_alan_iyi_SAYILMAZ():
    """dict olmayan bir deger 'olculmus' sayilmamali."""
    for kotu in ("evet", 1, [], None):
        assert _yuzey_gecerlilik({"yuzey_cozunurlugu": kotu})["ogrenilebilir"] is False


def test_load_VARSAYILAN_olarak_filtreliyor():
    """Filtre opt-in olsaydı çağıranlar unutur ve kirli havuzdan öğrenirdi."""
    import inspect

    import mentor
    sig = inspect.signature(mentor._load)
    assert sig.parameters["sadece_gecerli"].default is True


def test_harvest_DISLANANI_RAPORLUYOR():
    """Havuz sessizce küçülürse 'modelim neden kötü öneriyor' sorusu cevapsız kalır."""
    import inspect

    import mentor
    src = inspect.getsource(mentor.harvest_mesh)
    for alan in ("n_ogrenilebilir", "n_dislanan", "n_yuzey_olculmemis"):
        assert alan in src


def test_gercek_havuz_FILTRELENIYOR():
    """Regresyon: filtre gerçekten uygulanıyor mu (alan eklemekle yetinilmemiş)."""
    import mentor
    if not mentor.MESH_MEMORY.exists():
        pytest.skip("mesh_memory.jsonl yok")
    filtreli = len(mentor._load("cfd"))
    ham = len(mentor._load("cfd", sadece_gecerli=False))
    assert filtreli <= ham
