"""MaterialLibrary / MaterialProperties karakterizasyon testleri.

Türetilen elastik sabitlerin (G, K) fiziksel formüllerini ve doğrulama
mantığını dondurur. Malzeme isimlerini hardcode etmez (DB içeriğinden bağımsız).
"""
import pytest

from material_database import MaterialLibrary, MaterialProperties


@pytest.fixture
def lib() -> MaterialLibrary:
    return MaterialLibrary()  # varsayılan malzemeleri üretir


def test_library_has_materials(lib):
    names = lib.list_materials()
    assert len(names) > 0
    assert lib.get_material(names[0]) is not None


def test_shear_modulus_formula(lib):
    """G = E / (2(1+ν)) — izotropik elastisite kimliği."""
    mat = lib.get_material(lib.list_materials()[0])
    expected_g = mat.youngs_modulus / (2 * (1 + mat.poisson_ratio))
    assert mat.shear_modulus == pytest.approx(expected_g, rel=1e-9)


def test_roundtrip_dict(lib):
    mat = lib.get_material(lib.list_materials()[0])
    restored = MaterialProperties.from_dict(mat.to_dict())
    assert restored.youngs_modulus == pytest.approx(mat.youngs_modulus)
    assert restored.density == pytest.approx(mat.density)


def test_validation_rejects_bad_poisson():
    base = MaterialLibrary().get_material(MaterialLibrary().list_materials()[0]).to_dict()
    base["poisson_ratio"] = 0.9  # > 0.5 → geçersiz
    with pytest.raises(ValueError):
        MaterialProperties.from_dict(base)


def test_export_csv(lib, tmp_path):
    out = tmp_path / "materials.csv"
    lib.export_csv(out)
    assert out.exists() and out.stat().st_size > 0
