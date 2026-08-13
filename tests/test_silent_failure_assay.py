"""Silent-failure assay — detektör metrik mantığı (classify/confusion) testleri."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "sfa", ROOT / "experiments" / "silent_failure_assay.py")
sfa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sfa)


def _cell(naive, truth, flagged):
    return {"naive": naive, "truth": truth, "flagged": flagged}


def test_classify_four_quadrants():
    tau = 0.05
    # silent (err>tau) & caught(flagged) → TP
    assert sfa.classify(_cell(1.2, 1.0, True), tau)[0] == "TP"
    # silent & not caught → FN (guard kör-noktası)
    assert sfa.classify(_cell(1.2, 1.0, False), tau)[0] == "FN"
    # valid (err<tau) & caught → FP (konservatif guard)
    assert sfa.classify(_cell(1.01, 1.0, True), tau)[0] == "FP"
    # valid & not caught → TN
    assert sfa.classify(_cell(1.01, 1.0, False), tau)[0] == "TN"


def test_confusion_sensitivity_specificity():
    corpus = [_cell(2.0, 1.0, True),    # TP
              _cell(2.0, 1.0, False),   # FN
              _cell(1.0, 1.0, True),    # FP
              _cell(1.0, 1.0, False)]   # TN
    r = sfa.confusion(corpus, 0.05)
    assert (r["TP"], r["FN"], r["FP"], r["TN"]) == (1, 1, 1, 1)
    assert abs(r["sensitivity"] - 0.5) < 1e-9   # 1/(1+1)
    assert abs(r["specificity"] - 0.5) < 1e-9
    assert abs(r["prevalence"] - 0.5) < 1e-9


def test_real_corpus_loads_and_runs():
    r = sfa.confusion(sfa.CORPUS, 0.05)
    assert len(sfa.CORPUS) >= 12
    assert 0.0 <= r["sensitivity"] <= 1.0 and 0.0 <= r["specificity"] <= 1.0
    # rocket-fin geometri vakası FN olmalı (otomatik guard yok)
    fin = next(c for c in sfa.CORPUS if c["case"] == "rocket-finned")
    assert sfa.classify(fin, 0.05)[0] == "FN"


# ── Ölçülen kusur (2026-08-12 hakem turu) ───────────────────────────────────
# `TAU_BY_Q.get(q, tau)` yedeği, sözlükte olmayan 6 niceliği (hoop, deflection,
# Kt-stress, P_cr, peak-vM) sessizce GLOBAL tau'ya düşürüyordu. Böylece
# "niceliğe-özel" denen manşet, --tau bayrağının fonksiyonu oluyordu:
# %5 → 0,82/0,78 · %10 → 0,80/0,74. Makalenin baş bulgusu olan tutarlı-yük
# defekti de yalnız o belgelenmemiş yedek sayesinde TP sayılıyordu.
# Bu testler yedeğin geri gelmesini engeller.

def test_ASIL_KUSUR_manset_global_tau_dan_BAGIMSIZ():
    """per_q=True sonucu, global τ ne olursa olsun DEĞİŞMEMELİ."""
    referans = sfa.confusion(sfa.CORPUS, 0.05, per_q=True)
    for tau in (0.01, 0.02, 0.10, 0.15, 0.50):
        o = sfa.confusion(sfa.CORPUS, tau, per_q=True)
        for k in ("TP", "FP", "TN", "FN"):
            assert o[k] == referans[k], (
                f"global τ={tau} per-nicelik sonucu değiştirdi ({k}): "
                f"{o[k]} != {referans[k]} — yedek geri gelmiş olabilir")


def test_bilinmeyen_nicelik_SESSIZCE_dusmez_hata_firlatir():
    """Tanımsız nicelik varsayılana düşerse kusur geri gelir; hata fırlamalı."""
    hucre = {"q": "tanimsiz-nicelik", "naive": 1.2, "truth": 1.0, "flagged": True}
    try:
        sfa.classify(hucre, 0.05, per_q=True)
    except KeyError as e:
        assert "tanimsiz-nicelik" in str(e)
    else:
        raise AssertionError("bilinmeyen nicelik sessizce kabul edildi")


def test_TAU_BY_Q_korpusu_TAM_kapsar():
    """Korpustaki her nicelik etiketinin açık bir τ'su olmalı."""
    eksik = {c["q"] for c in sfa.CORPUS} - set(sfa.TAU_BY_Q)
    assert not eksik, f"τ tanımsız nicelik(ler): {sorted(eksik)}"


def test_wilson_araligi_nokta_degeri_KAPSAR_ve_tasmaz():
    for k, n in ((8, 10), (14, 19), (0, 5), (5, 5)):
        lo, hi = sfa.wilson(k, n)
        assert 0.0 <= lo <= k / n <= hi <= 1.0, (k, n, lo, hi)


def test_kucuk_n_araligi_GENIS_kalir():
    """n~10'da aralık dar çıkıyorsa hesap yanlıştır — çıplak nokta-değer yanıltır."""
    lo, hi = sfa.wilson(8, 10)
    assert hi - lo > 0.3, f"n=10'da aralık {hi - lo:.2f} — fazla dar"


def test_confusion_araliklari_RAPORLAR():
    o = sfa.confusion(sfa.CORPUS, 0.05, per_q=True)
    for k in ("sensitivity_CI95", "specificity_CI95", "prevalence_CI95"):
        assert o.get(k) and len(o[k]) == 2, f"{k} eksik"


def test_DONDURULMUS_sonuc_duzeltmeden_ETKILENMEZ():
    """Düzeltme-sonrası kapılar dondurulmuş eşik sonucunu DEĞİŞTİRMEMELİ.

    Doğrulayıcı bir testin tek anlamı, sonucunu gördükten sonra sistemi
    değiştirip o değişikliği aynı teste yazmamaktır.
    """
    dondurulmus = sfa.confusion(sfa.CORPUS, 0.05, per_q=True)
    assert (dondurulmus["TP"], dondurulmus["FP"],
            dondurulmus["TN"], dondurulmus["FN"]) == (14, 5, 18, 7)


def test_ablasyon_kollari_AYRISIR():
    """Ablasyon kolları farklı kapı kümesini GERÇEKTEN ölçmeli.

    ÖLÇÜLEN KUSUR: `kapilar` `confusion`'dan `duzeltilmis_flag`'e geçmiyordu;
    üç kol da varsayılan ikili kapıyla koşuyor, aynı matrisi veriyordu. Kusur
    ancak yeniden-sınıflanan sayıları (3 / 8 / 8) matrislerle çelişince
    görüldü — matrisler tek başına bakıldığında tutarlı görünüyordu.
    """
    fizik = sfa.confusion(sfa.CORPUS, 0.05, per_q=True, duzeltilmis=("fizik",))
    ag = sfa.confusion(sfa.CORPUS, 0.05, per_q=True, duzeltilmis=("ag",))
    assert (fizik["TP"], fizik["FN"]) != (ag["TP"], ag["FN"])
    # Fizik kapısı ÖZGÜLLÜĞE mal olmaz: fizik-dışı bir sayıyı bayraklamak
    # hiçbir doğru sertifikayı bozmaz.
    dondurulmus = sfa.confusion(sfa.CORPUS, 0.05, per_q=True)
    assert fizik["specificity"] == dondurulmus["specificity"]
    # Ağ kapısı daha güçlü ama BEDELLİ.
    assert ag["sensitivity"] > fizik["sensitivity"]
    assert ag["specificity"] < dondurulmus["specificity"]
