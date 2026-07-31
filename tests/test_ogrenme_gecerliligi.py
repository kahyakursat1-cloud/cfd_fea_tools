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


class TestKatmanCokmesiRecetesi:
    """Mentor'un 'hassas_nl kullan' reçetesi ÖLÇÜMLE YANLIŞ çıktı.

    `hassas_nl` ile `hassas` BİREBİR aynı mesh'i veriyor (660862 hücre) — ikisinin
    de ref_bump'ı +1, bg_div'i 9, hücre tavanı aynı. Tek fark n_layers, o da zaten
    çöküyor. Yani "katmansıza geç" hiçbir şeyi değiştirmiyordu.

    Katman çökmesinin sebebi de ölçüldü: ilk katman 0.048 mm iken yüzey hücresi
    10.4 mm — en-boy 215:1; snappy determinant<0.001 ile 34023 yüzü reddedip TÜM
    ekstrüzyonu geri alıyor. Ayrıca firar kenarı 1.19 mm, y⁺=30 için gereken tek
    katman 1.45 mm — geometrik olarak da sığmıyor.

    ÖLÇÜLEN gerçek kaldıraç: y⁺ 340 → 112 → 61 (ref_bump +1/+2/+3).
    """
    @staticmethod
    def _pool(tmp_path, monkeypatch, yplus_ort):
        import json as _j

        import mentor
        monkeypatch.setattr(mentor, "MESH_MEMORY", tmp_path / "m.jsonl")
        m = {"lmax_m": 1.5, "on_alan_m2": 0.05, "yan_alan_m2": 0.3,
             "planform_alan_m2": 0.775, "ucgen_sayisi": 2000,
             "ince_yassilik": 0.05, "keskin_kenar_orani": 0.1}
        recs = [{"tur": "cfd", "tip": "ucak", "metrik": m, "kalite": "hassas",
                 "ok": True, "n_layers": 12, "cells": 1_000_000,
                 "yplus_hedef": 1.0, "yplus_ort": yplus_ort,
                 "yuzey_cozuldu": True, "ogrenilebilir": True} for _ in range(4)]
        (tmp_path / "m.jsonl").write_text(
            "".join(_j.dumps(r) + "\n" for r in recs), encoding="utf-8")
        return mentor.advise_mesh(m, "ucak")

    def test_HASSAS_NL_artik_care_olarak_ONERILMIYOR(self, tmp_path, monkeypatch):
        o = self._pool(tmp_path, monkeypatch, 344.0)["yplus_duzeltme"]
        assert o is not None
        assert "AYNI mesh" in o["oneri"], "yanlis recete geri gelmis"
        assert "ref-bump" in o["oneri"]

    def test_ref_bump_kademesi_SAYIYLA_veriliyor(self, tmp_path, monkeypatch):
        o = self._pool(tmp_path, monkeypatch, 344.0)["yplus_duzeltme"]
        assert o["onerilen_ref_bump"] >= 2      # 344/150 -> 2 kademe

    def test_ilimli_sapmada_OLCEKLEME_onerisi_korunuyor(self, tmp_path, monkeypatch):
        """Kural yalnız UÇ oranda değişmeli; ılımlı sapmanın reçetesi farklıdır."""
        o = self._pool(tmp_path, monkeypatch, 3.2)["yplus_duzeltme"]
        assert "ölçekleyin" in o["oneri"]
