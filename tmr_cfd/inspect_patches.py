"""OpenFOAM polyMesh patch geometri inspektörü — her boundary patch'in bbox + ortalama
normal'ini verir (TMR C-grid patch'lerini airfoil/farfield/empty/wake-cut diye ayırmak için).
Kullanım: python inspect_patches.py <case_dir>
"""
import re
import sys
from pathlib import Path

import numpy as np


def read_points(p):
    txt = p.read_text()
    body = txt[txt.index("("):]
    nums = re.findall(r"\(([-\d.eE+ ]+)\)", body)
    return np.array([[float(x) for x in n.split()] for n in nums])


def read_faces(p):
    txt = p.read_text()
    body = txt[txt.index("\n(") + 2:]
    faces = []
    for m in re.finditer(r"(\d+)\(([\d ]+)\)", body):
        faces.append([int(x) for x in m.group(2).split()])
    return faces


def read_boundary(p):
    txt = p.read_text()
    pats = []
    for m in re.finditer(r"(\w+)\s*\{([^}]*)\}", txt):
        body = m.group(2)
        nf = re.search(r"nFaces\s+(\d+)", body)
        sf = re.search(r"startFace\s+(\d+)", body)
        if nf and sf:
            pats.append((m.group(1), int(nf.group(1)), int(sf.group(1))))
    return pats


def main():
    case = Path(sys.argv[1])
    pm = case / "constant" / "polyMesh"
    pts = read_points(pm / "points")
    faces = read_faces(pm / "faces")
    bnd = read_boundary(pm / "boundary")
    print(f"{'patch':<12} {'nFaces':>7}  {'x[min,max]':>16} {'y[min,max]':>16} "
          f"{'z[min,max]':>14}  {'|nz|':>5} {'r_orta':>7}")
    for name, nf, sf in bnd:
        if nf == 0:
            print(f"{name:<12} {nf:>7}  (boş)")
            continue
        fc, nz = [], []
        for fi in range(sf, sf + nf):
            f = faces[fi]
            P = pts[f]
            c = P.mean(axis=0)
            fc.append(c)
            v1, v2 = P[1] - P[0], P[2] - P[0]
            n = np.cross(v1, v2)
            n /= (np.linalg.norm(n) + 1e-30)
            nz.append(abs(n[2]))
        fc = np.array(fc)
        r = np.sqrt(fc[:, 0] ** 2 + fc[:, 1] ** 2).mean()
        print(f"{name:<12} {nf:>7}  [{fc[:,0].min():6.1f},{fc[:,0].max():6.1f}] "
              f"[{fc[:,1].min():6.1f},{fc[:,1].max():6.1f}] "
              f"[{fc[:,2].min():5.2f},{fc[:,2].max():5.2f}]  {np.mean(nz):5.2f} {r:7.2f}")


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    main()
