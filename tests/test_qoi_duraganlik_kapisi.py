"""QoI-durağanlık: "residualControl tetiklenmedi" ≠ "Cd hâlâ hareket ediyor".

ASME V&V pratiğinde hüküm İLGİLENİLEN BÜYÜKLÜĞÜN yakınsamasına dayanır; rezidüel
seviyesi onun VEKİLİDİR. Aynı ayrım 2B NACA2412 çapasında kurulup commit edilmişti
(87751f9) ama araç yolunda uygulanmamıştı.

ÖLÇÜLDÜ (güvenilirlik taraması, hassas_nl + ref_bump 2): üç geometri YALNIZ rezidüel
yüzünden düştü — Cd sürüklenmesi %0.21 / %0.61 / %0.80, salınım YOK, ~400-500
iterasyon. Bağımsız doğrulama: genel_kup800 Cd=1.0375 vs literatür (Hoerner, küp)
1.05 → %-1.2. Yani bu koşularda sayı OTURMUŞ.

KAPI GEVŞETİLMİYOR: salınan koşu HÂLÂ düşer ve rezidüel durumu etikette yazılı kalır.
"""
import pytest

from validity_envelope import QOI_DURAGAN_DRIFT_PCT, sonuc_kapisi

OK = {"verdict": "ok"}


def _c(**k):
    d = {"drift_ok": True, "rezidual_ok": False, "cd_drift_son20pct": 0.5,
         "salinim": {"osilasyon": False}}
    d.update(k)
    return d


def test_tam_yakinsak_etiketi_DEGISMEDI():
    r = sonuc_kapisi(OK, _c(rezidual_ok=True, cd_drift_son20pct=0.1))
    assert r["seviye"] == "ok" and r["etiket"] == "✅ yakınsadı"
    assert r["gerekce"] == []


@pytest.mark.parametrize("drift", [0.212, 0.609, 0.796])
def test_OLCULEN_UC_VAKA_gecer(drift):
    """kup800 / genel_kapsul / a320 — gercek olculen driftler."""
    r = sonuc_kapisi(OK, _c(cd_drift_son20pct=drift))
    assert r["seviye"] == "ok"
    assert "QoI durağan" in r["etiket"]


def test_SALINAN_kosu_HALA_dusuyor():
    """Limit çevriminde Cd, salınımın nerede durduğuna bağlıdır."""
    r = sonuc_kapisi(OK, _c(cd_drift_son20pct=0.2,
                            salinim={"osilasyon": True, "genlik_pct": 4.7, "gecis": 9}))
    assert r["seviye"] == "uyari"
    assert "salınımlı" in r["etiket"]


def test_gevsek_drift_gecmiyor():
    assert sonuc_kapisi(OK, _c(cd_drift_son20pct=1.5))["seviye"] == "uyari"
    assert sonuc_kapisi(OK, _c(cd_drift_son20pct=QOI_DURAGAN_DRIFT_PCT + 0.01))["seviye"] == "uyari"


def test_drift_OLCULEMEZSE_gecmiyor():
    """'Ölçemedim' geçer not değildir — bu oturumun tekrarlayan dersi."""
    assert sonuc_kapisi(OK, _c(cd_drift_son20pct=None))["seviye"] == "uyari"


def test_drift_ok_DEGILSE_gecmiyor():
    assert sonuc_kapisi(OK, _c(drift_ok=False, cd_drift_son20pct=0.2))["seviye"] == "uyari"


def test_REZIDUEL_KISITI_GIZLENMIYOR():
    """Birini yazıp diğerini gizlemek ya bulguyu bastırır ya güveni şişirir."""
    r = sonuc_kapisi(OK, _c(cd_drift_son20pct=0.212))
    g = " ".join(r["gerekce"])
    assert "residualControl tetiklenmedi" in g
    assert "QoI" in g


def test_FIZIK_KAPISI_hala_ONCE_geliyor():
    """Yakınsamış ama fizik-dışı bir koşuya 'ok' demek en tehlikeli hatadır."""
    r = sonuc_kapisi({"verdict": "inadmissible", "reasons": ["Cd<0"]},
                     _c(cd_drift_son20pct=0.1))
    assert r["seviye"] == "engel"


def test_esik_DRIFT_LIMIT_ten_SIKI():
    """'Kabul edilebilir' (2.0) ile 'oturmuş' (1.0) ayrı ölçütlerdir."""
    from vehicle_pipeline import DRIFT_LIMIT_PCT
    assert QOI_DURAGAN_DRIFT_PCT < DRIFT_LIMIT_PCT


class TestSalinimKabulu:
    """Limit çevrimi: genliği ÖLÇÜLMÜŞ ve BANDA KATILMIŞSA kabul edilebilir.

    Bu "limit çevrimi yakınsadı" demek DEĞİLDİR — akış hâlâ zaman-bağımlıdır ve
    kesin çözüm URANS'tır. Söylenen: genlik küçükse VE raporlanan sayısal
    belirsizliğe GERÇEKTEN girmişse, "Cd ± band" mühendislik açısından savunulabilir.

    ÖLÇÜLDÜ (12 geometri): salınım genlikleri %0.68-2.5; aynı koşuların MODEL-form
    belirsizliği %12. Salınım, zaten raporlanan bandın beşte biri kadar. Böyle bir
    sonucu tümden reddetmek orantısız — ama genliğin bandda olması ŞART, ve bu
    doğrulanabilir bir koşuldur, iyi niyet beyanı değil.
    """
    @staticmethod
    def _c(genlik):
        return {"drift_ok": True, "rezidual_ok": False, "cd_drift_son20pct": 0.5,
                "salinim": {"osilasyon": True, "genlik_pct": genlik, "gecis": 9}}

    @staticmethod
    def _b(u_say, u_mod=12.0):
        return {"u_sayisal_pct": u_say, "u_model_pct": u_mod}

    @pytest.mark.parametrize("genlik", [0.68, 1.2, 1.7, 1.75, 1.9, 2.5])
    def test_OLCULEN_genlikler_kabul(self, genlik):
        """Taramada olculen gercek genlikler."""
        r = sonuc_kapisi(OK, self._c(genlik), self._b(genlik))
        assert r["seviye"] == "ok"
        assert "salınımlı" in r["etiket"]

    def test_BUYUK_genlik_HALA_dusuyor(self):
        assert sonuc_kapisi(OK, self._c(5.0), self._b(5.0))["seviye"] == "uyari"

    def test_genlik_BANDA_GIRMEMISSE_dusuyor(self):
        """Doğrulanabilir koşul: genlik raporlanan belirsizlikte OLMALI."""
        assert sonuc_kapisi(OK, self._c(1.7), self._b(None))["seviye"] == "uyari"
        assert sonuc_kapisi(OK, self._c(1.7), self._b(0.1))["seviye"] == "uyari"

    def test_belirsizlik_YOKSA_dusuyor(self):
        """'Ölçemedim' geçer not değildir."""
        assert sonuc_kapisi(OK, self._c(1.7), None)["seviye"] == "uyari"

    def test_model_belirsizligi_KUCUKSE_salinim_baskin_olur_ve_duser(self):
        """Salınım ancak model-form yanında KÜÇÜK kalırsa ihmal edilebilir."""
        assert sonuc_kapisi(OK, self._c(2.5), self._b(2.5, 3.0))["seviye"] == "uyari"

    def test_etiket_YAKINSADI_DEMIYOR(self):
        """Etiket asla 'yakınsadı' demez — akış zaman-bağımlı."""
        r = sonuc_kapisi(OK, self._c(1.7), self._b(1.7))
        assert r["etiket"] != "✅ yakınsadı"
        assert "URANS" in " ".join(r["gerekce"])

    def test_drift_bozuksa_dusuyor(self):
        c = self._c(1.0); c["drift_ok"] = False
        assert sonuc_kapisi(OK, c, self._b(1.0))["seviye"] == "uyari"

    def test_FIZIK_KAPISI_hala_once(self):
        r = sonuc_kapisi({"verdict": "inadmissible", "reasons": ["Cd<0"]},
                         self._c(1.0), self._b(1.0))
        assert r["seviye"] == "engel"


def test_cagiranlar_BELIRSIZLIGI_geciriyor():
    """Geçirilmezse kapı hiç devreye girmez — ölçüm eklenip tüketilmeme deseni."""
    import inspect

    import app_analyzer
    import experiments.guvenilirlik_taramasi as gt
    for mod, fn in ((gt, gt.savunulabilir_mi),):
        src = inspect.getsource(fn)
        i = src.index("sonuc_kapisi(")
        assert "belirsizlik" in src[i:i + 200]
    assert "belirsizlik" in inspect.getsource(app_analyzer).split("sonuc_kapisi(")[1][:200]
