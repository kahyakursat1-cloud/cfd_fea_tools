"""
Elliptic (Winslow) O-grid -> dogrudan OpenFOAM polyMesh.
=======================================================
Wake-cut YOK (O-grid: TE'de tek seam). gmsh/stitchMesh YOK (polyMesh direkt yazilir).
Buyuk domain (R), y+~1 (tanh radyal), Winslow smoothing -> dusuk non-ortho.
Amac: gecerli mesh (0 negatif) + Cd hata arastirma-sinifi.
"""
import math
from pathlib import Path

import numpy as np

from analysis.backend import linux_run


def naca0012_loop(n_around):
    """Kapali NACA0012 dongusu: ust-TE -> LE -> alt-TE, kosinus kumeleme (LE+TE sik).
    n_around tek olmali; donus i=0..n_around-1, i=n_around -> i=0'a sarar.
    Kapali-TE katsayisi (-0.1036): yt(1)=0, aksi halde TE'deki kalinlik bosluguna
    sarilan yuzler her cozunurlukte ters-yonelimli/carpik hucre uretiyor (checkMesh).
    """
    t = 0.12
    def yt(x):
        return (t/0.2)*(0.2969*np.sqrt(np.clip(x,0,None)) - 0.1260*x - 0.3516*x**2
                        + 0.2843*x**3 - 0.1036*x**4)
    nh = n_around // 2
    beta = np.linspace(0, np.pi, nh+1)
    xc = 0.5*(1 - np.cos(beta))            # 0..1, LE+TE sik
    up = np.column_stack([xc,  yt(xc)])    # LE->TE ust
    lo = np.column_stack([xc, -yt(xc)])    # LE->TE alt
    # dongu: ust TE->LE  +  alt LE->TE  (TE'ler tekrar etmesin)
    loop = np.vstack([up[::-1][:-1], lo[:-1]])   # (2*nh,) nokta, kapali
    return loop


def tanh_radial(nj, first, R):
    """Ilk hucreyi TAM 'first' yapan geometrik radyal dagilim (nj+1 nokta, toplam R).

    NOT (2026-06-10): onceki cosh-tabanli form 'first'i raw[-1] normalizasyonunda
    SADELESTIRIYORDU — ilk hucre yuksekligi kontrolsuzdu (olculen y+ ort. 7-12,
    hedef ~1; kOmegaSSTLM y+<=1 sartini ihlal). Buyume orani bisection ile cozulur.
    """
    lo, hi = 1.0 + 1e-9, 2.0
    for _ in range(100):
        r = 0.5*(lo + hi)
        if first*(r**nj - 1)/(r - 1) < R: lo = r
        else: hi = r
    r = 0.5*(lo + hi)
    d = np.concatenate([[0.0], np.cumsum(first*r**np.arange(nj))])
    return d/d[-1]*R


def build_ogrid(naca="0012", n_around=240, nj=120, first_cell=8e-6, R=40.0, sweeps=16, iters=120):
    loop = naca0012_loop(n_around)
    I = len(loop)                          # cevre nokta sayisi (i=0..I-1 sarar)
    rad = tanh_radial(nj, first_cell, R)   # (nj+1,)
    # dis cember: merkez (0.5,0) etrafinda R yariçap
    cx, cy = 0.5, 0.0
    th = np.array([math.atan2(p[1]-cy, p[0]-cx) for p in loop])
    outer = np.column_stack([cx + R*np.cos(th), cy + R*np.sin(th)])

    # TFI baslangic
    X = np.zeros((I, nj+1)); Y = np.zeros((I, nj+1))
    for j in range(nj+1):
        e = rad[j]/R
        X[:, j] = (1-e)*loop[:, 0] + e*outer[:, 0]
        Y[:, j] = (1-e)*loop[:, 1] + e*outer[:, 1]

    # Winslow eliptik smoothing (i periyodik, j=0/j=nj sabit)
    eta = rad/R
    for sweep in range(sweeps):
        for _ in range(iters):
            xm, xp = np.roll(X, 1, 0), np.roll(X, -1, 0)   # i-1, i+1 (periyodik)
            ym, yp = np.roll(Y, 1, 0), np.roll(Y, -1, 0)
            xi = (xp - xm)[:, 1:nj]; yi = (yp - ym)[:, 1:nj]
            xj = (X[:, 2:] - X[:, :-2]); yj = (Y[:, 2:] - Y[:, :-2])
            a = 0.25*(xj*xj + yj*yj)
            g = 0.25*(xi*xi + yi*yi)
            b = 0.0625*(xi*xj + yi*yj)
            xij = (np.roll(X, -1, 0)[:, 2:] - np.roll(X, -1, 0)[:, :-2]
                   - np.roll(X, 1, 0)[:, 2:] + np.roll(X, 1, 0)[:, :-2])
            yij = (np.roll(Y, -1, 0)[:, 2:] - np.roll(Y, -1, 0)[:, :-2]
                   - np.roll(Y, 1, 0)[:, 2:] + np.roll(Y, 1, 0)[:, :-2])
            den = 2*(a+g) + 1e-30
            Xn = (a*(xp[:, 1:nj] + xm[:, 1:nj]) + g*(X[:, 2:] + X[:, :-2]) - 0.5*b*xij)/den
            Yn = (a*(yp[:, 1:nj] + ym[:, 1:nj]) + g*(Y[:, 2:] + Y[:, :-2]) - 0.5*b*yij)/den
            X[:, 1:nj] = 0.35*X[:, 1:nj] + 0.65*Xn
            Y[:, 1:nj] = 0.35*Y[:, 1:nj] + 0.65*Yn
        # radyal yeniden kumele (ilk hucre korunur)
        for i in range(I):
            lx, ly = X[i], Y[i]
            seg = np.sqrt(np.diff(lx)**2 + np.diff(ly)**2)
            arc = np.concatenate([[0], np.cumsum(seg)])
            if arc[-1] > 0:
                arc /= arc[-1]
                X[i] = np.interp(eta, arc, lx); Y[i] = np.interp(eta, arc, ly)
    return X, Y, I, nj


def write_polymesh(case, X, Y, I, nj, span=0.1):
    """Dogrudan OpenFOAM polyMesh (points/faces/owner/neighbour/boundary).
    O-grid: i periyodik (seam internal), j=0 airfoil, j=nj farfield, k front/back empty.
    """
    pm = Path(case)/"constant"/"polyMesh"; pm.mkdir(parents=True, exist_ok=True)
    J = nj
    def pid(i, j, k): return k*I*(J+1) + (i % I)*(J+1) + j
    def cid(i, j):    return (i % I)*J + j
    pts = []
    for k, z in enumerate((0.0, span)):
        for i in range(I):
            for j in range(J+1):
                pts.append((X[i, j], Y[i, j], z))
    cc = {}  # cell center
    for i in range(I):
        for j in range(J):
            ns = [pid(i,j,0),pid(i+1,j,0),pid(i+1,j+1,0),pid(i,j+1,0),
                  pid(i,j,1),pid(i+1,j,1),pid(i+1,j+1,1),pid(i,j+1,1)]
            cc[cid(i,j)] = np.mean([pts[n] for n in ns], axis=0)

    faces=[]; owner=[]; neigh=[]
    def oriented(quad, own, nei_center):
        p = [np.array(pts[q]) for q in quad]
        nrm = np.cross(p[1]-p[0], p[3]-p[0])
        if np.dot(nrm, nei_center - cc[own]) < 0:
            quad = [quad[0], quad[3], quad[2], quad[1]]
        return quad

    # internal: radyal (j arasi)
    int_faces=[]
    for i in range(I):
        for j in range(J-1):
            o, n = cid(i,j), cid(i,j+1)
            q=[pid(i,j+1,0),pid(i+1,j+1,0),pid(i+1,j+1,1),pid(i,j+1,1)]
            int_faces.append((oriented(q,o,cc[n]),o,n))
    # internal: cevresel (i arasi, seam dahil) -> owner<neighbour
    for i in range(I):
        for j in range(J):
            o, n = cid(i,j), cid(i+1,j)
            lo, hi = min(o,n), max(o,n)
            q=[pid(i+1,j,0),pid(i+1,j+1,0),pid(i+1,j+1,1),pid(i+1,j,1)]
            int_faces.append((oriented(q,lo,cc[hi]),lo,hi))
    int_faces.sort(key=lambda f:(f[1],f[2]))
    for q,o,n in int_faces:
        faces.append(q); owner.append(o); neigh.append(n)
    nInternal=len(faces)

    # boundary: airfoil (j=0), farfield (j=nj), frontAndBack (k=0,1)
    patches=[]
    def add_bpatch(name, quads_owners):
        start=len(faces)
        for q,o in quads_owners:
            p=[np.array(pts[x]) for x in q]
            nrm=np.cross(p[1]-p[0],p[3]-p[0])
            # disa: owner merkezinden yuze
            fc=np.mean(p,axis=0)
            if np.dot(nrm, fc-cc[o])<0: q=[q[0],q[3],q[2],q[1]]
            faces.append(q); owner.append(o)
        patches.append((name,len(quads_owners),start))
    airf=[([pid(i,0,0),pid(i+1,0,0),pid(i+1,0,1),pid(i,0,1)],cid(i,0)) for i in range(I)]
    add_bpatch("airfoil",airf)
    farf=[([pid(i,J,0),pid(i+1,J,0),pid(i+1,J,1),pid(i,J,1)],cid(i,J-1)) for i in range(I)]
    add_bpatch("farfield",farf)
    fb=[]
    for i in range(I):
        for j in range(J):
            fb.append(([pid(i,j,0),pid(i+1,j,0),pid(i+1,j+1,0),pid(i,j+1,0)],cid(i,j)))
            fb.append(([pid(i,j,1),pid(i+1,j,1),pid(i+1,j+1,1),pid(i,j+1,1)],cid(i,j)))
    add_bpatch("frontAndBack",fb)

    def hdr(cls,obj):
        return (f"FoamFile{{version 2.0; format ascii; class {cls}; location \"constant/polyMesh\"; object {obj};}}\n")
    (pm/"points").write_text(hdr("vectorField","points")+f"{len(pts)}\n(\n"+
        "".join(f"({x:.10g} {y:.10g} {z:.10g})\n" for x,y,z in pts)+")\n")
    (pm/"faces").write_text(hdr("faceList","faces")+f"{len(faces)}\n(\n"+
        "".join(f"4({q[0]} {q[1]} {q[2]} {q[3]})\n" for q in faces)+")\n")
    (pm/"owner").write_text(hdr("labelList","owner")+f"{len(owner)}\n(\n"+
        "".join(f"{o}\n" for o in owner)+")\n")
    (pm/"neighbour").write_text(hdr("labelList","neighbour")+f"{len(neigh)}\n(\n"+
        "".join(f"{n}\n" for n in neigh)+")\n")
    bnd=hdr("polyBoundaryMesh","boundary")+f"{len(patches)}\n(\n"
    for name,nf,st in patches:
        typ="empty" if name=="frontAndBack" else ("wall" if name=="airfoil" else "patch")
        bnd+=f"  {name}{{ type {typ}; nFaces {nf}; startFace {st}; }}\n"
    bnd+=")\n"
    (pm/"boundary").write_text(bnd)
    return len(pts), len(faces), I*J, nInternal


if __name__ == "__main__":
    import subprocess
    import sys
    R = float(sys.argv[1]) if len(sys.argv)>1 else 40.0
    case = Path("ogrid_test")
    import shutil
    if case.exists(): shutil.rmtree(case)
    (case/"system").mkdir(parents=True, exist_ok=True)
    for f,c in [("controlDict",'application foamRun; startFrom startTime; startTime 0; endTime 1; deltaT 1; writeInterval 1;'),
                ("fvSchemes",'ddtSchemes{default steadyState;} gradSchemes{default Gauss linear;} divSchemes{default none;} laplacianSchemes{default Gauss linear corrected;} interpolationSchemes{default linear;} snGradSchemes{default corrected;}'),
                ("fvSolution",'solvers{} SIMPLE{}')]:
        (case/"system"/f).write_text(f'FoamFile{{version 2.0; format ascii; class dictionary; object {f};}}\n'+c+"\n")
    X,Y,I,nj = build_ogrid(R=R)
    npts,nf,nc,ni = write_polymesh(case, X, Y, I, nj)
    print(f"polyMesh: {npts} nokta, {nf} yuz ({ni} internal), {nc} hucre")
    p=str(case.resolve()); wsl=f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
    r=linux_run(f"source /opt/openfoam11/etc/bashrc && cd {wsl} && checkMesh 2>&1", 300)
    import re
    for key in ["cells:","non-orthogonality Max","negative volume","zero area","Mesh OK","FAILED","Max skewness","Max aspect"]:
        for line in r.stdout.splitlines():
            if key in line: print("  "+line.strip()); break
