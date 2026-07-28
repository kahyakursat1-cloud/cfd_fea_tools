r"""mesh_quality_gate sayı ayrıştırma — İYİ MESH'te çökme hatası.

Eski desen `([\d.eE+]+)` EKSİ ÜSSÜ kapsamıyordu:
    "Max skewness = 9.8987286e-05"  ->  yakalanan "9.8987286e"  ->  ValueError
ve TÜM analiz çöküyordu. Kritik ayrıntı: bu YALNIZ skewness KÜÇÜKKEN olur, yani
mesh İYİYKEN. Güvenilirlik taramasında 12 geometrinin 3'ü (%25) tam bu sebeple
çöktü — üçü de aslında sağlıklı mesh'lerdi.
"""
import pytest

from analysis.openfoam_runner import mesh_quality_gate

BAS = ("Mesh non-orthogonality Max: {no} average: 5.0\n"
       "Max skewness = {sk} OK.\n"
       "Max aspect ratio = {ar} OK.\n")


def _g(no="30", sk="1.2", ar="10"):
    return mesh_quality_gate(BAS.format(no=no, sk=sk, ar=ar))


def test_EKSI_USLU_skewness_cokmez():
    r = _g(sk="9.8987286e-05")
    assert r["skew_max"] == pytest.approx(9.8987286e-05)
    assert r["verdict"] == "ok"


def test_eksi_uslu_aspect_ve_nonortho_da_okunur():
    r = _g(no="1.234e-02", ar="5.5e-01")
    assert r["non_ortho_max"] == pytest.approx(1.234e-02)
    assert r["aspect_max"] == pytest.approx(0.55)


def test_ARTI_uslu_hala_calisiyor():
    r = _g(ar="2.72109e+04")
    assert r["aspect_max"] == pytest.approx(27210.9, rel=1e-3)


def test_normal_ondalik_bozulmadi():
    r = _g(no="63.751", sk="1.02413")
    assert r["non_ortho_max"] == pytest.approx(63.751)
    assert r["skew_max"] == pytest.approx(1.02413)


def test_reddetme_esikleri_calisiyor():
    assert _g(no="88.9")["verdict"] == "reject"
    assert _g(sk="7.0")["verdict"] == "reject"


def test_OKUNAMAYAN_metrik_sorun_yok_SAYILMAZ():
    """2eb2686'nın dersi: ayrıştırılamayan metriği 'ok' saymak kapıyı kör eder."""
    r = mesh_quality_gate("Max skewness = ÇÖPÇÖP\n")
    assert r["skew_max"] is None


def test_metrik_hic_yoksa_None():
    r = mesh_quality_gate("bombos log")
    assert r["non_ortho_max"] is None and r["skew_max"] is None
