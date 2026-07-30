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
