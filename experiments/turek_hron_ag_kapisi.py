"""AĞ KAPISI: snappyHexMesh ince alanda 2B'liği koruyor mu?

FSI çapasının GERÇEK kapısı budur ve geometriden ayrıdır. Geometri hazır ve
doğrulandı (`turek_hron_ag.json`) ama bu depoda gövde-etrafı ağ tek yoldan
kuruluyor: `snappyHexMesh`. Ve snappy 3B bir araçtır --- hücreleri
İZOTROPİK böler, yani ince (tek hücreli) bir alanda z yönünde de bölebilir.
Bölerse ön/arka yüzler `empty` olmaktan çıkar ve vaka artık 2B DEĞİLDİR.

BU SORULMADAN AĞ KURULMAZ. Cevap hayırsa Turek--Hron bu yoldan
ulaşılamaz ve alternatif (elle `blockMeshDict`, O-grid) AYRI ve büyük bir
iştir --- bunu ÖNCE bilmek, saatler sonra öğrenmekten iyidir.

ÜÇ ÖLÇÜM, ÜÇÜ DE `checkMesh` VE `boundary` DOSYASINDAN:
  1. Ön/arka yamalar hâlâ `empty` mi?
  2. z yönünde hücre sayısı hâlâ 1 mi? (hacim/yüzey oranından ölçülür)
  3. Gövde yüzeyi GERÇEKTEN yakalandı mı? (yama var mı, yüzü var mı)

    python experiments/turek_hron_ag_kapisi.py
Çıktı: turek_hron_ag_kapisi.json
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

from turek_hron_ag import (  # noqa: E402
    KANAL_H,
    KANAL_L,
    MERKEZ,
    STL,
    Z_KALINLIK,
)

from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import windows_to_wsl_path  # noqa: E402

CIKTI = KOK / "turek_hron_ag_kapisi.json"
VAKA = KOK / "turek_hron_case"
# Taban ag: kanal boyunca kaba, snappy inceltecek. z'de TEK hucre.
NX, NY = 250, 41
# Govde cevresi inceltme seviyesi. Yuksek tutmak z'de de bolme riskini
# artirir --- kapinin olctugu sey tam olarak bu.
SEVIYE = (2, 2)


def _hdr(cls: str, obj: str, loc: str) -> str:
    return ("FoamFile\n{\n    version 2.0;\n    format ascii;\n"
            f"    class {cls};\n    location \"{loc}\";\n"
            f"    object {obj};\n}}\n")


def _blockmesh() -> str:
    v = [f"({x} {y} {z})"
         for z in (0.0, Z_KALINLIK)
         for y in (0.0, KANAL_H)
         for x in (0.0, KANAL_L)]
    # Kose sirasi: 0..3 z0 duzlemi, 4..7 z1 duzlemi (x hizli, sonra y)
    return (_hdr("dictionary", "blockMeshDict", "system")
            + "convertToMeters 1;\nvertices\n(\n" + "\n".join(v) + "\n);\n"
            + "blocks\n(\n"
            + f"  hex (0 1 3 2 4 5 7 6) ({NX} {NY} 1) simpleGrading (1 1 1)\n"
            + ");\nedges ();\nboundary\n(\n"
            + "  giris { type patch; faces ((0 2 6 4)); }\n"
            + "  cikis { type patch; faces ((1 5 7 3)); }\n"
            + "  ust   { type wall;  faces ((2 3 7 6)); }\n"
            + "  alt   { type wall;  faces ((0 4 5 1)); }\n"
            + "  yanlar { type empty; faces ((0 1 3 2) (4 6 7 5)); }\n"
            + ");\nmergePatchPairs ();\n")


def _snappy() -> str:
    return (_hdr("dictionary", "snappyHexMeshDict", "system")
            + "castellatedMesh true;\nsnap true;\naddLayers false;\n"
            + "geometry\n{\n  govde.stl { type triSurfaceMesh; name govde; }\n}\n"
            + "castellatedMeshControls\n{\n"
            + "  maxLocalCells 2000000;\n  maxGlobalCells 4000000;\n"
            + "  minRefinementCells 0;\n  nCellsBetweenLevels 2;\n"
            + "  resolveFeatureAngle 30;\n  allowFreeStandingZoneFaces true;\n"
            + "  features ();\n"
            + "  refinementSurfaces\n  {\n"
            + f"    govde {{ level ({SEVIYE[0]} {SEVIYE[1]}); }}\n  }}\n"
            + "  refinementRegions {}\n"
            # IC NOKTA: govdenin DISINDA olmali. Kanalin sol-ust kosesi
            # silindirden de bayraktan da uzak.
            + "  locationInMesh (0.05 0.35 " + f"{Z_KALINLIK / 2}" + ");\n}\n"
            + "snapControls\n{\n  nSmoothPatch 3;\n  tolerance 2.0;\n"
            + "  nSolveIter 30;\n  nRelaxIter 5;\n  nFeatureSnapIter 10;\n"
            + "  implicitFeatureSnap false;\n  explicitFeatureSnap true;\n"
            + "  multiRegionFeatureSnap false;\n}\n"
            + "addLayersControls\n{\n  relativeSizes true;\n  layers {}\n"
            + "  expansionRatio 1.2;\n  finalLayerThickness 0.5;\n"
            + "  minThickness 0.1;\n  nGrow 0;\n  featureAngle 60;\n"
            + "  nRelaxIter 3;\n  nSmoothSurfaceNormals 1;\n"
            + "  nSmoothNormals 3;\n  nSmoothThickness 10;\n"
            + "  maxFaceThicknessRatio 0.5;\n  maxThicknessToMedialRatio 0.3;\n"
            + "  minMedianAxisAngle 90;\n  nBufferCellsNoExtrude 0;\n"
            + "  nLayerIter 50;\n}\n"
            + "meshQualityControls\n{\n  maxNonOrtho 65;\n  maxBoundarySkewness 20;\n"
            + "  maxInternalSkewness 4;\n  maxConcave 80;\n  minVol 1e-13;\n"
            + "  minTetQuality -1e30;\n  minArea -1;\n  minTwist 0.02;\n"
            + "  minDeterminant 0.001;\n  minFaceWeight 0.02;\n"
            + "  minVolRatio 0.01;\n  minTriangleTwist -1;\n"
            + "  nSmoothScale 4;\n  errorReduction 0.75;\n}\n"
            + "mergeTolerance 1e-6;\n")


def _controldict() -> str:
    return (_hdr("dictionary", "controlDict", "system")
            + "application simpleFoam;\nstartFrom startTime;\nstartTime 0;\n"
            + "stopAt endTime;\nendTime 1;\ndeltaT 1;\n"
            + "writeControl timeStep;\nwriteInterval 1;\n")


def kur(vaka: Path) -> None:
    if vaka.exists():
        shutil.rmtree(vaka)
    for d in ("system", "constant/triSurface"):
        (vaka / d).mkdir(parents=True, exist_ok=True)
    (vaka / "system" / "blockMeshDict").write_text(_blockmesh(), encoding="utf-8")
    (vaka / "system" / "snappyHexMeshDict").write_text(_snappy(), encoding="utf-8")
    (vaka / "system" / "controlDict").write_text(_controldict(), encoding="utf-8")
    # fvSchemes/fvSolution: blockMesh ve snappy icin BOS da olsa gerekli.
    (vaka / "system" / "fvSchemes").write_text(
        _hdr("dictionary", "fvSchemes", "system")
        + "ddtSchemes { default steadyState; }\n"
        + "gradSchemes { default Gauss linear; }\n"
        + "divSchemes { default none; }\n"
        + "laplacianSchemes { default Gauss linear corrected; }\n"
        + "interpolationSchemes { default linear; }\n"
        + "snGradSchemes { default corrected; }\n", encoding="utf-8")
    (vaka / "system" / "fvSolution").write_text(
        _hdr("dictionary", "fvSolution", "system")
        + "solvers { }\nSIMPLE { nNonOrthogonalCorrectors 0; }\n",
        encoding="utf-8")
    shutil.copy(STL, vaka / "constant" / "triSurface" / "govde.stl")


def _kos(vaka: Path, komut: str, tmo: int = 900) -> dict:
    """Komutu koş ve gerekçeyi GERÇEKTEN oku.

    KUSUR ILK KOSUDA CIKTI: komut ciktisini `> log.X` ile dosyaya
    yonlendiriyor, sonra `r.stdout`u gerekce diye yaziyorduk --- yani
    gerekce BOS gorunuyordu. OpenFOAM'in FATAL ERROR'u log dosyasindaydi
    ve kimse okumuyordu. Bu deponun tekrarlayan kusuru, bu kez sondanin
    kendisinde: sebep VAR, tuketici YOK.
    """
    yol = windows_to_wsl_path(vaka)
    r = linux_run(f"cd '{yol}' && source /opt/openfoam11/etc/bashrc && {komut}",
                  timeout=tmo)
    kuyruk = (r.stdout or "")[-600:] + (r.stderr or "")[-300:]
    m = re.search(r">\s*(log\.\S+)", komut)
    if m:
        log = vaka / m.group(1)
        if log.exists():
            metin = log.read_text(errors="replace")
            hata = re.search(r"-->\s*FOAM FATAL(?: ERROR| IO ERROR)?:(.{0,600})",
                             metin, re.S)
            kuyruk = ((hata.group(0) if hata else metin[-800:]).strip()
                      + ("\n[stdout] " + kuyruk if kuyruk.strip() else ""))
    return {"komut": komut, "rc": r.returncode, "kuyruk": kuyruk[:1200]}


def _boundary_oku(vaka: Path) -> dict:
    p = vaka / "constant" / "polyMesh" / "boundary"
    if not p.exists():
        return {"okunabildi": False, "neden": "boundary dosyası yok"}
    t = p.read_text(errors="replace")
    yamalar = {}
    for m in re.finditer(r"(\w+)\s*\{[^{}]*?type\s+(\w+);[^{}]*?nFaces\s+(\d+);",
                         t, re.S):
        yamalar[m.group(1)] = {"tip": m.group(2), "nFaces": int(m.group(3))}
    return {"okunabildi": True, "yamalar": yamalar}


def _checkmesh(vaka: Path) -> dict:
    r = _kos(vaka, "checkMesh -constant 2>&1 | tail -40", tmo=600)
    t = r["kuyruk"]
    hucre = re.search(r"cells:\s+(\d+)", t)
    return {"rc": r["rc"], "hucre": int(hucre.group(1)) if hucre else None,
            "mesh_ok": "Mesh OK" in t, "kuyruk": t[-400:]}


def olc() -> dict:
    if not STL.exists():
        return _ozetle({"neden": "turek_hron.stl yok — önce turek_hron_ag.py"},
                       None, None)
    kur(VAKA)
    adimlar = [_kos(VAKA, "blockMesh > log.blockMesh 2>&1")]
    if adimlar[-1]["rc"] == 0:
        adimlar.append(_kos(VAKA, "snappyHexMesh -overwrite > log.snappy 2>&1",
                            tmo=1800))
    sinir = _boundary_oku(VAKA) if adimlar[-1]["rc"] == 0 else {"okunabildi": False,
                                                               "neden": "ağ kurulmadı"}
    kalite = _checkmesh(VAKA) if sinir.get("okunabildi") else None
    return _ozetle({"adimlar": adimlar}, sinir, kalite)


def _ozetle(kosu: dict, sinir, kalite) -> dict:
    y = (sinir or {}).get("yamalar", {})
    yan = y.get("yanlar", {})
    govde = next((v for k, v in y.items() if "govde" in k.lower()), None)
    empty_kaldi = yan.get("tip") == "empty"
    govde_var = bool(govde and govde["nFaces"] > 0)
    # Z YONUNDE HUCRE SAYISI: 2B'de her hucrenin IKI empty yuzu vardir,
    # yani nFaces(yanlar) = 2 * hucre_sayisi. z'de bolunme olursa oran duser.
    hucre = (kalite or {}).get("hucre")
    z_orani = (yan.get("nFaces", 0) / hucre) if (hucre and yan) else None
    tek_hucre = z_orani is not None and abs(z_orani - 2.0) < 1e-9
    return {
        "vaka": "Turek-Hron ağ kapısı — snappy 2B'liği koruyor mu?",
        "_neden": ("snappy 3B bir aractir ve hucreleri IZOTROPIK boler. Ince "
                   "bir alanda z'de de bolerse on/arka yuzler `empty` "
                   "olmaktan cikar ve vaka 2B DEGILDIR. Bu sorulmadan ag "
                   "kurulmaz."),
        "taban_ag": {"nx": NX, "ny": NY, "nz": 1, "seviye": list(SEVIYE)},
        "kosu": kosu,
        "sinir": sinir,
        "checkMesh": kalite,
        "yanlar_empty_kaldi": bool(empty_kaldi),
        "govde_yamasi_var": govde_var,
        "empty_yuz_bolu_hucre": None if z_orani is None else round(z_orani, 6),
        "z_yonunde_tek_hucre": bool(tek_hucre),
        "kapi_gecildi": bool(empty_kaldi and govde_var and tek_hucre),
        "verdikt": _hukum(kosu, sinir, kalite, empty_kaldi, govde_var,
                          z_orani, tek_hucre),
        "_kisit": (
            "BU KAPI AKIS COZMEZ. Yalniz agin 2B kalip kalmadigini ve govde "
            "yuzeyinin yakalanip yakalanmadigini olcer. Ag KALITESI "
            "(non-ortho, skewness) checkMesh ciktisinda gorunur ama burada "
            "HUKME sokulmaz --- kapiyi gecen bir ag, iyi bir ag demek "
            "degildir. Seviye ve taban ag SECILDI, optimize EDILMEDI."),
        "_uretim": "Üretim: python experiments/turek_hron_ag_kapisi.py",
    }


def _hukum(kosu, sinir, kalite, empty_kaldi, govde_var, z_orani, tek) -> str:
    if "neden" in kosu:
        return f"KOŞULAMADI: {kosu['neden']}"
    dusen = [a for a in kosu.get("adimlar", []) if a["rc"] != 0]
    if dusen:
        son = dusen[-1]
        # ARIZAYI ADLANDIR, HAM LOGU DOKME. Okur bir hukum bekler; log
        # kuyrugu kayitta zaten duruyor.
        if "not fully 3D" in son["kuyruk"]:
            return (
                "KAPI GEÇİLMEDİ --- ve engel ayar değil ARACIN KENDİSİ: "
                "snappyHexMesh, `empty` yamalı bir ağı REDDEDİYOR "
                "(\"Mesh provided is not fully 3D as required for mesh "
                "relaxation after snapping\"). Yani bu depoda gövde-etrafı "
                "ağ kuran TEK yol 2B vakada KULLANILAMAZ. Sonuç bir ayar "
                "denemesiyle değişmez; Turek-Hron için ağ elle "
                "`blockMeshDict` ile (silindir çevresinde O-grid) kurulmalı "
                "ve bu AYRI, büyük bir iştir. Bilinen üçüncü yol --- snappy'yi "
                "3B koşup sonra `createPatch` ile yüzleri `empty` yapmak --- "
                "z yönünde bölünmeyi ENGELLEMEZ (snappy izotropik böler), "
                "yani 2B'lik yine kaybolur. Kapının erken sorulmasının "
                "kazandırdığı şey budur: ağ kurma denemelerine saatler "
                "harcanmadan yol kapandı.")
        return (f"AĞ ADIMI DÜŞTÜ ({son['komut']}, rc={son['rc']}). "
                f"Gerekçe kayıtta: {son['kuyruk'][:200]}")
    s = f"{(kalite or {}).get('hucre')} hücre. "
    s += (f"Yan yamalar tipi: {(sinir.get('yamalar', {}).get('yanlar') or {}).get('tip')}. ")
    if not govde_var:
        return s + ("GÖVDE YAMASI YOK ya da yüzsüz --- snappy geometriyi "
                    "yakalamadı; `locationInMesh` gövdenin içinde kalmış "
                    "olabilir. KAPI GEÇİLMEDİ.")
    if not empty_kaldi:
        return s + ("ÖN/ARKA YÜZLER ARTIK `empty` DEĞİL --- vaka 2B olmaktan "
                    "çıktı. Turek-Hron bu yoldan ulaşılamaz; alternatif elle "
                    "`blockMeshDict` (O-grid) ve AYRI bir iştir. KAPI "
                    "GEÇİLMEDİ.")
    if not tek:
        return s + (f"Z YÖNÜNDE BÖLÜNME VAR: empty yüz / hücre = {z_orani} "
                    f"(2,0 olmalı). snappy izotropik bölmüş, ağ artık ince "
                    f"3B --- 2B çözüm yapılamaz. KAPI GEÇİLMEDİ.")
    return s + ("Ön/arka `empty` kaldı, z'de tek hücre (empty yüz/hücre = "
                "2,0) ve gövde yüzeyi yakalandı. KAPI GEÇİLDİ --- akış hâlâ "
                "ÇÖZÜLMEDİ ve ağ kalitesi hükme sokulmadı.")


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
