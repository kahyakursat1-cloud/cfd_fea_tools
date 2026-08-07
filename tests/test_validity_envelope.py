"""Okula-güvenli geçerlilik-zarfı sınıflandırıcısı — sert-kapı mantığı dondurulur.
Dayanak gerçek doğrulamalar: α≤8 lift OK / α>8 ~%45 (erken stall), mutlak drag yakınsamıyor."""
from validity_envelope import (
    CLMAX_REF,
    OUT,
    TREND,
    VALIDATED,
    analyze_polar_envelope,
    banner_md,
    classify_cfd,
    classify_fea,
    overall_class,
)

# Gerçek geçiş-modeli poları (NACA0012): α=8'de tepe, α=10'da rollover (stall).
_POLAR = [{"alpha": 0, "Cl": -0.0006, "Cd": 0.0037}, {"alpha": 4, "Cl": 0.4235, "Cd": -0.0006},
          {"alpha": 8, "Cl": 0.7832, "Cd": 0.0020}, {"alpha": 10, "Cl": 0.5819, "Cd": 0.052},
          {"alpha": 12, "Cl": 0.6568, "Cd": 0.093}]


def _by_q(verdicts, key):
    return next(v for v in verdicts if key in v.quantity)


def test_attached_flow_lift_design_safe():
    """|α|≤8, ses-altı: taşıma DOĞRULANMIŞ + tasarım-güvenli; mutlak drag EĞİLİM."""
    v = classify_cfd("ucak", 4.0, mach=0.1)
    lift = _by_q(v, "C_L")
    assert lift.klass == VALIDATED and lift.design_safe is True
    drag = _by_q(v, "C_D")
    assert drag.klass == TREND and drag.design_safe is False
    assert overall_class(v) == TREND          # drag eğilim → genel eğilim


def test_high_alpha_lift_out_of_envelope():
    """α>8: taşıma ZARF-DIŞI, tasarım-GÜVENSİZ (erken stall, ~%45)."""
    v = classify_cfd("ucak", 10.0, mach=0.1)
    lift = _by_q(v, "C_L")
    assert lift.klass == OUT and lift.design_safe is False
    assert "45" in lift.message
    assert overall_class(v) == OUT


def test_supersonic_drag_trend_only():
    """Ma≥0.3: mutlak Cd EĞİLİM (~%15 taban-drag fazlası)."""
    v = classify_cfd("roket", 2.0, mach=2.0)
    drag = _by_q(v, "C_D")
    assert drag.klass == TREND and drag.design_safe is False
    assert "15" in drag.message


def test_gci_band_makes_drag_validated():
    """3-mesh GCI varsa mutlak Cd DOĞRULANMIŞ olabilir."""
    v = classify_cfd("ucak", 4.0, mach=0.1, has_gci_band=True)
    assert _by_q(v, "C_D").klass == VALIDATED


def test_fea_representative_safe_peak_trend():
    base = classify_fea(has_singularity=False)
    assert base[0].klass == VALIDATED and base[0].design_safe is True
    sing = classify_fea(has_singularity=True)
    assert any(x.klass == TREND and not x.design_safe for x in sing)


def test_fea_buckling_margin_gate():
    """Burkulma marjı: λ≥1.5 DOĞRULANMIŞ+güvenli; λ<1.5 EĞİLİM+güvensiz (kusur duyarlı)."""
    safe = classify_fea(buckling_margin=2.4)
    buck = _by_q(safe, "Burkulma")
    assert buck.klass == VALIDATED and buck.design_safe is True
    low = _by_q(classify_fea(buckling_margin=1.1), "Burkulma")
    assert low.klass == TREND and low.design_safe is False
    # marj verilmezse burkulma kalemi hiç eklenmez
    assert not any("Burkulma" in x.quantity for x in classify_fea())


def test_banner_loud_gate():
    """Banner: zarf-dışı → 🔴 'KULLANMA', güvensiz kalemler açıklamasıyla listelenir."""
    out_v = classify_cfd("ucak", 12.0, mach=0.1)
    b = banner_md(out_v)
    assert "🔴" in b and "KULLANMA" in b
    assert "HAYIR" in b                        # tasarımda-kullanılır sütunu sert
    assert "Tasarımda kullanılır mı?" in b
    # bağlı akış: sadece sarı dikkat
    ok_v = classify_cfd("ucak", 4.0, mach=0.1)
    assert "🟡" in banner_md(ok_v) and "DİKKAT" in banner_md(ok_v)


def test_polar_envelope_detects_rollover_not_clmax():
    """Stall-onset = Cl-rollover (α=10) yalnız ZARF-SINIRI sinyali; CLmax CFD'den DEĞİL."""
    env = analyze_polar_envelope(_POLAR, clmax_ref=CLMAX_REF["naca0012"])
    assert env.stall_onset_detected and env.stall_onset_alpha == 10.0   # fiziksel rollover
    assert env.alpha_envelope_max == 8.0
    assert env.cfd_clmax_apparent == 0.7832          # görünür tepe — CLmax DEĞİL
    assert env.clmax_reference[0] == 1.49            # gerçek CLmax yalnız deneyden
    assert "GEÇERLİ DEĞİL" in env.verdict and "TÜRETİLMEMİŞ" in env.verdict


def test_polar_envelope_no_ref_refuses_clmax():
    """Deneysel referans yoksa: CLmax CFD'den TAHMİN EDİLMEMELİ der."""
    env = analyze_polar_envelope(_POLAR, clmax_ref=None)
    assert env.clmax_reference is None
    assert "TAHMİN EDİLMEMELİDİR" in env.verdict


def test_polar_envelope_attached_only_no_false_stall():
    """Yalnız bağlı-akış (rollover yok) → stall-onset YANLIŞ tetiklenmez."""
    attached = [{"alpha": 0, "Cl": 0.0}, {"alpha": 4, "Cl": 0.44}, {"alpha": 8, "Cl": 0.85}]
    env = analyze_polar_envelope(attached, clmax_ref=CLMAX_REF["naca0012"])
    assert env.stall_onset_detected is False


def test_GCI_yoksa_gerekce_BU_KOSUYU_anlatiyor():
    """Zarf gerekçesi başka bir çalışmanın ölçümünü bu koşuya atfedemez.

    Eski metin GCI bandı yokken "bu O-grid ailesinde mesh-yakınsamadı
    (p≈0.2)" diyordu; bu, kanat-profili O-grid ailesinin ölçümüydü. Ahmed
    gövdesi ve küp çapa raporlarına aynen basıldı — 3B bluff gövde koşusu,
    hiç kullanmadığı bir 2B grid ailesiyle gerekçelendirildi. Üstelik o aile
    sonradan TMR gridleriyle kapandı (GCI %1.7), yani cümle bugün yanlış.
    """
    from validity_envelope import classify_cfd
    cd = [x for x in classify_cfd("roket", 0.0, 0.05, has_gci_band=False)
          if x.quantity.startswith("C_D")][0]
    assert "O-grid" not in cd.message
    assert "p≈0.2" not in cd.message
    assert "hesaplanmadı" in cd.message or "ölçülmedi" in cd.message


def test_iki_agli_duyarlilik_GCI_BANDI_diye_sunulmuyor():
    """±%x iki-ağ farkı bir yakınsama bandı değildir: gözlenen mertebe
    hesaplanamaz, dolayısıyla Richardson genişletmesi yoktur."""
    from validity_envelope import classify_cfd
    cd = [x for x in classify_cfd("roket", 0.0, 0.05, has_gci_band=False,
                                  band_pct=3.4) if x.quantity.startswith("C_D")][0]
    assert "3.4" in cd.message
    assert "DEĞİLDİR" in cd.message
    assert cd.design_safe is False


def test_GCI_bandi_varsa_DOGRULANMIS_kaliyor():
    from validity_envelope import VALIDATED, classify_cfd
    cd = [x for x in classify_cfd("roket", 0.0, 0.05, has_gci_band=True)
          if x.quantity.startswith("C_D")][0]
    assert cd.klass == VALIDATED and cd.design_safe is True
