"""Kuvvet-platosu durdurucu — drift mantığı + plato'da controlDict'e stopAt yazımı.
Saf-Python (CFD yok); sentetik forceCoeffs.dat."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tmr_cfd"))
from force_plateau import monitor, relative_drift  # noqa: E402


def test_relative_drift():
    assert relative_drift([1.0, 1.0, 1.0]) == 0.0
    assert relative_drift([0.0082, 0.00821, 0.0082]) < 2e-3          # plato → küçük (~1.2e-3)
    assert relative_drift([0.90, 0.95, 1.00, 1.04]) > 0.1            # tırmanış → büyük
    # |ortalama|≈0 → relative drift PATLAR (bu yüzden monitör Cl@α=0'ı lifting-gate ile atlar)
    assert relative_drift([1e-6, -1e-6, 5e-7]) > 1.0


def _write_fc(case: Path, cds, cls):
    d = case / "postProcessing" / "forceCoeffs" / "0"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["# Time Cm Cd Cl Cl(f) Cl(r)"]
    for i, (cd, cl) in enumerate(zip(cds, cls), start=1):
        lines.append(f"{i*50} 0.0 {cd} {cl} 0.0 0.0")
    (d / "forceCoeffs.dat").write_text("\n".join(lines))
    (case / "system").mkdir(parents=True, exist_ok=True)
    (case / "system" / "controlDict").write_text(
        "application foamRun;\nstopAt endTime;\nrunTimeModifiable yes;\n")


def test_monitor_writes_stop_on_plateau(tmp_path):
    """Plato (15 satır, son 10 sabit) → controlDict'e stopAt writeNow yazılır."""
    cds = [0.0082] * 15
    cls = [0.95] * 15
    _write_fc(tmp_path, cds, cls)
    r = monitor(tmp_path, window=10, tol=1.5e-3, min_rows=12, timeout=5)
    assert r["durum"] == "plato"
    assert "stopAt writeNow" in (tmp_path / "system" / "controlDict").read_text()


def test_monitor_alpha0_plateaus_on_cd_alone(tmp_path):
    """α=0: Cl≈0 (gürültülü, lifting değil) → Cl gate atlanır, Cd platosuyla durur."""
    cds = [0.00820] * 15
    cls = [(-1) ** i * 1e-5 for i in range(15)]      # ~0 etrafında salınım
    _write_fc(tmp_path, cds, cls)
    r = monitor(tmp_path, window=10, tol=1.5e-3, min_rows=12, poll=0.3, timeout=2)
    assert r["durum"] == "plato"
    assert "stopAt writeNow" in (tmp_path / "system" / "controlDict").read_text()


def test_monitor_does_not_stop_while_rising(tmp_path):
    """Hâlâ tırmanan kuvvet (drift > tol) → durdurmaz (koşu-bitti veya timeout döner)."""
    cds = [0.020 - i * 0.0003 for i in range(15)]   # belirgin trend
    cls = [0.90 + i * 0.004 for i in range(15)]
    _write_fc(tmp_path, cds, cls)
    r = monitor(tmp_path, window=10, tol=1e-4, min_rows=12, poll=0.3, timeout=1)
    assert r["durum"] == "timeout"                  # plato yok → durdurmadı
    assert "stopAt writeNow" not in (tmp_path / "system" / "controlDict").read_text()
