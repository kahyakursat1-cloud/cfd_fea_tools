"""Kuvvet-platosu durdurucu — KÖK NEDEN çözümü: residual-yakınsama ≠ kuvvet-yakınsama.

residualControl, kuvvet katsayısı (Cd/Cl) henüz platoya oturmadan tetiklenebilir (α≥10
stall-yakınında belirgin; üç grid farklı yarı-yakınsamış noktada durup sahte non-monotonluk
verdi). Bu monitör KOŞAN bir case'in forceCoeffs.dat'ını izler; Cd VE Cl son-pencere göreli
drift'i eşik altına inince controlDict'e `stopAt writeNow` yazar → foamRun (runTimeModifiable
yes) temiz durur. OpenFOAM runTimeControl'a Python alternatifi (syntax-bağımsız, test edilebilir).

Kullanım (koşan case'e iliştir, arka plan): python tmr_cfd/force_plateau.py <case_dir>
"""
import sys
import time
from pathlib import Path


def relative_drift(vals) -> float:
    """Pencere göreli drift = (max−min)/|ortalama|. Plato → 0'a iner. (|ortalama|≈0 niceliği
    — Cl@α=0 — çağıran 'lifting' kapısıyla atlar; burada saf-relative.)"""
    vals = [float(v) for v in vals]
    if not vals:
        return float("inf")
    m = sum(vals) / len(vals)
    return (max(vals) - min(vals)) / (abs(m) + 1e-30)


def _read_force(fdat: Path):
    """forceCoeffs.dat → (iters, Cd_list, Cl_list). Sütun: Time Cm Cd Cl ..."""
    if not fdat.exists():
        return [], [], []
    its, cds, cls = [], [], []
    for ln in fdat.read_text(errors="ignore").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        p = ln.split()
        if len(p) >= 4:
            try:
                its.append(float(p[0])); cds.append(float(p[2])); cls.append(float(p[3]))
            except ValueError:
                pass
    return its, cds, cls


def monitor(case_dir, window=10, tol=1.5e-3, poll=20.0, min_rows=12, timeout=None) -> dict:
    """case_dir'i izle; son `window` satırda hem Cd hem Cl drift < tol olunca controlDict'e
    `stopAt writeNow` yaz. window satır = window×writeInterval iter (varsayılan 50 → 500 iter).
    Döner: {durum, iters, Cd, Cl, drift_cd, drift_cl}."""
    case = Path(case_dir)
    fdat = case / "postProcessing" / "forceCoeffs" / "0" / "forceCoeffs.dat"
    cdict = case / "system" / "controlDict"
    t0 = time.time()
    while True:
        if timeout and time.time() - t0 > timeout:
            return {"durum": "timeout"}
        its, cds, cls = _read_force(fdat)
        if len(cds) >= max(min_rows, window):
            d_cd = relative_drift(cds[-window:])
            cl_win = cls[-window:]
            lifting = abs(sum(cl_win) / len(cl_win)) > 0.05    # α=0'da Cl≈0 → Cl gate'i atla
            d_cl = relative_drift(cl_win) if lifting else 0.0
            if d_cd < tol and d_cl < tol:
                txt = cdict.read_text()
                if "stopAt writeNow" not in txt:
                    cdict.write_text(txt.replace("stopAt endTime;", "stopAt writeNow;"))
                return {"durum": "plato", "iters": its[-1], "Cd": cds[-1], "Cl": cls[-1],
                        "drift_cd": d_cd, "drift_cl": d_cl}
        # foamRun bitmiş/durmuşsa (case End yazmış) çık
        log = case / "log.run"
        if log.exists():
            tail = log.read_text(errors="ignore")[-400:]
            if "Finalising parallel run" in tail or tail.rstrip().endswith("End"):
                return {"durum": "kosu_bitti", "iters": (its[-1] if its else None),
                        "Cd": (cds[-1] if cds else None), "Cl": (cls[-1] if cls else None)}
        time.sleep(poll)


def main():
    case = sys.argv[1]
    window = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    tol = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5e-3
    print(f"[force-plateau] izleniyor: {case} (window={window} satır, tol={tol})", flush=True)
    r = monitor(case, window=window, tol=tol)
    print(f"[force-plateau] {r}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
