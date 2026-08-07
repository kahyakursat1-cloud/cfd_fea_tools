"""Et kalınlığı kestirimi — ince özelliği GERÇEKTEN görüyor mu?

Bu sayı FEA kabuk kalınlığının ve `resolution_warning`'in girdisi. MiniHawk'ta
`rtree` yokken ray yolu sessizce düşmüş, bbox yedeği (gövde çapı 80 mm) ölçüm
sanılmış ve kanat hiç ölçülmemişti. Kusur düzeltildi; bu testler iki şeyi
bağlıyor: (1) ray yolu ince özelliği gövdeye rağmen buluyor, (2) düşüş
gerçekleştiğinde `kalinlik_olculdu_mu()` bunu SÖYLÜYOR.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

trimesh = pytest.importorskip("trimesh")

from vehicle_pipeline import (  # noqa: E402
    estimate_thin_thickness,
    kalinlik_olculdu_mu,
)


def _govde_ve_ince_kanat():
    """80 mm çaplı gövde + 4 mm kalınlıkta düz kanat. Bbox en-ince boyutu
    kanadın AÇIKLIĞI kadar büyük olur; ince özelliği yalnız ray görür."""
    govde = trimesh.creation.box(extents=[0.30, 0.08, 0.08])
    kanat = trimesh.creation.box(extents=[0.06, 0.40, 0.004])
    return trimesh.util.concatenate([govde, kanat])


def test_dolu_kupte_kalinlik_KENAR_UZUNLUGU():
    kup = trimesh.creation.box(extents=[0.1, 0.1, 0.1])
    t = estimate_thin_thickness(kup, samples=400)
    assert t is not None
    if kalinlik_olculdu_mu()["olculdu"]:
        assert t == pytest.approx(0.1, rel=0.15)


def test_ince_kanat_GOVDEYE_RAGMEN_bulunuyor():
    m = _govde_ve_ince_kanat()
    t = estimate_thin_thickness(m, samples=600)
    if not kalinlik_olculdu_mu()["olculdu"]:
        pytest.skip("ray backend yok — bu ortamda bbox yedeği geçerli")
    bbox_min = float((m.bounds[1] - m.bounds[0]).min())
    assert t < bbox_min, "ince özellik bbox'ın altına inmedi — maskelenmiş"
    assert t < 0.02, f"4 mm kanat {t*1000:.1f} mm ölçüldü"


def test_dusuk_persentil_INCEYI_secer():
    """Persentil yükseldikçe kestirim kalınlaşır: alt persentil tercihi
    'gövde inceyi maskelemesin' amacını taşıyor."""
    m = _govde_ve_ince_kanat()
    ince = estimate_thin_thickness(m, samples=600, percentile=10.0)
    if not kalinlik_olculdu_mu()["olculdu"]:
        pytest.skip("ray backend yok")
    kalin = estimate_thin_thickness(m, samples=600, percentile=90.0)
    assert ince <= kalin


def test_ray_dusunce_KAYNAK_yalan_soylemiyor(monkeypatch):
    """Sessiz bozulmanın kendisi: yedeğe düşülünce olculdu=False olmalı ve
    neden ölçülmediği yazmalı. Aksi halde bbox ölçüm sanılır."""
    def _patla(*a, **k):
        raise ModuleNotFoundError("No module named 'rtree'")
    monkeypatch.setattr(trimesh.proximity, "thickness", _patla)
    kup = trimesh.creation.box(extents=[0.3, 0.08, 0.05])
    t = estimate_thin_thickness(kup, samples=100)
    k = kalinlik_olculdu_mu()
    assert k["olculdu"] is False
    assert "rtree" in k["neden"]
    assert t == pytest.approx(0.05, rel=1e-6)   # bbox en-ince boyutu


def test_yetersiz_ornek_de_OLCUM_sayilmiyor(monkeypatch):
    """İstisna atılmadan da düşüş olur: geçerli örnek eşiğin altındaysa
    dönen değer bbox'tır ve bu da ölçüm değildir."""
    monkeypatch.setattr(trimesh.proximity, "thickness",
                        lambda *a, **k: np.full(10, np.nan))
    kup = trimesh.creation.box(extents=[0.3, 0.08, 0.05])
    estimate_thin_thickness(kup, samples=200)
    k = kalinlik_olculdu_mu()
    assert k["olculdu"] is False
    assert "yetersiz" in k["neden"]


def test_dejenere_geometride_deger_OLCUM_diye_satilmiyor(monkeypatch):
    """Sıfır hacimli (tek üçgen) girdide bbox yedeği anlamsız bir kalınlık
    verir — 1 m. Fonksiyon bunu engelleyemez ama ÖLÇÜM diye sunamaz: tek
    koruma `olculdu` bayrağıdır ve çağıran ona bakmak zorundadır."""
    duz = trimesh.Trimesh(vertices=np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]]),
                          faces=np.array([[0, 1, 2]]))
    monkeypatch.setattr(trimesh.proximity, "thickness",
                        lambda *a, **k: np.array([]))
    t = estimate_thin_thickness(duz, samples=50)
    assert kalinlik_olculdu_mu()["olculdu"] is False
    assert t is None or t > 0.5      # bbox'tan gelen anlamsız büyük değer


# ── İnce özellik FEA mesh'inde kaç elemanla temsil ediliyor ───────────────

def test_ince_ozellik_tek_elemanliysa_HUKUM_soyluyor():
    """thin/2 hedefi 'iki eleman' NİYETİYDİ; clip alt/üst sınıra çarpınca
    niyet tutmaz. Hüküm bunu söylemezse SF sağlam sanılır."""
    from vehicle_fea import yapisal_hukum
    h = yapisal_hukum({"emniyet_faktoru": 3.0,
                       "ince_ozellik_cozunurlugu": {
                           "ince_m": 0.004, "hedef_kenar_m": 0.01,
                           "eleman_karsi": 0.4, "kalinlik_olculdu": True,
                           "yeterli": False}})
    assert h["seviye"] == "guvenli"          # SF hâlâ yüksek
    assert any("eleman" in g for g in h["gerekce"]), h["gerekce"]


def test_kalinlik_olculmediyse_HUKUM_bunu_ayirt_ediyor():
    """İki farklı kusur: 'ölçtük ama ağ kaba' ile 'hiç ölçmedik'. İkincisi
    daha kötü — hangi kalınlığa göre boyutlandığı bilinmiyor."""
    from vehicle_fea import yapisal_hukum
    h = yapisal_hukum({"emniyet_faktoru": 3.0,
                       "ince_ozellik_cozunurlugu": {
                           "ince_m": 0.08, "hedef_kenar_m": 0.04,
                           "eleman_karsi": 2.0, "kalinlik_olculdu": False,
                           "kaynak_notu": "ModuleNotFoundError: rtree",
                           "yeterli": False}})
    g = " ".join(h["gerekce"])
    assert "ÖLÇÜLMEDİ" in g and "rtree" in g


def test_cozunurluk_yeterliyse_gereksiz_uyari_YOK():
    from vehicle_fea import yapisal_hukum
    h = yapisal_hukum({"emniyet_faktoru": 3.0,
                       "ince_ozellik_cozunurlugu": {
                           "ince_m": 0.02, "hedef_kenar_m": 0.005,
                           "eleman_karsi": 4.0, "kalinlik_olculdu": True,
                           "yeterli": True}})
    assert not any("eleman" in g or "ÖLÇÜLMEDİ" in g for g in h["gerekce"])


def test_hukum_gerekcesi_RAPORA_da_giriyor(tmp_path):
    """Gerekçe arayüzde yazılıyor, raporda yazılmıyordu. Rapor dışarıya
    verilen belgedir; SF'yi sınırlayan koşul orada eksikse okuyucu çıplak
    SF görür."""
    from vehicle_fea import _append_report
    rap = tmp_path / "rapor"
    rap.mkdir()
    (rap / "RAPOR.md").write_text("# Test\n\n---\n*Otomatik üretildi*\n",
                                  encoding="utf-8")
    _append_report(tmp_path, {
        "status": "ok", "model": "dolu katı", "malzeme": "Al 6061-T6",
        "mesnet": "kök", "dugum": 1000, "eleman": 500, "sabit_dugum": 20,
        "toplam_kuvvet_N": 12.3, "max_sehim_mm": 0.4, "_not": "dolu-katı",
        "max_von_mises_MPa": 30.0, "emniyet_faktoru": 3.0,
        "ince_ozellik_cozunurlugu": {
            "ince_m": 0.004, "hedef_kenar_m": 0.01, "eleman_karsi": 0.4,
            "kalinlik_olculdu": True, "yeterli": False}})
    txt = (rap / "RAPOR.md").read_text(encoding="utf-8")
    assert "HÜKÜM GEREKÇESİ" in txt
    assert "0.4 eleman" in txt
