"""auto_pilot sınıflandırma + konfigürasyon mantığı (sentetik geo dict ile)."""
import math

import auto_pilot as ap


def _geo(L, W, H, planform=None, frontal=None, bodies=1, faces=5000):
    fr = frontal if frontal is not None else math.pi * (min(W, H) / 2) ** 2
    pf = planform if planform is not None else L * W
    return {"boyutlar_m": [L, W, H], "lmax_m": max(L, W, H),
            "on_alan_m2": fr, "planform_alan_m2": pf,
            "govde_sayisi": bodies, "ucgen_sayisi": faces, "su_gecirmez": True}


def test_classify_rocket():
    g = _geo(2.5, 0.12, 0.12)            # ince, yuvarlak kesit
    assert ap.classify_vehicle(g)["tip"] == "roket"


def test_classify_wing_aircraft():
    g = _geo(2.5, 1.2, 0.08, frontal=1.2 * 0.08)   # yassı + geniş
    assert ap.classify_vehicle(g)["tip"] == "ucak"


def test_classify_cube_is_generic():
    g = _geo(0.5, 0.5, 0.5, frontal=0.25)          # küt, kompakt, tek gövde
    assert ap.classify_vehicle(g)["tip"] == "genel"


def test_classify_multikopter():
    g = _geo(0.4, 0.38, 0.12, frontal=0.05, bodies=5)   # kompakt + çok kol
    assert ap.classify_vehicle(g)["tip"] == "multikopter"


def test_quality_scales_with_size():
    assert ap._quality_for(5.0, 50_000) == "hizli"      # büyük geometri
    assert ap._quality_for(0.2, 8_000) == "hassas"      # küçük/basit
    assert ap._quality_for(1.0, 50_000) == "standart"


def test_narrate_referee_offline(monkeypatch):
    # API anahtarı olmadan bile hakem-seviyesi eleştirel yorum (çevrimdışı)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = {"tip": "roket", "guven": 0.8, "kural_tip": "roket",
           "plan": "süpersonik tarama", "gerekce": ["ince"]}
    out = ap.narrate(cfg, {"Cd_toplam": 0.23})
    assert "roket" in out and "V&V" in out and "C_D" in out      # eleştirel öğeler
    assert "API" not in out                                      # şablon değil, hakem


def test_seed_library_loaded():
    # uzman-etiketli seed tabanı yüklenir (eğitim aktif)
    cases = ap._load_cases()
    assert len(cases) >= ap.MIN_CASES
    tipler = {c["onayli_tip"] for c in cases}
    assert {"roket", "ucak", "genel"}.issubset(tipler)


def test_hybrid_subtypes_in_library_and_preset():
    # hibrit alt-tipler seed'de var ve CFD preset'ine eşlenir
    tipler = {c["onayli_tip"] for c in ap._load_cases()}
    assert "kanatli_roket" in tipler and "tilt_rotor" in tipler
    assert ap.PRESET_MAP["kanatli_roket"] == "roket"      # füze → süpersonik roket preset
    assert ap.PRESET_MAP["tilt_rotor"] == "ucak"          # VTOL → kaldırma-ilgili
    cfg = {"kalite": "standart", "guven": 0.7}
    ap.apply_type_settings(cfg, "kanatli_roket")
    assert cfg["rejim"] == "supersonic" and cfg["vehicle_preset"] == "roket"
    ap.apply_type_settings(cfg, "tilt_rotor")
    assert cfg["rejim"] == "subsonic" and cfg.get("aoa_listesi")


def test_learned_vote_knn(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "SEED", tmp_path / "seed.jsonl")
    monkeypatch.setattr(ap, "MEMORY", tmp_path / "mem.jsonl")
    assert ap.learned_vote({"L_D": 11, "W_L": 0.06, "H_L": 0.05, "H_W": 1.0}) is None
    for _ in range(10):
        ap.record_case({"L_D": 12, "W_L": 0.05, "H_L": 0.05, "H_W": 1.0, "govde": 1},
                       "roket", "roket", {"Cd_toplam": 0.2})
    v = ap.learned_vote({"L_D": 11, "W_L": 0.06, "H_L": 0.05, "H_W": 0.95, "govde": 1})
    assert v is not None and v["tip"] == "roket" and v["guven"] >= 0.6


def test_learned_overrides_rule(tmp_path, monkeypatch):
    # kural 'genel' der ama kütüphane güçlü 'multikopter' derse öğrenilen kazanır
    monkeypatch.setattr(ap, "SEED", tmp_path / "seed.jsonl")
    monkeypatch.setattr(ap, "MEMORY", tmp_path / "mem.jsonl")
    m = {"L_D": 1.2, "W_L": 0.7, "H_L": 0.25, "H_W": 0.35, "govde": 1}
    for _ in range(10):
        ap.record_case(m, "genel", "multikopter", {"Cd_toplam": 0.9})
    g = {"boyutlar_m": [0.5, 0.42, 0.15], "on_alan_m2": 0.06,
         "planform_alan_m2": 0.21, "govde_sayisi": 1, "ucgen_sayisi": 5000}
    res = ap.classify_vehicle(g)
    assert res.get("ogrenilen") is not None


def test_cd_outlier_flags_anomaly(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "SEED", tmp_path / "seed.jsonl")
    monkeypatch.setattr(ap, "MEMORY", tmp_path / "mem.jsonl")
    for _ in range(6):
        ap.record_case({"L_D": 12, "W_L": 0.05, "H_L": 0.05, "H_W": 1.0, "govde": 1},
                       "roket", "roket", {"Cd_toplam": 0.2})
    assert ap.cd_outlier("roket", 0.9) is not None      # aykırı
    assert ap.cd_outlier("roket", 0.21) is None          # normal
