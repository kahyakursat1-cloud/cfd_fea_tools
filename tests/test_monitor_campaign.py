"""TMR GCI monitör — durum sınıflama testleri (_state). Salt-okunur log parse mantığı."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("monitor_campaign",
                                              ROOT / "tmr_cfd" / "monitor_campaign.py")
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)


def _mk_case(tmp_path, force_rows=None, log_tail=None):
    case = tmp_path / "case"
    (case / "system").mkdir(parents=True)
    if force_rows is not None:
        fd = case / "postProcessing" / "forceCoeffs" / "0"
        fd.mkdir(parents=True)
        lines = ["# Time Cm Cd Cl Clf Clr"]
        for it, cd, cl in force_rows:
            lines.append(f"{it}\t0.0\t{cd}\t{cl}\t0\t0")
        (fd / "forceCoeffs.dat").write_text("\n".join(lines))
    if log_tail is not None:
        (case / "log.run").write_text(log_tail)
    return case


def test_state_basladi_yok(tmp_path):
    assert mc._state(tmp_path / "yok")["durum"] == "başlamadı"


def test_state_kuruluyor(tmp_path):
    case = _mk_case(tmp_path)                        # system var, force yok
    assert mc._state(case)["durum"] == "kuruluyor"


def test_state_kosuyor_drift_buyuk(tmp_path):
    rows = [(50 * i, 0.02 - i * 1e-3, 0.5 + i * 0.05) for i in range(1, 13)]  # tırmanan (lifting)
    case = _mk_case(tmp_path, rows)
    s = mc._state(case)
    assert s["durum"] == "koşuyor"
    assert s["d_cl"] > mc.TOL_CL                     # Cl drift büyük (birincil nicelik)


def test_state_plato(tmp_path):
    rows = [(50 * i, 0.0121, 1.068) for i in range(1, 13)]   # düz → drift≈0 (lifting)
    case = _mk_case(tmp_path, rows)
    s = mc._state(case)
    assert s["durum"] == "plato"
    assert s["d_cl"] < mc.TOL_CL                     # Cl platosu (birincil nicelik)


def test_state_bitti(tmp_path):
    rows = [(50 * i, 0.0121, 1.068) for i in range(1, 13)]
    case = _mk_case(tmp_path, rows, log_tail="...\nFinalising parallel run\n")
    assert mc._state(case)["durum"] == "✅ BİTTİ"
