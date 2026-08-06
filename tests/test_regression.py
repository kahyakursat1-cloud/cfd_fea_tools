"""Numerik regresyon ağı — golden değerler.

2026-06-03 canlı doğrulanan çıktıları dondurur. Amaç: kod düzenlemeleri veya
solver sürüm güncellemeleri sonuçları sessizce kaydırırsa testin kırılması.

Saf-analitik testler her zaman koşar. Dış araç (OpenFOAM/CalculiX/conda env)
gerektirenler `external` (+ ağır olanlar `slow`) işaretlidir; CI'da atlanır,
bu makinede `pytest -m external` ile manuel doğrulanır.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# ── Golden değerler (2026-06-03 canlı koşu) ──────────────────────────────────
GOLDEN = {
    "flutter_velocity_ms": 361.9,      # rocket_fin.flutter_velocity("balsa")
    "coupling_lift_Fz_N": 9.4958,      # coupling_fsi, medium_fixed VTK+STL
    "coupling_drag_Fx_N": 1.3449,
    "coupling_conservation": 3.9e-15,
    "cfd_alpha4_Cl": 0.4124,           # run_aoa_polar.py 4 (OpenFOAM)
    "cfd_alpha4_Cd": 0.03795,
    # VLM egimi IKI ASAMADA duzeldi (ikisi de GERILEME DEGIL):
    #   0.0625 -> 0.0483  panel yogunlugu (varsayilan YAKINSAMAMIS: span verimi
    #                     e=1.08 cikiyordu, oysa eliptik yukleme MATEMATIKSEL
    #                     UST SINIRDIR (e=1) — yani eski egim fiziksel olarak
    #                     IMKANSIZ bir cozumden geliyordu)
    #   0.0483 -> 0.0504  UC KUMELEMESI (OutCluster 1.0 -> 0.25). Duzgun aralikli
    #                     dagilim uc girdabinin gradyanini yakalamiyordu; Cl(8)
    #                     serisi MONOTON DEGILDI (0.1417/0.3866/0.3815/0.4324,
    #                     sacilma %11.78). Kumeleme ile monoton: 0.4566/0.4112/
    #                     0.4030/0.4029, band %2.18 (band_from_levels, boyut=1).
    #   0.0504 -> 0.0462  KAMBURLUK ACILDI (VLM_KAMBUR=True). Onceki tum degerler
    #                     SIMETRIK kesitli bir kanada aitti; aracin kanadi
    #                     NACA2412. Kamburluk alpha<=8'de temiz yakinsiyor
    #                     (olculdu), ama dizi salinimli oldugu icin band %2.18 ->
    #                     %19.72'ye cikti (6 kademe: 20..120 panel).
    # DIKKAT: bu altin deger DOGRU demek DEGIL. Ayni sayi `polar_birlestirme`nin
    # tasima-egimi kapisi tarafindan REDDEDILIYOR: kuram 0.07661/derece,
    # olculen 0.04616 (-%40). Farki GOVDE getiriyor (ciplak kanat -%10,
    # kanat+govde -%54). Altin deger BEKLENMEDIK DEGISIMI yakalar, dogrulugu
    # onaylamaz — dogruluk hukmu kapida verilir.
    "vspaero_cl_slope": 0.0462,        # OpenVSP VLM, alpha 0/4/8, 80 span-panel + uc kumeleme 0.25 + kamburluk
    "openrocket_apogee_m": 50.5,       # rockets/simple.ork
    "validate_fea_defl_err_pct": 0.05, # ankastre kiriş, CalculiX
    "fea_wing_limit_SF": 1.61,         # kanat yapısal, kritik gust
}

COUPLING_VTK = ROOT / "mesh_independence/cases/medium_fixed/VTK/aircraft/aircraft_143.vtk"
COUPLING_STL = ROOT / "mesh_independence/cases/medium_fixed/constant/triSurface/aircraft.stl"


# ════════════════════════════════════════════════════════════════════════════
# SAF ANALİTİK — her zaman koşar (dış araç yok)
# ════════════════════════════════════════════════════════════════════════════

def test_flutter_velocity_golden():
    """NACA TN 4197 fin flutter hızı — roketin baskın yapısal kriteri."""
    from rocket_fin import flutter_velocity
    vf = flutter_velocity("balsa")["flutter_velocity_ms"]
    assert vf == pytest.approx(GOLDEN["flutter_velocity_ms"], rel=1e-3)


@pytest.mark.skipif(
    not (COUPLING_VTK.exists() and COUPLING_STL.exists()),
    reason=("medium_fixed CFD VTK/STL fixture diskte yok (~6 GB case, .gitignore'da). "
            "Korunum garantisi tests/test_coupling_fsi.py::test_conservation_machine_precision"
            " ile sentetik girdide her koşuda doğrulanır; burada yalnız bu vakaya ait "
            "golden lift/drag değerleri test edilemiyor."),
)
def test_coupling_conservation_golden():
    """1-way FSI: CFD basınç → FEA düğüm kuvveti, momentum korunumu."""
    from coupling_fsi import cfd_pressure_to_fea_loads
    r = cfd_pressure_to_fea_loads(str(COUPLING_VTK), str(COUPLING_STL))
    assert r["status"] == "SUCCESS"
    assert r["lift_Fz_N"] == pytest.approx(GOLDEN["coupling_lift_Fz_N"], rel=1e-3)
    assert r["drag_Fx_N"] == pytest.approx(GOLDEN["coupling_drag_Fx_N"], rel=1e-3)
    # Korunum hatası makine-epsilon mertebesinde kalmalı (algoritmik garanti)
    assert r["conservation_error"] < 1e-10


# ════════════════════════════════════════════════════════════════════════════
# DIŞ ARAÇ GOLDEN — mevcut JSON sonuçlarından (üretildiyse doğrula)
# CI'da atlanır; bu makinede pipeline koşunca üretilen JSON'lara karşı kontrol.
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.external
def test_cfd_alpha4_polar_golden():
    """OpenFOAM AoA=4 polar — Cl/Cd kayması yakalanır (mesh sabit → tekrarlanabilir)."""
    pj = ROOT / "aoa_polar.json"
    if not pj.exists():
        pytest.skip("aoa_polar.json yok — önce: python run_aoa_polar.py 4")
    data = json.loads(pj.read_text())
    a4 = next((r for r in data if r.get("alpha") == 4 and r.get("status") == "SUCCESS"), None)
    if a4 is None:
        pytest.skip("alpha=4 SUCCESS sonucu yok")
    assert a4["Cl"] == pytest.approx(GOLDEN["cfd_alpha4_Cl"], rel=0.03)
    assert a4["Cd"] == pytest.approx(GOLDEN["cfd_alpha4_Cd"], rel=0.05)


@pytest.mark.external
def test_fea_wing_limit_sf_golden():
    """CalculiX kanat yapısal — limit emniyet faktörü."""
    fj = ROOT / "fea_critical.json"
    if not fj.exists():
        pytest.skip("fea_critical.json yok — önce: python pipeline.py fea")
    d = json.loads(fj.read_text())
    assert d["limit"]["safety_factor"] == pytest.approx(GOLDEN["fea_wing_limit_SF"], rel=0.05)


@pytest.mark.external
def test_vspaero_slope_golden():
    """OpenVSP VLM lift eğrisi eğimi."""
    pj = ROOT / "vspaero_polar.json"
    if not pj.exists():
        pytest.skip("vspaero_polar.json yok — önce: python pipeline.py vspaero 0 4 8")
    _v = json.loads(pj.read_text(encoding="utf-8-sig"))
    _v = _v.get("polar", []) if isinstance(_v, dict) else _v
    data = [d for d in _v if d.get("Cl") is not None]
    if len(data) < 2:
        pytest.skip("yetersiz VLM noktası")
    slope = (data[-1]["Cl"] - data[0]["Cl"]) / (data[-1]["alpha"] - data[0]["alpha"])
    assert slope == pytest.approx(GOLDEN["vspaero_cl_slope"], rel=0.05)


@pytest.mark.external
def test_openrocket_apogee_golden():
    """OpenRocket uçuş simülasyonu — apogee."""
    rj = ROOT / "openrocket_result.json"
    if not rj.exists():
        pytest.skip("openrocket_result.json yok — önce: python pipeline.py rocket")
    d = json.loads(rj.read_text())
    assert d["apogee_m"] == pytest.approx(GOLDEN["openrocket_apogee_m"], rel=0.05)
