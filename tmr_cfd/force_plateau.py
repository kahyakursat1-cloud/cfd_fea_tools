"""Kuvvet-platosu durdurucu — KÖK NEDEN çözümü: residual-yakınsama ≠ kuvvet-yakınsama.

residualControl, kuvvet katsayısı (Cd/Cl) henüz platoya oturmadan tetiklenebilir (α≥10
stall-yakınında belirgin; üç grid farklı yarı-yakınsamış noktada durup sahte non-monotonluk
verdi). Bu monitör KOŞAN bir case'in forceCoeffs.dat'ını izler; Cd VE Cl son-pencere göreli
drift'i eşik altına inince controlDict'e `stopAt writeNow` yazar → foamRun (runTimeModifiable
yes) temiz durur. OpenFOAM runTimeControl'a Python alternatifi (syntax-bağımsız, test edilebilir).

Kullanım (koşan case'e iliştir, arka plan): python tmr_cfd/force_plateau.py <case_dir>
"""
import re
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


def forcecoeffs_dat(case) -> Path:
    """En güncel forceCoeffs çıktı dosyası. RESUME'da (startFrom latestTime) functionObject
    yeni <startTime> alt-dizini açar (postProcessing/forceCoeffs/<t>/); en büyük numaralıyı
    döndür — devam eden koşunun verisi orada. Tek "0" varsa onu döndürür (geriye-uyumlu)."""
    base = Path(case) / "postProcessing" / "forceCoeffs"
    if not base.is_dir():
        return base / "0" / "forceCoeffs.dat"
    subs = [d for d in base.iterdir() if d.is_dir() and d.name.replace(".", "", 1).isdigit()]
    if not subs:
        return base / "0" / "forceCoeffs.dat"
    return max(subs, key=lambda d: float(d.name)) / "forceCoeffs.dat"


def _read_force(fdat: Path):
    """İki formatı da okur → (iters, drag, lift):
    • forceCoeffs.dat (skaler): sütun Time Cm Cd Cl → drag=Cd, lift=Cl.
    • forces.dat (vektör): `t ((Fpx..)(Fvx..)) ..` → drag=Fpx+Fvx (eksenel), lift=0
      (katsayı yok; relative-drift ölçek-bağımsız olduğundan plato tespiti yine geçerli,
      eksenel cisim non-lifting → Cd-kapısı). rocket_cfd/transition_polar bunu kullanabilir."""
    if not fdat.exists():
        return [], [], []
    its, cds, cls = [], [], []
    # Sutunlar KONUMDAN degil BASLIKTAN okunur: forceCoeffs.dat duzeni ayarlara gore
    # degisir (Cd(f)/Cd(r) eklenince kayar) ve sabit indeks sessizce YANLIS niceligi
    # okur — erken-durdurma karari ve raporlanan plato degeri o yanlis sayiya dayanir.
    # Kanonik analysis/openfoam_runner.parse_force_coeffs_text ile ayni davranis.
    cd_i, cl_i = 2, 3        # baslik yoksa tarihsel varsayilan
    for ln in fdat.read_text(errors="ignore").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith("#"):
            if "Cd" in ln:
                parts = ln.lstrip("#").split()
                for i, tok in enumerate(parts):
                    if tok == "Cd":
                        cd_i = i
                    elif tok == "Cl":
                        cl_i = i
            continue
        if "(" in ln:                           # forces.dat (kuvvet vektörü) formatı
            nums = re.findall(r"[-+]?\d+\.?\d*[eE]?[-+]?\d*", ln)
            if len(nums) >= 5:
                try:
                    its.append(float(nums[0])); cds.append(float(nums[1]) + float(nums[4]))
                    cls.append(0.0)
                # sessiz-yutma: kabul — bozuk satır atlanır; sütun-adı tabanlı okuma başarısızsa çağıran plato bulamaz ve erken-durdurma DEVREYE GİRMEZ (güvenli taraf)
                except ValueError:
                    pass
        else:                                   # forceCoeffs.dat (skaler) formatı
            p = ln.split()
            if len(p) > max(cd_i, cl_i):
                try:
                    its.append(float(p[0]))
                    cds.append(float(p[cd_i])); cls.append(float(p[cl_i]))
                # sessiz-yutma: kabul — bozuk satır atlanır; sütun-adı tabanlı okuma başarısızsa çağıran plato bulamaz ve erken-durdurma DEVREYE GİRMEZ (güvenli taraf)
                except ValueError:
                    pass
    return its, cds, cls


def monitor(case_dir, window=10, tol=1.5e-3, poll=20.0, min_rows=12, timeout=None) -> dict:
    """case_dir'i izle; son `window` satırda hem Cd hem Cl drift < tol olunca controlDict'e
    `stopAt writeNow` yaz. window satır = window×writeInterval iter (varsayılan 50 → 500 iter).
    Döner: {durum, iters, Cd, Cl, drift_cd, drift_cl}."""
    case = Path(case_dir)
    cdict = case / "system" / "controlDict"
    t0 = time.time()
    while True:
        if timeout and time.time() - t0 > timeout:
            return {"durum": "timeout"}
        fdat = forcecoeffs_dat(case)            # RESUME'da yeni alt-dizini yakala (her poll)
        its, cds, cls = _read_force(fdat)
        if len(cds) >= max(min_rows, window):
            d_cd = relative_drift(cds[-window:])
            cl_win = cls[-window:]
            lifting = abs(sum(cl_win) / len(cl_win)) > 0.05    # α=0'da Cl≈0 → Cl gate'i atla
            d_cl = relative_drift(cl_win) if lifting else 0.0
            # Plato BİRİNCİL nicelik üzerinden: lifting'de Cl (Cd açıda gürültülü/ikincil,
            # küçük mutlak Cd → relative-drift şişer), α=0'da Cd. Yavaş-creep eden ince
            # grid'in sahte-platosunu önler (Cl asimptotu varmadan d_cd<tol olabiliyordu).
            converged = (d_cl < tol) if lifting else (d_cd < tol)
            if converged:
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
