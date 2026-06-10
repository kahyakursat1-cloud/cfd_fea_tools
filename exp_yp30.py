"""Basit O-grid, y+~30 sweet-spot (log-law) — drag'i duzeltme denemesi."""
import json
import sys
from pathlib import Path

from validation_suite import NACA0012Validation


class V30(NACA0012Validation):
    def __init__(s, bp, grading, n_norm=100, n_prof=240):
        super().__init__(bp); s.n_prof=n_prof; s.n_norm=n_norm; s.grading=grading
a=int(sys.argv[1]) if len(sys.argv)>1 else 4
# y+~30 -> ilk hucre ~0.47mm; grading taramasi
for G in [2000, 4400, 8000]:
    v=V30(f"validation/yp30_{G}", grading=G)
    r=v.run(alpha_deg=a)
    if "Cd_sim" in r:
        print(f"grading={G:6d}: Cd={r['Cd_sim']} (err={r.get('Cd_err_pct')}%)  Cl={r['Cl_sim']} (err={r.get('Cl_err_pct')}%)  {r['status']}", flush=True)
    else:
        print(f"grading={G:6d}: FAILED {r.get('step')}", flush=True)
