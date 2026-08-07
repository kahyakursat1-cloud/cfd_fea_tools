"""Rapor SAVUNULABİLİRLİK satırları (VKI/TU Delft hakem-düzeyi çıktı garantisi).
Her sayısal iddianın yönetici-parametre (Re/Ma) + doğrulama-kaynağı + belirsizlik-bandı
+ far-field çapraz-kontrol taşıdığını dondurur — AERO-ARCHITECT+ grant kredibilitesi."""
from pathlib import Path

from vehicle_pipeline import VehicleAnalysisResult
from vehicle_report import build_vehicle_report


def _mock(tmp):
    r = VehicleAnalysisResult(
        status="ok", vehicle_type="roket", stl="x.stl", velocity=30.0, alpha_deg=0.0,
        geometry={"dosya": "r.stl", "boyutlar_m": [0.77, 0.08, 0.08], "lmax_m": 0.77,
                  "ucgen_sayisi": 2048, "su_gecirmez": True, "on_alan_m2": 0.005,
                  "planform_alan_m2": 0.06, "yuzey_alani_m2": 0.18, "radyal_doluluk": 1.0})
    r.cd, r.cd_wake, r.cda_m2, r.drag_N = 0.275, 0.245, 0.0014, 0.76
    r.aref_m2, r.aref_mode = 0.005, "frontal"
    r.mesh = {"cells": 343000, "non_ortho_max": 45, "skew_max": 2.1}
    r.convergence = {"iterasyon": 120, "cd_drift_son20pct": 0.5, "drift_ok": True,
                     "son_rezidualler": {"p": "8e-4"}, "rezidual_ok": False}
    r.uyarilar = []
    return build_vehicle_report(r, [(i, 0.27, 0.0) for i in range(120)], {"p": [1e-3]}, tmp)


def test_report_carries_defensibility_lines(tmp_path):
    txt = _mock(tmp_path).read_text(encoding="utf-8")
    assert "Re =" in txt and "Ma =" in txt                      # yönetici parametreler
    assert "Çözücü doğrulaması" in txt and "NACA0012" in txt    # doğrulama-kaynağı (Annex I)
    assert "TREND-düzeyi" in txt                                # Cd belirsizlik-bandı satır-içi
    assert "far-field" in txt and "yakınsama güveni" in txt     # iz-momentum çapraz-kontrol
    assert "## 6. Geçerlilik Sınırları (V&V)" in txt            # V&V limitleri bölümü


def test_kirpilan_itki_RAPOR_SATIRINDA_soyleniyor(tmp_path):
    """Froude kapağı devreye girerse rapor UYGULANAN itkiyi yazmalı.
    Eskiden pervane satırı istenen itkiyi yazıyor, kırpma uyarısı ise dört
    bölüm aşağıda duruyordu: iki bölümü yan yana koymayan okuyucu analiz
    edilmemiş bir itkiyi analiz edilmiş sanıyordu."""
    from vehicle_pipeline import propeller_params
    r = VehicleAnalysisResult(
        status="ok", vehicle_type="roket", stl="x.stl", velocity=5.0, alpha_deg=0.0,
        geometry={"dosya": "r.stl", "boyutlar_m": [0.77, 0.08, 0.08], "lmax_m": 0.77,
                  "ucgen_sayisi": 2048, "su_gecirmez": True, "on_alan_m2": 0.005,
                  "planform_alan_m2": 0.06, "yuzey_alani_m2": 0.18, "radyal_doluluk": 1.0})
    r.cd, r.cda_m2, r.drag_N = 0.275, 0.0014, 0.76
    r.aref_m2, r.aref_mode = 0.005, "frontal"
    r.mesh = {"cells": 343000, "non_ortho_max": 45, "skew_max": 2.1}
    r.convergence = {"iterasyon": 120, "cd_drift_son20pct": 0.5, "drift_ok": True,
                     "son_rezidualler": {"p": "8e-4"}, "rezidual_ok": False}
    r.pervane = propeller_params(5000.0, 0.10, 5.0)
    r.uyarilar = [r.pervane["uyari"]]
    txt = build_vehicle_report(r, [(i, 0.27, 0.0) for i in range(120)],
                               {"p": [1e-3]}, tmp_path).read_text(encoding="utf-8")
    assert "UYGULANDI" in txt and "kırpıldı" in txt
    assert f"{r.pervane['uygulanan_itki_N']}" in txt
