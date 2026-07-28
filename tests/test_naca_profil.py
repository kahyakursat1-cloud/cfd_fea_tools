"""NACA profil üreticisi — MiniHawk teşhisinin dayandığı KOŞULSUZ kanıt.

MiniHawk 3B koşusu Cl=0.0143 verdi (NACA2412 α=0 için 2B beklenti ~0.23). İki açıklama
vardı: (a) profil yanlış, (b) profil doğru ama 3B mesh kamburluğu çözmüyor.
Bu testler (a)'yı ANALİTİK olarak eler — CFD'ye, grid üreticisine, çözücüye bağlı
değildir.

DÜZELTME: (a) elendiği için (b) DOĞRUDUR diye yazılmıştı. Bu eleme ARTIK GEÇERSİZ.
2B ölçümü (temiz C-grid, nonOrtho 63.8, y⁺<0.61, iki α noktası) şunu verdi: taşıma
eğimi 0.947·2π — kusursuz, ama α_L0 = −0.81° (olması gereken −2.07°). Yani kamburluk
katkısı 2B'DE DE eksik. Öyleyse MiniHawk'ın düşük Cl'i için "3B mesh çözünürlüğü"
tek aday değildir; her iki koşuya da ORTAK bir sebep aranmalıdır.
"""
import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
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
        """'Üretilemedi' tek başına bilgi değil; NEDEN üretilemediği kayıtlı olmalı.
        Ayrıca kayıt, önceki YANLIŞ kök-sebep atfını açıkça düzeltmeli: 'grid makuldü,
        dönüştürücü bozdu' denmişti — bu, iki koşunun skewness'ının aynı çıkmasına
        dayanan, koordinat ölçülmeden yapılmış bir çıkarımdı."""
        d = self._d()
        if d.get("durum") == "cfd_uretilemedi":
            g = d["_grid_altyapisi"]
            assert "DUZELTMESI" in g, "yanlis kok-sebep atfi kanitta duzeltilmemis"
            assert "CIKARIMDI" in g and "OLCULMEDEN" in g

    def test_bozuk_mesh_uzerinde_Cl_YAYINLANMIYOR(self):
        """En önemli kural: nonOrtho 180 / skewness 1e152 olan bir mesh'ten sayı
        yayınlamak yanıltıcıdır. Kanıtta Cl olmamalı."""
        d = self._d()
        if d.get("durum") == "cfd_uretilemedi":
            assert d.get("Cl") is None

    def test_verdikt_capa_uretilip_uretilmedigini_ACIKCA_soyler(self):
        """Eski sürüm burada 'PROFIL DOGRU ... 3B MESH COZUNURLUGU' metnini ŞART
        koşuyordu — yani bir SONUCU test ediyordu. O sonuç ELEME ile kurulmuştu
        ('profil doğru, öyleyse geriye 3B mesh kalıyor') ve 2B ölçümü onu ÇÜRÜTTÜ:
        temiz bir 2B C-grid'de de kamburluk katkısı eksik çıkıyor (α_L0 −0.81°,
        olması gereken −2.07°). Test artık sonucu değil, DÜRÜSTLÜĞÜ bağlar:
        kanıt ya çapayı ürettiğini ya da neden üretemediğini söylemeli."""
        v = self._d()["verdikt"]
        assert any(k in v for k in ("PROFIL DOGRU", "YAKINSAMADI", "KAMBURLUK",
                                    "KALITE KAPISINDA", "URETILEMEDI")), v

    def test_MiniHawk_teshisi_ELEME_ile_kurulmuyor(self):
        """2B'de de kamburluk açığı ölçüldükten sonra '3B mesh çözünürlüğü' artık
        eleme yoluyla iddia EDİLEMEZ. Kanıt bunu iddia ediyorsa, kamburluk kapısını
        GEÇMİŞ olmalı."""
        d = self._d()
        v = d["verdikt"]
        e = d.get("alfa_taramasi") or {}
        if "3B MESH COZUNURLUGUNDEN" in v and "kamburluk_gecti" in e:
            assert e["kamburluk_gecti"] is True, (
                "2B kamburluk kapisi kaldi ama verdikt hatayi 3B'ye atiyor")


def test_dat_yazici_FIRAR_KENARINDAN_basliyor(tmp_path):
    """ASIL KÖK SEBEP buydu. Construct2D firar kenarından başlayan eğri bekler;
    `_naca4_profile` hücum kenarında başlar. Eski 'ters çevir' sezgisi yönü
    düzeltiyor ama BAŞLANGICI taşımıyordu → yüzey spline'ı burunda süreksiz →
    marş patlıyor (j=0 noktalarının %66'sı aralık dışı, x 13327'ye kadar).
    Bu tek hata, 'üç ayrı altyapı başarısızlığı' tablosunun tamamını üretmişti."""
    from experiments.naca2412_kesit import profil_dat
    d = tmp_path / "p.dat"
    profil_dat(d)
    xy = np.array([[float(v) for v in s.split()]
                   for s in d.read_text().splitlines()[1:]])
    assert xy[0, 0] == pytest.approx(xy[:, 0].max()), "eğri firar kenarında başlamıyor"
    assert xy[-1] == pytest.approx(xy[0]), "eğri firar kenarında kapanmıyor"
    # burun TAM ortada olmalı: başlangıç yanlışsa hücum kenarı uca kayar
    burun = int(np.argmin(xy[:, 0]))
    assert 0.4 < burun / (len(xy) - 1) < 0.6, f"burun {burun}/{len(xy)-1} — dizilim bozuk"


def test_iki_topoloji_de_destekleniyor(tmp_path, monkeypatch):
    """CGRD artık write_cgrid_gmsh ile destekleniyor; eski 'topo != OGRD reddet'
    kapısı kalktı. Desteklenmeyen bir topoloji ise hâlâ AÇIKÇA reddedilmeli."""
    import construct2d_bridge as cb
    monkeypatch.setattr(cb, "run_construct2d", lambda *a, **k: None)
    for topo in ("OGRD", "CGRD"):
        r = cb.build_mesh("yok.dat", str(tmp_path / topo), name="x", topo=topo)
        assert r["step"] == "construct2d", (topo, r)   # topoloji kapısına takılmadı
    r = cb.build_mesh("yok.dat", str(tmp_path / "z"), name="x", topo="XXXX")
    assert r["status"] == "FAILED" and r["step"] == "topoloji"


def test_egim_ve_kamburluk_AYRI_hukumler():
    """TEK α NOKTASI YETMEZ. Cl(0) düşük çıktığında iki AYRI sebep vardır:
    çözücü sirkülasyonu üretemiyordur, ya da kamburluk çözülmüyordur. Ölçülen
    değerlerle (α=0: 0.0839, α=4: 0.4995) birincisi TEMİZ, ikincisi BAŞARISIZ."""
    from experiments.naca2412_kesit import _tasima_egimi
    e = _tasima_egimi({0.0: {"Cl": 0.0839}, 4.0: {"Cl": 0.4995}})
    assert e["egim_gecti"] is True, "egim 2pi'ye oturuyor — cozucu suclanmamali"
    assert e["kamburluk_gecti"] is False
    assert e["alfa_L0_deg"] == pytest.approx(-0.81, abs=0.02)
    assert e["egim_2pi_orani"] == pytest.approx(0.947, abs=0.005)


def test_kamburluksuz_kanat_KAMBURLUK_KAPISINDA_kalir():
    """Kamburluk hiç uygulanmazsa α_L0 tanım gereği 0 olur — VSPAERO yolunun
    ölçülen davranışı tam budur. Kapı bunu geçirmemeli."""
    from experiments.naca2412_kesit import _tasima_egimi
    e = _tasima_egimi({0.0: {"Cl": 0.0}, 4.0: {"Cl": 0.44}})
    assert e["alfa_L0_deg"] == pytest.approx(0.0, abs=1e-6)
    assert e["kamburluk_gecti"] is False
    assert e["egim_gecti"] is True          # egim yine dogru olabilir


def test_tek_nokta_UYDURMA_egim_donmez():
    from experiments.naca2412_kesit import _tasima_egimi
    assert "olculemedi" in _tasima_egimi({0.0: {"Cl": 0.08}})
    assert "olculemedi" in _tasima_egimi({0.0: {"Cl": None}, 4.0: {"Cl": None}})


def test_alfa_yanitsizsa_SIFIRA_BOLMEZ():
    from experiments.naca2412_kesit import _tasima_egimi
    assert "olculemedi" in _tasima_egimi({0.0: {"Cl": 0.1}, 4.0: {"Cl": 0.1}})


class TestDuraganBuyukluk:
    """'residualControl tetiklenmedi' ile 'Cl hâlâ hareket ediyor' AYNI ŞEY DEĞİL.

    Ölçüldü: 20000 iterasyonda Ux/k/omega platoda kaldı ama Cl kuyruk bandı ±0.0000
    (α=0) / ±0.0001 (α=4) ve İKİ BAĞIMSIZ koşu dört haneye kadar aynı değeri verdi.
    Kör bir "yakınsamadı" hükmü, ayırıcı bulguyu (eğim doğru / kamburluk eksik)
    tamamen bastırıyordu. Kapı gevşetilmiyor: rezidüel durumu verdiktte AYRICA yazılı.
    """
    @staticmethod
    def _cfd(**k):
        d = {"Cl": 0.0839, "Cl_band": 0.0,
             "yakinsama": {"yakinsadi": False, "iterasyon": 20000,
                           "platoda": ["Ux"], "salinim": {"osilasyon": False}}}
        d.update(k)
        return d

    def test_dar_bant_DURAGAN_sayilir(self):
        from experiments.naca2412_kesit import _buyukluk_duragan
        assert _buyukluk_duragan(self._cfd()) is True

    def test_genis_bant_duragan_DEGIL(self):
        from experiments.naca2412_kesit import _buyukluk_duragan
        assert _buyukluk_duragan(self._cfd(Cl_band=0.02)) is False

    def test_SALINIM_varsa_duragan_sayilmaz(self):
        from experiments.naca2412_kesit import _buyukluk_duragan
        c = self._cfd()
        c["yakinsama"]["salinim"] = {"osilasyon": True}
        assert _buyukluk_duragan(c) is False

    def test_band_yoksa_duragan_DEMEZ(self):
        from experiments.naca2412_kesit import _buyukluk_duragan
        assert _buyukluk_duragan({"Cl": 0.08}) is False

    def test_verdikt_REZIDUEL_KISITINI_gizlemez(self):
        from experiments.naca2412_kesit import _tasima_egimi, _verdikt
        e = _tasima_egimi({0.0: {"Cl": 0.0839}, 4.0: {"Cl": 0.4995}})
        v = _verdikt(0.0839, 0.0136, {}, -63.0, {**self._cfd(), "_egim": e})
        assert "residualControl tetiklenmedi" in v
        assert "DURAGAN" in v
        assert "KAMBURLUK COZULMUYOR" in v

    def test_salinan_kosu_HALA_reddedilir(self):
        """Gevşetme yalnız DURAĞAN büyüklük için; limit çevrimi hâlâ çapa değil."""
        from experiments.naca2412_kesit import _verdikt
        c = self._cfd(Cl_band=0.03)
        c["yakinsama"]["salinim"] = {"osilasyon": True}
        assert "YAKINSAMADI" in _verdikt(0.0839, 0.0136, {}, -63.0, c)
