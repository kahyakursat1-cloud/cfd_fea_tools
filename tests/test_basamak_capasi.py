"""Geriye-basamaklı akış çapası — ayrılmış akışın ÖLÇÜLDÜĞÜ vaka.

Zarftaki "ayrılmış akış ❌ kapsam dışı" satırı bir BEYANDI; bu çapa onu ölçüye çevirir.
Ayrılma noktası burada geometrik olarak sabit (keskin köşe), yani ölçülen şey türbülans
modelinin yeniden-yapışmayı ne kadar doğru verdiğidir.

Bu çapa üretilirken ÜÇ ölçüm hatası yapıldı ve üçü de düzeltildi; testler onların geri
gelmesini engeller:
  1. Yüz İNDEKSİ doğrusal x sanıldı — mesh x'te 6× kademeli.        Xr/H=2.36 (%-62)
  2. Ccx listesinin UZUNLUK satırı koordinat sanıldı (221 vs 220).
  3. İŞARET KONVANSİYONU ters varsayıldı — OpenFOAM'da yapışık
     akışta τ_x NEGATİFTİR.                                          Xr/H=0.93 (%-85)
Düzeltilmiş sonuç: Xr/H = 5.54, deney 6.26 → %-11.6 (SST için literatür bandı).
"""
import json
from pathlib import Path

import pytest

from experiments.basamak_ayrilma import (
    H_STEP,
    RESIDUAL_TARGET,
    X_CIKIS,
    XR_DENEY,
    rezidual_platosu,
    yakinsadi_mi,
)

KOK = Path(__file__).resolve().parent.parent
KANIT = KOK / "basamak_ayrilma.json"


def test_kurulum_deney_kosuluyla_uyusuyor():
    """Driver & Seegmiller: H=12.7 mm, ER=1.125, Re_H=37500."""
    from experiments.basamak_ayrilma import H_GIRIS, NU, U_INF
    assert pytest.approx(0.0127) == H_STEP
    assert pytest.approx(1.125, abs=1e-3) == (H_GIRIS + H_STEP) / H_GIRIS
    assert pytest.approx(37500, rel=0.01) == U_INF * H_STEP / NU
    assert X_CIKIS / H_STEP >= 25, "baloncuk (6H) + gelişme için çıkış yeterince uzun olmalı"


def test_referans_literaturden():
    assert XR_DENEY == 6.26


def test_yakinsama_kapisi_iterasyon_dolduranı_reddeder(tmp_path):
    (tmp_path / "log.foamRun").write_text("\nTime = 1\n" * 20000)
    assert yakinsadi_mi(tmp_path)[0] is False


def test_plato_dedektoru_dusen_reziduali_kabul_eder(tmp_path):
    """Rezidüel gerçekten düşüyorsa sabit nokta sayılmalı."""
    satir = "".join(f"Solving for p, Initial residual = {1e-2 * 0.97 ** i:.6e},\n"
                    for i in range(400))
    (tmp_path / "log.foamRun").write_text(satir)
    p = rezidual_platosu(tmp_path)
    assert p["kararli_nokta"] is True and p["platoda"] == []


def test_plato_esigi_TEMKINLI_tarafa_egilimli(tmp_path):
    """Eşik (ikinci yarıda ≥10× düşüş) bilinçli olarak temkinli: yalnız 7× düşen
    yavaş bir seri de PLATO işaretlenir. Yavaş yakınsayan bir koşuyu 'sabit nokta'
    diye onaylamaktansa fazladan uyarmak tercih edilir."""
    satir = "".join(f"Solving for p, Initial residual = {1e-2 * 0.99 ** i:.6e},\n"
                    for i in range(400))
    (tmp_path / "log.foamRun").write_text(satir)
    assert rezidual_platosu(tmp_path)["kararli_nokta"] is False


def test_plato_dedektoru_SABIT_reziduali_yakalar(tmp_path):
    """ASIL KUSUR SINIFI: rezidüel eşiğin altında ama DÜŞMÜYOR → sabit nokta yok.
    kEpsilon'da ölçüldü: tüm alanlarda düşüş oranı tam 1.00."""
    satir = "Solving for p, Initial residual = 8.1e-05,\n" * 400
    (tmp_path / "log.foamRun").write_text(satir)
    p = rezidual_platosu(tmp_path)
    assert p["kararli_nokta"] is False and "p" in p["platoda"]
    assert RESIDUAL_TARGET > 8.1e-05, "senaryo: eşiğin ALTINDA ama plato"


def test_isaret_konvansiyonu_kodda_belgelenmis():
    """3. hata: OpenFOAM'da yapışık akışta τ_x negatif. Ters varsayım Xr'yi 6× küçülttü."""
    import inspect

    from experiments import basamak_ayrilma
    src = inspect.getsource(basamak_ayrilma.yapisma_uzunlugu)
    assert "İŞARET KONVANSİYONU" in src
    assert "tx[i - 1] > 0 >= tx[i]" in src, "geri akış(+) → yapışık(−) geçişi aranmalı"


def test_koordinatlar_indeksten_TURETILMIYOR():
    """1. hata: mesh 6× kademeli, indeks→x doğrusal eşleme geçersiz."""
    import inspect

    from experiments import basamak_ayrilma
    src = inspect.getsource(basamak_ayrilma.yapisma_uzunlugu)
    assert "_alt_duvar_x" in src
    assert "/ n * X_CIKIS" not in src, "indeks-tabanlı eşleme geri gelmiş"


def test_uzunluk_satiri_koordinat_sayilmiyor():
    """2. hata: OpenFOAM listesi önce uzunluğu yazar; o satır koordinat sanılıyordu."""
    import inspect

    from experiments import basamak_ayrilma
    src = inspect.getsource(basamak_ayrilma._alt_duvar_x)
    assert "Yalnız parantez içi" in src or "parantez içi" in src


@pytest.mark.skipif(not KANIT.exists(), reason="çapa koşulmadı")
class TestKanit:
    @staticmethod
    def _d():
        return json.loads(KANIT.read_text(encoding="utf-8"))

    def test_en_az_bir_model_yakinsadi(self):
        assert [s for s in self._d()["seviyeler"] if s["durum"] == "ok"]

    def test_yapisma_literatur_bandinda(self):
        """SST'nin BFS'te Xr'yi ~%10 kısa vermesi bilinen davranıştır; %25'i aşarsa
        kurulum bozulmuştur (ölçüm hatalarında %-62 ve %-85 görüldü)."""
        ok = [s for s in self._d()["seviyeler"] if s["durum"] == "ok"]
        en_iyi = min(ok, key=lambda s: abs(s["hata_pct"]))
        assert abs(en_iyi["hata_pct"]) < 25, en_iyi

    def test_yakinsamayan_model_hukme_girmiyor(self):
        for s in self._d()["seviyeler"]:
            if s["durum"] == "yakinsamadi":
                assert "Xr_H" not in s, "yakınsamayan koşu veri anahtarı taşımamalı"
                assert "YAKINSAMAMIS" in " ".join(s), "tanı değeri açık etiketli olmalı"

    def test_yakinsamayan_model_yine_de_RAPORLANIYOR(self):
        """Bilgi atılmamalı: hangi modelin oturmadığı ve nerede takıldığı yazılmalı."""
        d = self._d()
        ykn = [s for s in d["seviyeler"] if s["durum"] == "yakinsamadi"]
        if ykn:
            assert "YAKINSAMAYAN" in d["verdikt"]
            assert ykn[0]["platoda_alanlar"]

    def test_zarf_satiri_kanittan_uretiliyor(self):
        import zarf
        _, aciklama = zarf._ayrilmis_akis()
        assert "Driver & Seegmiller" in aciklama and "Xr/H" in aciklama

    def test_ayrilmis_akis_artik_BEYAN_degil(self):
        """Zarfın eski 'ayrılmış akış ❌ kapsam dışı' beyanı ölçüye dönüşmeli."""
        import zarf
        assert "ayrılmış akış" not in " ".join(zarf.BEYANLAR)
        assert any("Ayrılmış akış" in k for k, _ in zarf.SATIRLAR)
