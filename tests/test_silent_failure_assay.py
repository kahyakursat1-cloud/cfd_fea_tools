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
