"""Çözülen geometrinin ok açısı KAYITTA duruyor mu.

ÖLÇÜLDÜ 2026-08-23: 30° ok açılı bir levha hatta verildi; kanonikleştirme ana
ekseni hizalarken hücum kenarı ok açısını 5,6°'ye DÜŞÜRDÜ ve kayıtta bunun izi
yoktu. Oryantasyon alanı yalnız "burun=+x üst=+z" diyordu; hazırlık kaydı
dönmeyi NİTELİKSEL beyan ediyordu ("asal eksenler→xyz") ama NE KADAR döndüğünü
değil.

Ok açısı aerodinamik olarak anlamlı bir büyüklüktür --- eğilme-burulma
kuplajını, dolayısıyla statik aeroelastik davranışı o belirler. Sessizce
değiştirmek, kullanıcının verdiği geometriden BAŞKA bir şey çözmek olur.

TANIM: HÜCUM KENARI ok açısı --- her açıklık istasyonunun kendi $x_{min}$'i
alınır, dolayısıyla ok kayması veterle karışmaz.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from vehicle_pipeline import _planform_ok_acisi  # noqa: E402


def _ok_levha(tmp_path: Path, lam_deg: float, L=0.300, veter=0.040, t=0.001):
    """Kanonik çerçevede ok açılı levha: açıklık y, veter x, kalınlık z."""
    tan = np.tan(np.radians(lam_deg))
    v = []
    for y in (0.0, L):
        x0 = y * tan
        for x in (x0, x0 + veter):
            for z in (0.0, t):
                v.append((x, y, z))
    f = [(0, 2, 3), (0, 3, 1), (4, 7, 6), (4, 5, 7), (0, 1, 5), (0, 5, 4),
         (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]
    m = trimesh.Trimesh(vertices=np.array(v), faces=np.array(f), process=True)
    p = tmp_path / f"ok{lam_deg:g}.stl"
    m.export(p)
    return p


@pytest.mark.parametrize("lam", [0.0, 15.0, 30.0, 45.0, 60.0])
def test_ok_acisi_GERI_okunuyor(tmp_path, lam):
    """45° ve 60°'de de tutmalı: orada ok kayması açıklıktan büyüktür ve
    sınırlayıcı kutuya bakan bir ölçüt eksenleri yer değiştirir."""
    olculen = _planform_ok_acisi(_ok_levha(tmp_path, lam))
    assert olculen == pytest.approx(lam, abs=0.3), (
        f"{lam}° ok açılı levhada {olculen}° ölçüldü")


def test_GERI_ok_acisi_da_okunuyor(tmp_path):
    assert _planform_ok_acisi(_ok_levha(tmp_path, -20.0)) == pytest.approx(-20.0, abs=0.3)


def test_KANAT_OLMAYAN_govdede_hukum_YOK(tmp_path):
    """Küpte ok açısı tanımsızdır; 0 dönmek onu 'ok açısı yok' göstermek olurdu."""
    p = tmp_path / "kup.stl"
    trimesh.creation.box(extents=(0.1, 0.1, 0.1)).export(p)
    assert _planform_ok_acisi(p) is None


def test_OKUNAMAYAN_dosya_sifir_donmuyor(tmp_path):
    assert _planform_ok_acisi(tmp_path / "yok.stl") is None


def test_GERCEK_kosularda_makul(tmp_path):
    """Düz levha 0°, MiniHawk 0° (düz kanat), küp tanımsız."""
    for ad, beklenen in (("fsi_tahrikH/fsi_tahrikH_prep.stl", 0.0),
                         ("minihawk/minihawk_prep.stl", 0.0)):
        p = KOK / "vehicle_runs" / ad
        if not p.exists():
            continue
        assert _planform_ok_acisi(p) == pytest.approx(beklenen, abs=0.5), ad


def test_HAT_bu_alani_geometriye_YAZIYOR():
    """Ölçüm üretiliyor ama kayda girmiyorsa görünmez — deponun baskın kusuru."""
    import ast
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    yazim = [d for d in ast.walk(ast.parse(src))
             if isinstance(d, ast.Assign)
             and any(isinstance(t, ast.Subscript)
                     and isinstance(t.slice, ast.Constant)
                     and t.slice.value == "planform_ok_acisi_deg"
                     for t in d.targets)]
    assert yazim, "hat ok açısını geo sözlüğüne yazmıyor"


def test_EKSEN_TAHMIN_EDILMIYOR():
    """Çerçeve zaten biliniyor; geri çıkarmaya çalışan üç ölçüt de kırılmıştı.

    Bu test o kararı bağlar: eksen seçimi yeniden 'akıllı' yapılırsa kırılgan
    teşhis geri gelir.
    """
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    i = src.index("def _planform_ok_acisi(")
    govde = src[i:src.index("\ndef ", i + 10)]
    assert "ACIKLIK, VETER, KALINLIK = 1, 0, 2" in govde
    assert "argmin" not in govde, "eksen yeniden tahmin ediliyor"
