import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import validation_anchors as va  # noqa: E402


def test_combine_rss():
    assert va.combine_uncertainty(3.0, 4.0) == 5.0      # √(9+16)
    assert va.combine_uncertainty(None, 8.0) == 8.0     # tek bileşen
    assert va.combine_uncertainty(None, None) is None


def test_regime_mapping():
    assert va.regime_of("ucak", {"lift_relevant": True}) == "lifting"
    assert va.regime_of("genel", {"lift_relevant": False}) == "bluff"


def test_literature_prior_when_no_band(tmp_path, monkeypatch):
    monkeypatch.setattr(va, "_BAND_FILE", tmp_path / "yok.json")
    r = va.model_uncertainty_pct("lifting", wall_resolved=True)
    assert r["u_model_pct"] == 5.0 and "öncül" in r["kaynak"]
    r2 = va.model_uncertainty_pct("bluff", wall_resolved=False)
    assert r2["u_model_pct"] == 20.0


def test_measured_band_overrides_prior(tmp_path, monkeypatch):
    bf = tmp_path / "band.json"
    bf.write_text(json.dumps({"lifting": {"wall_resolved": 2.3}}), encoding="utf-8")
    monkeypatch.setattr(va, "_BAND_FILE", bf)
    r = va.model_uncertainty_pct("lifting", wall_resolved=True)
    assert r["u_model_pct"] == 2.3 and "ölçülen" in r["kaynak"]


def test_anchors_have_required_fields():
    for name, a in va.ANCHORS.items():
        assert a["Cd"] > 0 and a["regime"] in ("lifting", "bluff") and a["ref"]


def test_geom_generators_match_anchors():
    import validate_pipeline as vpl
    for name, (gen, vtype, kw) in vpl._GEOM.items():
        assert name in va.ANCHORS                # üreteci olan her çapa tanımlı olmalı
        assert callable(gen) and isinstance(kw, dict)


def test_disk_body_faces_flow():
    import validate_pipeline as vpl
    m = vpl.disk_body()
    ext = m.bounds[1] - m.bounds[0]
    assert abs(ext[0] - 0.01) < 1e-6              # kalınlık akış (+x) yönünde
    assert abs(ext[1] - 0.1) < 1e-3 and abs(ext[2] - 0.1) < 1e-3
    assert m.is_watertight


def test_naca_wing_geometry():
    import validate_pipeline as vpl
    m = vpl.naca0012_wing()
    ext = m.bounds[1] - m.bounds[0]
    assert abs(ext[0] - 0.15) < 1e-3               # kiriş (x)
    assert abs(ext[1] - 0.90) < 1e-6               # açıklık (y) = AR·c
    assert 0.015 < ext[2] < 0.020                  # kalınlık ~%12·c
    assert m.is_watertight


def test_accept_gate_wake_path():
    # Yüzey yolu çöker (roket senaryosu) ama iz-momentum GCI asimptotik → wake ile KABUL
    import validate_pipeline as vpl
    gci_bad = {"monotonic": True, "p_in_range": False, "gci_fine_pct": 800.0, "asymptotic": 1.3}
    wake = {"gci": {"monotonic": True, "p_in_range": True, "gci_fine_pct": 3.0,
                    "asymptotic": 1.05, "f_exact": 0.148},
            "lsr": None}
    ok, cd, yontem = vpl._accept(gci_bad, None, -0.86, 0.154, wake)
    assert ok and cd == 0.148 and "wake-GCI" in yontem
    # wake de genişse RED sürer
    wake_kotu = {"gci": {"monotonic": True, "p_in_range": False, "gci_fine_pct": 90.0,
                         "asymptotic": 9.0, "f_exact": 0.1}, "lsr": None}
    ok, _, yontem = vpl._accept(gci_bad, None, -0.86, 0.154, wake_kotu)
    assert not ok and yontem is None
    # wake-LSR dar bandı da kabul yolu
    wake_lsr = {"gci": None, "lsr": {"n": 4, "u_pct": 8.0, "f_exact": 0.15, "kural": "standart"}}
    ok, cd, yontem = vpl._accept({}, None, None, 0.154, wake_lsr)
    assert ok and cd == 0.15 and "wake-LSR" in yontem


def test_accept_gate_gci_lsr_priority():
    import validate_pipeline as vpl
    gci_ok = {"monotonic": True, "p_in_range": True, "gci_fine_pct": 2.0, "asymptotic": 1.02}
    ok, cd, yontem = vpl._accept(gci_ok, None, 0.30, 0.31)
    assert ok and cd == 0.30 and "GCI" in yontem                 # asimptotik GCI birincil
    gci_bad = {"monotonic": True, "p_in_range": False, "gci_fine_pct": 80.0, "asymptotic": 5.0}
    lsr_dar = {"n": 4, "u_pct": 9.0, "f_exact": 0.29, "kural": "standart", "guvenilir": True}
    ok, cd, yontem = vpl._accept(gci_bad, lsr_dar, -0.8, 0.31)
    assert ok and cd == 0.29 and "LSR" in yontem                 # GCI düştü → dar LSR bandı
    lsr_genis = {"n": 4, "u_pct": 60.0, "f_exact": 0.29, "kural": "salınımlı", "guvenilir": False}
    ok, cd, yontem = vpl._accept(gci_bad, lsr_genis, -0.8, 0.31)
    assert not ok and yontem is None                             # geniş band validasyon yapamaz
    ok, _, _ = vpl._accept({}, None, None, 0.31)
    assert not ok                                                # kanıt yok → RED


def test_sphere_skipped_with_honest_reason():
    import validate_pipeline as vpl
    assert "sphere" not in vpl._GEOM and "sphere" in vpl._SKIP_REASON
    assert "GEÇİŞ" in vpl._SKIP_REASON["sphere"]                 # gerekçe kayıtlı


def test_ahmed_body_dimensions():
    import validate_pipeline as vpl
    m = vpl.ahmed_body()
    ext = m.bounds[1] - m.bounds[0]
    assert abs(ext[0] - 1.044) < 1e-6            # SAE standart uzunluk
    assert abs(ext[1] - 0.389) < 1e-6            # genişlik
    assert abs(ext[2] - 0.288) < 1e-6            # yükseklik
    assert m.is_watertight and m.is_convex
    # arka slant: x=L tabanında üst köşe H - 0.222·sin25° ≈ 0.1942'de olmalı
    rear = m.vertices[m.vertices[:, 0] > 1.044 - 1e-6]
    assert abs(rear[:, 2].max() - (0.288 - 0.222 * 0.42262)) < 1e-3
    # frontal alan ~ W·H (yuvarlatma köşe payı düşer): 0.10–0.112 m² bandı
    from vehicle_pipeline import _hull_projected_area
    af = _hull_projected_area(m.vertices, 0)
    assert 0.100 < af < 0.113


def test_hassas_quality_is_wall_resolved():
    from vehicle_pipeline import MESH_QUALITY
    assert MESH_QUALITY["hassas"]["n_layers"] >= 10
    assert MESH_QUALITY["hassas"]["yplus_target"] <= 1.0
    assert MESH_QUALITY["standart"]["n_layers"] == 0     # standart hâlâ duvar-fonksiyonu
