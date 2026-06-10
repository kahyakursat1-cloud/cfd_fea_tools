"""GCI ek seviye kosucusu (asimptotik aralik testi, alpha=4, 2-asamali).
Kullanim: python exp_gci_xfine.py [etiket na nj sweeps iters]  (vars: xfine 440 220 22 150)
"""
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import exp_transition as T

from ogrid_elliptic import build_ogrid, write_polymesh

alpha=4; R=40.0; rho,V,chord=1.225,50.0,1.0
lbl,na,njj,sw,it=(sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5])) if len(sys.argv)>5 else ("xfine",440,220,22,150)
case=Path(f"gci_{lbl}")
if case.exists(): shutil.rmtree(case)
(case/"system").mkdir(parents=True,exist_ok=True)
X,Y,I,nj=build_ogrid(R=R,n_around=na,nj=njj,first_cell=8e-6,sweeps=sw,iters=it)
write_polymesh(case,X,Y,I,nj)
T.setup(case,alpha)
p=str(case.resolve()); wsl=f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
def of(cmd,t=2400): return subprocess.run(f'wsl bash -c "source /opt/openfoam11/etc/bashrc && export FOAM_SIGFPE=false && cd {wsl} && {cmd}"',shell=True,capture_output=True,text=True,timeout=t)

def parse_cd_cl(fdat):
    ll=[l for l in fdat.read_text().splitlines() if l.strip() and not l.startswith("#")]
    nums=re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', ll[-1])
    Fx=float(nums[1])+float(nums[4]); Fy=float(nums[2])+float(nums[5])
    a=math.radians(alpha); q=0.5*rho*V**2; S=chord*0.1
    return (Fx*math.cos(a)+Fy*math.sin(a))/(q*S), (-Fx*math.sin(a)+Fy*math.cos(a))/(q*S)

out={"mesh":f"{na}x{njj} sweeps={sw} iters={it}"}
T.ctrl(case,"kOmegaSST",2000)
of("potentialFoam -initialiseUBCs -writep >log.pot 2>&1; foamRun -solver incompressibleFluid >log.s1 2>&1")
lt=max((d for d in case.iterdir() if d.is_dir() and d.name!="0" and d.name.replace(".","",1).isdigit()),key=lambda d:float(d.name),default=None)
if lt is None:
    out["status"]="stage1_failed"
else:
    cd1,cl1=parse_cd_cl(case/"postProcessing"/"forces"/"0"/"forces.dat")
    out["SST"]={"Cd":round(cd1,5),"Cl":round(cl1,4)}
    print(f"{lbl} SST: Cd={cd1:.5f} Cl={cl1:.4f}",flush=True)
    for fld in ("gammaInt","ReThetat"): shutil.copy(case/"0"/fld, lt/fld)
    T.ctrl(case,"kOmegaSSTLM",4000)
    of("foamRun -solver incompressibleFluid >log.s2 2>&1")
    s2=(case/"log.s2").read_text(errors="ignore")
    if "FOAM FATAL" in s2 or not s2.rstrip().endswith("End"):
        out["status"]="stage2_failed"; print(f"{lbl}: STAGE2 FATAL/CRASH",flush=True)
    else:
        ff=sorted((case/"postProcessing"/"forces").glob("*/forces.dat"),key=lambda f:float(f.parent.name))
        cd2,cl2=parse_cd_cl(ff[-1])
        out["LM"]={"Cd":round(cd2,5),"Cl":round(cl2,4)}; out["status"]="ok"
        print(f"{lbl} LM:  Cd={cd2:.5f} Cl={cl2:.4f}",flush=True)
Path(f"gci_{lbl}.json").write_text(json.dumps(out,indent=2))
