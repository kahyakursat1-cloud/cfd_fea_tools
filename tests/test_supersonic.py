"""supersonic_cfd saf fonksiyonlari: ses hizi, prepad, rejim-bazli BC secimi."""
import math

import numpy as np
import trimesh

import supersonic_cfd as s
import supersonic_report as sr


def test_sound_speed_sea_level():
    a = s.sound_speed(288.15)
    assert 340 < a < 341   # ~340.3 m/s


def test_quiescent_prepad_positive():
    assert s._quiescent_prepad() > 0   # akisin upstream'i gecmesi icin ek gecis


def test_friction_cd_physical():
    # tipik roket: pozitif, makul mertebe (0.01-0.2 frontal ref.)
    cdf = s.friction_cd(252.0, 2.69, 2.4, 0.059, 0.74, 1.225)
    assert 0.01 < cdf < 0.30
    # Mach artinca Cf duser (sikistirilabilirlik); Re sabit
    assert s.friction_cd(680.0, 2.69, 2.4, 0.059, 2.0, 1.225) < \
           s.friction_cd(680.0, 2.69, 2.4, 0.059, 0.3, 1.225)
    # islak alan artinca surtunme drag artar
    assert s.friction_cd(252.0, 2.69, 4.0, 0.059, 0.74, 1.225) > cdf


def _write_fields(tmp_path, mach):
    (tmp_path / "0").mkdir()
    s._write_shock_fields(tmp_path, "govde", mach, 288.15, 101325.0)
    return (tmp_path / "0" / "U").read_text(), (tmp_path / "0" / "p").read_text()


def test_subsonic_uses_freestream_bc(tmp_path):
    # M<1.05 transonik: dis sinirlar freestream (oto in/outflow), outlet de dahil
    u_txt, p_txt = _write_fields(tmp_path, 0.74)
    assert "freestreamVelocity" in u_txt
    assert "freestreamPressure" in p_txt
    assert "zeroGradient" not in u_txt.split("govde")[0]   # outlet zeroGradient YOK


def test_supersonic_uses_fixed_inlet_zerograd_outlet(tmp_path):
    # M>=1.05 supersonik: sabit-giris + zeroGradient-cikis (dogrulanmis yol)
    u_txt, _ = _write_fields(tmp_path, 2.0)
    assert "fixedValue" in u_txt
    assert "outlet { type zeroGradient; }" in u_txt
    assert "freestream" not in u_txt


def test_quiescent_init_zeroes_internal_velocity(tmp_path):
    (tmp_path / "0").mkdir()
    s._write_shock_fields(tmp_path, "govde", 3.0, 288.15, 101325.0, quiescent=True)
    u_txt = (tmp_path / "0" / "U").read_text()
    assert "internalField uniform (0 0 0)" in u_txt


def test_viscous_writes_turbulence_fields(tmp_path):
    (tmp_path / "0").mkdir()
    s._write_shock_fields(tmp_path, "govde", 2.0, 288.15, 101325.0, viscous=True)
    u_txt = (tmp_path / "0" / "U").read_text()
    assert "noSlip" in u_txt and "slip;" not in u_txt.split("noSlip")[0][-20:]
    assert (tmp_path / "0" / "k").exists()
    assert (tmp_path / "0" / "omega").exists()
    assert "kqRWallFunction" in (tmp_path / "0" / "k").read_text()
    assert "nutkWallFunction" in (tmp_path / "0" / "nut").read_text()


def test_inviscid_no_turbulence_fields(tmp_path):
    (tmp_path / "0").mkdir()
    s._write_shock_fields(tmp_path, "govde", 2.0, 288.15, 101325.0, viscous=False)
    assert "slip" in (tmp_path / "0" / "U").read_text()
    assert not (tmp_path / "0" / "k").exists()


def test_viscous_thermo_is_RAS(tmp_path):
    (tmp_path / "constant").mkdir()
    s._write_shock_thermo(tmp_path, viscous=True)
    assert "RAS" in (tmp_path / "constant" / "momentumTransport").read_text()
    assert "kOmegaSST" in (tmp_path / "constant" / "momentumTransport").read_text()


def test_supersonic_init_uses_freestream_internal(tmp_path):
    (tmp_path / "0").mkdir()
    u = s._write_shock_fields(tmp_path, "govde", 3.0, 288.15, 101325.0, quiescent=False)
    u_txt = (tmp_path / "0" / "U").read_text()
    assert math.isclose(u, 3.0 * s.sound_speed(288.15), rel_tol=1e-6)
    assert "internalField uniform (0 0 0)" not in u_txt


def test_body_silhouette_captures_extent(tmp_path):
    # 2m uzun, yariçap 0.1m gövde -> zarf ~0.1, x-ekseni 2m yayilir
    box = trimesh.creation.cylinder(radius=0.1, height=2.0)
    box.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    src = tmp_path / "govde.stl"
    box.export(str(src))
    xbc, zc, env = sr._body_silhouette(src)
    assert (xbc.max() - xbc.min()) > 1.8           # x boyunca ~2 m
    assert 0.05 < float(env.max()) < 0.15          # yariçap ~0.1 m


def test_supersonic_report_helpers_importable():
    # figür/rapor fonksiyonlari yüklenebilir (VTK/matplotlib yoksa bile import OK)
    assert callable(sr.build_supersonic_report)
    assert callable(sr.render_field_figure)
    assert callable(sr.export_field_cutplane)


def test_mesh_metrics_parses_checkmesh(tmp_path):
    (tmp_path / "log.checkMesh").write_text(
        "    cells:            336143\n"
        "    Max aspect ratio = 3.853635 OK.\n"
        "    Mesh non-orthogonality Max: 46.29828 average: 0.95\n"
        "    Max skewness = 1.835658 OK.\nMesh OK.\n")
    mm = sr._mesh_metrics(tmp_path)
    assert mm["cells"] == 336143
    assert abs(mm["skew_max"] - 1.8357) < 1e-3
    assert abs(mm["non_ortho_max"] - 46.298) < 1e-2
    assert abs(mm["aspect_max"] - 3.8536) < 1e-3
    assert mm["mesh_ok"] is True


def test_canonicalize_axial_orients_rocket():
    import trimesh

    from vehicle_pipeline import canonicalize_axial
    # dikey modellenen roket (uzun eksen z) → +x'e hizalanır, ince kesit y/z'de
    rok_z = trimesh.creation.cylinder(radius=0.05, height=1.6)
    out, note = canonicalize_axial(rok_z)
    ext = (out.bounds[1] - out.bounds[0])
    assert ext[0] > 1.5 and ext[1] < 0.2 and ext[2] < 0.2   # uzun eksen artık x
    assert note and "x" in note
    # yassı kanat (yuvarlak kesit değil) → DOKUNULMAZ (None)
    wing = trimesh.creation.box(extents=(0.5, 2.0, 0.05))
    assert canonicalize_axial(wing)[1] is None
    # zaten +x hizalı roket → no-op
    rok_x = trimesh.creation.cylinder(radius=0.05, height=1.6)
    rok_x.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    assert canonicalize_axial(rok_x)[1] is None


def test_cp_theory_values():
    # M0.74 transonik: durma Cp0>1 (sıkıştırılabilirlik), kritik Cp*<0
    assert sr._isentropic_cp0(0.74) > 1.0
    assert sr._critical_cp(0.74) < 0.0
    # M2 süpersonik: durma referansı daha yüksek
    assert sr._isentropic_cp0(2.0) > sr._isentropic_cp0(0.74)
