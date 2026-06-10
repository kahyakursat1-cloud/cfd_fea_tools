"""vehicle_pipeline saf fonksiyonlari: geometri, log parserlar, presetler."""
import numpy as np
import pytest
import trimesh

from vehicle_pipeline import (
    MESH_QUALITY,
    VEHICLE_PRESETS,
    _hull_projected_area,
    orientation_matrix,
    parse_checkmesh,
    parse_residuals,
    prepare_geometry,
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


def test_orientation_matrix_maps_nose_to_x_up_to_z():
    R = orientation_matrix("+y", "+x")
    assert np.allclose(R @ np.array([0, 1, 0.0]), [1, 0, 0])   # burun -> +x
    assert np.allclose(R @ np.array([1, 0, 0.0]), [0, 0, 1])   # ust -> +z
    assert np.linalg.det(R) == pytest.approx(1.0)              # sag-el, yansima yok


def test_orientation_matrix_identity():
    assert np.allclose(orientation_matrix("+x", "+z"), np.eye(3))


def test_orientation_matrix_rejects_parallel_axes():
    with pytest.raises(ValueError):
        orientation_matrix("+x", "-x")


def test_prepare_geometry_repairs_open_cube(tmp_path):
    box = trimesh.creation.box(extents=(1, 1, 1))
    broken = trimesh.Trimesh(vertices=box.vertices, faces=box.faces[:-2])  # 2 ucgen sil
    assert not broken.is_watertight
    src = tmp_path / "bozuk.stl"
    broken.export(str(src))
    prepared, info = prepare_geometry(src, tmp_path / "out")
    assert not info["su_gecirmez_once"]
    assert info["su_gecirmez_sonra"]
    assert any("delik" in r for r in info["onarimlar"])
    assert trimesh.load(str(prepared), force="mesh").is_watertight


def test_prepare_geometry_counts_bodies(tmp_path):
    a = trimesh.creation.box(extents=(1, 1, 1))
    b = trimesh.creation.box(extents=(1, 1, 1))
    b.apply_translation((3, 0, 0))
    src = tmp_path / "iki_govde.stl"
    trimesh.util.concatenate([a, b]).export(str(src))
    prepared, info = prepare_geometry(src, tmp_path / "out")
    assert info["govde_sayisi"] == 2
    assert prepared.exists()


def test_prepare_geometry_rejects_empty(tmp_path):
    src = tmp_path / "bos.stl"
    src.write_text("solid bos\nendsolid bos\n")
    with pytest.raises(ValueError):
        prepare_geometry(src, tmp_path / "out")


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
