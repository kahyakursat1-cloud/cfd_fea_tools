"""Geçiş modeli ÖN KOŞULU — çözücüden ÖNCE, çünkü sonuç "makul görünür" ama anlamsızdır.

Langtry-Menter laminer bölgeyi ve geçiş noktasını sınır tabakanın İÇİNDE çözer.
Duvar-fonksiyonu mesh'inde (y⁺≫30) laminer altkatman hiç ayrıklaştırılmaz; model
yine bir sayı üretir ve o sayı fiziksel görünür. Güvenilirlik taramasında ölçülen
y⁺ dağılımı 1866–70766 idi — yani varsayılan preset'te bu tuzağa düşmek KESİN.

2B çapada kazancın GERÇEK olduğu ölçüldü (y⁺<0.61): kOmegaSST α_L0=−0.81°,
kOmegaSSTLM −2.18° (referans −2.07°). Kazanç duvar çözünürlüğüne BAĞLI.
"""
import pytest

from analysis.openfoam_runner import GECIS_MODELLERI, gecis_modeli_onkosulu


def test_varsayilan_model_kisitlanmiyor():
    assert gecis_modeli_onkosulu("kOmegaSST", 0, 30.0) == ""
    assert gecis_modeli_onkosulu("kOmegaSST", 12, 1.0) == ""


def test_KATMANSIZ_gecis_modeli_reddedilir():
    s = gecis_modeli_onkosulu("kOmegaSSTLM", 0, 30.0)
    assert s and "DUVAR-COZUNUR" in s
    assert "hassas" in s          # ne yapilacagi da yaziyor


def test_yuksek_yplus_hedefi_reddedilir():
    s = gecis_modeli_onkosulu("kOmegaSSTLM", 12, 30.0)
    assert s and "y+" in s


def test_duvar_cozunur_kurulum_KABUL():
    assert gecis_modeli_onkosulu("kOmegaSSTLM", 12, 1.0) == ""


def test_pipeline_kapiyi_COZUCUDEN_ONCE_cagiriyor():
    """Kapı mesh/CFD'den sonra çağrılırsa saatler boşa gider."""
    import inspect

    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    i_kapi = src.index("gecis_modeli_onkosulu")
    for sonra in ("build_case", "run_cfd", "CFDCase("):
        if sonra in src:
            assert i_kapi < src.index(sonra), f"kapi {sonra}'den SONRA cagriliyor"


def test_pipeline_SESSIZ_UYARIYLA_devam_etmiyor():
    import inspect

    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    blok = src[src.index("gecis_modeli_onkosulu"):][:600]
    assert "raise ValueError" in blok, "sessiz uyariyla devam ediyor"


def test_gecis_modeli_listesi_bos_degil():
    assert "kOmegaSSTLM" in GECIS_MODELLERI


def test_LM_alanlari_ve_semalari_case_te_var(tmp_path):
    """Eksik alan/şema çözücüyü AÇIKLAMASIZ düşürür."""
    from analysis.openfoam_runner import _write_fv_schemes, _write_gecis_alanlari
    (tmp_path / "0").mkdir()
    (tmp_path / "system").mkdir()
    _write_gecis_alanlari(tmp_path, "govde", 0.0018)
    for f in ("gammaInt", "ReThetat"):
        assert (tmp_path / "0" / f).exists()
    ret = (tmp_path / "0" / "ReThetat").read_text()
    v = float(ret.split("internalField   uniform ")[1].split(";")[0])
    assert 200 < v < 3000, f"ReThetat={v} fiziksel disi"
    _write_fv_schemes(tmp_path)
    s = (tmp_path / "system" / "fvSchemes").read_text()
    assert "div(phi,gammaInt)" in s and "div(phi,ReThetat)" in s


def test_gevsetme_ve_residualControl_LM_alanlarini_kapsiyor(tmp_path):
    from analysis.openfoam_runner import _write_fv_solution
    (tmp_path / "system").mkdir(parents=True)
    _write_fv_solution(tmp_path)
    s = (tmp_path / "system" / "fvSolution").read_text()
    assert s.count("gammaInt") >= 2 and s.count("ReThetat") >= 2
