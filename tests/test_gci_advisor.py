"""gci_advisor — GCI sonuç-hasadı + koşu-öncesi öğrenilen-öncül (kNN)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gci_advisor as ga  # noqa: E402

_GEO = {"dosya": "r.stl", "boyutlar_m": [0.8, 0.08, 0.08], "lmax_m": 0.8,
        "ucgen_sayisi": 2000, "su_gecirmez": True, "on_alan_m2": 0.005,
        "planform_alan_m2": 0.06, "yuzey_alani_m2": 0.2,
        "ince_yassilik": 0.9, "radyal_doluluk": 1.0}


def _sonuc(gci_fine=8.0, verdikt="⚠️ Mesh bağımsızlığı GÖSTERİLEMEDİ: p dışı",
           u_num=None, p=0.3):
    return {"status": "ok", "vehicle_type": "roket", "geometry": _GEO,
            "mesh": {"cells": 500000},
            "mesh_duyarlilik": {"seviyeler": [{"ad": "kaba"}, {"ad": "orta"}, {"ad": "ince"}],
                                "gci": {"p": p, "gci_fine_pct": gci_fine, "monotonic": True},
                                "verdikt": verdikt},
            "belirsizlik": {"u_sayisal_pct": u_num}}


def test_harvest_collects_and_rewrites(tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "HERE", tmp_path)
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "gci_memory.jsonl")
    for i, (g, v) in enumerate([(4.0, "✅ Yakınsadı"), (60.0, "⚠️ GÖSTERİLEMEDİ"),
                                (12.0, "⚠️ GÖSTERİLEMEDİ")]):
        d = tmp_path / "vehicle_runs" / f"m{i}"
        d.mkdir(parents=True)
        (d / "sonuc.json").write_text(json.dumps(_sonuc(g, v)), encoding="utf-8")
    (tmp_path / "vehicle_runs" / "bos").mkdir()
    (tmp_path / "vehicle_runs" / "bos" / "sonuc.json").write_text(
        json.dumps({"status": "failed"}), encoding="utf-8")   # GCI'sız → alınmaz
    r = ga.harvest()
    assert r["n_kayit"] == 3 and r["asimptotik"] == 1
    recs = ga._load()
    assert all(rc["tip"] == "roket" and rc["metrik"] for rc in recs)
    r2 = ga.harvest()                              # idempotent: yeniden yazar, şişmez
    assert r2["n_kayit"] == 3


def test_advise_predicts_band_and_asymptotic_probability(tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "mem.jsonl")
    import auto_pilot as ap
    metrik = ap.classify_vehicle(_GEO)["metrik"]
    recs = [{"tip": "roket", "metrik": metrik, "u_num_pct": u, "p": 0.4,
             "asimptotik_ok": ok} for u, ok in
            [(40.0, False), (60.0, False), (55.0, False), (35.0, False), (8.0, True)]]
    (tmp_path / "mem.jsonl").write_text(
        "".join(json.dumps(r) for r in recs).replace("}{", "}\n{") + "\n", encoding="utf-8")
    out = ga.advise(metrik, "roket")
    assert out is not None and out["n_destek"] == 5 and out["ayni_tip"]
    assert out["asimptotik_olasilik"] < 0.5        # çoğunluk kapıyı geçememiş
    assert "LSR" in out["oneri"]                   # → 4+ seviye + LSR önerisi
    assert 8.0 <= out["u_num_beklenen_pct"] <= 60.0
    assert "ÖNCÜL" in out["etiket"]                # dürüstlük etiketi zorunlu


def test_advise_refuses_thin_data(tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "mem.jsonl")
    import auto_pilot as ap
    metrik = ap.classify_vehicle(_GEO)["metrik"]
    (tmp_path / "mem.jsonl").write_text(
        json.dumps({"tip": "roket", "metrik": metrik, "u_num_pct": 10.0,
                    "asimptotik_ok": True}) + "\n", encoding="utf-8")
    assert ga.advise(metrik, "roket") is None      # n<4 → şeffaf ret, sahte güven yok
