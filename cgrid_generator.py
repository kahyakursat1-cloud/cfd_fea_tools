"""
C-Grid Generator — y+<1 ortogonal yapisal airfoil mesh
=======================================================
O-grid'in temel limitini cozer: radyal-projeksiyon O-grid TE'de non-ortho 82
veriyor ve y+<1'de coker. C-grid:
  - Yuzey-normali boyunca hiperbolik ekstrüzyon -> near-wall ORTOGONAL
  - Iz (wake) cut ile sharp-TE singularitesi asilir
  - Iz-cut dugumleri paylasilir -> surekli mesh (gmshToFoam ic-yuz tespit eder)

Cikti: Gmsh MSH 2.2 -> gmshToFoam -> OpenFOAM polyMesh.

Hedef: checkMesh non-ortho < 30, ilk hucre ~1e-5 (y+~1 @ Re=3e6), Cd hata < %5.
"""

import math
import subprocess
import numpy as np
from pathlib import Path


def naca4_thickness(x, t=0.12):
    return (t/0.2)*(0.2969*np.sqrt(np.maximum(x, 0)) - 0.1260*x
                    - 0.3516*x**2 + 0.2843*x**3 - 0.1015*x**4)


def naca4_camber(x, m=0.0, p=0.4):
    if m == 0:
        return np.zeros_like(x), np.zeros_like(x)
    yc = np.where(x < p, m/p**2*(2*p*x - x**2),
                  m/(1-p)**2*((1-2*p)+2*p*x - x**2))
    dyc = np.where(x < p, 2*m/p**2*(p-x), 2*m/(1-p)**2*(p-x))
    return yc, dyc


def airfoil_surface(naca="0012", n_half=100):
    """Kapali airfoil: TE_lower -> LE -> TE_upper. Cosine kumeleme.
    Donduru: (na+1, 2) — i=0 TE_lower, orta LE, son TE_upper.
    """
    m = int(naca[0])/100.0; p = int(naca[1])/10.0 if int(naca[0]) else 0.4
    t = int(naca[2:])/100.0
    beta = np.linspace(0, np.pi, n_half)
    xc = 0.5*(1-np.cos(beta))          # 0..1 cosine
    yt = naca4_thickness(xc, t)
    yc, dyc = naca4_camber(xc, m, p)
    th = np.arctan(dyc)
    xu = xc - yt*np.sin(th); yu = yc + yt*np.cos(th)
    xl = xc + yt*np.sin(th); yl = yc - yt*np.cos(th)
    # lower TE->LE (ters), sonra upper LE->TE
    xlo = xl[::-1]; ylo = yl[::-1]      # x:1->0
    xup = xu[1:];   yup = yu[1:]        # x:0->1 (LE tekrar yok)
    X = np.concatenate([xlo, xup]); Y = np.concatenate([ylo, yup])
    return np.column_stack([X, Y])


def tanh_spacing(n, first, total):
    """tanh kumeleme: ilk aralik ~first, toplam ~total, n hucre."""
    # normalize: s in [0,1], yogunluk duvarda
    s = np.linspace(0, 1, n+1)
    # stretching faktoru bul (Vinokur benzeri basit tanh)
    # ratio = total/first hedef
    beta = 4.0
    for _ in range(60):
        d = np.tanh(beta*s)/np.tanh(beta)
        f0 = (d[1]-d[0])*total
        if abs(f0-first)/first < 0.01:
            break
        beta *= (1 + 0.5*math.copysign(1, f0-first)) if f0 > first else (1/(1+0.3))
        beta = min(max(beta, 0.5), 12)
    d = np.tanh(beta*s)/np.tanh(beta)
    return d*total


def build_cgrid(naca="0012", n_half=100, nw=60, nj=90,
                first_cell=1e-5, R_far=15.0, wake_len=15.0, span=0.1):
    """C-grid dugum koordinatlari + wake-cut paylasimli node ID haritasi.
    Donduru: nodes (list of (x,y,z)), node_id[(i,j,k)], dims (I, nj, 2)
    """
    af = airfoil_surface(naca, n_half)           # (na+1,2)
    na = len(af)-1
    # Iz dugumleri: TE(1,0) -> outflow(wake_len, 0), x kumeleme
    xte = af[-1, 0]                               # ~1.0
    sw = np.linspace(0, 1, nw+1)**1.3             # TE'de sik
    xwake = xte + (wake_len-xte)*sw               # 1 -> wake_len
    wake_lower = np.column_stack([xwake[::-1], np.zeros(nw+1)])   # outflow->TE
    wake_upper = np.column_stack([xwake, np.zeros(nw+1)])        # TE->outflow

    # Inner i-line (j=0): lower wake (outflow->TE) + airfoil(TE->LE->TE) + upper wake(TE->outflow)
    # lower wake: i=0..nw  (i=nw = TE)
    # airfoil:    i=nw..nw+na (paylasimli TE uclar)
    # upper wake: i=nw+na..nw+na+nw = I
    inner = np.vstack([wake_lower[:-1], af, wake_upper[1:]])     # TE'ler tekrar etmesin
    I = len(inner)-1                              # son index
    # segment sinirlari
    i_te1 = nw                                    # lower TE (airfoil basi)
    i_te2 = nw+na                                 # upper TE (airfoil sonu)

    # Outward normaller (inner curve boyunca, merkezi fark + smoothing)
    nrm = np.zeros_like(inner)
    for i in range(I+1):
        a = inner[max(i-1, 0)]; b = inner[min(i+1, I)]
        tx, ty = b[0]-a[0], b[1]-a[1]
        L = math.hypot(tx, ty) or 1e-12
        # sol-normal (disa): (ty,-tx)/L for CW... airfoil lower->upper CCW disa = (-ty,tx)? ayarla
        nrm[i] = (ty/L, -tx/L)
    # Airfoil bolgesinde normalin disa baktigindan emin ol (merkezden disa)
    cx, cy = 0.4, 0.0
    for i in range(i_te1, i_te2+1):
        if np.dot(nrm[i], inner[i]-[cx, cy]) < 0:
            nrm[i] *= -1
    # Iz bolgesi: alt iz -y, ust iz +y
    for i in range(0, i_te1):
        nrm[i] = (0.0, -1.0)
    for i in range(i_te2+1, I+1):
        nrm[i] = (0.0, 1.0)
    # Normal alanini yumusat (TE kinklerini gider) — duvar tegetini koru
    for _ in range(30):
        new = nrm.copy()
        for i in range(1, I):
            new[i] = 0.5*nrm[i] + 0.25*(nrm[i-1]+nrm[i+1])
            n = math.hypot(*new[i]) or 1e-12
            new[i] /= n
        nrm = new

    # Radyal mesafe dagilimi (tanh, y+~1)
    dist = tanh_spacing(nj, first_cell, R_far)    # (nj+1,)
    eta_d = dist / R_far                           # [0,1]

    # ── Dis sinir: kendisiyle kesismeyen dikdortgen C (inner arc-length ile esle)
    # Kose noktalari: lower-outflow, front-bottom, front-top, upper-outflow
    xw = inner[0, 0]                               # outflow x (=wake_len)
    xf = 0.5 - R_far                               # front (sol) x
    yb, yt = -R_far, R_far
    # dikdortgen cevre yolu (lower-outflow -> bottom -> front -> top -> upper-outflow)
    corners = np.array([[xw, yb], [xf, yb], [xf, yt], [xw, yt]])
    cseg = np.linalg.norm(np.diff(corners, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(cseg)]); cum /= cum[-1]
    def outer_at(s):                               # s in [0,1] cevre konumu
        k = np.searchsorted(cum, s, side='right') - 1
        k = min(max(k, 0), 2)
        f = (s - cum[k]) / (cum[k+1] - cum[k] + 1e-30)
        return corners[k] + f*(corners[k+1] - corners[k])

    # inner arc-length fraksiyonu
    iseg = np.linalg.norm(np.diff(inner, axis=0), axis=1)
    isarc = np.concatenate([[0], np.cumsum(iseg)]); isarc /= isarc[-1]
    outer = np.array([outer_at(s) for s in isarc])

    # ── Algebraik baslangic: TFI (inner->outer, tanh radyal) ─────────────────
    P = np.zeros((I+1, nj+1, 2))
    for j in range(nj+1):
        P[:, j] = (1-eta_d[j])*inner + eta_d[j]*outer

    # ── Winslow eliptik grid uretimi + yeniden kumeleme ──────────────────────
    # Winslow (∇²ξ=0,∇²η=0) -> near-ortogonal, cakismasiz grid (basit Laplace'in
    # aksine). Iteratif Gauss-Seidel; duvar/far/outflow sabit. Her N turda tanh
    # ile yeniden kumele -> ilk hucre y+ korunur.
    eta = dist / R_far
    X = P[:, :, 0].copy(); Y = P[:, :, 1].copy()
    for sweep in range(6):
        for _ in range(60):
            xi  = X[2:, 1:nj] - X[:-2, 1:nj]; yi = Y[2:, 1:nj] - Y[:-2, 1:nj]
            xj  = X[1:I, 2:] - X[1:I, :-2];   yj = Y[1:I, 2:] - Y[1:I, :-2]
            a = 0.25*(xj*xj + yj*yj)               # alpha
            g = 0.25*(xi*xi + yi*yi)               # gamma
            b = 0.0625*(xi*xj + yi*yj)             # beta
            xij = X[2:, 2:] - X[2:, :-2] - X[:-2, 2:] + X[:-2, :-2]
            yij = Y[2:, 2:] - Y[2:, :-2] - Y[:-2, 2:] + Y[:-2, :-2]
            denom = 2*(a + g) + 1e-30
            Xn = (a*(X[2:, 1:nj] + X[:-2, 1:nj]) + g*(X[1:I, 2:] + X[1:I, :-2])
                  - 0.5*b*xij) / denom
            Yn = (a*(Y[2:, 1:nj] + Y[:-2, 1:nj]) + g*(Y[1:I, 2:] + Y[1:I, :-2])
                  - 0.5*b*yij) / denom
            X[1:I, 1:nj] = 0.4*X[1:I, 1:nj] + 0.6*Xn   # under-relax
            Y[1:I, 1:nj] = 0.4*Y[1:I, 1:nj] + 0.6*Yn
        # yeniden kumele (tanh) — ilk hucre korunur
        for i in range(1, I):
            lx, ly = X[i], Y[i]
            seg = np.sqrt(np.diff(lx)**2 + np.diff(ly)**2)
            arc = np.concatenate([[0], np.cumsum(seg)])
            if arc[-1] > 0:
                arc /= arc[-1]
                X[i] = np.interp(eta, arc, lx); Y[i] = np.interp(eta, arc, ly)
    P[:, :, 0] = X; P[:, :, 1] = Y

    # Dugum uretimi + wake-cut paylasimi
    nodes = []
    node_id = {}
    def add(x, y, z):
        nodes.append((x, y, z)); return len(nodes)   # 1-based (gmsh)

    zs = [0.0, span]
    for k, z in enumerate(zs):
        for i in range(I+1):
            for j in range(nj+1):
                # wake-cut paylasimi: j=0 ust-iz dugumu, alt-iz mirror'una esle
                if j == 0 and i > i_te2:
                    mi = I - i                       # alt iz mirror index
                    if 0 <= mi < i_te1:
                        node_id[(i, j, k)] = node_id[(mi, 0, k)]
                        continue
                node_id[(i, j, k)] = add(P[i, j, 0], P[i, j, 1], z)
    return nodes, node_id, (I, nj), (i_te1, i_te2)


def write_gmsh(path, nodes, node_id, dims, te, outpatch_x=None):
    """Gmsh MSH 2.2: dugumler + hex hucreler + sinir quad'lari + PhysicalNames."""
    I, nj = dims
    i_te1, i_te2 = te
    lines = ["$MeshFormat\n2.2 0 8\n$EndMeshFormat\n"]
    lines.append("$PhysicalNames\n5\n")
    lines.append('2 1 "airfoil"\n2 2 "farfield"\n2 3 "frontAndBack"\n3 4 "internal"\n2 5 "outlet"\n')
    lines.append("$EndPhysicalNames\n")
    lines.append(f"$Nodes\n{len(nodes)}\n")
    for nid, (x, y, z) in enumerate(nodes, 1):
        lines.append(f"{nid} {x:.9g} {y:.9g} {z:.9g}\n")
    lines.append("$EndNodes\n")

    elems = []
    eid = 0
    def E(typ, phys, ns):
        nonlocal eid; eid += 1
        elems.append(f"{eid} {typ} 2 {phys} {phys} " + " ".join(map(str, ns)) + "\n")

    coord = {nid: np.array(p) for nid, p in enumerate(nodes, 1)}
    def signed_vol(ns):
        # hex hacmi: alt yuz merkezinden 6 tet (yaklasik isaret testi)
        p = [coord[n] for n in ns]
        # taban normali (p0->p1 x p0->p3) . (p0->p4)
        return np.dot(np.cross(p[1]-p[0], p[3]-p[0]), p[4]-p[0])

    # Hexler (i,j arasi, k=0->1 span) — isaret negatifse winding ters cevir
    for i in range(I):
        for j in range(nj):
            n0 = node_id[(i, j, 0)];   n1 = node_id[(i+1, j, 0)]
            n2 = node_id[(i+1, j+1, 0)]; n3 = node_id[(i, j+1, 0)]
            m0 = node_id[(i, j, 1)];   m1 = node_id[(i+1, j, 1)]
            m2 = node_id[(i+1, j+1, 1)]; m3 = node_id[(i, j+1, 1)]
            hexn = [n0, n1, n2, n3, m0, m1, m2, m3]
            if signed_vol(hexn) < 0:
                hexn = [n0, n3, n2, n1, m0, m3, m2, m1]   # taban winding ters
            E(5, 4, hexn)

    # airfoil patch: j=0, i in [i_te1, i_te2]
    for i in range(i_te1, i_te2):
        a = node_id[(i, 0, 0)]; b = node_id[(i+1, 0, 0)]
        c = node_id[(i+1, 0, 1)]; d = node_id[(i, 0, 1)]
        E(3, 1, [a, b, c, d])
    # farfield patch: j=nj (tum i)
    for i in range(I):
        a = node_id[(i, nj, 0)]; b = node_id[(i+1, nj, 0)]
        c = node_id[(i+1, nj, 1)]; d = node_id[(i, nj, 1)]
        E(3, 2, [a, b, c, d])
    # outlet: i=0 ve i=I (downstream outflow, tum j)
    for iface in (0, I):
        for j in range(nj):
            if iface == 0:
                a = node_id[(0, j, 0)]; b = node_id[(0, j+1, 0)]
                c = node_id[(0, j+1, 1)]; d = node_id[(0, j, 1)]
            else:
                a = node_id[(I, j, 0)]; b = node_id[(I, j+1, 0)]
                c = node_id[(I, j+1, 1)]; d = node_id[(I, j, 1)]
            E(3, 5, [a, b, c, d])
    # frontAndBack (empty): k=0 ve k=1 tum hucre yuzleri
    for k, kk in ((0, 0), (1, 1)):
        for i in range(I):
            for j in range(nj):
                a = node_id[(i, j, kk)]; b = node_id[(i+1, j, kk)]
                c = node_id[(i+1, j+1, kk)]; d = node_id[(i, j+1, kk)]
                E(3, 3, [a, b, c, d])

    lines.append(f"$Elements\n{len(elems)}\n")
    lines.extend(elems)
    lines.append("$EndElements\n")
    Path(path).write_text("".join(lines))


def _min_case(case_dir):
    """gmshToFoam/checkMesh icin minimal system/ dosyalari."""
    sysd = case_dir/"system"; sysd.mkdir(parents=True, exist_ok=True)
    (sysd/"controlDict").write_text(
        'FoamFile{ version 2.0; format ascii; class dictionary; object controlDict; }\n'
        'application foamRun; startFrom startTime; startTime 0; endTime 1;\n'
        'deltaT 1; writeInterval 1; writeFormat ascii;\n')
    (sysd/"fvSchemes").write_text(
        'FoamFile{ version 2.0; format ascii; class dictionary; object fvSchemes; }\n'
        'ddtSchemes{ default steadyState; } gradSchemes{ default Gauss linear; }\n'
        'divSchemes{ default none; } laplacianSchemes{ default Gauss linear corrected; }\n'
        'interpolationSchemes{ default linear; } snGradSchemes{ default corrected; }\n')
    (sysd/"fvSolution").write_text(
        'FoamFile{ version 2.0; format ascii; class dictionary; object fvSolution; }\n'
        'solvers{} SIMPLE{}\n')


def generate(case_dir, naca="0012", **kw):
    case_dir = Path(case_dir)
    (case_dir/"constant"/"polyMesh").mkdir(parents=True, exist_ok=True)
    _min_case(case_dir)
    nodes, nid, dims, te = build_cgrid(naca, **kw)
    msh = case_dir/"cgrid.msh"
    write_gmsh(str(msh), nodes, nid, dims, te)
    return msh, dims


if __name__ == "__main__":
    import sys
    case = Path("cgrid_test")
    msh, dims = generate(case, naca="0012")
    print(f"C-grid uretildi: {msh}  dims(I,nj)={dims}  dugum~{dims[0]*dims[1]*2}")
    # gmshToFoam + checkMesh
    p = str(case.resolve()); wsl = f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
    def of(cmd, t=300):
        return subprocess.run(
            f'wsl bash -c "source /opt/openfoam11/etc/bashrc && cd {wsl} && {cmd}"',
            shell=True, capture_output=True, text=True, timeout=t)
    r = of(f"gmshToFoam cgrid.msh > log.g2f 2>&1")
    print("gmshToFoam rc:", r.returncode)
    r2 = of("checkMesh > log.check 2>&1")
    chk = (case/"log.check").read_text(errors="replace")
    for key in ["cells:", "non-orthogonality Max", "Max skewness", "Max aspect", "Mesh OK", "FAILED"]:
        for line in chk.splitlines():
            if key in line:
                print("  ", line.strip()); break
