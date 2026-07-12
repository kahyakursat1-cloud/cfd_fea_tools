"""vehicle_pipeline saf fonksiyonlari: geometri, log parserlar, presetler."""
import numpy as np
import pytest
import trimesh

from vehicle_pipeline import (
    MESH_QUALITY,
    VEHICLE_PRESETS,
    _hull_projected_area,
    farfield_domain,
    orientation_matrix,
    parse_checkmesh,
    parse_residuals,
    prepare_geometry,
    resolution_warning,
)


def test_weld_axial_segments_coaxial_gap():
    # İki eş-eksenli aynı-kesit gövde + boşluk (kopuk roket) → tek watertight cisme kaynar
    from vehicle_pipeline import weld_axial_segments
    b1 = trimesh.creation.box((0.15, 0.08, 0.08)); b1.apply_translation((-0.125, 0, 0))
    b2 = trimesh.creation.box((0.15, 0.08, 0.08)); b2.apply_translation((0.125, 0, 0))
    m = trimesh.util.concatenate([b1, b2])                  # boşluk x∈[-0.05,0.05]
    assert len(m.split(only_watertight=False)) == 2
    welded, note = weld_axial_segments(m)
    assert note is not None and welded.is_watertight and welded.body_count == 1


def test_weld_leaves_lateral_assembly_untouched():
    # Yanal-yayılı montaj (gövde + geniş kanat) → guard reddeder, DOKUNULMAZ
    from vehicle_pipeline import weld_axial_segments
    body = trimesh.creation.box((0.8, 0.06, 0.06)).subdivide()   # ana gövde (çok yüz)
    wing = trimesh.creation.box((0.2, 0.40, 0.02))               # yanal kanat (büyük kesit)
    m = trimesh.util.concatenate([body, wing])
    _, note = weld_axial_segments(m)
    assert note is None


def test_farfield_lift_aware_domain():
    # Taşıyıcı cisim (ucak) far-field'i küt/eksenelden daha geniş (yanal+upstream)
    ucak = farfield_domain(VEHICLE_PRESETS["ucak"], alpha_deg=0.0)
    roket = farfield_domain(VEHICLE_PRESETS["roket"], alpha_deg=0.0)
    assert ucak[0] >= 7.0 and ucak[2] >= 7.0          # upstream + lateral büyütüldü
    assert roket == VEHICLE_PRESETS["roket"]["domain"]  # lift_relevant değil → değişmez
    # Yüksek alfada (güçlü lift) yanal daha da geniş
    ucak_hi = farfield_domain(VEHICLE_PRESETS["ucak"], alpha_deg=10.0)
    assert ucak_hi[2] >= ucak[2] and ucak_hi[2] >= 9.0


def test_presets_complete_and_consistent():
    for key, p in VEHICLE_PRESETS.items():
        assert p["aref_mode"] in ("planform", "frontal")
        assert len(p["domain"]) == 3
        rmin, rmax = p["refinement"]
        assert rmin <= rmax
    # auto_pilot'un her tipi bir CFD preset'ine inmeli (hibritler dahil)
    from auto_pilot import PRESET_MAP, TIPLER
    assert set(TIPLER) == set(PRESET_MAP)
    assert set(PRESET_MAP.values()) <= set(VEHICLE_PRESETS)


def test_trailing_mean_cuts_stopping_noise():
    import math

    from vehicle_pipeline import trailing_mean
    # Plato ~0.5 + son-iterasyonda durdurma-sapması (0.31): ortalama platoyu korur
    vals = [0.5 - 0.2 * math.exp(-i / 10) for i in range(80)] + [0.31]
    m = trailing_mean(vals, fallback=0.31)
    assert abs(m - 0.5) < 0.02                               # plato korunur
    assert abs(m - 0.5) < abs(vals[-1] - 0.5)                # son-değer sapmasını yumuşatır
    assert trailing_mean([0.3] * 100, 99.0) == pytest.approx(0.3)
    assert trailing_mean([0.3] * 5, fallback=1.23) == 1.23   # kısa tarihçe → fallback
    assert trailing_mean([float("nan")] * 30, 0.5) == 0.5    # NaN'lar elenir → fallback


def test_car_preset_auto_ground_clearance():
    from vehicle_pipeline import auto_ground_clearance
    araba = VEHICLE_PRESETS["araba"]
    assert araba["ground"] and araba["aref_mode"] == "frontal"
    assert auto_ground_clearance(araba, height_m=1.4, ground_clearance=None) == 0.238
    assert auto_ground_clearance(araba, 1.4, 0.05) == 0.05            # kullanıcı öncelikli
    assert auto_ground_clearance(VEHICLE_PRESETS["ucak"], 1.4, None) is None  # serbest-akış
    assert set(MESH_QUALITY) == {"hizli", "standart", "hassas", "hassas_nl"}
    for q in MESH_QUALITY.values():           # her kalite tutarlı anahtar setine sahip
        assert {"end_time", "ref_bump", "max_cells", "bg_div", "n_layers", "yplus_target"} <= set(q)
    assert MESH_QUALITY["hassas_nl"]["n_layers"] == 0      # katmansız (ince-kanat güvenli)
    assert MESH_QUALITY["hassas"]["n_layers"] > 0          # duvar-çözünür


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


def test_resolution_warning_thin_wing_flags():
    # 3 m kanat acikligi, 12 mm kalinlik, hizli mod (L/5, ref 1): hucre 0.3 m >> kalinlik
    w = resolution_warning(3.0, 5, 1, 0.012)
    assert w is not None and "hassas" in w


def test_resolution_warning_ok_for_blunt_body():
    # 0.5 m kup, standart mod (L/7, ref 2): hucre ~18 mm, 0.5/0.018 ~ 28 >= 6
    assert resolution_warning(0.5, 7, 2, 0.5) is None


def test_thin_thickness_plate_vs_cube():
    from vehicle_pipeline import estimate_thin_thickness
    plate = trimesh.creation.box(extents=(1.0, 1.0, 0.02))
    t_plate = estimate_thin_thickness(plate, samples=150)
    assert t_plate is not None and t_plate < 0.1   # ~0.02 bekleriz, bbox-min ile ayni
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    t_cube = estimate_thin_thickness(cube, samples=150)
    assert t_cube is not None and t_cube > 0.5     # kup kalin: ~1.0


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


def test_prepare_geometry_autoscale_mm_to_m(tmp_path):
    # mm-ölçekli roket (2000 birim) -> ÷1000 = 2 m
    box = trimesh.creation.box(extents=(2000, 200, 200))
    src = tmp_path / "mm_roket.stl"
    box.export(str(src))
    prepared, info = prepare_geometry(src, tmp_path / "out")
    assert info.get("birim_olcek") == "mm→m"
    lmax = float((lambda m: (m.bounds[1] - m.bounds[0]).max())(
        trimesh.load(str(prepared), force="mesh")))
    assert 1.9 < lmax < 2.1


def test_prepare_geometry_keeps_meter_scale(tmp_path):
    # zaten metre (2 birim) -> ölçek YOK
    box = trimesh.creation.box(extents=(2.0, 0.2, 0.2))
    src = tmp_path / "m_roket.stl"
    box.export(str(src))
    _, info = prepare_geometry(src, tmp_path / "out")
    assert "birim_olcek" not in info


def test_oc_update_hits_volume_target():
    from vehicle_topopt import _oc_update
    n = 500
    rng = np.random.default_rng(7)
    rho = np.full(n, 0.5)
    sens = rng.uniform(0.1, 1.0, n)
    vol = np.ones(n)
    passive = np.zeros(n, dtype=bool)
    new = _oc_update(rho, sens, vol, volfrac=0.4, passive=passive)
    assert abs((new * vol).sum() / vol.sum() - 0.4) < 0.02
    assert new.min() >= 0.05 - 1e-9 and new.max() <= 1.0 + 1e-9


def test_oc_update_respects_passive():
    from vehicle_topopt import _oc_update
    n = 100
    rho = np.full(n, 0.5)
    sens = np.ones(n)
    vol = np.ones(n)
    passive = np.zeros(n, dtype=bool)
    passive[:10] = True
    new = _oc_update(rho, sens, vol, volfrac=0.3, passive=passive)
    assert np.allclose(new[:10], 1.0)


def test_tet_volumes_unit_tet():
    from vehicle_topopt import _tet_volumes
    P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)
    v = _tet_volumes(P, np.array([[0, 1, 2, 3]]))
    assert v[0] == pytest.approx(1 / 6)


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
