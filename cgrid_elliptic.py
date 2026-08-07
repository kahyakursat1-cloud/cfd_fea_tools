"""
Elliptic C-grid (wake-kumelemeli) -> dogrudan OpenFOAM polyMesh.
================================================================
O-grid ailesi Cd icin asimptotik araliga girmiyor (bkz. gci_airfoil.json):
wake kumelemesi yok ve TE tekilligi sub-lineer hata uretiyor. C-grid wake
hattini cozumler. Wake kesigi stitchMesh ile DEGIL, j=0 dugumlerinin
koordinat-birlestirmesiyle kapatilir; hash-tabanli yazici cakisan yuzleri
otomatik internal face yapar (exp_cgrid_* denemelerinin basarisiz noktasi).
Kapali-TE katsayisi (-0.1036) ogrid_elliptic dersinden devralinir.
"""
import math
from pathlib import Path

import numpy as np

from analysis.backend import linux_run
from analysis.ccx_runner import windows_to_wsl_path
from ogrid_elliptic import tanh_radial


def naca0012_y(x):
    t = 0.12
    return (t/0.2)*(0.2969*np.sqrt(np.clip(x, 0, None)) - 0.1260*x - 0.3516*x**2
                    + 0.2843*x**3 - 0.1036*x**4)


def geometric_spacing(d0, L, n):
    """n araliga, ilk aralik d0, toplam L: buyume orani bisection ile."""
    lo, hi = 1.0 + 1e-9, 2.0
    for _ in range(80):
        r = 0.5*(lo + hi)
        tot = d0*(r**n - 1)/(r - 1)
        if tot < L: lo = r
        else: hi = r
    r = 0.5*(lo + hi)
    s = np.concatenate([[0.0], np.cumsum(d0*r**np.arange(n))])
    return s/s[-1]*L


def build_cgrid(n_air=200, n_wake=60, nj=100, first_cell=8e-6,
                R=15.0, L_wake=20.0, sweeps=8, iters=100):
    # sweeps=8/iters=100: y+ duzeltmeli duvar kumelemesi (gercek 8e-6 ilk hucre)
    # icin ampirik tatli nokta (skew<4, non-ortho ~70); fazla Winslow wake
    # kesiginin iki yakasini bagimsiz kaydirip skew uretiyor
    """j=0 egrisi: alt-wake(ters) + airfoil(alt TE->LE->ust TE) + ust-wake.
    Dis sinir: y=-R duz + (0.5,0) merkezli yari-cember + y=+R duz.
    Donus: X, Y (I x nj+1), I, nj, n_wake."""
    nh = n_air // 2
    beta = np.linspace(0, np.pi, nh+1)
    xc = 0.5*(1 - np.cos(beta))
    lo_surf = np.column_stack([xc[::-1], -naca0012_y(xc[::-1])])   # TE->LE alt
    up_surf = np.column_stack([xc[1:],   naca0012_y(xc[1:])])      # LE->TE ust (LE tekrarsiz)
    airfoil = np.vstack([lo_surf, up_surf])                        # 2*nh+1 nokta, TE->TE

    d_te = math.dist(airfoil[0], airfoil[1])
    wx = 1.0 + geometric_spacing(max(d_te, 1e-4), L_wake - 1.0, n_wake)
    wake_lo = np.column_stack([wx[::-1][:-1], np.zeros(n_wake)])   # uzak->TE'ye dogru (TE haric)
    wake_up = np.column_stack([wx[1:],        np.zeros(n_wake)])   # TE sonrasi->uzak

    j0 = np.vstack([wake_lo, airfoil, wake_up])
    I = len(j0)                                                    # 2*n_wake + 2*nh + 1

    # dis sinir — PARCA-BAZLI esleme (global yay-uzunlugu esleme TFI hatlarini
    # cevirip caprazlatiyor: ic egrinin %5'i airfoil, dis sinirin %54'u yay):
    # alt wake <-> y=-R duz kenar, airfoil <-> sol yari-cember, ust wake <-> y=+R
    cx = 0.5
    def seg_t(seg_pts):
        s = np.sqrt(np.sum(np.diff(seg_pts, axis=0)**2, axis=1))
        t = np.concatenate([[0], np.cumsum(s)])
        return t/t[-1]
    t_lo = seg_t(np.vstack([wake_lo, airfoil[:1]]))[:-1]           # wake_lo noktalari
    t_af = seg_t(airfoil)
    t_up = seg_t(np.vstack([airfoil[-1:], wake_up]))[1:]
    out_lo = np.column_stack([L_wake + t_lo*(cx - L_wake), -R*np.ones(len(t_lo))])
    th = -np.pi/2 - t_af*np.pi                                     # (0.5,-R) -> sol -> (0.5,+R)
    out_af = np.column_stack([cx + R*np.cos(th), R*np.sin(th)])
    out_up = np.column_stack([cx + t_up*(L_wake - cx), R*np.ones(len(t_up))])
    outer = np.vstack([out_lo, out_af, out_up])

    rad = tanh_radial(nj, first_cell, R)
    eta = rad/R
    X = np.zeros((I, nj+1)); Y = np.zeros((I, nj+1))
    for j in range(nj+1):
        e = eta[j]
        X[:, j] = (1-e)*j0[:, 0] + e*outer[:, 0]
        Y[:, j] = (1-e)*j0[:, 1] + e*outer[:, 1]

    # Winslow smoothing — i NON-periyodik (uclar outlet'te sabit), j=0/j=nj sabit
    for _ in range(sweeps):
        for _ in range(iters):
            xi = (X[2:, 1:nj] - X[:-2, 1:nj]); yi = (Y[2:, 1:nj] - Y[:-2, 1:nj])
            xj = (X[1:-1, 2:] - X[1:-1, :-2]); yj = (Y[1:-1, 2:] - Y[1:-1, :-2])
            a = 0.25*(xj*xj + yj*yj)
            g = 0.25*(xi*xi + yi*yi)
            b = 0.0625*(xi*xj + yi*yj)
            xij = (X[2:, 2:] - X[2:, :-2] - X[:-2, 2:] + X[:-2, :-2])
            yij = (Y[2:, 2:] - Y[2:, :-2] - Y[:-2, 2:] + Y[:-2, :-2])
            den = 2*(a+g) + 1e-30
            Xn = (a*(X[2:, 1:nj] + X[:-2, 1:nj]) + g*(X[1:-1, 2:] + X[1:-1, :-2]) - 0.5*b*xij)/den
            Yn = (a*(Y[2:, 1:nj] + Y[:-2, 1:nj]) + g*(Y[1:-1, 2:] + Y[1:-1, :-2]) - 0.5*b*yij)/den
            X[1:-1, 1:nj] = 0.35*X[1:-1, 1:nj] + 0.65*Xn
            Y[1:-1, 1:nj] = 0.35*Y[1:-1, 1:nj] + 0.65*Yn
        for i in range(1, I-1):
            lx, ly = X[i], Y[i]
            s = np.sqrt(np.diff(lx)**2 + np.diff(ly)**2)
            arcl = np.concatenate([[0], np.cumsum(s)])
            if arcl[-1] > 0:
                arcl /= arcl[-1]
                X[i] = np.interp(eta, arcl, lx); Y[i] = np.interp(eta, arcl, ly)
    return X, Y, I, nj, n_wake


def write_polymesh_cgrid(case, X, Y, I, nj, n_wake, span=0.1):
    """Hash-tabanli polyMesh yazici. Wake j=0 dugumleri koordinatla birlestirilir
    -> kesigin iki yakasi otomatik internal face olur."""
    pm = Path(case)/"constant"/"polyMesh"; pm.mkdir(parents=True, exist_ok=True)
    J = nj
    pts = []
    canon = {}
    nid = {}
    for k, z in enumerate((0.0, span)):
        for i in range(I):
            for j in range(J+1):
                if j == 0:
                    key = (round(X[i, 0], 10), round(Y[i, 0], 10), k)
                    if key in canon:
                        nid[(i, j, k)] = canon[key]; continue
                    canon[key] = len(pts)
                pts.append((X[i, j], Y[i, j], z))
                nid[(i, j, k)] = len(pts) - 1

    def cid(i, j): return i*J + j
    cc = {}
    faces_map = {}

    def add_face(quad, cell, tag):
        key = frozenset(quad)
        if key in faces_map:
            faces_map[key][2].append(cell)
        else:
            faces_map[key] = (quad, tag, [cell])

    for i in range(I-1):
        for j in range(J):
            c = cid(i, j)
            ns = [nid[(i, j, 0)], nid[(i+1, j, 0)], nid[(i+1, j+1, 0)], nid[(i, j+1, 0)],
                  nid[(i, j, 1)], nid[(i+1, j, 1)], nid[(i+1, j+1, 1)], nid[(i, j+1, 1)]]
            cc[c] = np.mean([pts[n] for n in set(ns)], axis=0)
            add_face([ns[0], ns[1], ns[5], ns[4]], c, "jlo")
            add_face([ns[3], ns[2], ns[6], ns[7]], c, "jhi")
            add_face([ns[0], ns[3], ns[7], ns[4]], c, "ilo")
            add_face([ns[1], ns[2], ns[6], ns[5]], c, "ihi")
            add_face([ns[0], ns[1], ns[2], ns[3]], c, "z0")
            add_face([ns[4], ns[5], ns[6], ns[7]], c, "z1")

    def oriented(quad, frm, to):
        p = [np.array(pts[q]) for q in quad]
        nrm = np.cross(p[1]-p[0], p[3]-p[0])
        if np.dot(nrm, np.asarray(to) - np.asarray(frm)) < 0:
            return [quad[0], quad[3], quad[2], quad[1]]
        return quad

    internal, bnd = [], {"airfoil": [], "farfield": [], "outlet": [], "frontAndBack": []}
    for quad, tag, cells in faces_map.values():
        if len(cells) == 2:
            o, n = min(cells), max(cells)
            internal.append((oriented(quad, cc[o], cc[n]), o, n))
        else:
            o = cells[0]
            fcen = np.mean([pts[q] for q in quad], axis=0)
            q = oriented(quad, cc[o], fcen)
            if tag in ("z0", "z1"): bnd["frontAndBack"].append((q, o))
            elif tag == "jhi":      bnd["farfield"].append((q, o))
            elif tag == "jlo":      bnd["airfoil"].append((q, o))
            else:                   bnd["outlet"].append((q, o))
    internal.sort(key=lambda f: (f[1], f[2]))

    faces, owner, neigh = [], [], []
    for q, o, n in internal:
        faces.append(q); owner.append(o); neigh.append(n)
    n_internal = len(faces)
    patches = []
    for name in ("airfoil", "farfield", "outlet", "frontAndBack"):
        start = len(faces)
        for q, o in bnd[name]:
            faces.append(q); owner.append(o)
        patches.append((name, len(bnd[name]), start))

    def hdr(cls, obj):
        return (f"FoamFile{{version 2.0; format ascii; class {cls}; "
                f"location \"constant/polyMesh\"; object {obj};}}\n")
    (pm/"points").write_text(hdr("vectorField", "points")+f"{len(pts)}\n(\n" +
        "".join(f"({x:.10g} {y:.10g} {z:.10g})\n" for x, y, z in pts)+")\n")
    (pm/"faces").write_text(hdr("faceList", "faces")+f"{len(faces)}\n(\n" +
        "".join(f"4({q[0]} {q[1]} {q[2]} {q[3]})\n" for q in faces)+")\n")
    (pm/"owner").write_text(hdr("labelList", "owner")+f"{len(owner)}\n(\n" +
        "".join(f"{o}\n" for o in owner)+")\n")
    (pm/"neighbour").write_text(hdr("labelList", "neighbour")+f"{len(neigh)}\n(\n" +
        "".join(f"{n}\n" for n in neigh)+")\n")
    typ = {"airfoil": "wall", "farfield": "patch", "outlet": "patch", "frontAndBack": "empty"}
    b = hdr("polyBoundaryMesh", "boundary")+f"{len(patches)}\n(\n"
    for name, nf, st in patches:
        b += f"  {name}{{ type {typ[name]}; nFaces {nf}; startFace {st}; }}\n"
    b += ")\n"
    (pm/"boundary").write_text(b)
    return len(pts), len(faces), (I-1)*J, n_internal


if __name__ == "__main__":
    import shutil
    import subprocess
    import sys
    na = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    nw = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    njj = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    case = Path("cgrid_test")
    if case.exists(): shutil.rmtree(case)
    (case/"system").mkdir(parents=True, exist_ok=True)
    for f, c in [("controlDict", 'application foamRun; startFrom startTime; startTime 0; endTime 1; deltaT 1; writeInterval 1;'),
                 ("fvSchemes", 'ddtSchemes{default steadyState;} gradSchemes{default Gauss linear;} divSchemes{default none;} laplacianSchemes{default Gauss linear corrected;} interpolationSchemes{default linear;} snGradSchemes{default corrected;}'),
                 ("fvSolution", 'solvers{} SIMPLE{}')]:
        (case/"system"/f).write_text(f'FoamFile{{version 2.0; format ascii; class dictionary; object {f};}}\n'+c+"\n")
    X, Y, I, nj, n_wake = build_cgrid(n_air=na, n_wake=nw, nj=njj)
    npts, nf, nc, ni = write_polymesh_cgrid(case, X, Y, I, nj, n_wake)
    print(f"polyMesh: {npts} nokta, {nf} yuz ({ni} internal), {nc} hucre")
    # ARKA UC KATMANI: `wsl bash -c` elle kurulmustu, yani CFD_BACKEND=docker
    # bu betikte hicbir sey degistirmiyordu. Case iskeleti degismedi.
    wsl = windows_to_wsl_path(case.resolve())
    r = linux_run(f"source /opt/openfoam11/etc/bashrc && unset FOAM_SIGFPE && "
                  f"cd {wsl} && checkMesh 2>&1", 600)
    print("MESH OK" if "Mesh OK" in r.stdout else "FAILED")
    for key in ("cells:", "non-orthogonality Max", "Max skewness", "open cells",
                "incorrectly oriented", "Failed", "Max aspect"):
        for line in r.stdout.splitlines():
            if key in line: print("  "+line.strip()); break
