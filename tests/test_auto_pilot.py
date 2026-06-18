"""auto_pilot sınıflandırma + konfigürasyon mantığı (sentetik geo dict ile)."""
import math

import pytest

import auto_pilot as ap


@pytest.fixture
def empty_lib(tmp_path, monkeypatch):
    """Öğrenme kütüphanesini boş izole et → KURAL sınıflandırması deterministik test edilir
    (canlı-birikmiş kütüphaneye bağımlı olmasın; öğrenilen-override ayrı testlerde)."""
    monkeypatch.setattr(ap, "SEED", tmp_path / "s.jsonl")
    monkeypatch.setattr(ap, "REAL_SEED", tmp_path / "r.jsonl")
    monkeypatch.setattr(ap, "MEMORY", tmp_path / "m.jsonl")


def _geo(L, W, H, planform=None, frontal=None, bodies=1, faces=5000):
    fr = frontal if frontal is not None else math.pi * (min(W, H) / 2) ** 2
    pf = planform if planform is not None else L * W
    return {"boyutlar_m": [L, W, H], "lmax_m": max(L, W, H),
            "on_alan_m2": fr, "planform_alan_m2": pf,
            "govde_sayisi": bodies, "ucgen_sayisi": faces, "su_gecirmez": True}


def test_classify_rocket(empty_lib):
    g = _geo(2.5, 0.12, 0.12)            # ince, yuvarlak kesit
    assert ap.classify_vehicle(g)["tip"] == "roket"


def test_classify_wing_aircraft(empty_lib):
    g = _geo(2.5, 1.2, 0.08, frontal=1.2 * 0.08)   # yassı + geniş
    assert ap.classify_vehicle(g)["tip"] == "ucak"


def test_classify_cube_is_generic(empty_lib):
    g = _geo(0.5, 0.5, 0.5, frontal=0.25)          # küt, kompakt, tek gövde
    assert ap.classify_vehicle(g)["tip"] == "genel"


def test_classify_multikopter(empty_lib):
    g = _geo(0.4, 0.38, 0.12, frontal=0.05, bodies=5)   # kompakt + çok kol
    assert ap.classify_vehicle(g)["tip"] == "multikopter"


def test_quality_scales_with_size():
    assert ap._quality_for(5.0, 50_000) == "hizli"      # büyük geometri
    assert ap._quality_for(0.2, 8_000) == "hassas"      # küçük/basit
    assert ap._quality_for(1.0, 50_000) == "standart"


def test_supersonic_quality_is_coarser():
    # süpersonik shockFluid explicit/deltaT-limitli → kaba mesh (intractable olmasın)
    # ses-altı standart kalan geometri, süpersonikte hizli'ye düşer
    assert ap._quality_for(2.34, 720, "supersonic") == "hizli"   # rocket_tvc vakası
    assert ap._quality_for(1.0, 50_000, "supersonic") == "hizli"
    assert ap._quality_for(0.3, 8_000, "supersonic") == "standart"  # çok küçük: makul
    assert ap._regime_for_tip("roket") == "supersonic"
    assert ap._regime_for_tip("kaldirici_govde") == "supersonic"
    assert ap._regime_for_tip("ucak") == "subsonic"


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


def test_real_seed_anchors_loaded():
    # internet-CAD gerçek-dünya çapaları kütüphaneye karışır (gerçek oranlar)
    cases = ap._load_cases()
    real = [c for c in cases if c["dosya"].startswith("real:")]
    assert real, "gerçek-dünya çapaları yüklenmeli"
    assert all(c["kaynak"].startswith("internet-CAD") for c in real)
    # roket çapası mevcut (bbox tavanı uçak↔kaldırıcı gövdede; roket temiz ayrışır)
    assert any(c["onayli_tip"] == "roket" for c in real)
    assert all(c["metrik"].get("planform_frontal") is not None for c in real)


def test_planform_frontal_in_features():
    # planform/frontal ayırt edici boyut olarak k-NN vektöründe yer alır
    a = ap._features({"L_D": 2.2, "W_L": 0.7, "H_L": 0.25, "H_W": 0.4,
                      "planform_frontal": 2.7, "govde": 1})
    b = ap._features({"L_D": 2.2, "W_L": 0.7, "H_L": 0.25, "H_W": 0.4,
                      "planform_frontal": 4.0, "govde": 1})
    assert a != b and len(a) == 7           # pf farkı vektörü değiştirir


def test_thin_flatness_in_features():
    # bbox-üstü kanat-inceliği özelliği: ince kanat (0.1) ≠ kalın gövde (0.45)
    base = {"L_D": 2.2, "W_L": 0.7, "H_L": 0.25, "H_W": 0.4,
            "planform_frontal": 3.0, "govde": 1}
    wing = ap._features({**base, "ince_yassilik": 0.10})
    body = ap._features({**base, "ince_yassilik": 0.45})
    assert wing != body
    # eksik (None) → güvenli varsayılan (küt=1.0), çökmez
    assert len(ap._features({**base, "ince_yassilik": None})) == 7


def test_learned_vote_knn(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "SEED", tmp_path / "seed.jsonl")
    monkeypatch.setattr(ap, "REAL_SEED", tmp_path / "real.jsonl")
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
    monkeypatch.setattr(ap, "REAL_SEED", tmp_path / "real.jsonl")
    monkeypatch.setattr(ap, "MEMORY", tmp_path / "mem.jsonl")
    m = {"L_D": 1.2, "W_L": 0.7, "H_L": 0.25, "H_W": 0.35, "govde": 1}
    for _ in range(10):
        ap.record_case(m, "genel", "multikopter", {"Cd_toplam": 0.9})
    g = {"boyutlar_m": [0.5, 0.42, 0.15], "on_alan_m2": 0.06,
         "planform_alan_m2": 0.21, "govde_sayisi": 1, "ucgen_sayisi": 5000}
    res = ap.classify_vehicle(g)
    assert res.get("ogrenilen") is not None


def test_referee_gate_blocks_bad_cd(tmp_path, monkeypatch):
    # hakem-kapısı: zayıf yakınsama / fiziksel-olmayan / aykırı Cd temiz çapa OLMAZ
    monkeypatch.setattr(ap, "SEED", tmp_path / "seed.jsonl")
    monkeypatch.setattr(ap, "REAL_SEED", tmp_path / "real.jsonl")
    monkeypatch.setattr(ap, "MEMORY", tmp_path / "mem.jsonl")
    m = {"L_D": 12, "W_L": 0.05, "H_L": 0.05, "H_W": 1.0, "govde": 1}
    # temiz koşu → güvenilir çapa
    g_ok = ap.record_case(m, "roket", "roket", {"Cd_toplam": 0.22, "Cd_drift_pct": 1.0})
    assert g_ok["cd_guvenilir"] and not g_ok["suspect"]
    # zayıf yakınsama (drift %12) → şüpheli, çapa değil
    g_drift = ap.record_case(m, "roket", "roket", {"Cd_toplam": 0.3, "Cd_drift_pct": 12.0})
    assert g_drift["suspect"] and not g_drift["cd_guvenilir"]
    # fiziksel olmayan Cd → şüpheli
    assert ap.record_case(m, "roket", "roket", {"Cd_toplam": -0.1})["suspect"]
    # şüpheli vakalar cd_toplam=None yazılır → temiz Cd dağılımına girmez
    cds = [c.get("cd_toplam") for c in ap._load_cases() if c.get("cd_toplam")]
    assert cds == [0.22]                 # yalnız güvenilir koşu çapa oldu
    # tip etiketi yine de öğrenildi (şüpheli vakalar da kütüphanede, metrik+tip)
    assert len(ap._load_cases()) == 3


def test_cd_predict_declines_thin_data(tmp_path, monkeypatch):
    # Geometri-farkında Cd-tahmini: <min_support vaka → şeffaf REDDET (sahte güven yok)
    monkeypatch.setattr(ap, "SEED", tmp_path / "seed.jsonl")
    monkeypatch.setattr(ap, "REAL_SEED", tmp_path / "real.jsonl")
    monkeypatch.setattr(ap, "MEMORY", tmp_path / "mem.jsonl")
    m = {"L_D": 8, "W_L": 0.1, "H_L": 0.1, "H_W": 1.0, "govde": 1}
    for _ in range(3):                       # 3 < min_support(5)
        ap.record_case(m, "roket", "roket", {"Cd_toplam": 0.4, "Cd_drift_pct": 1.0})
    assert ap.cd_predict(m, "roket") is None


def test_cd_predict_and_prior_check(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "SEED", tmp_path / "seed.jsonl")
    monkeypatch.setattr(ap, "REAL_SEED", tmp_path / "real.jsonl")
    monkeypatch.setattr(ap, "MEMORY", tmp_path / "mem.jsonl")
    for i in range(8):                       # 8 benzer roket, Cd≈0.40–0.47
        m = {"L_D": 8 + i * 0.1, "W_L": 0.08, "H_L": 0.08, "H_W": 1.0, "govde": 1}
        ap.record_case(m, "roket", "roket", {"Cd_toplam": 0.40 + 0.01 * i, "Cd_drift_pct": 1.0})
    q = {"L_D": 8.3, "W_L": 0.08, "H_L": 0.08, "H_W": 1.0, "govde": 1}
    pred = ap.cd_predict(q, "roket")
    assert pred is not None and pred["n_destek"] == 8
    assert 0.35 < pred["cd_tahmin"] < 0.50        # komşu Cd'lerin makul ortalaması
    assert ap.cd_prior_check(q, "roket", 0.43) is None   # tutarlı → bayrak yok
    assert ap.cd_prior_check(q, "roket", 2.5) is not None  # bariz sapma → bayrak


def test_cd_outlier_flags_anomaly(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "SEED", tmp_path / "seed.jsonl")
    monkeypatch.setattr(ap, "REAL_SEED", tmp_path / "real.jsonl")
    monkeypatch.setattr(ap, "MEMORY", tmp_path / "mem.jsonl")
    for _ in range(6):
        ap.record_case({"L_D": 12, "W_L": 0.05, "H_L": 0.05, "H_W": 1.0, "govde": 1},
                       "roket", "roket", {"Cd_toplam": 0.2})
    assert ap.cd_outlier("roket", 0.9) is not None      # aykırı
    assert ap.cd_outlier("roket", 0.21) is None          # normal


def test_runtime_band():
    # çözücü-öncesi kaba süre bandı: süpersonik büyük → uzun; ses-altı küçük-hızlı → kısa
    assert "uzun" in ap._runtime_band("supersonic", "hizli", 2.0)
    assert ap._runtime_band("subsonic", "hizli", 0.6) == "hızlı (<15 dk)"
    assert "uzun" in ap._runtime_band("subsonic", "hassas", 0.3)   # hassas → ağır
