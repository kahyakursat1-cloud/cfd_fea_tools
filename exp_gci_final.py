"""GCI mesh-bagimsizlik: 3 cozunurluk, alpha=4, transition modeli, valid O-grid."""
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import exp_transition as T  # setup/ctrl fonksiyonlarini yeniden kullan
from ogrid_elliptic import build_ogrid, write_polymesh

alpha=4; R=40.0; rho,V,chord=1.225,50.0,1.0
meshes={"coarse":(200,100),"medium":(260,130),"fine":(340,170)}
cd={}; status={}
for lvl,(na,njj) in meshes.items():
    case=Path(f"gci_{lvl}")
    if case.exists(): shutil.rmtree(case)
    (case/"system").mkdir(parents=True,exist_ok=True)
    X,Y,I,nj=build_ogrid(R=R,n_around=na,nj=njj,first_cell=8e-6)
    write_polymesh(case,X,Y,I,nj)
    T.setup(case,alpha)
    p=str(case.resolve()); wsl=f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
    def of(cmd,t=2400,wsl=wsl): return subprocess.run(f'wsl bash -c "source /opt/openfoam11/etc/bashrc && export FOAM_SIGFPE=false && cd {wsl} && {cmd}"',shell=True,capture_output=True,text=True,timeout=t)
    T.ctrl(case,"kOmegaSST",2000)
    of("potentialFoam -initialiseUBCs -writep >log.pot 2>&1; foamRun -solver incompressibleFluid >log.s1 2>&1")
    lt=max((d for d in case.iterdir() if d.is_dir() and d.name!="0" and d.name.replace(".","",1).isdigit()),key=lambda d:float(d.name),default=None)
    if lt is None: print(f"{lvl}: STAGE1 FAIL",flush=True); status[lvl]="stage1_failed"; continue
    for fld in ("gammaInt","ReThetat"): shutil.copy(case/"0"/fld, lt/fld)
    T.ctrl(case,"kOmegaSSTLM",4000)
    of("foamRun -solver incompressibleFluid >log.s2 2>&1")
    if "FOAM FATAL" in (case/"log.s2").read_text(errors="ignore"):
        print(f"{lvl}: STAGE2 FATAL",flush=True); status[lvl]="stage2_failed"; continue
    ff=sorted((case/"postProcessing"/"forces").glob("*/forces.dat"),key=lambda f:float(f.parent.name))
    if not ff: print(f"{lvl}: FAIL",flush=True); status[lvl]="no_forces"; continue
    ll=[l for l in ff[-1].read_text().splitlines() if l.strip() and not l.startswith("#")]
    nums=re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', ll[-1])
    Fx=float(nums[1])+float(nums[4]); Fy=float(nums[2])+float(nums[5])
    a=math.radians(alpha); drag=Fx*math.cos(a)+Fy*math.sin(a)
    q=0.5*rho*V**2; S=chord*0.1; Cdv=drag/(q*S); ncell=na*njj
    if not (math.isfinite(Cdv) and abs(Cdv)<0.5):
        print(f"{lvl}: DIVERGED Cd={Cdv:.3g}",flush=True); status[lvl]=f"diverged Cd={Cdv:.3g}"; continue
    cd[lvl]=Cdv; status[lvl]="ok"
    print(f"{lvl:7s} cells~{ncell:6d}: Cd={Cdv:.5f}",flush=True)
# GCI (Richardson)
if len(cd)==3:
    Nf,Nm,Nc=340*170,260*130,200*100
    r=( (Nf/Nm)**0.5 + (Nm/Nc)**0.5 )/2
    f1,f2,f3=cd["fine"],cd["medium"],cd["coarse"]
    e32,e21=f3-f2,f2-f1
    if e21!=0 and (e32/e21)>0:
        p_ord=math.log(abs(e32/e21))/math.log(r)
        fext=(r**p_ord*f1-f2)/(r**p_ord-1)
        gci=1.25*abs((f1-f2)/f1)/(r**p_ord-1)*100
        print(f"\nGCI: p={p_ord:.2f}  Richardson Cd(h->0)={fext:.5f}  GCI(fine)={gci:.2f}%  monotonik={'evet' if e32/e21>0 else 'hayir'}")
        json.dump({"model":"kOmegaSSTLM","status":status,"cd":cd,"p":round(p_ord,3),"Cd_extrap":round(fext,5),"gci_pct":round(gci,3)},open("gci_final.json","w"),indent=2)
    else:
        print(f"\nGCI: monotonik degil (e32/e21={e32/e21:.2f}) - sadece Cd degerleri raporlanir")
        json.dump({"model":"kOmegaSSTLM","status":status,"cd":cd},open("gci_final.json","w"),indent=2)
else:
    json.dump({"model":"kOmegaSSTLM","status":status,"cd":cd},open("gci_final.json","w"),indent=2)
