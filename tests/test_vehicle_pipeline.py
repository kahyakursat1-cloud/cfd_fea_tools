"""vehicle_pipeline saf fonksiyonlari: geometri, log parserlar, presetler."""
import numpy as np
import pytest

from vehicle_pipeline import (
    MESH_QUALITY,
    VEHICLE_PRESETS,
    _hull_projected_area,
    parse_checkmesh,
    parse_residuals,
)


def test_presets_complete_and_consistent():
    for key, p in VEHICLE_PRESETS.items():
        assert p["aref_mode"] in ("planform", "frontal")
        assert len(p["domain"]) == 3
        rmin, rmax = p["refinement"]
        assert rmin <= rmax
    assert set(MESH_QUALITY) == {"hizli", "standart", "hassas"}


def test_hull_projected_area_unit_cube():
    cube = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float)
    assert _hull_projected_area(cube, 0) == pytest.approx(1.0)
    assert _hull_projected_area(cube, 2) == pytest.approx(1.0)


def test_parse_checkmesh(tmp_path):
    log = tmp_path / "log.checkMesh"
    log.write_text(
        "    cells:            96800\n"
        "    Mesh non-orthogonality Max: 63.934 average: 18.97\n"
        "   ***Max skewness = 5.12439, 2 highly skew faces detected\n"
        "Mesh OK.\n"
    )
    q = parse_checkmesh(log)
    assert q["cells"] == 96800
    assert q["non_ortho_max"] == pytest.approx(63.934)
    assert q["skew_max"] == pytest.approx(5.12439)
    assert q["mesh_ok"]


def test_parse_checkmesh_missing_file(tmp_path):
    q = parse_checkmesh(tmp_path / "yok")
    assert q["cells"] is None and q["mesh_ok"] is None


def test_parse_residuals(tmp_path):
    log = tmp_path / "log.foamRun"
    log.write_text(
        "Time = 1\n"
        "smoothSolver:  Solving for Ux, Initial residual = 0.1, Final residual = 1e-06, No Iterations 2\n"
        "GAMG:  Solving for p, Initial residual = 0.5, Final residual = 0.01, No Iterations 3\n"
        "GAMG:  Solving for p, Initial residual = 0.2, Final residual = 0.005, No Iterations 2\n"
        "Time = 2\n"
        "smoothSolver:  Solving for Ux, Initial residual = 0.01, Final residual = 1e-07, No Iterations 2\n"
        "GAMG:  Solving for p, Initial residual = 0.05, Final residual = 0.001, No Iterations 2\n"
    )
    r = parse_residuals(log)
    assert r["Ux"] == [0.1, 0.01]
    assert r["p"] == [0.5, 0.05]   # iterasyon ici tekrarlardan ilki
