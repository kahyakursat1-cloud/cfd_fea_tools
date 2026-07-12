"""yolculuk — rehberli analiz-mühendisi yetiştirme motoru: plan + seviye ilerlemesi."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yolculuk  # noqa: E402


def test_plan_wing_includes_polar_and_lessons():
    p = yolculuk.plan({"tip": "ucak", "analiz": "polar"}, seviye="oyg")
    adlar = [a["ad"] for a in p]
    assert adlar[0] == "geometri_kontrol" and adlar[-1] == "rapor_savunma"
    assert "polar_tarama" in adlar and "dogrulama_gci" in adlar
    assert adlar.index("mesh_secim") < adlar.index("ilk_kosu") < adlar.index("dogrulama_gci")
    mesh = next(a for a in p if a["ad"] == "mesh_secim")
    assert mesh["soru"] and mesh["ipucu"] and mesh["ders_md"]     # her adım öğretir
    assert "Öğrenme Kutusu" in mesh["ders_md"]                     # ÖYG dili


def test_plan_rocket_gets_cd_mach_not_polar():
    p = yolculuk.plan({"tip": "roket", "analiz": "cd_mach"}, seviye="byf")
    adlar = [a["ad"] for a in p]
    assert "polar_tarama" not in adlar and "cd_mach_tarama" in adlar
    ders = next(a["ders_md"] for a in p if a["ders_md"])
    assert "GCI" not in ders                                       # BYF: jargon yok


def test_plan_car_gets_ground_step():
    p = yolculuk.plan({"tip": "araba", "analiz": "tekil"}, seviye="oyg")
    adlar = [a["ad"] for a in p]
    assert "zemin_etkisi" in adlar and "polar_tarama" not in adlar
    assert adlar.index("zemin_etkisi") < adlar.index("ilk_kosu")   # koşudan önce kurulmalı
    zemin = next(a for a in p if a["ad"] == "zemin_etkisi")
    assert "Zemin etkisi" in (zemin["ders_md"] or "")              # araba → zemin dersi


def test_progression_byf_to_proje(tmp_path):
    prof = tmp_path / "profil.json"
    assert yolculuk._seviye_from({"analiz_sayisi": 0, "adimlar": {}}) == "byf"
    p = None
    for _ in range(yolculuk.ESIK_PROJE):
        yolculuk.adim_tamamla("dogrulama_gci", profil_dosya=prof)
        p = yolculuk.adim_tamamla("rapor_savunma", profil_dosya=prof)
    assert p["analiz_sayisi"] == yolculuk.ESIK_PROJE
    assert p["seviye"] == "proje"                                  # şeffaf kuralla terfi
    ara = {"analiz_sayisi": yolculuk.ESIK_OYG, "adimlar": {}}
    assert yolculuk._seviye_from(ara) == "oyg"
    # PROJE için GCI+savunma şart: sayı yetse de doğrulamasız terfi YOK
    cok_ama_gcisiz = {"analiz_sayisi": 20, "adimlar": {"rapor_savunma": 20}}
    assert yolculuk._seviye_from(cok_ama_gcisiz) == "oyg"


def test_invalid_step_rejected(tmp_path):
    with pytest.raises(ValueError):
        yolculuk.adim_tamamla("olmayan_adim", profil_dosya=tmp_path / "p.json")
