"""TMR grid → OpenFOAM → SST çözüm, TEK komut (geometri-tabanlı patch ayrımı).
plot3dToFoam → autoPatch → patch'leri GEOMETRİYLE sınıfla (auto-isim sabitleme) →
createPatch (airfoil/farfield/frontAndBack) → setup_case → decompose+foamRun NP=8 → Cd.
Kullanım: python build_and_run.py <grid.p3dfmt> <case_dir> <alpha> [endTime] [NP]
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

try:                                            # cp1254 (TR Windows) stdout α/° patlamasın
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# sessiz-yutma: kabul — modül-düzeyi uyumluluk kalkanı (import/sürüm farkı); çalışma-zamanı sonucu etkilemez
except (AttributeError, ValueError):
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from inspect_patches import read_boundary, read_faces, read_points  # noqa: E402

GRID = Path(sys.argv[1]).resolve()
CASE = Path(sys.argv[2]).resolve()
ALPHA = sys.argv[3]
END = sys.argv[4] if len(sys.argv) > 4 else "5000"
NP = sys.argv[5] if len(sys.argv) > 5 else "8"
ENV = "source /opt/openfoam11/etc/bashrc && export HWLOC_COMPONENTS=-gl && unset FOAM_SIGFPE"


def wsl(case_unix, cmd, t=36000):
    return subprocess.run(f'wsl bash -c "{ENV} && cd {case_unix} && {cmd}"',
                          shell=True, capture_output=True, text=True, timeout=t)


def to_unix(p: Path):
    s = str(p)
    return f"/mnt/{s[0].lower()}{s[2:].replace(chr(92), '/')}"


def classify_and_createpatch(case: Path):
    """autoPatch sonrası patch'leri geometriyle sınıfla, createPatchDict üret."""
    pm = case / "constant" / "polyMesh"
    pts = read_points(pm / "points")
    faces = read_faces(pm / "faces")
    bnd = read_boundary(pm / "boundary")
    front, rim = [], []   # front/back (normal Y'de) ve rim (airfoil/farfield, normal X-Z'de)
    for name, nf, sf in bnd:
        if nf == 0:
            continue
        ny, rr = [], []
        for fi in range(sf, sf + nf):
            P = pts[faces[fi]]
            c = P.mean(axis=0)
            n = np.cross(P[1] - P[0], P[2] - P[0])
            n /= (np.linalg.norm(n) + 1e-30)
            ny.append(abs(n[1]))
            rr.append((c[0] ** 2 + c[1] ** 2) ** 0.5)
        # 2D düzlem X-Z, span Y: front/back yüzlerinin normali Y'de (|n_y|≈1);
        # airfoil/farfield yüzleri X-Z'de (|n_y|≈0). Merkez-y İKİSİNDE de sabit (-0.5)
        # olduğundan ayraç center DEĞİL normal olmalı.
        r = float(np.mean(rr))
        (front if np.mean(ny) > 0.5 else rim).append((name, nf, r))
    rim.sort(key=lambda t: t[2])           # r küçükten büyüğe
    airfoil = rim[0][0]                     # en küçük yarıçap = airfoil
    farfields = [t[0] for t in rim[1:]]     # geri kalan rim = farfield (dış + outflow)
    fb = [t[0] for t in front]
    print(f"  airfoil={airfoil} (r={rim[0][2]:.2f}) | farfield={farfields} | frontAndBack={fb}",
          flush=True)
    dct = ("FoamFile{version 2.0;format ascii;class dictionary;object createPatchDict;}\n"
           "pointSync false;\npatches\n(\n"
           f"  {{ name airfoil; patchInfo{{type wall;}} constructFrom patches; patches ({airfoil}); }}\n"
           f"  {{ name farfield; patchInfo{{type patch;}} constructFrom patches; patches ({' '.join(farfields)}); }}\n"
           f"  {{ name frontAndBack; patchInfo{{type empty;}} constructFrom patches; patches ({' '.join(fb)}); }}\n"
           ");\n")
    (case / "system").mkdir(parents=True, exist_ok=True)
    (case / "system" / "createPatchDict").write_text(dct)


def _resumable(case: Path) -> bool:
    """Decompose edilmiş çözüm var mı (processor0'da time>0)? Varsa rebuild yerine devam et —
    yarı-yakınsamış case'i silmeden force-plateau'ya kadar koştur (compute israfını önler)."""
    p0 = case / "processor0"
    if not p0.is_dir():
        return False
    return any(d.is_dir() and d.name.replace(".", "", 1).isdigit() and float(d.name) > 0
               for d in p0.iterdir())


def _solve_report(cu):
    """foamRun -parallel'i arka planda koş + force_plateau ile izle (Cd/Cl drift<tol →
    stopAt writeNow), sonra forceCoeffs son satırı raporla. Build ve resume yolları paylaşır."""
    from force_plateau import forcecoeffs_dat, monitor
    # RESUME yarış-koşulu: eski log.run "End" ile biter; foamRun truncate etmeden monitör
    # okursa anında "kosu_bitti" döner → sil, böylece "End" yalnız YENİ koşu bitince görünür.
    (CASE / "log.run").unlink(missing_ok=True)
    solve = (f'wsl bash -c "{ENV} && cd {cu} && '
             f'mpirun --oversubscribe -np {NP} foamRun -solver incompressibleFluid -parallel '
             f'>log.run 2>&1"')
    proc = subprocess.Popen(solve, shell=True)
    pl = monitor(CASE, window=10, tol=1.5e-3, poll=20.0, timeout=36000)
    print(f"[{CASE.name}] force-plateau: {pl}", flush=True)
    # monitor plato görünce stopAt writeNow yazar; çözücü buna yanıt vermezse (asılı MPI —
    # hwloc vakası) sınırsız wait tüm gece kampanyasını kilitler. Sarmalayıcıyı öldürmek
    # WSL tarafındaki mpirun'ı bırakabilir, ama kampanya bir sonraki seviyeye geçer.
    try:
        proc.wait(timeout=1800)
    except subprocess.TimeoutExpired:
        print(f"[{CASE.name}] UYARI: çözücü stopAt'e 30 dk'da yanıt vermedi — sonlandırılıyor",
              flush=True)
        proc.kill()
        proc.wait()
    fdat = forcecoeffs_dat(CASE)
    if fdat.exists():
        last = [ln for ln in fdat.read_text().splitlines() if ln.strip() and not ln.startswith("#")][-1]
        cols = last.split()
        print(f"[{CASE.name}] BİTTİ: Cd={cols[2]} Cl={cols[3]} (iter {cols[0]})", flush=True)
    else:
        print(f"[{CASE.name}] forceCoeffs YOK — log.run son:", flush=True)
        print((CASE / "log.run").read_text(errors="ignore")[-400:], flush=True)
    return 0


def main():
    cu = to_unix(CASE)
    if _resumable(CASE):
        print(f"[{CASE.name}] RESUME — mevcut çözümden devam (rebuild yok)...", flush=True)
        # dict'leri tazele (residual 1e-9 + stopAt endTime, force-plateau uyumlu); startFrom
        # latestTime processor çözümünden devam eder, processor alanlarına dokunulmaz.
        subprocess.run([sys.executable, str(HERE / "setup_case.py"), str(CASE), ALPHA, "6e6", END],
                       check=True, timeout=600)
        return _solve_report(cu)
    return _full_build_and_solve(cu)


def _full_build_and_solve(cu):
    CASE.mkdir(parents=True, exist_ok=True)
    (CASE / "system").mkdir(exist_ok=True)
    # plot3dToFoam minimal controlDict gerektirir
    (CASE / "system" / "controlDict").write_text(
        "FoamFile{version 2.0;format ascii;class dictionary;object controlDict;}\n"
        "application foamRun; startFrom startTime; startTime 0; stopAt endTime;\n"
        "endTime 1; deltaT 1; writeControl timeStep; writeInterval 1;\n")
    print(f"[{CASE.name}] plot3dToFoam...", flush=True)
    r = wsl(cu, f"plot3dToFoam -noBlank {to_unix(GRID)}")
    if "End" not in r.stdout:
        print("plot3dToFoam FAIL:", r.stdout[-400:], r.stderr[-300:]); return 1
    print(f"[{CASE.name}] autoPatch...", flush=True)
    wsl(cu, "autoPatch 80 -overwrite")
    classify_and_createpatch(CASE)
    wsl(cu, "createPatch -overwrite >log.createpatch 2>&1")
    bnd_txt = (CASE / "constant" / "polyMesh" / "boundary").read_text()
    if "airfoil" not in bnd_txt or "defaultFaces" in bnd_txt:
        print(f"[{CASE.name}] createPatch BAŞARISIZ (boundary'de airfoil yok/defaultFaces var) — "
              "log.createpatch:", flush=True)
        print((CASE / "log.createpatch").read_text(errors="ignore")[-500:], flush=True)
        return 1
    print(f"[{CASE.name}] setup_case α={ALPHA}...", flush=True)
    subprocess.run([sys.executable, str(HERE / "setup_case.py"), str(CASE), ALPHA, "6e6", END],
                   check=True, timeout=600)
    (CASE / "system" / "decomposeParDict").write_text(
        f"FoamFile{{version 2.0;format ascii;class dictionary;object decomposeParDict;}}\n"
        f"numberOfSubdomains {NP};\nmethod scotch;\n")
    print(f"[{CASE.name}] decompose + foamRun NP={NP} (force-plateau izlemeli)...", flush=True)
    wsl(cu, "decomposePar -force >log.decomp 2>&1")
    # residual≠kuvvet: foamRun'u arka planda koş, force_plateau ile izle → Cd/Cl platoya
    # oturunca controlDict'e stopAt writeNow yaz (runTimeModifiable). residual 1e-9 backstop.
    return _solve_report(cu)


if __name__ == "__main__":
    sys.exit(main())
