"""Düz levha cilt-sürtünmesi çapası — MiniHawk'ın NİTEL uyarısını NİCEL yapan vaka.

Bu çapanın ilk sürümü, bu projede defalarca yakalanan iki hatayı KENDİSİ yaptı:
  1. y⁺ 1000/3000/8000 hedefleri aynı doymuş mesh'e çöktü ve üç BAĞIMSIZ veri
     noktası gibi raporlandı (ölçülen y⁺ üçünde de 169.2 idi).
  2. Yakınsamayan bir koşunun Cf'i veri sayıldı (1500 iterasyon, residualControl'e
     ulaşılmadı, %-10.7 "sonuç" olarak yazıldı).
Testler bu iki korumanın yerinde kaldığını doğrular; kanıt dosyasının kendisi de
tutarlılık için okunur.
"""
import json
from pathlib import Path

import pytest

from experiments.duz_levha_cf import (
    H_DOMAIN,
    NY_MIN,
    cf_referans,
    delta99,
    hucre_sayisi,
    yakinsadi_mi,
)

KANIT = Path(__file__).resolve().parent.parent / "duz_levha_cf.json"


def test_referans_bagintisi_literaturle_uyusuyor():
    """Cf = 0.0592 Re_x^(-1/5); Re_x=1e6'da Schlichting tablosu ≈0.00374 verir."""
    assert cf_referans(1e6) == pytest.approx(0.00374, abs=5e-5)
    # 1/7-kuvvet yasası Re arttıkça Cf'i düşürmeli
    assert cf_referans(1e7) < cf_referans(1e6) < cf_referans(1e5)


def test_delta99_makul():
    """x=0.5 m, Re_x=1e6 → türbülanslı ST kalınlığı ~12 mm mertebesinde."""
    assert 0.008 < delta99() < 0.016


def test_ulasilamayan_yplus_kopya_mesh_uretmez():
    """ASIL HATA: ilk hücre alanla kıyaslanabilir olunca genişleme çözücüsü doyar ve
    farklı y⁺ hedefleri AYNI mesh'i verir. Üretilemeyen hedef None dönmeli."""
    assert hucre_sayisi(H_DOMAIN) is None
    assert hucre_sayisi(H_DOMAIN / NY_MIN * 1.01) is None


def test_ulasilabilir_hedefte_ilk_hucre_gercekten_uretilebilir():
    """δ1 ≤ H/n olmalı — yoksa blockMesh talep edileni veremez, sessizce başka mesh kurar."""
    for ilk in (1e-5, 1e-4, 1e-3, 5e-3, 2e-2):
        n = hucre_sayisi(ilk)
        if n is not None:
            assert ilk <= H_DOMAIN / n, f"δ1={ilk} n={n} ile üretilemez"


def test_hucre_sayisi_ust_sinirla_kirpilir():
    from experiments.duz_levha_cf import NY
    assert hucre_sayisi(1e-6) == NY


def test_yakinsama_kapisi_log_yoksa_gecmez(tmp_path):
    assert yakinsadi_mi(tmp_path) == (False, 0)


def test_yakinsama_kapisi_iterasyon_dolduran_kosuyu_reddeder(tmp_path):
    """Sayı üretilmiş olması sayının veri olduğu anlamına gelmez."""
    (tmp_path / "log.foamRun").write_text("\nTime = 1\n" * 1500)
    yakin, it = yakinsadi_mi(tmp_path)
    assert yakin is False and it == 1500


def test_yakinsama_kapisi_gercek_yakinsamayi_taniyor(tmp_path):
    (tmp_path / "log.foamRun").write_text("\nTime = 1\nSIMPLE solution converged in 109\nEnd\n")
    assert yakinsadi_mi(tmp_path) == (True, 109)


@pytest.mark.skipif(not KANIT.exists(), reason="çapa henüz koşulmadı")
class TestKanit:
    @staticmethod
    def _d():
        return json.loads(KANIT.read_text(encoding="utf-8"))

    def test_yakinsamayan_seviye_veri_olarak_gecmiyor(self):
        for s in self._d()["seviyeler"]:
            if s["durum"] != "ok":
                assert "Cf" not in s, f"{s['durum']} seviyesinde Cf raporlanmış"

    def test_olculen_yplus_degerleri_benzersiz(self):
        yp = [round(s["yplus_olculen"], 1) for s in self._d()["seviyeler"]
              if s["durum"] == "ok"]
        assert len(yp) == len(set(yp)), f"kopya mesh sızmış: {yp}"

    def test_duvar_fonksiyonu_bandinda_cf_makul(self):
        """30 ≤ y⁺ ≤ 300 duvar fonksiyonunun geçerli olduğu bant — burada Cf tutmalı."""
        bant = [s for s in self._d()["seviyeler"]
                if s["durum"] == "ok" and 30 <= s["yplus_olculen"] <= 300]
        assert bant, "bantta hiç seviye yok"
        assert max(abs(s["hata_pct"]) for s in bant) <= 8

    def test_ASIL_BULGU_ilk_hucre_sinir_tabakayi_yutunca_surtunme_cokuyor(self):
        """MiniHawk'ın durumu: ilk hücre sınır tabakadan büyük. Çapanın varlık sebebi
        bu sayıyı vermek — 'çözülmüyor' demek yerine 'yaklaşık %40 eksik' demek."""
        asiri = [s for s in self._d()["seviyeler"]
                 if s["durum"] == "ok" and s["ilk_hucre_delta99"] > 2]
        assert asiri, "sınır tabakayı yutan seviye koşulmamış"
        assert min(s["hata_pct"] for s in asiri) < -25

    def test_verdikt_bandi_adlandiriyor(self):
        v = self._d()["verdikt"]
        assert "30-300" in v or "%5" in v

    def test_zarf_satiri_kanittan_uretiliyor(self):
        import zarf
        _, aciklama = zarf._duz_levha()
        assert "Schlichting" in aciklama and "δ99" in aciklama
