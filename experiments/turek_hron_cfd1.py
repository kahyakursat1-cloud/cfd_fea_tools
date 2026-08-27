"""Turek--Hron CFD1 — akış çözülür ve YAYIMLANMIŞ bir referansa bakılır.

NEREDE DURUYORUZ. Geometri kuruldu ve doğrulandı, ağ kuruldu ve kapıyı
geçti (33.168 hücre, 2B, `checkMesh` OK). Ama ``ağ hazır'' ile ``çapa
koşuldu'' arasında bir adım daha var: akış.

CFD1 SEÇİLDİ, FSI1 DEĞİL --- ve sırası bu. CFD1 aynı geometride RİJİT
bayrakla kararlı akıştır; yapısal taraf hiç girmez. Kapatmadığı şey açık:
kuplajı sınamaz. Kapattığı şey ise FSI1'in ÖNKOŞULU --- akış tarafı yanlışsa
kuplaj doğru olamaz ve o hatayı kuplajda aramak saatler yer.

KOŞUL (Turek \\& Hron 2006, CFD1):
    rho = 1000 kg/m^3,  nu = 1e-3 m^2/s,  U_ort = 0,2 m/s
    Re = U_ort * D / nu = 0,2 * 0,1 / 1e-3 = 20   -> LAMINER
    giriş profili  u(y) = 1,5 * U_ort * y (H-y) / (H/2)^2

REFERANS DEĞERLER BU DEPODA BİRİNCİL KAYNAKTAN DOĞRULANMADI. Yayımlanan
sürükleme ve taşıma değerleri karşılaştırma için YAZILIR ama bir çapa
hükmüne temel yapılmadan önce teyit edilmelidir --- bu, ölçümün değil
kaydın kısıtıdır ve kayda geçer.

    python experiments/turek_hron_cfd1.py
Çıktı: turek_hron_cfd1.json
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

from turek_hron_ag import KANAL_H, MERKEZ, YARICAP, Z_KALINLIK  # noqa: E402
from turek_hron_gmsh import MSH  # noqa: E402
from turek_hron_gmsh import VAKA as AG_VAKA

from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import windows_to_wsl_path  # noqa: E402

CIKTI = KOK / "turek_hron_cfd1.json"
VAKA = KOK / "turek_hron_cfd1_case"

RHO = 1000.0
NU = 1.0e-3
U_ORT = 0.2
CAP = 2 * YARICAP
RE = U_ORT * CAP / NU
ITER = 3000
# Yayimlanan CFD1 degerleri --- KARSILASTIRMA icin, hukum icin DEGIL.
# Bu depoda BIRINCIL KAYNAKTAN DOGRULANMADI.
REF = {"surukleme_N": 14.29, "tasima_N": 1.119, "_dogrulandi": False}
# Yakinsama: rezidueller bu esigin altina inmeli (deponun kendi olcutu).
REZ_ESIGI = 1e-5


def _hdr(cls: str, obj: str, loc: str) -> str:
    return ("FoamFile\n{\n    version 2.0;\n    format ascii;\n"
            f"    class {cls};\n    location \"{loc}\";\n"
            f"    object {obj};\n}}\n")


def _U_alan() -> str:
    """Giriş profili PARABOLİK --- düz profil YANLIŞ referans verir.

    Turek-Hron kanal akisidir ve referans degerler PARABOLIK girise aittir.
    Duz (uniform) giris ayni ortalama hizla farkli bir kuvvet uretir; bu
    fark kucuk degildir ve sessizdir --- sonuc yine "makul" gorunur.
    """
    return (_hdr("volVectorField", "U", "0")
            + "dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (0 0 0);\n"
            + "boundaryField\n{\n"
            + "  giris\n  {\n    type codedFixedValue;\n"
            + "    value uniform (0 0 0);\n    name parabolikGiris;\n"
            + "    code\n    #{\n"
            + "      const fvPatch& p = patch();\n"
            + f"      const scalar H = {KANAL_H};\n"
            + f"      const scalar Um = {U_ORT};\n"
            + "      vectorField v(p.size(), vector::zero);\n"
            + "      forAll(p, i)\n      {\n"
            + "        const scalar y = p.Cf()[i].y();\n"
            + "        v[i] = vector(1.5*Um*y*(H-y)/((H/2)*(H/2)), 0, 0);\n"
            + "      }\n      operator==(v);\n    #};\n  }\n"
            + "  cikis { type zeroGradient; }\n"
            + "  ust { type noSlip; }\n  alt { type noSlip; }\n"
            + "  govde { type noSlip; }\n  yanlar { type empty; }\n}\n")


def _p_alan() -> str:
    return (_hdr("volScalarField", "p", "0")
            + "dimensions [0 2 -2 0 0 0 0];\ninternalField uniform 0;\n"
            + "boundaryField\n{\n  giris { type zeroGradient; }\n"
            + "  cikis { type fixedValue; value uniform 0; }\n"
            + "  ust { type zeroGradient; }\n  alt { type zeroGradient; }\n"
            + "  govde { type zeroGradient; }\n  yanlar { type empty; }\n}\n")


def _kur(vaka: Path) -> None:
    if vaka.exists():
        shutil.rmtree(vaka)
    (vaka / "system").mkdir(parents=True)
    (vaka / "0").mkdir()
    (vaka / "constant").mkdir()
    shutil.copy(MSH, vaka / "turek_hron_2b.msh")
    (vaka / "0" / "U").write_text(_U_alan(), encoding="utf-8")
    (vaka / "0" / "p").write_text(_p_alan(), encoding="utf-8")
    (vaka / "constant" / "physicalProperties").write_text(
        _hdr("dictionary", "physicalProperties", "constant")
        + f"viscosityModel constant;\nnu [0 2 -1 0 0 0 0] {NU};\n",
        encoding="utf-8")
    (vaka / "constant" / "momentumTransport").write_text(
        _hdr("dictionary", "momentumTransport", "constant")
        # LAMINER: Re=20. Turbulans modeli acmak, olmayan bir viskoziteyi
        # eklemek ve referanstan sapmak demektir.
        + "simulationType laminar;\n", encoding="utf-8")
    (vaka / "system" / "controlDict").write_text(
        _hdr("dictionary", "controlDict", "system")
        + "application simpleFoam;\nstartFrom startTime;\nstartTime 0;\n"
        + f"stopAt endTime;\nendTime {ITER};\ndeltaT 1;\n"
        + "writeControl timeStep;\nwriteInterval 500;\npurgeWrite 2;\n"
        + "functions\n{\n  kuvvetler\n  {\n    type forces;\n"
        + "    libs (\"libforces.so\");\n    patches (govde);\n"
        + f"    rho rhoInf;\n    rhoInf {RHO};\n"
        + f"    CofR ({MERKEZ[0]} {MERKEZ[1]} 0);\n"
        + "    writeControl timeStep;\n    writeInterval 10;\n  }\n}\n",
        encoding="utf-8")
    (vaka / "system" / "fvSchemes").write_text(
        _hdr("dictionary", "fvSchemes", "system")
        + "ddtSchemes { default steadyState; }\n"
        + "gradSchemes { default Gauss linear; }\n"
        + "divSchemes\n{\n  default none;\n"
        + "  div(phi,U) bounded Gauss linearUpwind grad(U);\n"
        + "  div((nuEff*dev2(T(grad(U))))) Gauss linear;\n}\n"
        + "laplacianSchemes { default Gauss linear corrected; }\n"
        + "interpolationSchemes { default linear; }\n"
        + "snGradSchemes { default corrected; }\n", encoding="utf-8")
    (vaka / "system" / "fvSolution").write_text(
        _hdr("dictionary", "fvSolution", "system")
        + "solvers\n{\n"
        + "  p { solver GAMG; tolerance 1e-9; relTol 0.01;\n"
        + "      smoother GaussSeidel; }\n"
        + "  U { solver smoothSolver; smoother symGaussSeidel;\n"
        + "      tolerance 1e-9; relTol 0.1; }\n}\n"
        + "SIMPLE\n{\n  nNonOrthogonalCorrectors 1;\n  consistent yes;\n"
        + "  residualControl { p 1e-6; U 1e-6; }\n}\n"
        + "relaxationFactors { equations { U 0.9; \"(p|pFinal)\" 0.9; } }\n",
        encoding="utf-8")


def _kos(vaka: Path, komut: str, tmo: int = 3600) -> dict:
    yol = windows_to_wsl_path(vaka)
    r = linux_run(f"cd '{yol}' && source /opt/openfoam11/etc/bashrc && {komut}",
                  timeout=tmo)
    kuyruk = (r.stdout or "")[-400:] + (r.stderr or "")[-300:]
    m = re.search(r">\s*(log\.\S+)", komut)
    if m and (vaka / m.group(1)).exists():
        metin = (vaka / m.group(1)).read_text(errors="replace")
        hata = re.search(r"-->\s*FOAM FATAL(?: ERROR| IO ERROR)?:(.{0,600})",
                         metin, re.S)
        kuyruk = (hata.group(0) if hata else metin[-700:]).strip()
    return {"komut": komut, "rc": r.returncode, "kuyruk": kuyruk[:900]}


def _kuvvet_oku(vaka: Path) -> dict:
    """forces functionObject çıktısından SON kuvvet ve KUYRUK BANDI.

    Son satiri tek basina almak, yakinsamamis bir kosuda salinimin
    neresinde durulduguna baglidir --- bu depo o dersi vehicle_pipeline'da
    ogrendi. Kuyruk ortalamasi ve bandi birlikte verilir.
    """
    aday = list(vaka.glob("postProcessing/kuvvetler/*/force*.dat"))
    if not aday:
        return {"okundu": False, "neden": "force.dat yok"}
    satirlar = [ln for ln in aday[0].read_text(errors="replace").splitlines()
                if ln.strip() and not ln.startswith("#")]
    if not satirlar:
        return {"okundu": False, "neden": "force.dat boş"}
    fx, fy = [], []
    for ln in satirlar:
        s = re.findall(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?", ln)
        if len(s) >= 7:
            # zaman, sonra (toplam) (basinc) (viskoz) uclu vektorler
            fx.append(float(s[1]) + float(s[4]))
            fy.append(float(s[2]) + float(s[5]))
    if not fx:
        return {"okundu": False, "neden": "kuvvet sütunu ayrıştırılamadı",
                "ornek": satirlar[-1][:200]}
    n = max(len(fx) // 10, 3)
    ham_fx, ham_fy = sum(fx[-n:]) / n, sum(fy[-n:]) / n
    # BIRIM DERINLIGE NORMALIZE --- BIRIM TUZAGI VE SESSIZDIR.
    #
    # 2B vakada z kalinligi KEYFI bir modelleme secimidir (burada 0,01 m).
    # Cozucunun verdigi kuvvet O DILIME aittir; Turek-Hron'un yayimladigi
    # degerler ise BIRIM DERINLIK basinadir. Normalize edilmezse sonuc tam
    # olarak kalinlik carpani kadar yanlis cikar ve "fizik yanlis" gibi
    # gorunur: olculdu, surukleme 0,1428 N ve referans 14,29 --- %-99,0
    # sapma, yani 100 kat, yani TAM OLARAK 1/0,01. Normalize edilince
    # %-0,07 kaldi.
    olcek = 1.0 / Z_KALINLIK
    return {"okundu": True, "n_kayit": len(fx),
            "z_kalinlik_m": Z_KALINLIK, "birim_derinlik_olcegi": olcek,
            "ham_surukleme_N": ham_fx, "ham_tasima_N": ham_fy,
            "surukleme_N": ham_fx * olcek, "tasima_N": ham_fy * olcek,
            "surukleme_band_N": (max(fx[-n:]) - min(fx[-n:])) / 2 * olcek,
            "tasima_band_N": (max(fy[-n:]) - min(fy[-n:])) / 2 * olcek,
            "kuyruk_ornek": n,
            "_birim": "N/m (birim derinlik) --- ham deger z dilimine aitti"}


def _rezidueller(vaka: Path) -> dict:
    log = vaka / "log.simpleFoam"
    if not log.exists():
        return {"okundu": False}
    t = log.read_text(errors="replace")
    son = {}
    for alan in ("Ux", "Uy", "p"):
        m = re.findall(rf"Solving for {alan}, Initial residual = ([\d.eE+-]+)", t)
        if m:
            son[alan] = float(m[-1])
    return {"okundu": bool(son), "son": son,
            "yakinsadi": bool(son) and all(v < REZ_ESIGI for v in son.values()),
            "iterasyon": len(re.findall(r"^Time = ", t, re.M))}


def olc() -> dict:
    if not MSH.exists():
        return _ozetle([], None, None, "turek_hron_2b.msh yok — önce "
                                       "turek_hron_gmsh.py")
    _kur(VAKA)
    adimlar = [_kos(VAKA, "gmshToFoam turek_hron_2b.msh > log.gmshToFoam 2>&1")]
    if adimlar[-1]["rc"] == 0:
        # `yanlar` yamasini empty yap --- ag yolundaki ayni duzeltme.
        b = VAKA / "constant" / "polyMesh" / "boundary"
        b.write_text(re.sub(r"(yanlar\s*\{[^}]*?type\s+)\w+;", r"\1empty;",
                            b.read_text(errors="replace"), flags=re.S),
                     encoding="utf-8")
        adimlar.append(_kos(VAKA, "simpleFoam > log.simpleFoam 2>&1", tmo=5400))
    kuvvet = _kuvvet_oku(VAKA) if adimlar[-1]["rc"] == 0 else None
    rez = _rezidueller(VAKA)
    return _ozetle(adimlar, kuvvet, rez, None)


def _ozetle(adimlar, kuvvet, rez, neden) -> dict:
    sapma = None
    if kuvvet and kuvvet.get("okundu"):
        sapma = {
            "surukleme_pct": round(100 * (kuvvet["surukleme_N"]
                                          - REF["surukleme_N"])
                                   / REF["surukleme_N"], 2),
            "tasima_pct": round(100 * (kuvvet["tasima_N"] - REF["tasima_N"])
                                / REF["tasima_N"], 2),
        }
    return {
        "vaka": "Turek-Hron CFD1 — rijit bayrak, kararlı, Re=20",
        "_neden": ("'Ag hazir' ile 'capa kosuldu' arasinda akis adimi var. "
                   "CFD1 kuplaji SINAMAZ ama FSI1'in ONKOSULUDUR: akis "
                   "tarafi yanlissa kuplaj dogru olamaz ve o hatayi "
                   "kuplajda aramak saatler yer."),
        "kosul": {"rho": RHO, "nu": NU, "U_ort": U_ORT, "D": CAP,
                  "Re": RE, "giris": "parabolik", "model": "laminer",
                  "iterasyon_tavani": ITER},
        "referans": REF,
        "adimlar": adimlar,
        "kuvvet": kuvvet,
        "rezidueller": rez,
        "sapma": sapma,
        "verdikt": _hukum(adimlar, kuvvet, rez, sapma, neden),
        "_kisit": (
            "REFERANS DEGERLER BU DEPODA BIRINCIL KAYNAKTAN DOGRULANMADI; "
            "karsilastirma icin yazildilar ve bir CAPA HUKMUNE temel "
            "yapilmadan once teyit edilmelidir. Ayrica AG-BAGIMSIZLIGI "
            "SINANMADI --- tek ag, tek cozunurluk; sapmanin ne kadari "
            "ayriklastirmadan geldigi BILINMIYOR. CFD1 kuplaji sinamaz."),
        "_uretim": "Üretim: python experiments/turek_hron_cfd1.py",
    }


def _hukum(adimlar, kuvvet, rez, sapma, neden) -> str:
    if neden:
        return f"KOŞULAMADI: {neden}"
    dusen = [a for a in adimlar if a["rc"] != 0]
    if dusen:
        return (f"ADIM DÜŞTÜ ({dusen[-1]['komut']}): "
                f"{dusen[-1]['kuyruk'][:300]}")
    if not (kuvvet and kuvvet.get("okundu")):
        return (f"AKIŞ KOŞTU ama KUVVET OKUNAMADI: "
                f"{(kuvvet or {}).get('neden')} --- sonuç yok.")
    s = (f"{rez.get('iterasyon')} iterasyon, son rezidüeller "
         f"{rez.get('son')}. Sürükleme {kuvvet['surukleme_N']:.4f} N "
         f"(±{kuvvet['surukleme_band_N']:.4f}), taşıma "
         f"{kuvvet['tasima_N']:.4f} N (±{kuvvet['tasima_band_N']:.4f}). ")
    if not rez.get("yakinsadi"):
        s += (f"YAKINSAMADI (eşik {REZ_ESIGI:g}) --- sayı bir EĞİLİMDİR, "
              f"çapa değil. ")
    s += (f"Yayımlanan CFD1: sürükleme {REF['surukleme_N']} N, taşıma "
          f"{REF['tasima_N']} N --- sapma %{sapma['surukleme_pct']} ve "
          f"%{sapma['tasima_pct']}. ")
    if abs(sapma["surukleme_pct"]) < 5.0 and rez.get("yakinsadi"):
        return s + ("Sürükleme referansın %5 bandında ve koşu yakınsadı. "
                    "AMA referans bu depoda doğrulanmadı ve ağ-bağımsızlığı "
                    "sınanmadı --- bu bir EĞİLİM sonucudur, çapa değil.")
    return s + ("Sonuç referanstan sapıyor ya da koşu yakınsamadı; "
                "ağ-bağımsızlığı sınanmadan sapmanın kaynağı ayrılamaz.")


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
