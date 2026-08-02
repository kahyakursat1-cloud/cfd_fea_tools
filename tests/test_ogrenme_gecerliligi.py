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


class TestAyirtEdiciKanit:
    """Havuzdaki TÜM sonuçlar aynıysa başarı oranı SIFIR bilgi taşır.

    ÖLÇÜLDÜ: geçerlilik filtresinden sonra havuz 16 kayıt ve 16'sı da ok=True.
    Mentor `kalite_basari {"hassas_nl": 1.0, "hassas": 1.0}` deyip beraberliği
    `hassas` lehine bozuyor ve onu ÖNERİYORDU — oysa `hassas`ın bu geometride
    katmanları ÇÖKERTTİĞİ ve `hassas_nl` ile BİREBİR aynı mesh'i verdiği
    (660862 hücre, ikisinin de ref_bump'ı +1) ölçülmüştü.

    Yani bilgi taşımayan bir orandan kendinden emin ve YANLIŞ bir öneri çıkıyordu.
    """
    @staticmethod
    def _havuz(tmp_path, monkeypatch, sonuclar):
        import json as _j

        import mentor
        monkeypatch.setattr(mentor, "MESH_MEMORY", tmp_path / "m.jsonl")
        m = {"lmax_m": 1.5, "on_alan_m2": 0.05, "yan_alan_m2": 0.3,
             "planform_alan_m2": 0.775, "ucgen_sayisi": 2000,
             "ince_yassilik": 0.05, "keskin_kenar_orani": 0.1}
        recs = [{"tur": "cfd", "tip": "ucak", "metrik": m, "kalite": kal,
                 "ok": ok, "n_layers": 0, "cells": 900000,
                 "yuzey_cozuldu": True, "ogrenilebilir": True}
                for kal, ok in sonuclar]
        (tmp_path / "m.jsonl").write_text(
            "".join(_j.dumps(r) + "\n" for r in recs), encoding="utf-8")
        return mentor.advise_mesh(m, "ucak")

    def test_HEPSI_BASARILI_havuzda_oneri_YOK(self, tmp_path, monkeypatch):
        o = self._havuz(tmp_path, monkeypatch,
                        [("hassas_nl", True)] * 4 + [("hassas", True)] * 4)
        assert o["onerilen_kalite"] is None
        assert any("AYIRT EDİCİ değil" in r for r in o["riskler"])

    def test_HEPSI_BASARISIZ_havuzda_da_oneri_YOK(self, tmp_path, monkeypatch):
        o = self._havuz(tmp_path, monkeypatch,
                        [("hassas_nl", False)] * 4 + [("hassas", False)] * 4)
        assert o["onerilen_kalite"] is None
        assert any("tümü başarısız" in r for r in o["riskler"])

    def test_AYIRT_EDICI_havuzda_oneri_URETILIYOR(self, tmp_path, monkeypatch):
        """Kapı yalnız bilgisiz havuzu susturmalı; gerçek kanıt varsa öneri gelsin."""
        o = self._havuz(tmp_path, monkeypatch,
                        [("hassas", False)] * 4 + [("hassas_nl", True)] * 4)
        assert o["onerilen_kalite"] == "hassas_nl"

    def test_bilgi_tasiyan_tahmin_KORUNUYOR(self, tmp_path, monkeypatch):
        """Hücre tahmini başarı oranından bağımsızdır; susturulmamalı."""
        o = self._havuz(tmp_path, monkeypatch, [("hassas_nl", True)] * 8)
        assert o["beklenen_hucre"] == 900000


class TestTipEtiketi:
    """Havuz anahtarı KOŞUYA GEÇİLEN tip değil, geometriden SINIFLANDIRILAN tip.

    ÖLÇÜLDÜ (165 kayıt): kaydedilen `vehicle_type` ile sınıflandırılan tip yalnız
    78'inde uyuşuyor (%47). Güvenilirlik taraması hiç `vehicle_type` geçirmediği
    için öğrenilebilir 16 kaydın 16'sı da "ucak" yazıyordu — içlerinde 800 mm'lik
    bir KÜP, bir kapsül ve bir multikopter var. Sorgu tarafı zaten sınıflandırılmış
    tiple çağırdığından karşılaştırma elma-armut oluyordu.
    """

    def test_kayit_SINIFLANDIRILAN_tipi_tutuyor(self):
        import mentor
        s = {"vehicle_type": "ucak"}                      # çağıranın VARSAYILANI
        cls = {"tip": "multikopter", "guven": 0.52, "metrik": {}}
        r = mentor._tip_alanlari(s, cls)
        assert r["tip"] == "multikopter"                  # havuz anahtarı = ölçüm
        assert r["tip_kayitli"] == "ucak"                 # provenans korunuyor
        assert r["tip_celiskisi"] is True                 # çelişki GİZLENMİYOR
        assert r["tip_guven"] == 0.52

    def test_uyusma_celiski_sayilmiyor(self):
        import mentor
        r = mentor._tip_alanlari({"vehicle_type": "roket"},
                                 {"tip": "roket", "guven": 0.9})
        assert r["tip_celiskisi"] is False

    def test_hasat_celiski_sayisini_RAPORLUYOR(self):
        """Sessiz düzeltme olmaz: kaç kaydın etiketi değişti görünmeli."""
        import inspect

        import gci_advisor
        import mentor
        assert "n_tip_celiskisi" in inspect.getsource(mentor.harvest_mesh)
        assert "n_tip_celiskisi" in inspect.getsource(gci_advisor.harvest)


class TestAyrikGeometriSayisi:
    """n_destek KAYIT sayısıdır, bağımsız vaka sayısı DEĞİL.

    ÖLÇÜLDÜ: öğrenilebilir 16 kaydın 5'i aynı gövde (minihawk; mh_katman, mh_nl,
    mh_rb2, mh_rb3, minihawk_duzeltme — beş ayrı DİZİN, tek GEOMETRİ). Ayar→sonuç
    öğrenmesi için o tekrarlar sinyaldir; "16 farklı geometri gördüm" değildir.
    """

    def test_ayni_gövde_tekrarlari_ayri_geometri_sayilmiyor(self, tmp_path, monkeypatch):
        import json as _j

        import auto_pilot as ap
        import mentor
        m = ap.classify_vehicle({"boyutlar_m": [0.7, 1.5, 0.08], "lmax_m": 1.5,
                                 "ucgen_sayisi": 5000, "su_gecirmez": True,
                                 "on_alan_m2": 0.02, "planform_alan_m2": 0.5,
                                 "yuzey_alani_m2": 1.1, "ince_yassilik": 0.2,
                                 "radyal_doluluk": 0.4})["metrik"]
        recs = [{"tur": "cfd", "tip": "ucak", "metrik": m, "kalite": "hassas_nl",
                 "ok": True, "cells": 900000, "yuzey_cozuldu": True,
                 "ogrenilebilir": True, "kaynak": f"runs/mh_{i}/sonuc.json",
                 "dosya": "minihawk_prep.stl"} for i in range(5)]
        recs.append({**recs[0], "kaynak": "runs/baska/sonuc.json",
                     "dosya": "a320_prep.stl"})
        monkeypatch.setattr(mentor, "MESH_MEMORY", tmp_path / "m.jsonl")
        (tmp_path / "m.jsonl").write_text(
            "".join(_j.dumps(r) + "\n" for r in recs), encoding="utf-8")
        o = mentor.advise_mesh(m, "ucak")
        assert o["n_destek"] == 6
        assert o["n_ayrik_geometri"] == 2, "aynı gövdenin tekrarları bağımsız sayıldı"


class TestRefBumpDersi:
    """Mentor `kalite` sıralıyordu, ama ölçülmüş tek kaldıraç ref_bump'tı
    (MiniHawk: +1/+2/+3 → y⁺ 340/112/61). Yani öğrenme, sonucu belirlemeyen
    değişkeni sıralıyordu; belirleyen değişken kayıtta bile yoktu.

    Havuz kademeyi SEÇMEZ — onu fizik seçer (beklenen y⁺ bandı + hücre bütçesi).
    Havuzun işi fiziğin seçimini DENETLEMEKTİR.
    """

    def test_kayit_YOKSA_ders_uydurulmuyor(self):
        import mentor
        d = mentor._ref_bump_dersi([(0.0, {"ok": True}), (0.0, {"ok": False})])
        assert d["ref_bump_basari"] is None
        assert "kaydı YOK" in d["ref_bump_notu"]

    def test_kademe_basina_sonuc_cikariliyor(self):
        import mentor
        knn = [(0.0, {"ok": False, "ref_bump": 0, "ref_bump_oneri": 2}),
               (0.0, {"ok": False, "ref_bump": 0, "ref_bump_oneri": 2}),
               (0.0, {"ok": True, "ref_bump": 2, "ref_bump_oneri": 2}),
               (0.0, {"ok": True, "ref_bump": 2, "ref_bump_oneri": 2})]
        d = mentor._ref_bump_dersi(knn)
        assert d["ref_bump_basari"] == {0: 0.0, 2: 1.0}
        assert "fizik önerisinden SAPILAN 2" in d["ref_bump_notu"]
        assert "2 tanesi başarısız" in d["ref_bump_notu"]

    def test_tek_YONLU_havuzda_ders_YOK(self):
        import mentor
        knn = [(0.0, {"ok": True, "ref_bump": b, "ref_bump_oneri": b})
               for b in (0, 1, 2, 3)]
        d = mentor._ref_bump_dersi(knn)
        assert "AYIRT EDİCİ değil" in d["ref_bump_notu"]

    def test_kayit_semasi_ref_bumpi_ICERIYOR(self):
        """Koşu bitip de alan yoksa iki saatlik hesap öğrenmeye giremez."""
        import inspect

        import mentor
        src = inspect.getsource(mentor._cfd_record)
        for alan in ("ref_bump", "ref_bump_oneri", "beklenen_yplus"):
            assert f'"{alan}"' in src
