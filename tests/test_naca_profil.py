"""NACA profil üreticisi — MiniHawk teşhisinin dayandığı KOŞULSUZ kanıt.

MiniHawk 3B koşusu Cl=0.0143 verdi (NACA2412 α=0 için 2B beklenti ~0.23). İki açıklama
vardı: (a) profil yanlış, (b) profil doğru ama 3B mesh kamburluğu çözmüyor.
Bu testler (a)'yı ANALİTİK olarak eler — CFD'ye, grid üreticisine, çözücüye bağlı
değildir. 2B CFD çapası bu depodaki grid altyapısıyla ÜRETİLEMEDİ (üç ayrı başarısızlık
biçimi naca2412_kesit.json içinde kayıtlı), o yüzden teşhisin dayanağı burasıdır.
"""
import json
from pathlib import Path

import pytest

pytest.importorskip("numpy")
from experiments.naca2412_kesit import profil_dogrulugu  # noqa: E402

KANIT = Path(__file__).resolve().parent.parent / "naca2412_kesit.json"


def test_profil_analitik_tanima_uyuyor():
    d = profil_dogrulugu()
    assert d["gecti"], d
    assert d["maks_sapma_kord"] < 1e-3, "kord'un binde birinden fazla sapma"


def test_kamburluk_TAM_dogru():
    """NACA2412'nin '2'si %2 kamburluk demektir; sapma olursa taşıma doğrudan kayar."""
    d = profil_dogrulugu()
    assert d["kamburluk_analitik"] == pytest.approx(d["kamburluk_tanim"], abs=1e-4)


def test_yeterli_nokta_karsilastirildi():
    """Birkaç noktada uyum tesadüf olabilir; kıyas kord boyunca yapılmalı."""
    assert profil_dogrulugu()["nokta"] >= 200


@pytest.mark.skipif(not KANIT.exists(), reason="çapa koşulmadı")
class TestKanit:
    @staticmethod
    def _d():
        return json.loads(KANIT.read_text(encoding="utf-8"))

    def test_profil_dogrulamasi_kanitta(self):
        assert self._d()["profil_dogrulama"]["gecti"] is True

    def test_CFD_uretilemedigi_SEBEBIYLE_yazili(self):
        """'Üretilemedi' tek başına bilgi değil; NEDEN üretilemediği kayıtlı olmalı —
        üç ayrı grid başarısızlığı ölçüldü ve hepsi yazılı."""
        d = self._d()
        if d.get("durum") == "cfd_uretilemedi":
            g = d["_grid_altyapisi"]
            assert "OGRD" in g and "ELLP" in g and "HYPR" in g
            assert "IRAKSADI" in g

    def test_bozuk_mesh_uzerinde_Cl_YAYINLANMIYOR(self):
        """En önemli kural: nonOrtho 180 / skewness 1e152 olan bir mesh'ten sayı
        yayınlamak yanıltıcıdır. Kanıtta Cl olmamalı."""
        d = self._d()
        if d.get("durum") == "cfd_uretilemedi":
            assert d.get("Cl") is None

    def test_teshis_verdiktte_acikca_yaziyor(self):
        v = self._d()["verdikt"]
        assert "PROFIL DOGRU" in v and "MESH COZUNURLUGU" in v
