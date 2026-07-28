"""write_cgrid_gmsh — C-grid'in iz kesiğini İÇ sınır yapan dönüştürücü.

Bu testler Construct2D'ye İHTİYAÇ DUYMAZ: sentetik, elle doğrulanabilir bir C-grid
kurar. Sebebi, gerçek koşuda yakalanan iki hatanın ikisinin de saf topoloji hatası
olmasıdır — biri ancak checkMesh'in "defaultFaces 2" satırıyla, diğeri ancak hücre
sayısının kanıtta 34650 / checkMesh'te 34551 çıkmasıyla görüldü. Sentetik gridde
ikisi de doğrudan sayılabilir.
"""
import re
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
from construct2d_bridge import write_cgrid_gmsh  # noqa: E402

NI, NJ, NWKE = 11, 3, 3


def _sentetik_cgrid():
    """j=0: iz kesiği (3 nokta, aynalı) → gövde → iz kesiği. i=0..10."""
    x0 = np.array([3, 2, 1, 0.8, 0.3, 0.0, 0.3, 0.8, 1, 2, 3], dtype=float)
    y0 = np.array([0, 0, 0, 0.05, 0.06, 0.0, -0.06, -0.05, 0, 0, 0], dtype=float)
    X = np.stack([x0, x0 * 1.0 + 0.0, x0 * 1.0], axis=1)
    Y = np.stack([y0, y0 + np.sign(y0 + 1e-9) * 0.5 + 0.5 * (y0 == 0), y0 * 3 + 2.0], axis=1)
    return X, Y


def _yaz(tmp_path):
    X, Y = _sentetik_cgrid()
    p = tmp_path / "m.msh"
    nwke, nhucre_i = write_cgrid_gmsh(str(p), X, Y, NI, NJ)
    return p, nwke, nhucre_i


def _yuzeyler(p: Path, fizik: int):
    """Verilen physical id'li 4-düğümlü yüzey (tip 3) elemanlarının düğüm listeleri."""
    g = p.read_text().split("$Elements")[1]
    out = []
    for satir in g.splitlines():
        t = satir.split()
        if len(t) == 9 and t[1] == "3" and t[3] == str(fizik):
            out.append([int(v) for v in t[5:]])
    return out


def test_iz_kesigi_bulunuyor(tmp_path):
    _, nwke, _ = _yaz(tmp_path)
    assert nwke == NWKE


def test_hucre_sayisi_i_yonunde_ni_eksi_bir(tmp_path):
    """C-grid i-yönünde PERİYODİK DEĞİL. `ni` döndürülünce çağıran hücre sayısını
    fazla rapor ediyordu (kanıt 34650, checkMesh 34551)."""
    _, _, nhucre_i = _yaz(tmp_path)
    assert nhucre_i == NI - 1


def test_airfoil_yamasi_FIRAR_KENARI_yuzlerini_kapsiyor(tmp_path):
    """İlk sürüm range(nwke, ni-1-nwke) idi: firar kenarına bitişik İKİ yüz hiçbir
    yamaya atanmıyor, gmshToFoam onları `defaultFaces`'e düşürüyordu. Kuvvet
    integrali `airfoil` yaması üzerinden alındığı için o iki yüz sessizce
    kaçırılırdı — Cl/Cd hatalı ama "başarılı" görünürdü."""
    p, nwke, _ = _yaz(tmp_path)
    yuz = _yuzeyler(p, 1)
    assert len(yuz) == NI - 2 * nwke + 1 == 6


def test_j0_kenarlarinin_TAMAMI_ya_airfoil_ya_ic_yuz(tmp_path):
    """Örtme testi: j=0 çizgisindeki hiçbir kenar boşta kalmamalı."""
    p, nwke, _ = _yaz(tmp_path)
    airfoil = {frozenset(k[:2]) for k in _yuzeyler(p, 1)}

    X, Y = _sentetik_cgrid()
    kimlik = {}
    n = 0
    for i in range(NI):
        for j in range(NJ):
            if j == 0 and i >= NI - nwke:
                kimlik[(i, j)] = kimlik[(NI - 1 - i, 0)]
                continue
            n += 1
            kimlik[(i, j)] = n

    kenarlar = [frozenset((kimlik[(i, 0)], kimlik[(i + 1, 0)])) for i in range(NI - 1)]
    bosta = [k for k in kenarlar
             if k not in airfoil and kenarlar.count(k) < 2]
    assert not bosta, f"hicbir yamaya ait olmayan j=0 kenari: {bosta}"


def test_iz_kesigi_dugumleri_BIRLESTIRILIYOR(tmp_path):
    """Birleşmezse iki yaka aynı yerde iki ayrı duvar olur (eski hata)."""
    p, nwke, _ = _yaz(tmp_path)
    n = int(re.search(r"\$Nodes\n(\d+)", p.read_text()).group(1))
    assert n == 2 * (NI * NJ - nwke)


def test_C_GRID_OLMAYAN_grid_sessizce_kabul_edilmiyor(tmp_path):
    X, Y = _sentetik_cgrid()
    X[0, 0] += 1.0                       # aynalama bozuldu -> iz kesiği yok
    with pytest.raises(ValueError, match="iz kesiği"):
        write_cgrid_gmsh(str(tmp_path / "x.msh"), X, Y, NI, NJ)
