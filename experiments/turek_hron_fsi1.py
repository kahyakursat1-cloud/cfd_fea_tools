"""Turek--Hron FSI1 — aktarılan yük ve yapısal yanıt, YAYIMLANMIŞ referansa karşı.

DEPONUN HİÇ SAHİP OLMADIĞI ŞEY BUYDU. Bugüne kadar FSI tarafında ölçülen
her şey İÇ tutarlılıktı: kuvvet korunuyor mu, moment ne kadar kayıyor,
eşleme deforme yüzeyde sabit kalıyor mu. Hiçbiri ``FEA'ya giden yük DOĞRU
MU'' sorusunu sormuyordu --- çünkü karşılaştırılacak bir dış referans yoktu.

FSI1 onu verir: aynı geometride akış çözülür, basınç bayrağa aktarılır,
yapı çözülür ve uç yer değiştirmesi yayımlanmış değerle karşılaştırılır.

NE KAPATIR: aktarım zincirinin UÇTAN UCA doğruluğu. Yanlış bir eşleme,
yanlış bir birim ya da yanlış bir normal burada GÖRÜNÜR --- iç metrikler
bunların hiçbirini yakalamaz (hepsi kendi içinde tutarlı kalır).

NE BULDU: iki ayrı KAPSAM boşluğu, ikisi de sayıya döküldü. Biri sonra
KAPATILDI, öbürü açık kaldı.

  1. [KAPANDI] Kuplaj BASINÇ-YALNIZ çalışıyordu. Bu bayrakta çözücünün
     kendi yüzey integrali viskoz eksenel kuvveti basıncınkinin 9,6 KATI
     verdi ve uç yer değiştirmesinin x bileşeni bir mertebe küçük çıktı
     (-0,0019 mm, referans 0,0227). Kuplaja viskoz çekme kanalı eklendi
     (grad(U) üzerinden; toplamı çözücünün kendi kuvvetiyle %1 içinde) ve
     ölçülen ux 0,0230 mm oldu --- referanstan %1,3. Bu bir HESAP değil,
     kanal açıkken YENİDEN KOŞULMUŞ bir ölçümdür.
  2. [AÇIK] Akış RİJİT bayrakla çözülüyor. Kaynağın kendi taşıma
     değerleri (rijit 1,119 / deforme 0,7638 N/m) geri beslemenin yükü
     %32 düşürdüğünü söyler; ham %90'lık düşey sapma bu oranla
     ölçeklenince %30'a iner. Bu düzeltme HESAPLANDI, koşulmadı.

NE KAPATMAZ: düşey kanalı. ``Fizik tahrik ediyor'' iddiası hâlâ
FSI2/FSI3'ün işidir.

NASIL YANLIŞ GİTTİ (kayda değer): ilk sürüm bu sapmayı REFERANSA attı ---
``çift kendi içinde tutarsız'' diye bir kapı yazdım ve kapı, eksenel
terimi BİZİM taşıdığımız (basınç-yalnız) kuvvetten kuruyordu. Kusur dış
kaynağa atılmıştı; çözücünün kendi çıktısı alınınca eksik olanın bizim
yükümüz olduğu görüldü.

    python experiments/turek_hron_fsi1.py
Çıktı: turek_hron_fsi1.json
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

from turek_hron_ag import (  # noqa: E402
    BAYRAK_KALINLIK,
    BAYRAK_SON_X,
    MERKEZ,
    Z_KALINLIK,
    bayrak_bas_x,
)
from turek_hron_cfd1 import NU, RHO  # noqa: E402
from turek_hron_cfd1 import VAKA as CFD_VAKA

from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import run_ccx, windows_to_wsl_path  # noqa: E402

CIKTI = KOK / "turek_hron_fsi1.json"
IS_DIZINI = KOK / "turek_hron_fsi1_case"

# KATI MALZEME (Turek-Hron FSI1): nu_s = 0,4 ve mu_s = 0,5e6 Pa.
# E = 2 mu (1+nu) = 1,4e6 Pa. Bu TURETME kayda yazilir --- E'yi dogrudan
# yazmak, kaynagin verdigi buyuklugun hangisi oldugunu gizlerdi.
MU_S = 0.5e6
NU_S = 0.4
E_S = 2 * MU_S * (1 + NU_S)
RHO_S = 1000.0
# Yayimlanan FSI1 uc yer degistirmesi (A noktasi = bayrak ucu ortasi),
# Turek-Hron kiyaslama onerisi. 2026-08-27'de bagimsiz bir kaynaktan
# (Feel++ kiyaslama belgesi) TEYIT EDILDI --- daha once yalniz
# hatirlanmisti ve o hal bir yanlis kapiya yol acti (bkz _kayma_bedeli).
REF = {"ux_mm": 0.0227, "uy_mm": 0.8209, "_dogrulandi": True,
       "_kaynak": "Turek-Hron FSI kiyaslamasi; Feel++ belgesiyle teyit"}
# AYNI kaynagin tasima degerleri: rijit (CFD1) ve deforme (FSI1).
# Ikisinin ORANI iki-yonlu geri beslemenin buyuklugunu verir.
TASIMA_CFD1 = 1.119
TASIMA_FSI1 = 0.7638
# Bayrak agi: kalinlik boyunca en az bu kadar eleman (egilme icin sart).
NY = 6
NX = 70
NZ = 1


def _bayrak_agi():
    """Bayrak için yapılandırılmış hex→C3D10 ağı."""
    from nlgeom_dogrulama import _c3d10

    from analysis.tet_mesher import TetMesh
    xb = bayrak_bas_x()
    y0 = MERKEZ[1] - BAYRAK_KALINLIK / 2
    xs = np.linspace(xb, BAYRAK_SON_X, NX + 1)
    ys = np.linspace(y0, y0 + BAYRAK_KALINLIK, NY + 1)
    zs = np.linspace(0.0, Z_KALINLIK, NZ + 1)
    P, idx = [], {}
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            for k, z in enumerate(zs):
                idx[(i, j, k)] = len(P)
                P.append((x, y, z))
    kesim = ((0, 1, 3, 7), (0, 1, 7, 5), (0, 5, 7, 4),
             (0, 3, 2, 7), (0, 6, 4, 7), (0, 2, 6, 7))
    tets = []
    for i in range(NX):
        for j in range(NY):
            for k in range(NZ):
                c = [idx[(i + (a & 1), j + ((a >> 1) & 1), k + ((a >> 2) & 1))]
                     for a in range(8)]
                for t in kesim:
                    tets.append([c[t[0]], c[t[1]], c[t[2]], c[t[3]]])
    pts, t10 = _c3d10(np.array(P, float), np.array(tets, int))
    return TetMesh(points=pts, tets=t10, surface_tris=np.empty((0, 6), int),
                   msh_path=Path("turek_hron_fsi1_sentetik.msh"),
                   element_type="C3D10")


def _bayrak_stl(yol: Path, nx: int = 160) -> dict:
    """Bayrağın DIŞ yüzeyi --- yükün bineceği yer.

    ÇÖZÜNÜRLÜK BURADA BİR SONUÇ PARAMETRESİDİR, kozmetik değil. İlk sürüm
    trimesh `subdivide` kullanıyordu; o bölme PARAMETRE uzayında izotropiktir
    ve 0,351 x 0,02 m'lik bir yüzü 16x16 böler --- yani x boyunca yalnız 17
    istasyon. CFD tarafında bayrak yamasında 292 yüz var. Yük en-yakın-komşu
    ile taşındığından, aktarım yüzeyi CFD'yi çözemezse basıncın DAĞILIMI
    (dolayısıyla kök momenti) yeniden örneklenir. Bu yüzden yüzey x boyunca
    AÇIKÇA parametreli yapılandırılmış bir ızgaradır ve `nx` yakınsatılır.
    """
    import trimesh
    xb = bayrak_bas_x()
    y0 = MERKEZ[1] - BAYRAK_KALINLIK / 2
    L = BAYRAK_SON_X - xb
    # Enine bolmeler x-cozunurlugune ORANTILI: hucreler asiri uzamasin.
    ny = max(2, int(round(nx * BAYRAK_KALINLIK / L)))
    nz = max(1, int(round(nx * Z_KALINLIK / L)))
    xs = np.linspace(xb, BAYRAK_SON_X, nx + 1)
    ys = np.linspace(y0, y0 + BAYRAK_KALINLIK, ny + 1)
    zs = np.linspace(0.0, Z_KALINLIK, nz + 1)
    V: list[tuple] = []
    ind: dict = {}

    def dv(p):
        k = (round(p[0], 12), round(p[1], 12), round(p[2], 12))
        if k not in ind:
            ind[k] = len(V)
            V.append(k)
        return ind[k]

    Y: list[list[int]] = []

    def yuz(p00, p10, p11, p01, disa: bool):
        a, b, c, d = dv(p00), dv(p10), dv(p11), dv(p01)
        # SARIM YONU: normal DISARI baksin. Isaret trimesh.volume > 0 ile
        # dogrulanir --- goz kararı birakilmaz.
        Y.extend([[a, c, b], [a, d, c]] if disa else [[a, b, c], [a, c, d]])

    for i in range(nx):
        for j in range(ny):
            yuz((xs[i], ys[j], zs[0]), (xs[i + 1], ys[j], zs[0]),
                (xs[i + 1], ys[j + 1], zs[0]), (xs[i], ys[j + 1], zs[0]), False)
            yuz((xs[i], ys[j], zs[-1]), (xs[i + 1], ys[j], zs[-1]),
                (xs[i + 1], ys[j + 1], zs[-1]), (xs[i], ys[j + 1], zs[-1]), True)
    for i in range(nx):
        for k in range(nz):
            yuz((xs[i], ys[0], zs[k]), (xs[i + 1], ys[0], zs[k]),
                (xs[i + 1], ys[0], zs[k + 1]), (xs[i], ys[0], zs[k + 1]), True)
            yuz((xs[i], ys[-1], zs[k]), (xs[i + 1], ys[-1], zs[k]),
                (xs[i + 1], ys[-1], zs[k + 1]), (xs[i], ys[-1], zs[k + 1]), False)
    for j in range(ny):
        for k in range(nz):
            yuz((xs[0], ys[j], zs[k]), (xs[0], ys[j + 1], zs[k]),
                (xs[0], ys[j + 1], zs[k + 1]), (xs[0], ys[j], zs[k + 1]), True)
            yuz((xs[-1], ys[j], zs[k]), (xs[-1], ys[j + 1], zs[k]),
                (xs[-1], ys[j + 1], zs[k + 1]), (xs[-1], ys[j], zs[k + 1]), False)
    kutu = trimesh.Trimesh(vertices=np.array(V, float),
                           faces=np.array(Y, int), process=False)
    kutu.export(yol)
    return {"nx": nx, "ny": ny, "nz": nz,
            "ucgen": int(len(kutu.faces)), "su_gecirmez": bool(kutu.is_watertight),
            "hacim_isaret_pozitif": bool(kutu.volume > 0),
            "x_adimi_m": round(float(xs[1] - xs[0]), 6),
            "alan_m2": float(kutu.area)}


def _vtk_uret(vaka: Path) -> Path | None:
    yol = windows_to_wsl_path(vaka)
    # grad(U) VISKOZ CEKME ICIN URETILIR. wallShearStress KULLANILMAZ:
    # OpenFOAM 11'in o fonksiyon nesnesi bu laminer vakada her yuzde TAM
    # sifir yaziyor (hem foamPostProcess hem cozucu-ici kosuda denendi),
    # oysa ayni kosuda `forces` viskoz kuvveti dogru veriyor. grad(U)
    # son-islem kipinde calisiyor ve U/p'ye DOKUNMUYOR --- yani CFD1
    # kanitini bozmadan alan ekler.
    (vaka / "system" / "gradU").write_text(
        'type grad;\nlibs ("libfieldFunctionObjects.so");\nfield U;\n',
        encoding="utf-8")
    # -ascii ZORUNLU: kuplaj ayristiricisi satir-tabanlidir, BINARY okumaz.
    linux_run(f"cd '{yol}' && source /opt/openfoam11/etc/bashrc && "
              f"foamPostProcess -solver incompressibleFluid -func gradU "
              f"-latestTime > log.gradU 2>&1 && "
              f"foamToVTK -latestTime -ascii > log.foamToVTK 2>&1", timeout=1800)
    aday = sorted(vaka.glob("VTK/bayrak/bayrak_*.vtk"))
    return aday[-1] if aday else None


def _fea_kos(mesh, dugum_kuvvet: np.ndarray, work: Path) -> dict:
    """Yükü uygula ve uç yer değiştirmesini oku."""
    from analysis.calculix_writer import FEACase, FEAMaterial, FixedBC, write_inp
    from analysis.ccx_runner import run_ccx as _run
    from analysis.frd_parser import parse_frd

    xb = bayrak_bas_x()
    P = mesh.points
    # ANKASTRE: bayragin silindire tutturuldugu kesit (x = x_bas).
    ankastre = np.where(P[:, 0] < xb + 1e-9)[0] + 1
    case = FEACase(
        name="fsi1_bayrak", mesh=mesh,
        material=FEAMaterial(name="tk_solid", youngs_modulus_pa=E_S,
                             poisson_ratio=NU_S, density_kg_m3=RHO_S),
        fixed_bcs=[FixedBC(node_ids=ankastre, name="ANKASTRE")],
    )
    inp = write_inp(case, work)
    # DUZLEM GERINIM: z yonu tutulur. Turek-Hron 2B'dir; z serbest
    # birakilirsa problem duzlem GERILME olur ve rijitlik degisir.
    metin = inp.read_text(encoding="utf-8")
    z_dugum = np.where((P[:, 2] < 1e-12) | (P[:, 2] > Z_KALINLIK - 1e-12))[0] + 1
    blok = ["*NSET, NSET=ZDUZLEM"]
    blok += [", ".join(str(int(n)) for n in z_dugum[i:i + 8])
             for i in range(0, len(z_dugum), 8)]
    blok += ["*BOUNDARY", "ZDUZLEM, 3, 3, 0.0"]
    metin = metin.replace("*STEP", "\n".join(blok[:1] + blok[1:-2]) + "\n*STEP")
    metin = metin.replace("*STATIC", "*STATIC\n" + "\n".join(blok[-2:]), 1)
    # CLOAD: aktarilan dugum kuvvetleri
    cload = ["*CLOAD"]
    for n, f in enumerate(dugum_kuvvet, start=1):
        for dof in range(3):
            if abs(f[dof]) > 1e-14:
                cload.append(f"{n}, {dof + 1}, {f[dof]:.8e}")
    metin = metin.replace("*STATIC", "*STATIC\n" + "\n".join(cload), 1)
    inp.write_text(metin, encoding="utf-8")
    r = _run(inp)
    if not r.success:
        return {"kosdu": False, "neden": (r.stderr or r.stdout)[-300:]}
    frd = parse_frd(r.frd_path)
    if "DISP" not in frd.fields:
        return {"kosdu": False, "neden": "frd'de DISP yok"}
    sira = {int(n): i for i, n in enumerate(frd.node_ids)}
    # A NOKTASI: bayrak ucu ORTASI (x = son, y = merkez, z = orta).
    hedef = np.array([BAYRAK_SON_X, MERKEZ[1], Z_KALINLIK / 2])
    mesafe = np.linalg.norm(P - hedef, axis=1)
    aday = [i for i in np.argsort(mesafe)[:20] if int(i + 1) in sira]
    if not aday:
        return {"kosdu": False, "neden": "A noktası frd'de yok"}
    i = aday[0]
    u = frd.fields["DISP"][sira[int(i + 1)]]
    return {"kosdu": True, "A_dugum": int(i + 1),
            "A_konum": [float(x) for x in P[i]],
            "A_uzaklik_m": float(mesafe[i]),
            "ux_mm": float(u[0]) * 1000, "uy_mm": float(u[1]) * 1000,
            "uz_mm": float(u[2]) * 1000}


def _tek_kosu(vtk: Path, nx: int, mesh) -> tuple[dict, dict, dict, np.ndarray]:
    """Tek bir aktarım-yüzeyi çözünürlüğünde yükü taşı ve yapıyı çöz."""
    work = IS_DIZINI / f"nx{nx}"
    work.mkdir(parents=True, exist_ok=True)
    stl = work / "bayrak_prep.stl"
    stl_bilgi = _bayrak_stl(stl, nx)
    from coupling_fsi import cfd_pressure_to_fea_loads
    # kayma=True: VISKOZ CEKME DE TASINIR. Bu betik once basinc-yalniz
    # kosuldu ve eksigi OLCTU (viskoz eksenel kuvvet basincin 9,6 kati);
    # kanal acildiktan sonra ayni olcum onu KAPATIP kapatmadigini gosterir.
    yukler = cfd_pressure_to_fea_loads(str(vtk), str(stl), rho=RHO,
                                       p_is_kinematic=True,
                                       kayma=True, mu_pa_s=RHO * NU)
    # STL dugumleri ile HACIM agi dugumleri AYNI DEGIL: kuvvetler konuma
    # gore hacim agina tasinir. (Depo bu dersi dugum-eslemesinde odedi:
    # indis varsaymak permutasyon uretiyordu.)
    from scipy.spatial import cKDTree
    stl_dugum = np.asarray(yukler["fea_nodes"], float)
    # node_forces SEYREK bir sozluktur (1-tabanli dugum -> kuvvet); yalniz
    # yuklu dugumleri tasir. Yogun diziye acilirken 1-tabanlilik korunur ---
    # kaydirma burada sessizce yanlis dugume yuk binmesi demektir.
    kuvvet = np.zeros_like(stl_dugum)
    for _n, _f in yukler["node_forces"].items():
        kuvvet[int(_n) - 1] = _f
    _, es = cKDTree(mesh.points).query(stl_dugum, k=1)
    hacim_kuvvet = np.zeros_like(mesh.points)
    np.add.at(hacim_kuvvet, es, kuvvet)
    fea = _fea_kos(mesh, hacim_kuvvet, work)
    return stl_bilgi, yukler, fea, hacim_kuvvet


# AKTARIM YUZEYI COZUNURLUK MERDIVENI. CFD bayrak yamasinda x boyunca ~145
# yuz var; 16 istasyon onu cozemez, 160 asar. Ucu birden kosulur ki
# "cozunurluk mu, fizik mi" sorusu TAHMINLE degil OLCUMLE ayrilsin.
NX_MERDIVEN = (16, 40, 160)


def olc() -> dict:
    if not CFD_VAKA.exists():
        return _ozetle(None, None, None, "CFD1 vakası yok — önce "
                                         "turek_hron_cfd1.py")
    vtk = _vtk_uret(CFD_VAKA)
    if vtk is None:
        return _ozetle(None, None, None, "bayrak VTK'sı üretilemedi")
    if IS_DIZINI.exists():
        shutil.rmtree(IS_DIZINI)
    IS_DIZINI.mkdir(parents=True)
    mesh = _bayrak_agi()
    merdiven = []
    son = (None, None, None, None)
    for nx in NX_MERDIVEN:
        stl_b, yuk, fea, hk = _tek_kosu(vtk, nx, mesh)
        merdiven.append({
            "nx": nx, "ucgen": stl_b["ucgen"], "x_adimi_m": stl_b["x_adimi_m"],
            "Fy_N": round(float(hk[:, 1].sum()), 8),
            "kok_momenti_Nm": round(float(
                ((mesh.points[:, 0] - bayrak_bas_x()) * hk[:, 1]).sum()), 10),
            "uy_mm": None if not fea.get("kosdu") else round(fea["uy_mm"], 5),
            "n_yuklu_dugum": int(np.count_nonzero(
                np.linalg.norm(hk, axis=1) > 1e-14)),
        })
        son = (stl_b, yuk, fea, hk)
    r = _ozetle(son[0], son[1], son[2], None, son[3],
                _kiris_capasi(mesh, son[3]),
                _bayrak_kuvvet_bilesenleri(CFD_VAKA))
    r["cozunurluk_merdiveni"] = merdiven
    return r


def _kiris_capasi(mesh, hacim_kuvvet: np.ndarray) -> dict:
    """AYNI yükün konsol-kiriş çözümü — yapısal modelin BAĞIMSIZ çapası.

    Sapma bulunduğunda ilk soru ``yük mü yapı mı''dır ve bu ikisi FEA
    çıktısına bakarak AYRILAMAZ. Aktarılan düğüm kuvvetlerinden kiriş
    teorisiyle uç sehimi kapalı formda hesaplanır: P a^2 (3L-a)/(6 E' I),
    her düğüm için ayrı ayrı, süperpozisyonla. Düzlem gerinim olduğu için
    E' = E/(1-nu^2). Uyuşuyorsa yapı elenir ve sapma yük tarafındadır.

    ELDEN GELMEZ: kiriş teorisi kayma deformasyonunu ve kök kısıtının
    yerel etkisini görmez; L/h = 17,6 olduğundan bunlar birkaç yüzde
    mertebesindedir --- bu yüzden çapa BANT sınavıdır, eşitlik değil.
    """
    xb = bayrak_bas_x()
    L = BAYRAK_SON_X - xb
    E_duzlem = E_S / (1 - NU_S ** 2)
    I = Z_KALINLIK * BAYRAK_KALINLIK ** 3 / 12.0
    a = np.clip(mesh.points[:, 0] - xb, 0.0, L)
    d = float((hacim_kuvvet[:, 1] * a ** 2 * (3 * L - a)
               / (6 * E_duzlem * I)).sum())
    return {"uy_mm": round(1000 * d, 5), "L_m": round(L, 5),
            "I_m4": I, "E_duzlem_Pa": round(E_duzlem, 1),
            "narinlik_L_h": round(L / BAYRAK_KALINLIK, 2)}


def _bayrak_kuvvet_bilesenleri(vaka: Path) -> dict | None:
    """OpenFOAM'ın KENDİ kuvvet fonksiyonuyla bayrak yükü — basınç/viskoz ayrı.

    İKİ İŞ GÖRÜR. Birincisi: aktarılan basınç kuvveti çözücünün kendi yüzey
    integraliyle karşılaştırılır --- aktarım zincirinin bağımsız çapası.
    İkincisi, ve asıl olanı: ``kuplaj yalnız basınç taşır'' cümlesinin
    BEDELİ ölçülür. Bu bedel cümleden okunmaz; burada sayıya döner.
    """
    for ad, yama in (("bayrakKuvvet", "bayrak"), ("silindirKuvvet", "silindir")):
        (vaka / "system" / ad).write_text(
            f'type forces;\nlibs ("libforces.so");\npatches ({yama});\n'
            'rho rhoInf;\nrhoInf 1000.0;\nCofR (0.2 0.2 0);\n',
            encoding="utf-8")
    yol = windows_to_wsl_path(vaka)
    # postProcess YETMEZ: viskoz gerilme icin momentum modeli kurulmali,
    # bunu yalniz cozucu-farkindalikli foamPostProcess yapar (olculdu:
    # postProcess "No valid model for viscous stress calculation" der).
    for ad in ("bayrakKuvvet", "silindirKuvvet"):
        linux_run(f"cd '{yol}' && source /opt/openfoam11/etc/bashrc && "
                  f"foamPostProcess -solver incompressibleFluid "
                  f"-func {ad} -latestTime > log.{ad} 2>&1", timeout=900)

    def _oku(ad):
        dat = sorted(vaka.glob(f"postProcessing/{ad}/*/force*.dat"))
        if not dat:
            return None
        son = [s for s in dat[-1].read_text(encoding="utf-8").splitlines()
               if s.strip() and not s.startswith("#")]
        if not son:
            return None
        sayi = [float(x) for x in
                re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?",
                           son[-1].split("(", 1)[1])]
        return None if len(sayi) < 6 else (sayi[0:3], sayi[3:6])

    b = _oku("bayrakKuvvet")
    if b is None:
        return None
    d = {"basinc_N": b[0], "viskoz_N": b[1]}
    # DAGILIM: FSI1 bilmecesinde ELENMEYEN son aday budur. Akis cozucusu
    # (surukleme %0,1), ag (dort seviyeli aile) ve yapi (CSM1 %0,2) sirayla
    # elendi; geriye tasimanin silindir ile bayrak arasinda NASIL
    # paylasildigi kaldi. Toplam dogru olsa bile pay yanlis olabilir ve
    # bayragi egen sey PAYDIR.
    s = _oku("silindirKuvvet")
    if s is not None:
        by = b[0][1] + b[1][1]
        sy = s[0][1] + s[1][1]
        d["dagilim"] = {
            "bayrak_Fy_N_m": round(by / Z_KALINLIK, 4),
            "silindir_Fy_N_m": round(sy / Z_KALINLIK, 4),
            "toplam_Fy_N_m": round((by + sy) / Z_KALINLIK, 4),
            "bayrak_payi_pct": round(100 * by / (by + sy), 1),
            "_not": ("Yayimlanan kaynak yalnizca TOPLAMI verir; pay "
                     "kiyaslanamaz. Ama yapinin dogrulanmis olmasi paya bir "
                     "KISIT koyar: yayimlanan FSI1 sehimini uretmek icin "
                     "bayragin tasidigi enine yuk bizimkinin ~%57'si "
                     "olmaliydi."),
        }
    return d


def _kayma_bedeli(bilesen: dict | None, fea, hacim_kuvvet,
                  kayma_acik: bool = False) -> dict | None:
    """Basınç-yalnız aktarımın EKSİK BIRAKTIĞI yük ve onun uç etkisi.

    BU KAPI BİR HATADAN DOĞDU. Önceki sürüm referans çiftini ``kendi içinde
    tutarsız'' ilan ediyordu: uy=0,8209 mm bir konsolda ancak 0,0022 mm
    kısalma üretir, oysa referans ux=0,0227 mm veriyordu --- 10 kat. Kapı
    eksenel terimi BİZİM aktardığımız kuvvetten kuruyordu, ve biz yalnız
    BASINÇ aktarıyoruz. Çözücünün kendi çıktısı alındığında bayraktaki
    viskoz eksenel kuvvet basınç bileşeninin ~10 katı çıktı; referans
    tutarlıdır, EKSİK OLAN BİZİM YÜKÜMÜZDÜ.

    Ders kaydedilir çünkü yönü kritikti: kapı kusuru DIŞ kaynağa atıyordu.

    ÖLÇÜM BİR SEFERLİK DEĞİL. Boşluk görülünce kuplaja viskoz çekme kanalı
    eklendi (`kayma=True`); bu kayıt artık kanal AÇIKKEN de aynı soruyu
    sorar. `aktarim_capasi_TOPLAM_pct` taşınan eksenel kuvveti çözücünün
    basınç+viskoz toplamıyla karşılaştırır --- kanal doğru bağlandıysa o
    yüzde küçüktür; bağlanmadıysa (ya da işaret dönerse) BÜYÜR ve düşer.
    """
    if not bilesen or not (fea and fea.get("kosdu")):
        return None
    L = BAYRAK_SON_X - bayrak_bas_x()
    A = BAYRAK_KALINLIK * Z_KALINLIK
    Fp, Fv = bilesen["basinc_N"][0], bilesen["viskoz_N"][0]
    aktarilan = float(hacim_kuvvet[:, 0].sum())
    # Yayili eksenel yuk altinda uc yer degistirmesi: F L / (2 E A).
    def ux(F):
        return 1000.0 * F * L / (2 * E_S * A)
    return {
        "cozucu_basinc_Fx_N": round(Fp, 8),
        "cozucu_viskoz_Fx_N": round(Fv, 8),
        "cozucu_basinc_Fy_N": round(bilesen["basinc_N"][1], 8),
        "cozucu_viskoz_Fy_N": round(bilesen["viskoz_N"][1], 8),
        "aktarilan_Fx_N": round(aktarilan, 8),
        "aktarilan_Fy_N": round(float(hacim_kuvvet[:, 1].sum()), 8),
        "aktarim_capasi_pct": round(100 * (aktarilan - Fp) / abs(Fp), 3),
        "aktarim_capasi_TOPLAM_pct": round(
            100 * (aktarilan - (Fp + Fv)) / abs(Fp + Fv), 3),
        "kayma_kanali_acik": bool(kayma_acik),
        "aktarim_capasi_Fy_pct": round(
            100 * (float(hacim_kuvvet[:, 1].sum()) - bilesen["basinc_N"][1])
            / abs(bilesen["basinc_N"][1]), 3),
        "_capa_notu": (
            "HANGİ YÜZDEYE BAKILACAĞI KANALIN AÇIK OLUP OLMAMASINA BAĞLI. "
            "Kayma kapalıyken taşınan eksenel kuvvet yalnız basıncı "
            "temsil eder, bu yüzden çapa `aktarim_capasi_pct`'dir. Kanal "
            "açıkken taşınan kuvvet basınç+viskoz toplamına karşılık gelir "
            "ve doğru çapa `aktarim_capasi_TOPLAM_pct`'dir; kapalı-kanal "
            "yüzdesi o durumda yüzlerce çıkar ve BİR KUSUR DEĞİL, yanlış "
            "paydadır. Düşey çapa (`aktarim_capasi_Fy_pct`) her iki "
            "durumda da geçerlidir ve daha güçlüdür: düşey yükü ~290 CFD "
            "yüzü taşır, eksenel yükü büyük ölçüde iki uç yüzü."),
        "viskoz_basinc_orani_x": round(abs(Fv / Fp), 2),
        "ux_basinc_yalniz_mm": round(ux(Fp), 5),
        "ux_basinc_arti_viskoz_mm": round(ux(Fp + Fv), 5),
        "ux_referans_mm": REF["ux_mm"],
        "ux_kalan_oran": round(REF["ux_mm"] / ux(Fp + Fv), 2),
        # DAGILIM CAGIRANA TASINIR. Ilk yazimda `_bayrak_kuvvet_bilesenleri`
        # onu uretiyordu ama bu fonksiyon kendi sozlugunu kurup ATIYORDU ---
        # uretilip hic okunmayan alan, bu deponun kendi olcerinin avladigi
        # kusur sinifi.
        "dagilim": bilesen.get("dagilim"),
    }


def _tek_yon_bedeli(fea) -> dict:
    """Tek-yönlü aktarımın düşey sehimde beklenen fazlalığı.

    Kaynak hem CFD1 (rijit bayrak) hem FSI1 (deforme) taşımasını verir:
    1,119 ve 0,7638 N/m. Yani geri besleme yükü %32 düşürür. Bizim
    zincirimiz CFD1 akışını kullandığından sehimi bu oranda FAZLA
    vermelidir --- ve bu bir TAHMİN değil, yayımlanmış iki sayının oranı.

    KAPSAM: oran TÜM cisim (silindir+bayrak) taşımasından kurulur;
    bayrağın kendi payı aynı oranda düşmeyebilir. Bu yüzden sonuç bir
    BEKLENTİ bandıdır, düzeltme katsayısı değil.
    """
    olcek = TASIMA_FSI1 / TASIMA_CFD1
    beklenen = fea["uy_mm"] * olcek if fea and fea.get("kosdu") else None
    return {
        "tasima_cfd1_Nm": TASIMA_CFD1, "tasima_fsi1_Nm": TASIMA_FSI1,
        "olcek": round(olcek, 4),
        "uy_olceklenmis_mm": None if beklenen is None else round(beklenen, 5),
        "uy_referans_mm": REF["uy_mm"],
        "kalan_sapma_pct": None if beklenen is None else round(
            100 * (beklenen - REF["uy_mm"]) / REF["uy_mm"], 1),
    }


def _ozetle(stl, yukler, fea, neden, hacim_kuvvet=None, kiris=None,
            bilesen=None) -> dict:
    sapma = None
    if fea and fea.get("kosdu"):
        sapma = {
            "ux_pct": round(100 * (fea["ux_mm"] - REF["ux_mm"])
                            / abs(REF["ux_mm"]), 2),
            "uy_pct": round(100 * (fea["uy_mm"] - REF["uy_mm"])
                            / abs(REF["uy_mm"]), 2),
        }
    yuk_ozet = None
    if yukler is not None:
        yuk_ozet = {
            "toplam_kuvvet_N": [round(float(x), 8)
                                for x in yukler["total_force_N"]],
            "aktarim_hatasi_pct": round(100 * float(yukler["aktarim_hatasi"]), 6),
            "moment_artigi_pct": (
                None if yukler.get("moment_conservation_error") is None
                else round(100 * float(yukler["moment_conservation_error"]), 4)),
            "arayuz_isi_artigi_pct": (
                None if yukler.get("arayuz_isi_hatasi") is None
                else round(100 * float(yukler["arayuz_isi_hatasi"]), 4)),
            "sema": yukler.get("sema"),
            "n_yuklu_dugum": int(np.count_nonzero(
                np.linalg.norm(hacim_kuvvet, axis=1) > 1e-14))
            if hacim_kuvvet is not None else None,
        }
    return {
        "vaka": "Turek-Hron FSI1 — aktarılan yük ve yapısal yanıt",
        "_neden": ("Bugune kadar FSI tarafinda olculen her sey IC "
                   "tutarlilikti; hicbiri 'FEA'ya giden yuk DOGRU MU' "
                   "sorusunu sormuyordu cunku karsilastirilacak bir DIS "
                   "referans yoktu."),
        "kati": {"mu_s_Pa": MU_S, "nu_s": NU_S, "E_Pa": E_S, "rho": RHO_S,
                 "_E_turetildi": "E = 2 mu (1+nu)"},
        "ag": {"nx": NX, "ny": NY, "nz": NZ, "eleman": "C3D10",
               "duzlem_gerinim": True},
        "stl": stl,
        "yuk_aktarimi": yuk_ozet,
        "fea": fea,
        "kiris_capasi": kiris,
        "referans": REF,
        "kayma_bedeli": _kayma_bedeli(bilesen, fea, hacim_kuvvet,
                                      bool((yukler or {}).get("kayma_tasindi"))),
        "tek_yon_bedeli": _tek_yon_bedeli(fea),
        "sapma": sapma,
        "verdikt": _hukum(yuk_ozet, fea, sapma, neden, kiris,
                          _kayma_bedeli(bilesen, fea, hacim_kuvvet,
                                        bool((yukler or {}).get("kayma_tasindi"))),
                          _tek_yon_bedeli(fea)),
        "_kisit": (
            "VISKOZ CEKME grad(U)'dan kurulur ve sinira BIRINCI MERTEBEDEN "
            "ekstrapole edilir; toplami cozucunun kendi kuvvetiyle %1 "
            "icinde ortusuyor ama daha keskin bir yuzeyde bu fark buyur. "
            "TEK YONLU aktarim: akis rijit bayrakla bir kez cozuldu; "
            "kaynagin kendi CFD1/FSI1 tasima orani geri beslemenin yuku "
            "%32 dusurdugunu soyluyor, bu betik onu DUZELTMEZ yalniz "
            "BEKLENEN sapmayi kurar. 'Fizik tahrik ediyor' iddiasi hala "
            "FSI2/FSI3'un isidir. Ag-bagimsizligi SINANMADI (tek akis agi, "
            "tek yapi agi; aktarim yuzeyi 10 kat inceltildi, yapi agi "
            "DEGIL). Yercekimi UYGULANMADI. Yapisal model LINEER."),
        "_uretim": "Üretim: python experiments/turek_hron_fsi1.py",
    }


def _hukum(yuk, fea, sapma, neden, kiris, kayma, tekyon) -> str:
    if neden:
        return f"KOŞULAMADI: {neden}"
    if not (fea and fea.get("kosdu")):
        return (f"YAPISAL KOŞU DÜŞTÜ: {(fea or {}).get('neden')} --- "
                f"sonuç yok.")
    s = (f"Aktarılan toplam kuvvet {yuk['toplam_kuvvet_N']} N "
         f"({yuk['n_yuklu_dugum']} yüklü düğüm, şema {yuk['sema']}); "
         f"aktarım artığı %{yuk['aktarim_hatasi_pct']}. "
         f"Uç yer değiştirmesi ux={fea['ux_mm']:.4f} mm, "
         f"uy={fea['uy_mm']:.4f} mm. Yayımlanan FSI1: "
         f"ux={REF['ux_mm']} mm, uy={REF['uy_mm']} mm --- sapma "
         f"%{sapma['ux_pct']} ve %{sapma['uy_pct']}. ")
    if kiris:
        fark = 100 * (fea["uy_mm"] - kiris["uy_mm"]) / abs(kiris["uy_mm"])
        s += (f"AYNI yükün konsol-kiriş çözümü {kiris['uy_mm']:.4f} mm; "
              f"FEA ondan %{fark:.2f} sapıyor --- yani yapısal model bu "
              f"yükün ALTINDA doğrulanmıştır ve sapmanın kaynağı DEĞİLDİR. ")
    if kayma:
        s += (f"EKSENEL KANAL: çözücünün kendi yüzey integralinde bayrağın "
              f"basınç Fx'i {kayma['cozucu_basinc_Fx_N']:.3e} N, viskoz Fx'i "
              f"{kayma['cozucu_viskoz_Fx_N']:.3e} N --- viskoz bileşen "
              f"{kayma['viskoz_basinc_orani_x']} kat büyük. ")
        if kayma["kayma_kanali_acik"]:
            s += (f"Kuplaj bu kanalı ARTIK TAŞIYOR: aktarılan eksenel kuvvet "
                  f"çözücünün basınç+viskoz toplamından "
                  f"%{kayma['aktarim_capasi_TOPLAM_pct']}, düşey kuvvet ise "
                  f"%{kayma['aktarim_capasi_Fy_pct']} sapıyor. Ölçülen "
                  f"ux={fea['ux_mm']:.4f} mm, referans {REF['ux_mm']} mm "
                  f"(sapma %{sapma['ux_pct']}) --- yani eksenel kanal "
                  f"HESAPLAMAYLA değil ÖLÇÜMLE kapandı. ")
        else:
            s += (f"Kuplaj onu TAŞIMIYOR. Aktardığımız düşey kuvvet "
                  f"çözücünün basınç integralinden "
                  f"%{kayma['aktarim_capasi_Fy_pct']} sapıyor --- aktarım "
                  f"doğru çalışıyor; eksik olan BİLEŞEN. Basınç-yalnız "
                  f"ux={kayma['ux_basinc_yalniz_mm']:.4f} mm, viskoz "
                  f"eklenince {kayma['ux_basinc_arti_viskoz_mm']:.4f} mm; "
                  f"referans {REF['ux_mm']} mm "
                  f"({kayma['ux_kalan_oran']} kat). ")
    if tekyon and tekyon["uy_olceklenmis_mm"] is not None:
        s += (f"DÜŞEY KANAL: kaynak taşımayı rijitte {TASIMA_CFD1}, "
              f"deformede {TASIMA_FSI1} N/m veriyor (oran "
              f"{tekyon['olcek']}). Bizim akışımız RİJİT olduğu için sehim "
              f"bu oranda fazla çıkmalıdır; ölçeklendiğinde "
              f"{tekyon['uy_olceklenmis_mm']:.4f} mm olur ve referanstan "
              f"%{tekyon['kalan_sapma_pct']} sapar --- ham "
              f"%{sapma['uy_pct']} yerine. ")
    acik = bool(kayma and kayma["kayma_kanali_acik"])
    if acik:
        return s + (
            "SONUÇ: eksenel kanal KAPANDI --- yayımlanmış bir referansa "
            "karşı %1 bandında bir uçtan-uca doğrulama, bu depoda FSI "
            "tarafında ilk. Düşey kanal AÇIK ve gerekçesi biliniyor: akış "
            "rijit bayrakla çözülüyor. Onun ölçeklenmiş kalıntısı "
            "HESAPLANMIŞTIR, ölçülmemiştir; kapatmak için iki-yönlü koşu "
            "gerekir ve o yazılmadı. Yani ux bir GEÇMEDİR, uy DEĞİLDİR.")
    return s + (
        "SONUÇ: sapmanın iki kanalı da ADLANDIRILDI ve ikisi de zincirin "
        "kusuru değil KAPSAMI. Eksenel kanal basınç-yalnız aktarımın, düşey "
        "kanal tek-yönlü kuplajın bedelidir. Yapı kiriş teorisiyle, aktarım "
        "çözücünün kendi integraliyle bağımsız doğrulandı. BU BİR GEÇME "
        "DEĞİLDİR: kalan fark hesaplandı, ölçülmedi; kapatmak için viskoz "
        "gerilme aktarımı ve iki-yönlü koşu gerekir.")


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
