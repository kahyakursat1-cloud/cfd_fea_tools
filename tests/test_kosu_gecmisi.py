"""kosu_gecmisi — koşu tarama + A/B karşılaştırma (ayırt-edilebilirlik hükmüyle)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kosu_gecmisi as kg  # noqa: E402


def _sonuc(cd=0.30, u=6.0, kalite="standart", tip="roket", hiz=30.0):
    return {"status": "ok", "vehicle_type": tip, "kalite": kalite, "velocity": hiz,
            "alpha_deg": 0.0, "cd": cd, "cl": None, "ld": None, "drag_N": round(cd * 10, 2),
            "belirsizlik": {"u_toplam_pct": u, "u_sayisal_kaynak": "GCI"},
            "mesh": {"cells": 500000}, "sinir_tabaka": {"yplus": {"ort": 40.0}},
            "mesh_duyarlilik": {"verdikt": "✅ Yakınsadı"}, "report": ""}


def _kur(tmp_path, adlar_cd):
    for ad, cd in adlar_cd:
        d = tmp_path / "vehicle_runs" / ad
        d.mkdir(parents=True)
        (d / "sonuc.json").write_text(json.dumps(_sonuc(cd)), encoding="utf-8")


def test_tara_and_tablo(tmp_path, monkeypatch):
    monkeypatch.setattr(kg, "HERE", tmp_path)
    _kur(tmp_path, [("m1", 0.30), ("m2", 0.28)])
    k = kg.tara()
    assert len(k) == 2 and {x["ad"] for x in k} == {"m1", "m2"}
    txt = kg.tablo_metni(k)
    assert "m1" in txt and "Cd" in txt
    assert kg.tablo_metni(k, tip="ucak") == "(koşu yok)"


def test_karsilastir_indistinguishable_within_band(tmp_path, monkeypatch):
    # ΔCd %6.7, band RSS %8.5 → fark bandın İÇİNDE: A/B ayırt edilemez (dürüst hüküm)
    monkeypatch.setattr(kg, "HERE", tmp_path)
    _kur(tmp_path, [("a", 0.30), ("b", 0.28)])
    c = kg.karsilastir("a", "b")
    ay = c["ayirt_edilebilirlik"]
    assert ay["dCd_pct"] == pytest.approx(6.67, abs=0.01)
    assert "İÇİNDE" in ay["hukum"]
    assert not c["uyarilar"]                       # aynı kalite/tip/hız → uyarı yok


def test_karsilastir_flags_family_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(kg, "HERE", tmp_path)
    d1 = tmp_path / "vehicle_runs" / "x1"; d1.mkdir(parents=True)
    d1.joinpath("sonuc.json").write_text(json.dumps(_sonuc(0.5, u=2.0, kalite="hizli")),
                                         encoding="utf-8")
    d2 = tmp_path / "vehicle_runs" / "x2"; d2.mkdir(parents=True)
    d2.joinpath("sonuc.json").write_text(json.dumps(_sonuc(0.3, u=2.0, kalite="hassas")),
                                         encoding="utf-8")
    c = kg.karsilastir("x1", "x2")
    assert any("kalite" in u for u in c["uyarilar"])       # farklı aile uyarısı
    assert "DIŞINDA" in c["ayirt_edilebilirlik"]["hukum"]  # %40 fark, %2.8 band


def test_karsilastir_unknown_run_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(kg, "HERE", tmp_path)
    with pytest.raises(ValueError):
        kg.karsilastir("yok1", "yok2")
