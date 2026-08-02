"""C-grid tek-case kosucusu (alpha=4, 2-asamali SST->LM) — Cd dogrulama yolu.
Kullanim: python exp_cgrid_run.py [etiket n_air n_wake nj s1_end s2_end]
Vars: base 200 60 100 3000 6000. O-grid'den farki: outlet patch'i var,
BC'ler burada yazilir (exp_transition.setup outlet bilmez).
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

from cgrid_elliptic import build_cgrid, write_polymesh_cgrid

alpha=4; rho,V,nu,chord=1.225,50.0,1.48e-5,1.0
lbl,na,nw,njj,s1_end,s2_end=(sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]),int(sys.argv[6])) if len(sys.argv)>6 else ("base",200,60,100,3000,6000)
R_dom=float(sys.argv[7]) if len(sys.argv)>7 else 15.0       # far-field yarıçapı (kiriş)
L_wk =float(sys.argv[8]) if len(sys.argv)>8 else 20.0       # wake uzunluğu (kiriş)
case=Path(f"gci_cg_{lbl}")
if case.exists(): shutil.rmtree(case)
(case/"system").mkdir(parents=True,exist_ok=True)
X,Y,I,nj,nwk=build_cgrid(n_air=na,n_wake=nw,nj=njj,R=R_dom,L_wake=L_wk)
npts,nf,ncell,nint=write_polymesh_cgrid(case,X,Y,I,nj,nwk)
print(f"{lbl}: {ncell} hucre",flush=True)

def setup(case,alpha):
    a=math.radians(alpha); Ux,Uy=V*math.cos(a),V*math.sin(a)
    It=0.0018; Lt=0.07; k0=1.5*(V*It)**2; w0=math.sqrt(k0)/(0.09**0.25*Lt); nut0=k0/w0
    z=case/"0"; z.mkdir(exist_ok=True)
    def W(n,b):(z/n).write_text(b)
    fs_v=f'farfield{{type freestreamVelocity;freestreamValue uniform ({Ux} {Uy} 0);}} outlet{{type freestreamVelocity;freestreamValue uniform ({Ux} {Uy} 0);}}'
    fs_p='farfield{type freestreamPressure;freestreamValue uniform 0;} outlet{type freestreamPressure;freestreamValue uniform 0;}'
    W("U",f'FoamFile{{version 2.0;format ascii;class volVectorField;object U;}} dimensions [0 1 -1 0 0 0 0]; internalField uniform ({Ux} {Uy} 0); boundaryField{{ airfoil{{type noSlip;}} {fs_v} frontAndBack{{type empty;}} }}')
    W("p",f'FoamFile{{version 2.0;format ascii;class volScalarField;object p;}} dimensions [0 2 -2 0 0 0 0]; internalField uniform 0; boundaryField{{ airfoil{{type zeroGradient;}} {fs_p} frontAndBack{{type empty;}} }}')
    def fs_s(v):
        return f'farfield{{type freestream;freestreamValue uniform {v};}} outlet{{type freestream;freestreamValue uniform {v};}}'
    W("k",f'FoamFile{{version 2.0;format ascii;class volScalarField;object k;}} dimensions [0 2 -2 0 0 0 0]; internalField uniform {k0:.6e}; boundaryField{{ airfoil{{type kqRWallFunction;value uniform {k0:.6e};}} {fs_s(f"{k0:.6e}")} frontAndBack{{type empty;}} }}')
    W("omega",f'FoamFile{{version 2.0;format ascii;class volScalarField;object omega;}} dimensions [0 0 -1 0 0 0 0]; internalField uniform {w0:.4f}; boundaryField{{ airfoil{{type omegaWallFunction;value uniform {w0:.4f};}} {fs_s(f"{w0:.4f}")} frontAndBack{{type empty;}} }}')
    W("nut",f'FoamFile{{version 2.0;format ascii;class volScalarField;object nut;}} dimensions [0 2 -1 0 0 0 0]; internalField uniform {nut0:.6e}; boundaryField{{ airfoil{{type nutLowReWallFunction;value uniform 0;}} farfield{{type calculated;value uniform {nut0:.6e};}} outlet{{type calculated;value uniform {nut0:.6e};}} frontAndBack{{type empty;}} }}')
    io_s='farfield{type inletOutlet;inletValue uniform %s;value uniform %s;} outlet{type inletOutlet;inletValue uniform %s;value uniform %s;}'
    W("gammaInt",'FoamFile{version 2.0;format ascii;class volScalarField;object gammaInt;} dimensions [0 0 0 0 0 0 0]; internalField uniform 1; boundaryField{ airfoil{type zeroGradient;} '+io_s % ("1","1","1","1")+' frontAndBack{type empty;} }')
    W("ReThetat",'FoamFile{version 2.0;format ascii;class volScalarField;object ReThetat;} dimensions [0 0 0 0 0 0 0]; internalField uniform 100; boundaryField{ airfoil{type zeroGradient;} '+io_s % ("100","100","100","100")+' frontAndBack{type empty;} }')
    (case/"constant"/"transportProperties").write_text(f'FoamFile{{version 2.0;format ascii;class dictionary;object transportProperties;}}\ntransportModel Newtonian; nu {nu};')
    src=Path(case/"system")
    tmp=Path("_cg_tmp"); tmp_sys=tmp/"system"
    if tmp.exists(): shutil.rmtree(tmp)
    tmp_sys.mkdir(parents=True)
    (tmp/"constant").mkdir()
    T.setup(tmp,alpha)
    shutil.copy(tmp_sys/"fvSchemes",src/"fvSchemes")
    # y+~1 duvar kumelemesi (aspect ~1e4) O-grid icin ayarlanmis relaxation'i
    # istikrarsizlastiriyor (mid SST Cd=-65 divergansi) — C-grid'e dusuk set
    fvsol=(tmp_sys/"fvSolution").read_text()
    fvsol=fvsol.replace(
        "relaxationFactors{equations{U 0.3;k 0.2;omega 0.2;gammaInt 0.2;ReThetat 0.2;}fields{p 0.15;}}",
        "relaxationFactors{equations{U 0.25;k 0.15;omega 0.15;gammaInt 0.15;ReThetat 0.15;}fields{p 0.1;}}")
    (src/"fvSolution").write_text(fvsol)
    shutil.rmtree(tmp)

setup(case,alpha)
p=str(case.resolve()); wsl=f"/mnt/{p[0].lower()}{p[2:].replace(chr(92),'/')}"
def of(cmd,t=7200): return subprocess.run(f'wsl bash -c "source /opt/openfoam11/etc/bashrc && unset FOAM_SIGFPE && cd {wsl} && {cmd}"',shell=True,capture_output=True,text=True,timeout=t)

def parse_cd_cl(fdat):
    ll=[line for line in fdat.read_text().splitlines() if line.strip() and not line.startswith("#")]
    nums=re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', ll[-1])
    Fx=float(nums[1])+float(nums[4]); Fy=float(nums[2])+float(nums[5])
    a=math.radians(alpha); q=0.5*rho*V**2; S=chord*0.1
    return (Fx*math.cos(a)+Fy*math.sin(a))/(q*S), (-Fx*math.sin(a)+Fy*math.cos(a))/(q*S)

out={"topology":"C-grid (wake-kumelemeli)","mesh":f"n_air={na} n_wake={nw} nj={njj}","cells":ncell,
     "s1_end":s1_end,"s2_end":s2_end}
# Asama 0: birinci-mertebe (upwind) isinma — y+~1 yuksek-AR hucrelerde
# linearUpwindV ile soguk kalkis patlamasinin standart caresi
s0_end=1500
fvs_ho=(case/"system"/"fvSchemes").read_text()
fvs_fo=fvs_ho.replace("div(phi,U) bounded Gauss linearUpwindV grad(U)","div(phi,U) bounded Gauss upwind")
(case/"system"/"fvSchemes").write_text(fvs_fo)
T.ctrl(case,"kOmegaSST",s0_end)
of("potentialFoam -initialiseUBCs -writep >log.pot 2>&1; foamRun -solver incompressibleFluid >log.s0 2>&1")
# Asama 1: yuksek-mertebe semaya gec, isinmis alandan devam
(case/"system"/"fvSchemes").write_text(fvs_ho)
T.ctrl(case,"kOmegaSST",s1_end)
cd_txt=(case/"system"/"controlDict").read_text()
(case/"system"/"controlDict").write_text(cd_txt.replace("startFrom startTime","startFrom latestTime"))
of("foamRun -solver incompressibleFluid >log.s1 2>&1")
lt=max((d for d in case.iterdir() if d.is_dir() and d.name!="0" and d.name.replace(".","",1).isdigit()),key=lambda d:float(d.name),default=None)
if lt is None:
    out["status"]="stage1_failed"
else:
    ff1=sorted((case/"postProcessing"/"forces").glob("*/forces.dat"),key=lambda f:float(f.parent.name))
    cd1,cl1=parse_cd_cl(ff1[-1])
    out["SST"]={"Cd":round(cd1,5),"Cl":round(cl1,4)}
    print(f"{lbl} SST: Cd={cd1:.5f} Cl={cl1:.4f}",flush=True)
    for fld in ("gammaInt","ReThetat"): shutil.copy(case/"0"/fld, lt/fld)
    T.ctrl(case,"kOmegaSSTLM",s2_end)
    of("foamRun -solver incompressibleFluid >log.s2 2>&1")
    s2=(case/"log.s2").read_text(errors="ignore")
    if "FOAM FATAL" in s2 or not s2.rstrip().endswith("End"):
        out["status"]="stage2_failed"; print(f"{lbl}: STAGE2 FATAL/CRASH",flush=True)
    else:
        ff=sorted((case/"postProcessing"/"forces").glob("*/forces.dat"),key=lambda f:float(f.parent.name))
        cd2,cl2=parse_cd_cl(ff[-1])
        out["LM"]={"Cd":round(cd2,5),"Cl":round(cl2,4)}; out["status"]="ok"
        print(f"{lbl} LM:  Cd={cd2:.5f} Cl={cl2:.4f}",flush=True)
# Cikti adi hesaplaniyor; literal ad kaynakta gecmedigi icin kanit denetimi
# bunu "uretici kod depoda YOK" saniyordu. Komut kanita YAZILIYOR.
out["_uretim"] = ("Üretim: python experiments/exp_cgrid_run.py "
                  + " ".join(sys.argv[1:]))
Path(f"gci_cgrid_{lbl}.json").write_text(json.dumps(out,indent=2))
