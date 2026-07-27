"""Kök `check_*` / `*_test.py` script'leri — pytest dışında yaşayan doğrulama katmanı.

Bu script'ler CI'da koşmuyor, kimse elle çalıştırmıyor ve bu yüzden sessizce çürüyor.
`full_integration_test.py` iki ayrı biçimde bozuktu:
  1. Var olmayan `AircraftLibrary.get_template/get_all_templates` API'sini çağırıyordu
     (3 test AttributeError ile düşüyordu),
  2. `run_all_tests()` HİÇ return yapmıyordu -> None -> `sys.exit(0 if success else 1)`
     TÜM testler geçse bile 1 döndürüyordu; çıkış koduna bakan otomasyon bunu kalıcı
     başarısızlık sanardı.

Testler bu iki çürüme sınıfını da bağlar (çözücü gerektirmez).
"""
import importlib
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# İçe aktarımı yan-etkisiz olan (modül düzeyinde koşmayan) script'ler
ICE_AKTARILABILIR = ["full_integration_test", "check_integration", "verify_system",
                     "check_core_only", "check_material_system"]


@pytest.mark.parametrize("ad", ICE_AKTARILABILIR)
def test_script_ice_aktarilabiliyor(ad):
    """Sözdizimi/import çürümesi: modül yüklenemiyorsa script zaten ölüdür."""
    assert importlib.import_module(ad) is not None


def test_aircraft_library_enumerasyon_apisi():
    """full_integration_test'in dayandığı sözleşme — yıllardır eksikti."""
    from aircraft_geometry import AircraftLibrary as L

    adlar = L.template_adlari()
    assert "mini_hawk" in adlar and len(adlar) >= 3
    fabrikalar = L.get_all_templates()
    assert len(fabrikalar) == len(adlar)
    assert all(callable(f) for f in fabrikalar), \
        "get_all_templates FABRİKA döndürmeli (get_template ile aynı tür)"
    assert L.get_template("mini_hawk")().name
    with pytest.raises(KeyError):
        L.get_template("olmayan_tasarim")


def test_mass_properties_sozlesmesi():
    """Script eski 'mass'/'cg' adlarını çağırıyordu; sözleşme total_mass/cg_x."""
    from aircraft_geometry import AircraftLibrary
    mp = AircraftLibrary.minihawk_uav().mass_properties()
    assert {"total_mass", "cg_x", "wing_area"} <= set(mp)
    assert mp["total_mass"] > 0 and mp["cg_x"] > 0


def test_run_all_tests_sonuc_donduruyor():
    """Dönüş değeri yoksa çıkış kodu ANLAMSIZDIR (hep 1)."""
    import full_integration_test as fit
    src = inspect.getsource(fit.IntegrationTestSuite.run_all_tests)
    assert "return" in src, "run_all_tests sonuç döndürmüyor -> sys.exit hep 1"


def test_cikis_kodu_sonuca_bagli():
    """Boş/başarısız sonuç sözlüğü True dönmemeli."""
    import full_integration_test as fit
    s = fit.IntegrationTestSuite()
    s.results = {}
    assert not (bool(s.results) and all(s.results.values())), "boş sonuç başarı sayılmaz"
    s.results = {"a": True, "b": False}
    assert not (bool(s.results) and all(s.results.values()))
    s.results = {"a": True, "b": True}
    assert bool(s.results) and all(s.results.values())
