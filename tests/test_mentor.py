"""mentor — mesh/ayar-sonuç öğrenmesi (negatif ders dahil) + seviyeli öğretici katman."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mentor  # noqa: E402

_GEO_KANAT = {"dosya": "w.stl", "boyutlar_m": [1.2, 1.5, 0.12], "lmax_m": 1.5,
              "ucgen_sayisi": 5000, "su_gecirmez": True, "on_alan_m2": 0.05,
              "planform_alan_m2": 1.4, "yuzey_alani_m2": 3.0,
              "ince_yassilik": 0.08, "radyal_doluluk": 0.9}


def _metrik(geo=_GEO_KANAT):
    import auto_pilot as ap
    return ap.classify_vehicle(geo)["metrik"]


def _sonuc(ok=True, kalite="standart", n_layers=0, yp_hedef=None, yp_ort=None):
    s = {"status": "ok" if ok else "failed", "vehicle_type": "ucak", "kalite": kalite,
         "geometry": _GEO_KANAT, "mesh": {"cells": 800000, "non_ortho_max": 55},
         "sinir_tabaka": {"katman_sayisi": n_layers, "yplus_hedef": yp_hedef,
                          "yplus": ({"ort": yp_ort} if yp_ort else None)},
         "convergence": {"drift_ok": ok}, "uyarilar": []}
    return s


def test_harvest_records_failures_too(tmp_path, monkeypatch):
    monkeypatch.setattr(mentor, "HERE", tmp_path)
    monkeypatch.setattr(mentor, "MESH_MEMORY", tmp_path / "mesh_memory.jsonl")
    runs = [( "m0", _sonuc(True, "standart")), ("m1", _sonuc(False, "hassas", n_layers=12)),
            ("m2", _sonuc(True, "hassas_nl"))]
    for ad, s in runs:
        d = tmp_path / "vehicle_runs" / ad
        d.mkdir(parents=True)
        (d / "sonuc.json").write_text(json.dumps(s), encoding="utf-8")
    (tmp_path / "vehicle_runs" / "m0" / "fea_sonuc.json").write_text(json.dumps(
        {"status": "ok", "model": "dolu katı", "mesnet": "y_min", "dugum": 40000,
         "eleman_tipi": "C3D10", "tekillik_suphesi": True, "gecersiz": None}),
        encoding="utf-8")
    r = mentor.harvest_mesh()
    assert r["n_cfd"] == 3 and r["n_fea"] == 1 and r["n_basarisiz"] == 1
    assert mentor.harvest_mesh()["n_kayit"] == 4          # idempotent


def test_advise_mesh_learns_layer_collapse(tmp_path, monkeypatch):
    # Negatif ders: kanatlı sınıfta 'hassas' (katmanlı) hep çöktü, 'hassas_nl' başarılı
    # → öneri hassas_nl + risk metni katman-çökmesini söylemeli (hq kampanya dersi, veriden).
    monkeypatch.setattr(mentor, "MESH_MEMORY", tmp_path / "mem.jsonl")
    m = _metrik()
    recs = ([{"tur": "cfd", "tip": "ucak", "metrik": m, "kalite": "hassas",
              "ok": False, "n_layers": 12, "cells": None} for _ in range(3)] +
            [{"tur": "cfd", "tip": "ucak", "metrik": m, "kalite": "hassas_nl",
              "ok": True, "n_layers": 0, "cells": 2_000_000} for _ in range(3)])
    (tmp_path / "mem.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    out = mentor.advise_mesh(m, "ucak")
    assert out["onerilen_kalite"] == "hassas_nl"
    assert out["kalite_basari"]["hassas"] == 0.0
    assert any("hassas_nl" in r or "katman" in r for r in out["riskler"])
    assert out["beklenen_hucre"] == 2_000_000
    assert "ÖNCÜL" in out["etiket"]


def test_advise_mesh_yplus_correction(tmp_path, monkeypatch):
    monkeypatch.setattr(mentor, "MESH_MEMORY", tmp_path / "mem.jsonl")
    m = _metrik()
    recs = [{"tur": "cfd", "tip": "roket", "metrik": m, "kalite": "hassas", "ok": True,
             "n_layers": 12, "cells": 1_000_000, "yplus_hedef": 1.0, "yplus_ort": 3.2}
            for _ in range(4)]
    (tmp_path / "mem.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    out = mentor.advise_mesh(m, "roket")
    assert out["yplus_duzeltme"] is not None
    assert out["yplus_duzeltme"]["olculen_hedef_orani"] == 3.2
    assert "ölçekleyin" in out["yplus_duzeltme"]["oneri"]      # ılımlı oran → ölçekleme


def test_advise_mesh_extreme_yplus_is_collapse_not_scaling(tmp_path, monkeypatch):
    # Oran 164× = katman-çökmesi imzası; 'hedefi 0.01× yap' önerisi YANLIŞ reçete olurdu
    monkeypatch.setattr(mentor, "MESH_MEMORY", tmp_path / "mem.jsonl")
    m = _metrik()
    recs = [{"tur": "cfd", "tip": "roket", "metrik": m, "kalite": "hassas", "ok": True,
             "n_layers": 12, "cells": 1_000_000, "yplus_hedef": 1.0, "yplus_ort": 164.0}
            for _ in range(4)]
    (tmp_path / "mem.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    out = mentor.advise_mesh(m, "roket")
    assert "layer-collapse" in out["yplus_duzeltme"]["oneri"]
    assert "ölçekleyin" not in out["yplus_duzeltme"]["oneri"]


def test_advise_fea_flags_singularity_class(tmp_path, monkeypatch):
    monkeypatch.setattr(mentor, "MESH_MEMORY", tmp_path / "mem.jsonl")
    m = _metrik()
    recs = [{"tur": "fea", "tip": "ucak", "metrik": m, "ok": True, "model": "dolu katı",
             "mesnet": "y_min", "dugum": 30000, "eleman_tipi": "C3D10",
             "tekillik": True, "mekanizma": False} for _ in range(4)]
    (tmp_path / "mem.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    out = mentor.advise_fea(m)
    assert out["tekillik_beklentisi"] == 1.0
    assert any("temsili" in n for n in out["notlar"])
    assert out["onerilen_model"] == "dolu"


def test_advisors_refuse_thin_data(tmp_path, monkeypatch):
    monkeypatch.setattr(mentor, "MESH_MEMORY", tmp_path / "yok.jsonl")
    assert mentor.advise_mesh(_metrik(), "ucak") is None
    assert mentor.advise_fea(_metrik()) is None


def test_egitim_notu_levels_differ_and_match_audience():
    ctx = {"tip": "ucak", "analiz": "polar", "fea": True}
    byf = mentor.egitim_notu(ctx, "byf")
    oyg = mentor.egitim_notu(ctx, "oyg")
    proje = mentor.egitim_notu(ctx, "proje")
    assert byf != oyg != proje
    assert "GCI" not in byf and "y⁺" not in byf       # BYF: jargon yok, analoji var
    assert "piksel" in byf or "fotoğraf" in byf
    assert "GCI" in proje and "RANS" in proje          # PROJE: mühendislik dili
    assert "stall" in oyg.lower() or "perdövites" in byf.lower()   # polar → aoa dersi
    assert "Emniyet faktörü" in oyg                    # fea → SF dersi
    assert mentor.egitim_notu(ctx, "bilinmeyen") == oyg  # bilinmeyen seviye → oyg
