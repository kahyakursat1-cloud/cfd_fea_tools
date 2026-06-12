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


def test_cp_theory_values():
    # M0.74 transonik: durma Cp0>1 (sıkıştırılabilirlik), kritik Cp*<0
    assert sr._isentropic_cp0(0.74) > 1.0
    assert sr._critical_cp(0.74) < 0.0
    # M2 süpersonik: durma referansı daha yüksek
    assert sr._isentropic_cp0(2.0) > sr._isentropic_cp0(0.74)
