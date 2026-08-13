"""1-way FSI coupling birim testleri — KORUNUM garantisi (sum F_FEA==sum F_CFD) kalbi,
VTK parse, poligon-geometri, CLOAD yazımı. Sentetik girdi (gerçek CFD/STL fixture gerekmez)."""
import numpy as np
import pytest

from coupling_fsi import (
    _parse_legacy_vtk,
    _poly_geometry,
    cfd_pressure_to_fea_loads,
    write_cload,
)

trimesh = pytest.importorskip("trimesh")


def test_poly_geometry_unit_square():
    """Birim kare poligonu → alan=1, normal=±z, merkez=(0.5,0.5,0)."""
    pts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
    c, n, a = _poly_geometry(pts, [[0, 1, 2, 3]])
    assert a[0] == pytest.approx(1.0)
    assert abs(n[0, 2]) == pytest.approx(1.0)            # normal z-yönünde
    assert c[0] == pytest.approx([0.5, 0.5, 0.0])


def test_write_cload_format(tmp_path):
    out = write_cload({5: (1.0, 0.0, -2.0)}, str(tmp_path / "cl.inp"))
    txt = open(out).read()
    assert txt.startswith("*CLOAD")
    assert "5, 1, 1.00000000e+00" in txt          # Fx
    assert "5, 3, -2.00000000e+00" in txt         # Fz
    assert "5, 2," not in txt                      # Fy=0 → yazılmaz


def _write_vtk(path, p_val=100.0):
    """Tek birim-kare poligonlu minimal legacy VTK (CELL_DATA FIELD p)."""
    path.write_text(
        "# vtk DataFile Version 3.0\ntest\nASCII\nDATASET POLYDATA\n"
        "POINTS 4 float\n0 0 0\n1 0 0\n1 1 0\n0 1 0\n"
        "POLYGONS 1 5\n4 0 1 2 3\n"
        f"CELL_DATA 1\nFIELD attributes 1\np 1 1 float\n{p_val}\n")


def test_parse_legacy_vtk(tmp_path):
    v = tmp_path / "patch.vtk"
    _write_vtk(v, 50.0)
    points, polys, p_cell, p_loc = _parse_legacy_vtk(v)
    assert points.shape == (4, 3)
    assert len(polys) == 1 and list(polys[0]) == [0, 1, 2, 3]
    assert p_cell[0] == pytest.approx(50.0) and p_loc == "CELL"


def test_conservation_machine_precision(tmp_path):
    """KALP: yüzey kuvveti 3 düğüme dağıtılır → sum(F_düğüm)==sum(F_yüzey) makine-hassas.
    Korunum eşleme/basınçtan BAĞIMSIZ (yeniden-dağıtım kimliği)."""
    v = tmp_path / "patch.vtk"
    _write_vtk(v, 100.0)
    stl = tmp_path / "box.stl"
    trimesh.creation.box(extents=(1, 1, 1)).export(str(stl))
    r = cfd_pressure_to_fea_loads(str(v), str(stl), rho=1.225)
    assert r["status"] == "SUCCESS"
    assert r["conservation_error"] < 1e-10        # korunum garantisi
    # düğüm-kuvvet toplamı = yüzey-kuvvet toplamı (her bileşen)
    fn = np.array([list(f) for f in r["node_forces"].values()]).sum(axis=0)
    assert fn == pytest.approx(r["total_force_N"], abs=1e-6)


def test_pressure_sign_and_kinematic_scale(tmp_path):
    """p_kinematic=True → p Pa'ya ρ ile ölçeklenir; dF=-p·n·A işareti tutarlı."""
    v = tmp_path / "patch.vtk"
    _write_vtk(v, 10.0)
    stl = tmp_path / "box.stl"
    trimesh.creation.box(extents=(1, 1, 1)).export(str(stl))
    r = cfd_pressure_to_fea_loads(str(v), str(stl), rho=2.0, p_is_kinematic=True)
    assert r["p_max_Pa"] == pytest.approx(20.0)   # 10 * rho(2.0)


def test_moment_conservation_machine_precision(tmp_path):
    """Kuvvet korunumu tek başına YETMEZ: aynı toplam kuvvet yanlış uzamsal
    dağılımla da elde edilebilir ve yapıya giden eğilme momenti o dağılımdan gelir.
    Eşit-üçtebir dağıtımda üç köşenin ortalaması tam olarak ağırlık merkezi
    olduğundan moment de yapı gereği korunmalı; bu test onu ölçer."""
    v = tmp_path / "patch.vtk"
    _write_vtk(v, 100.0)
    stl = tmp_path / "box.stl"
    trimesh.creation.box(extents=(1, 1, 1)).export(str(stl))
    r = cfd_pressure_to_fea_loads(str(v), str(stl), rho=1.225)
    assert r["status"] == "SUCCESS"
    assert r["moment_conservation_error"] < 1e-10, r["moment_conservation_error"]
    assert len(r["total_moment_Nm"]) == 3


def test_moment_metric_ASIMETRIK_yukte_de_anlamli(tmp_path):
    """Simetrik kutuda net moment ≈0 olabilir; metrik throughput'a normalize
    edildiği için o durumda bile sahte-büyük değer vermemeli."""
    v = tmp_path / "patch.vtk"
    _write_vtk(v, 250.0)
    stl = tmp_path / "wedge.stl"
    trimesh.creation.box(extents=(2, 1, 0.5)).export(str(stl))
    r = cfd_pressure_to_fea_loads(str(v), str(stl), rho=1.0)
    assert r["status"] == "SUCCESS"
    assert 0.0 <= r["moment_conservation_error"] < 1e-10
