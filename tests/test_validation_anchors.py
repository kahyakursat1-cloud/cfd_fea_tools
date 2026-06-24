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


def test_hassas_quality_is_wall_resolved():
    from vehicle_pipeline import MESH_QUALITY
    assert MESH_QUALITY["hassas"]["n_layers"] >= 10
    assert MESH_QUALITY["hassas"]["yplus_target"] <= 1.0
    assert MESH_QUALITY["standart"]["n_layers"] == 0     # standart hâlâ duvar-fonksiyonu
