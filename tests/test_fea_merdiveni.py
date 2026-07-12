"""FEA merdiveni: CLT eşdeğer-laminat + ortotropik .inp yazımı + spar/kaburga kirişleri."""
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import laminat  # noqa: E402

# Tipik karbon/epoksi UD katman (Pa)
E1, E2, G12, NU12 = 135e9, 10e9, 5e9, 0.30


def test_clt_unidirectional_recovers_ply():
    es = laminat.esdeger_sabitler(E1, E2, G12, NU12, [0, 0, 0, 0], 0.125e-3)
    assert es["Ex"] == pytest.approx(E1, rel=1e-6)
    assert es["Ey"] == pytest.approx(E2, rel=1e-6)
    assert es["Gxy"] == pytest.approx(G12, rel=1e-6)
    assert es["nuxy"] == pytest.approx(NU12, rel=1e-6)


def test_clt_cross_ply_symmetric():
    es = laminat.esdeger_sabitler(E1, E2, G12, NU12, [0, 90, 90, 0], 0.125e-3)
    assert es["Ex"] == pytest.approx(es["Ey"], rel=1e-9)       # çapraz serim → Ex=Ey
    assert E2 < es["Ex"] < E1                                   # katmanlar arası
    assert es["simetrik_mi"]


def test_clt_quasi_isotropic():
    es = laminat.esdeger_sabitler(E1, E2, G12, NU12,
                                  [0, 45, -45, 90, 90, -45, 45, 0], 0.125e-3)
    assert es["Ex"] == pytest.approx(es["Ey"], rel=1e-6)        # quasi-izotropik
    # izotropi ilişkisi: G ≈ E/(2(1+ν)) yaklaşık sağlanır
    g_iso = es["Ex"] / (2 * (1 + es["nuxy"]))
    assert es["Gxy"] == pytest.approx(g_iso, rel=0.05)


def test_clt_asymmetric_warns():
    es = laminat.esdeger_sabitler(E1, E2, G12, NU12, [0, 45, 90], 0.125e-3)
    assert not es["simetrik_mi"] and "SİMETRİK DEĞİL" in es["_not"]


def test_engineering_constants_9_shape():
    es = laminat.esdeger_sabitler(E1, E2, G12, NU12, [0, 90, 90, 0], 0.125e-3)
    ec = laminat.engineering_constants_9(es)
    assert len(ec) == 9 and all(v > 0 for v in ec[:3]) and ec[3] == es["nuxy"]


def test_write_inp_orthotropic_block(tmp_path):
    from analysis.calculix_writer import FEACase, FEAMaterial, write_inp
    from analysis.tet_mesher import TetMesh
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)
    mesh = TetMesh(points=pts, tets=np.array([[0, 1, 2, 3]]),
                   surface_tris=np.array([[0, 1, 2]]), msh_path=tmp_path / "x.msh",
                   element_type="C3D4")
    es = laminat.esdeger_sabitler(E1, E2, G12, NU12, [0, 90, 90, 0], 0.125e-3)
    mat = FEAMaterial("CFRP_esdeger", 70e9, 0.3, 1600.0,
                      engineering_constants=laminat.engineering_constants_9(es))
    inp = write_inp(FEACase(name="orto", mesh=mesh, material=mat), tmp_path)
    txt = inp.read_text(encoding="utf-8")
    assert "*ELASTIC, TYPE=ENGINEERING CONSTANTS" in txt
    satirlar = txt.splitlines()
    i = satirlar.index("*ELASTIC, TYPE=ENGINEERING CONSTANTS")
    assert len(satirlar[i + 1].split(",")) == 8                # ilk 8 değer
    assert float(satirlar[i + 2]) > 0                          # G23 ikinci satırda


def test_spar_kaburga_beams_share_shell_nodes():
    from vehicle_fea import _spar_kaburga_bolumu
    # ince dikdörtgen 'kanat derisi' (1.0 kiriş × 4.0 açıklık × 0.04 kalınlık)
    m = trimesh.creation.box(extents=(1.0, 4.0, 0.04)).subdivide().subdivide().subdivide()
    L, n = _spar_kaburga_bolumu(m, "ALU", sparlar=[0.25, 0.7], kaburga_n=3,
                                elem_offset=len(m.faces))
    assert n > 10 and L[0].startswith("*ELEMENT, TYPE=B31")
    assert any(s.startswith("*BEAM SECTION") and "SECTION=RECT" in s for s in L)
    ilk_eid = int(L[1].split(",")[0])
    assert ilk_eid == len(m.faces) + 1                         # id'ler kabuktan devam
    n1, n2 = (int(x) for x in L[1].split(",")[1:3])
    assert 1 <= n1 <= len(m.vertices) and 1 <= n2 <= len(m.vertices)  # kabuk düğümleri
    bos, n0 = _spar_kaburga_bolumu(m, "ALU", sparlar=None, kaburga_n=0, elem_offset=10)
    assert bos == [] and n0 == 0
