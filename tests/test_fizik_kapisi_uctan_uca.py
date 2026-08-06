"""Fizik kapısı mühendisin ELİNE GEÇEN çıktıda görünmeli — kapı sessiz kalırsa işe yaramaz.

Analiz mühendisi ham Cd'yi değil, raporu/sonuç nesnesini okur. Bu testler kapının üç
yüzeyde de göründüğünü çapalar: sonuç nesnesi (fizik_kabul), uyarı listesinin BAŞI ve
raporun en üstündeki zarf banner'ı.
"""
import numpy as np
import pytest

import vehicle_report
from validity_envelope import (
    OUT,
    TREND,
    VALIDATED,
    apply_physics_gate,
    classify_cfd,
    force_admissibility,
    overall_class,
)


class _Sonuc:
    """build_vehicle_report'un okuduğu asgari alan kümesi."""
    status = "OK"
    vehicle_type = "ucak"
    stl = "x.stl"
    velocity = 30.0
    alpha_deg = 4.0
    kalite = "hizli"
    aref_m2 = 0.5
    aref_mode = "frontal"
    cd = -0.0036
    cd_wake = None
    cl = 0.44
    ld = 12.2
    cda_m2 = 0.0016
    drag_N = 0.88
    cd_richardson = None
    belirsizlik = None
    convergence = {"rezidual_ok": True, "drift_ok": True}
    sinir_tabaka = None
    pervane = None
    cp_vtk = ""
    kesit_vtk = ""
    mesh_duyarlilik = None
    case_dir = ""
    report = ""
    error = ""
    validity = None
    fizik_kabul = None
    uyarilar = []
    mesh = {"hucre_sayisi": 100000, "non_ortho_max": 40.0, "skew_max": 1.5}
    geometry = {"dosya": "x.stl", "boyutlar_m": [1.0, 0.5, 0.2], "lmax_m": 1.0,
                "ucgen_sayisi": 1000, "su_gecirmez": True, "hacim_m3": 0.01,
                "alan_m2": 0.5, "on_alan_m2": 0.05, "ince_kalinlik_m": 0.01}


def test_negatif_cd_sonuc_nesnesinde_isaretlenir():
    f = force_admissibility(_Sonuc.cd, _Sonuc.cl, _Sonuc.alpha_deg)
    assert f["verdict"] == "inadmissible"


def test_fizik_kapisi_zarf_sinifini_ezer():
    """α=4°, M<0.3 + GCI bandı normalde Cd/Cl'i DOĞRULANMIŞ verir; fizik-dışı sayı ezmeli."""
    v = classify_cfd("ucak", 4.0, 0.09, has_gci_band=True, band_pct=2.0)
    assert [x.klass for x in v[:2]] == [VALIDATED, VALIDATED]
    ezilmis = apply_physics_gate(v, force_admissibility(-0.0036, 0.44, 4.0))
    assert overall_class(ezilmis) == OUT
    assert not any(x.design_safe for x in ezilmis)
    # gerekçe mesajlara da yazılmalı — aksi halde "ZARF-DIŞI" başlığı altında
    # "tasarım kararı için kullanılabilir" açıklaması kalır
    assert all("FİZİK KAPISI" in x.message for x in ezilmis)
    assert not any("kullanılabilir" in x.message for x in ezilmis)


def test_supheli_dogrulanmisi_egilime_indirir():
    v = classify_cfd("ucak", 4.0, 0.09, has_gci_band=True, band_pct=2.0)
    inik = apply_physics_gate(v, force_admissibility(0.03, -0.4, 4.0))   # ters işaretli lift
    assert [x.klass for x in inik[:2]] == [TREND, TREND]
    assert overall_class(inik) == TREND


def test_saglikli_kosuda_zarf_degismez():
    v = classify_cfd("ucak", 4.0, 0.09, has_gci_band=True, band_pct=2.0)
    assert apply_physics_gate(v, force_admissibility(0.03, 0.44, 4.0)) is v
    assert apply_physics_gate(v, None) is v


def test_raporda_fizik_kapisi_banner_altinda_gorunur(tmp_path, monkeypatch):
    r = _Sonuc()
    r.fizik_kabul = force_admissibility(r.cd, r.cl, r.alpha_deg)
    r.uyarilar = ["SONUÇ FİZİK KAPISINDAN GEÇMEDİ: negatif/sıfır sürükleme"]
    for ad in ("_fig_convergence", "_fig_residuals", "_fig_geometry"):
        monkeypatch.setattr(vehicle_report, ad, lambda *a, **k: None, raising=False)
    yol = vehicle_report.build_vehicle_report(r, [], {}, tmp_path)
    metin = yol.read_text(encoding="utf-8")
    ust = metin.split("## 1. Geometri")[0]
    assert "FİZİK KAPISI" in ust
    assert "tasarım kararında KULLANILMAZ" in metin
    assert "✅ DOĞRULANMIŞ" not in ust, "fizik-dışı koşu banner'da doğrulanmış satır göstermemeli"
    assert "Evet" not in ust.split("| Büyüklük |")[1].split("\n>\n")[0], \
        "hiçbir büyüklük 'tasarımda kullanılır: Evet' olmamalı"
    assert r.validity["sinif"] == OUT


def test_saglikli_kosu_kapiyi_tetiklemez(tmp_path, monkeypatch):
    r = _Sonuc()
    r.cd, r.cl = 0.032, 0.44
    r.fizik_kabul = force_admissibility(r.cd, r.cl, r.alpha_deg)
    assert r.fizik_kabul["verdict"] == "ok"
    for ad in ("_fig_convergence", "_fig_residuals", "_fig_geometry"):
        monkeypatch.setattr(vehicle_report, ad, lambda *a, **k: None, raising=False)
    metin = vehicle_report.build_vehicle_report(r, [], {}, tmp_path).read_text(encoding="utf-8")
    assert "FİZİK KAPISI" not in metin


def test_pipeline_uyariyi_listenin_basina_koyar():
    """Kaynak-düzeyi çapa: fizik uyarısı diğer uyarılardan ÖNCE eklenmeli."""
    import inspect

    import vehicle_pipeline
    src = inspect.getsource(vehicle_pipeline.run_vehicle_analysis)
    # cagri rejim beyaniyla cok satira yayildi (bkz. test_cl_rejim_siniri);
    # capa cagrinin BASLANGICINA tutunur, tam metnine degil.
    i_fizik = src.index("force_admissibility(cd, cl, alpha_deg,")
    i_mesh = src.index("Mesh non-ortogonallik")
    assert i_fizik < i_mesh
    assert np.isfinite(0.0)  # numpy importu testin ortam kontrolü
