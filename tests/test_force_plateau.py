"""Kuvvet-platosu durdurucu — drift mantığı + plato'da controlDict'e stopAt yazımı.
Saf-Python (CFD yok); sentetik forceCoeffs.dat."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tmr_cfd"))
from force_plateau import _read_force, forcecoeffs_dat, monitor, relative_drift  # noqa: E402


def test_read_force_handles_both_formats(tmp_path):
    """_read_force hem forceCoeffs (skaler) hem forces.dat (vektör) okur."""
    fc = tmp_path / "forceCoeffs.dat"
    fc.write_text("# Time Cm Cd Cl\n100\t0.01\t0.0082\t0.44\n150\t0.01\t0.0081\t0.45\n")
    its, drag, lift = _read_force(fc)
    assert its == [100.0, 150.0] and abs(drag[0] - 0.0082) < 1e-9 and abs(lift[1] - 0.45) < 1e-9
    fv = tmp_path / "forces.dat"          # vektör: drag = Fpx + Fvx (nums[1]+nums[4])
    fv.write_text("# Time forces\n"
                  "100\t((0.19 -1e-4 3e-3) (0.09 1e-5 -3e-5)) ((1e-6 0 0)(0 0 0))\n"
                  "150\t((0.20 0 0) (0.10 0 0)) ((0 0 0)(0 0 0))\n")
    its, drag, lift = _read_force(fv)
    assert its == [100.0, 150.0]
    assert abs(drag[0] - 0.28) < 1e-6 and abs(drag[1] - 0.30) < 1e-6   # Fpx+Fvx
    assert lift == [0.0, 0.0]                                          # eksenel → non-lifting


def test_forcecoeffs_dat_picks_latest_subdir(tmp_path):
    """RESUME: en büyük numaralı <startTime> alt-dizinini seçer (0 ve 20000 varsa → 20000)."""
    base = tmp_path / "postProcessing" / "forceCoeffs"
    (base / "0").mkdir(parents=True)
    assert forcecoeffs_dat(tmp_path) == base / "0" / "forceCoeffs.dat"   # tek dizin
    (base / "20000").mkdir()
    assert forcecoeffs_dat(tmp_path) == base / "20000" / "forceCoeffs.dat"   # resume devamı
    # postProcessing yoksa geriye-uyumlu "0" yolu
    assert forcecoeffs_dat(tmp_path / "yok").name == "forceCoeffs.dat"


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


def test_sutunlar_baslıktan_okunur(tmp_path):
    """Sabit indeks (p[2]=Cd, p[3]=Cl) forceCoeffs düzeni değişince SESSİZCE yanlış
    niceliği okur; erken-durdurma kararı ve raporlanan plato değeri o yanlış sayıya
    dayanır. Kanonik parser başlıktan okuyor, bu yol okumuyordu."""
    f = tmp_path / "forceCoeffs.dat"

    # standart düzen: Time Cm Cd Cl ...
    f.write_text("# Time \tCm \tCd \tCl \tCl(f)\n100\t0.01\t1.079\t0.0006\t0\n")
    _, cd, cl = _read_force(f)
    assert cd == [pytest.approx(1.079)] and cl == [pytest.approx(0.0006)]

    # KAYMIŞ düzen: Cd(f) araya girmiş -> sabit indeks yanlış sütunu okurdu
    f.write_text("# Time \tCm \tCd(f) \tCd \tCl\n100\t0.01\t0.5\t1.079\t0.0006\n")
    _, cd, cl = _read_force(f)
    assert cd == [pytest.approx(1.079)], "kaymış başlıkta yanlış sütun okundu"
    assert cl == [pytest.approx(0.0006)]

    # başlıksız -> tarihsel varsayılan (2,3) korunur
    f.write_text("100\t0.01\t1.079\t0.0006\n")
    _, cd, _ = _read_force(f)
    assert cd == [pytest.approx(1.079)]
