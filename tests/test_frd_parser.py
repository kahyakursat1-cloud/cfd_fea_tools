"""FRD parser — tüm FEA sonuç-okuma yolunun tek kapısı; sessiz yanlış-okuma en pahalı hata.

Sabit-genişlik sütun kayması veya eleman bloğunun düğüm sanılması, ccx hatasız koştuğu
için hiçbir yerde patlamaz — yalnızca gerilme/deplasman yanlış çıkar. Bu testler sentetik
ama format-sadık bir .frd üzerinde o yolları çapalar (gerçek ccx çıktısı gerektirmez).
"""
import numpy as np
import pytest

from analysis.frd_parser import parse_frd

DUGUMLER = [(1, 0.0, 0.0, 0.0), (2, 1.0, 0.0, 0.0),
            (3, -1.5, 2.25, -0.125), (4, 1e-4, -3.0, 0.5)]


def _dugum_satiri(nid, x, y, z):
    return f" -1{nid:>10}{x:12.5E}{y:12.5E}{z:12.5E}"


def _veri_satiri(nid, vals):
    return f" -1{nid:>10}" + "".join(f"{v:12.5E}" for v in vals)


def _frd_yaz(yol, disp=None, stress=None, eleman_blogu=True):
    s = ["    1C", "    1UDATE", f"    2C{len(DUGUMLER):>18}"]
    s += [_dugum_satiri(*d) for d in DUGUMLER]
    s.append(" -3")
    if eleman_blogu:
        # Eleman bloğu ATLANMALI: -1 satırları düğüm sanılırsa nokta bulutu bozulur
        s += ["    3C                 1", " -1         1    1    0    1", " -2         1"
              "         2         3         4", " -3"]
    if disp is not None:
        s += ["  100CL  101 DISP", " -4  DISP        4    1",
              " -5  D1          1    2    1    0", " -5  D2          1    2    2    0",
              " -5  D3          1    2    3    0", " -5  ALL         1    2    0    0    1ALL"]
        s += [_veri_satiri(n, v) for n, v in disp]
        s.append(" -3")
    if stress is not None:
        s += ["  100CL  101 STRESS", " -4  STRESS      6    1"]
        s += [f" -5  S{c}          1    4    {i + 1}    1"
              for i, c in enumerate(["XX", "YY", "ZZ", "XY", "YZ", "ZX"])]
        s += [_veri_satiri(n, v) for n, v in stress]
        s.append(" -3")
    s.append(" 9999")
    yol.write_text("\n".join(s), encoding="ascii")
    return yol


def test_dugum_koordinatlari_sutun_kaymasi_olmadan(tmp_path):
    r = parse_frd(_frd_yaz(tmp_path / "a.frd"))
    assert list(r.node_ids) == [1, 2, 3, 4]
    beklenen = np.array([[d[1], d[2], d[3]] for d in DUGUMLER])
    assert np.allclose(r.points, beklenen), "negatif/küçük değerlerde sütun kayması"


def test_eleman_blogu_dugum_sanilmaz(tmp_path):
    """3C bloğundaki -1 satırları nokta bulutuna sızarsa mesh sessizce bozulur:
    eleman bloğunun VARLIĞI okunan düğüm kümesini değiştirmemeli."""
    ile = parse_frd(_frd_yaz(tmp_path / "b1.frd", eleman_blogu=True))
    siz = parse_frd(_frd_yaz(tmp_path / "b2.frd", eleman_blogu=False))
    assert list(ile.node_ids) == list(siz.node_ids) == [d[0] for d in DUGUMLER]
    assert np.array_equal(ile.points, siz.points)


def test_disp_all_sutunu_atilir(tmp_path):
    disp = [(1, [0.0, 0.0, 0.0, 0.0]), (2, [3e-3, 4e-3, 0.0, 5e-3]),
            (3, [0.0, 0.0, -1e-3, 1e-3]), (4, [0.0, 0.0, 0.0, 0.0])]
    r = parse_frd(_frd_yaz(tmp_path / "c.frd", disp=disp))
    assert r.fields["DISP"].shape == (4, 3)
    mag = r.displacement_magnitude()
    assert mag[1] == pytest.approx(5e-3)          # 3-4-5 üçgeni
    assert mag.max() == pytest.approx(5e-3)


def test_von_mises_analitik(tmp_path):
    """Tek-eksenli çekme -> vm = σ; saf kayma -> vm = √3·τ."""
    tek_eksen = [1, [200e6, 0, 0, 0, 0, 0]]
    saf_kayma = [2, [0, 0, 0, 50e6, 0, 0]]
    hidrostatik = [3, [80e6, 80e6, 80e6, 0, 0, 0]]   # deviatorik yok -> vm = 0
    r = parse_frd(_frd_yaz(tmp_path / "d.frd",
                           stress=[tek_eksen, saf_kayma, hidrostatik, [4, [0] * 6]]))
    vm = r.von_mises()
    assert vm[0] == pytest.approx(200e6)
    assert vm[1] == pytest.approx(np.sqrt(3) * 50e6)
    assert vm[2] == pytest.approx(0.0, abs=1e-6)


def test_von_mises_onbellek_tutarli(tmp_path):
    r = parse_frd(_frd_yaz(tmp_path / "e.frd", stress=[[i + 1, [100e6, 0, 0, 0, 0, 0]]
                                                       for i in range(4)]))
    assert np.array_equal(r.von_mises(), r.von_mises())
    assert "VON_MISES" in r.fields


def test_alan_yoksa_none(tmp_path):
    r = parse_frd(_frd_yaz(tmp_path / "f.frd"))
    assert r.von_mises() is None and r.displacement_magnitude() is None


def test_dosya_yoksa_hata(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_frd(tmp_path / "yok.frd")


def test_dugumsuz_frd_sessizce_gecmez(tmp_path):
    p = tmp_path / "bos.frd"
    p.write_text("    1C\n 9999\n", encoding="ascii")
    with pytest.raises(RuntimeError):
        parse_frd(p)


def test_ozet_metni(tmp_path):
    r = parse_frd(_frd_yaz(tmp_path / "g.frd",
                           disp=[[1, [1e-3, 0, 0, 1e-3]], [2, [0, 0, 0, 0]],
                                 [3, [0, 0, 0, 0]], [4, [0, 0, 0, 0]]],
                           stress=[[i + 1, [100e6, 0, 0, 0, 0, 0]] for i in range(4)]))
    ozet = r.summary()
    assert "4 düğüm" in ozet and "1.0000 mm" in ozet and "100.00 MPa" in ozet
