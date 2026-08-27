"""Turek--Hron 2B ağı — gmsh yoluyla. snappy kapandıktan sonraki yol.

NEDEN BU YOL. Ağ kapısı (`turek_hron_ag_kapisi.json`) snappy'nin `empty`
yamalı bir ağı REDDETTİĞİNİ ölçtü --- aracın kendi hatası, ayar değil. O
noktada tek alternatif ``elle `blockMeshDict`, silindir çevresinde O-grid''
sanılıyordu ve ayrı, büyük bir iş olarak yazıldı.

ÜÇÜNCÜ BİR YOL VAR VE DEPO ONU ZATEN KULLANIYOR: gmsh. Tet ağı için
kurulu (`analysis/tet_mesher`), 2B düzlemsel alanı deliğiyle birlikte doğal
olarak mesh'liyor, tek katman ekstrüzyonu destekliyor ve OpenFOAM'ın
`gmshToFoam` çeviricisi bu kurulumda MEVCUT. Yani ``ayrı ve büyük iş''
tahmininin sınanması gerekiyordu --- sınanmadan bir yol kapalı ilan
edilirse, kapanan yol o değil ONU DENEMEK olur.

NE ÖLÇÜLÜR (ağ kapısıyla AYNI üç soru, çünkü kapı yolun değil SONUCUN
kapısıdır):
  1. Ön/arka yamalar `empty` mi?
  2. z yönünde tek hücre mi? (empty yüz / hücre = 2,0)
  3. Gövde yüzeyi ayrı bir yama olarak var mı?

    python experiments/turek_hron_gmsh.py
Çıktı: turek_hron_gmsh.json
"""
from __future__ import annotations

import json
import math
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

from turek_hron_ag import (  # noqa: E402
    BAYRAK_KALINLIK,
    BAYRAK_SON_X,
    KANAL_H,
    KANAL_L,
    MERKEZ,
    YARICAP,
    Z_KALINLIK,
    bayrak_bas_x,
)

from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import windows_to_wsl_path  # noqa: E402

CIKTI = KOK / "turek_hron_gmsh.json"
VAKA = KOK / "turek_hron_gmsh_case"
MSH = KOK / "turek_hron_2b.msh"

# Hucre boyu: govde cevresinde ince, uzakta kaba. Bayrak KALINLIGI 0,02 m
# ve onu en az bu kadar hucreyle cozmek gerekir --- yoksa bayragin iki
# yuzu ayni hucreye duser ve basinc farki KAYBOLUR.
BAYRAK_BASINA_HUCRE = 8
H_GOVDE = BAYRAK_KALINLIK / BAYRAK_BASINA_HUCRE
H_UZAK = 0.02


def _geometri_kur(gmsh) -> tuple[int, dict]:
    """Akış alanı = kanal MİNUS gövde. OCC boolean ile."""
    occ = gmsh.model.occ
    kanal = occ.addRectangle(0, 0, 0, KANAL_L, KANAL_H)
    daire = occ.addDisk(MERKEZ[0], MERKEZ[1], 0, YARICAP, YARICAP)
    xb = bayrak_bas_x()
    y0 = MERKEZ[1] - BAYRAK_KALINLIK / 2
    bayrak = occ.addRectangle(xb, y0, 0, BAYRAK_SON_X - xb, BAYRAK_KALINLIK)
    # GOVDE = daire BIRLESIM bayrak. Ayri cikarmak, aralarinda sifir
    # kalinlikta bir yuz birakip cozucuyu bozardi.
    govde, _ = occ.fuse([(2, daire)], [(2, bayrak)])
    akis, _ = occ.cut([(2, kanal)], govde)
    occ.synchronize()
    return akis[0][1], {"xb": xb, "y0": y0}


def _yamalar(gmsh, yuzey: int) -> dict:
    """Kenarları KONUMDAN sınıflandır --- etiket sırasına GÜVENME.

    OCC boolean sonrasi kenar numaralari kararli DEGILDIR: geometri az
    degisince siralama kayar ve "3 numarali kenar giristir" varsayimi
    sessizce yanlis olur. Siniflandirma kenarin ORTA NOKTASINA bakar.
    """
    # GOVDE IKIYE AYRILIR: FSI'de yuk yalniz BAYRAGA gider. Tek yama
    # olsaydi silindirin basinci de yapiya bindirilir ve sehim yanlis
    # cikardi --- silindir RIJIT bir mesnettir, yuk tasiyan uye degil.
    gruplar = {"giris": [], "cikis": [], "ust": [], "alt": [],
               "silindir": [], "bayrak": [], "govde": []}
    for _, kenar in gmsh.model.getBoundary([(2, yuzey)], oriented=False):
        x0, y0b, _, x1, y1b, _ = gmsh.model.getBoundingBox(1, kenar)
        xm, ym = (x0 + x1) / 2, (y0b + y1b) / 2
        if abs(xm) < 1e-9:
            gruplar["giris"].append(kenar)
        elif abs(xm - KANAL_L) < 1e-9:
            gruplar["cikis"].append(kenar)
        elif abs(ym - KANAL_H) < 1e-9:
            gruplar["ust"].append(kenar)
        elif abs(ym) < 1e-9:
            gruplar["alt"].append(kenar)
        else:
            gruplar["govde"].append(kenar)
            gruplar["bayrak" if _bayrak_mi(xm, ym) else "silindir"].append(kenar)
    return gruplar


def _bayrak_mi(xm: float, ym: float) -> bool:
    """Kenar orta noktası bayrağa mı ait? KONUMDAN, etiketten DEĞİL.

    Bayrak x >= x_bas ve |y - y_merkez| <= kalinlik/2 seridindedir. Cember
    yayinin o seritteki parcasi fuse ile ZATEN silinmistir (bayragin
    icinde kalir), yani yay hicbir parcasiyla bu olcute takilmaz.
    """
    xb = bayrak_bas_x()
    return (xm > xb + 1e-9
            and abs(ym - MERKEZ[1]) <= BAYRAK_KALINLIK / 2 + 1e-9)


def msh_yaz(yol: Path, olcek: float = 1.0) -> dict:
    """`olcek` hucre boyunu carpar --- 1.0 URETIM AGIDIR, degistirmez.

    Ag-bagimsizligi calismasi (`turek_hron_ag_bagimsizligi.py`) ayni
    geometriden bir aile uretmek icin buna ihtiyac duyar. Parametre
    EKLENDI, varsayilan KORUNDU: mevcut cagiranlarin hicbiri etkilenmez.
    """
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("turek_hron")
        yuzey, bilgi = _geometri_kur(gmsh)
        gruplar = _yamalar(gmsh, yuzey)
        if not gruplar["govde"]:
            return {"uretildi": False, "neden": "gövde kenarı bulunamadı"}

        # BOYUT ALANI: govde kenarlarina yakin ince, uzakta kaba.
        d = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(d, "CurvesList", gruplar["govde"])
        t = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(t, "InField", d)
        gmsh.model.mesh.field.setNumber(t, "SizeMin", H_GOVDE * olcek)
        gmsh.model.mesh.field.setNumber(t, "SizeMax", H_UZAK * olcek)
        gmsh.model.mesh.field.setNumber(t, "DistMin", 2 * YARICAP)
        gmsh.model.mesh.field.setNumber(t, "DistMax", 10 * YARICAP)
        gmsh.model.mesh.field.setAsBackgroundMesh(t)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.Algorithm", 8)      # Frontal-Delaunay quad
        gmsh.option.setNumber("Mesh.RecombineAll", 1)   # dortgen -> hekza

        # TEK KATMAN EKSTRUZYON: 2B'ligin kaynagi budur.
        ust = gmsh.model.occ.extrude([(2, yuzey)], 0, 0, Z_KALINLIK,
                                     numElements=[1], recombine=True)
        gmsh.model.occ.synchronize()

        hacim = [x[1] for x in ust if x[0] == 3]
        yan = [x[1] for x in ust if x[0] == 2 and x[1] != yuzey]
        # Z-DUZLEMI OLCUTU MODELDEN TURETILIR, TAHMIN EDILMEZ.
        # gmsh'in sinir kutusu +-1e-7 tolerans tasiyor: duzlemsel bir
        # yuzeyde bile dz = 2e-7 cikiyor. Ilk surum 1e-12 sart kosuyordu ve
        # ON/ARKA YUZLERI HIC BULAMADI (onarka_yuzeyi: 0) --- yani `yanlar`
        # yamasi hic yaratilmadi ve 2B'lik en bastan kayboldu.
        Z_DUZLEM_TOL = 0.01 * Z_KALINLIK

        def _z_duzlemi(etiket: int) -> bool:
            bb = gmsh.model.getBoundingBox(2, etiket)
            return (bb[5] - bb[2]) < Z_DUZLEM_TOL
        # Ekstruzyon sonrasi yan yuzeyleri KONUMDAN yeniden siniflandir.
        sinif = {k: [] for k in ("giris", "cikis", "ust", "alt",
                                 "silindir", "bayrak", "govde")}
        for s in yan:
            bb = gmsh.model.getBoundingBox(2, s)
            xm, ym = (bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2
            if _z_duzlemi(s):
                continue                       # z-duzlemi: on/arka
            if abs(xm) < 1e-9:
                sinif["giris"].append(s)
            elif abs(xm - KANAL_L) < 1e-9:
                sinif["cikis"].append(s)
            elif abs(ym - KANAL_H) < 1e-9:
                sinif["ust"].append(s)
            elif abs(ym) < 1e-9:
                sinif["alt"].append(s)
            else:
                sinif["govde"].append(s)
                sinif["bayrak" if _bayrak_mi(xm, ym) else "silindir"].append(s)
        onarka = [x for x in yan + [yuzey] if _z_duzlemi(x)]

        # `govde` fiziksel grup olarak YAZILMAZ: alt gruplarla (silindir,
        # bayrak) ORTUSUR ve gmshToFoam ayni yuzu iki yamaya koyamaz.
        # Kuvvet karsilastirmasi icin ikisi BIRLIKTE kullanilir.
        for ad, yuzeyler in [(k, v) for k, v in sinif.items() if k != "govde"]                 + [("yanlar", onarka)]:
            if yuzeyler:
                g = gmsh.model.addPhysicalGroup(2, yuzeyler)
                gmsh.model.setPhysicalName(2, g, ad)
        gv = gmsh.model.addPhysicalGroup(3, hacim)
        gmsh.model.setPhysicalName(3, gv, "akiskan")

        gmsh.model.mesh.generate(3)
        # SURUM 2.2 SART: `gmshToFoam` 4.x bicimini okumuyor ve arizasi
        # OKUNAKSIZ ("Attempt to get back from bad stream") --- bicim
        # uyusmazligini soylemiyor, ayristirici ortasinda coquyor.
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.write(str(yol))
        dugum = len(gmsh.model.mesh.getNodes()[0])
        # SAYIM KUSURU: `getElementsByType` (elemanTag, dugumTag) doner ve
        # ilk surum IKINCISINI sayiyordu --- hekza icin 8 kat fazla
        # (265.344 vs gercek 33.168). Kayit "hexa" diye dugum sayiyordu ve
        # checkMesh'in hucre sayisiyla ayrisiyordu; iki sayi yan yana
        # durdugu icin fark GORULEBILIRDI ve gorulmedi.
        hexa_tag, _ = gmsh.model.mesh.getElementsByType(5)
        prizma_tag, _ = gmsh.model.mesh.getElementsByType(6)
        return {"uretildi": True, "dugum": int(dugum),
                "hexa": int(len(hexa_tag)), "prizma": int(len(prizma_tag)),
                "govde_yuzeyi": len(sinif["govde"]),
                "silindir_yuzeyi": len(sinif["silindir"]),
                "bayrak_yuzeyi": len(sinif["bayrak"]),
                "onarka_yuzeyi": len(onarka),
                "hucre_boyu_govde_m": H_GOVDE * olcek, "olcek": olcek, "bayrak_bas_x": bilgi["xb"]}
    finally:
        gmsh.finalize()


def _kos(vaka: Path, komut: str, tmo: int = 900) -> dict:
    yol = windows_to_wsl_path(vaka)
    r = linux_run(f"cd '{yol}' && source /opt/openfoam11/etc/bashrc && {komut}",
                  timeout=tmo)
    kuyruk = (r.stdout or "")[-500:] + (r.stderr or "")[-300:]
    m = re.search(r">\s*(log\.\S+)", komut)
    if m and (vaka / m.group(1)).exists():
        metin = (vaka / m.group(1)).read_text(errors="replace")
        hata = re.search(r"-->\s*FOAM FATAL(?: ERROR| IO ERROR)?:(.{0,600})",
                         metin, re.S)
        kuyruk = (hata.group(0) if hata else metin[-700:]).strip()
    return {"komut": komut, "rc": r.returncode, "kuyruk": kuyruk[:900]}


def _yama_tipleri(vaka: Path) -> None:
    """Yama tiplerini düzelt --- gmshToFoam HEPSİNİ `patch` yazar.

    `yanlar` -> empty (2B'ligin kaynagi) ve duvarlar -> wall.

    DUVAR TIPI KOZMETIK DEGILDIR: `forces` fonksiyonu viskoz katkiyi duvar
    yamasindan okur; `patch` tipinde kayma-gerilmesi katkisi eksik
    kalabilir ve suruklemede SESSIZ bir eksiklik olur.

    `createPatch` YERINE dosya duzenlemesi: o arac bir sozluk daha ister ve
    bu adim yalniz tip degisikligidir. Degisiklik YAPISALDIR --- regex yama
    ADINA baglanir, dosyadaki sirasina degil.
    """
    p = vaka / "constant" / "polyMesh" / "boundary"
    t = p.read_text(errors="replace")

    # GERI-REFERANS YERINE ACIK FONKSIYON. Bu satir bir kez BOZUK
    # yazildi: `\1` geri-referansi dosyaya 0x01 KONTROL KARAKTERI
    # olarak dustu ve regex yama ADINI silip yerine "empty;" yazdi.
    # boundary dosyasi bozuldu, gmshToFoam "Patch 0 gets name ya" dedi ve
    # ag SESSIZCE yamasiz kaldi. Acik fonksiyon o sinifi imkansiz kilar:
    # yakalanan grup DEGISKENDEN gelir, kacis dizisinden degil.
    def _degistir(yeni_tip: str):
        return lambda m: m.group(1) + yeni_tip + ";"

    t = re.sub(r"(yanlar\s*\{[^}]*?type\s+)\w+;",
               _degistir("empty"), t, flags=re.S)
    for duvar in ("ust", "alt", "silindir", "bayrak"):
        t = re.sub(rf"(\b{duvar}\s*\{{[^}}]*?type\s+)\w+;",
                   _degistir("wall"), t, flags=re.S)
    p.write_text(t, encoding="utf-8")


def olc() -> dict:
    try:
        msh = msh_yaz(MSH)
    except Exception as e:                       # noqa: BLE001
        return _ozetle({"uretildi": False,
                        "neden": f"{type(e).__name__}: {e}"[:250]}, [], None, None)
    if not msh.get("uretildi"):
        return _ozetle(msh, [], None, None)
    if VAKA.exists():
        shutil.rmtree(VAKA)
    (VAKA / "system").mkdir(parents=True)
    shutil.copy(MSH, VAKA / "turek_hron_2b.msh")
    for ad, govde in (("controlDict",
                       "application simpleFoam;\nstartFrom startTime;\n"
                       "startTime 0;\nstopAt endTime;\nendTime 1;\ndeltaT 1;\n"
                       "writeControl timeStep;\nwriteInterval 1;\n"),
                      ("fvSchemes",
                       "ddtSchemes { default steadyState; }\n"
                       "gradSchemes { default Gauss linear; }\n"
                       "divSchemes { default none; }\n"
                       "laplacianSchemes { default Gauss linear corrected; }\n"
                       "interpolationSchemes { default linear; }\n"
                       "snGradSchemes { default corrected; }\n"),
                      ("fvSolution", "solvers { }\nSIMPLE { }\n")):
        (VAKA / "system" / ad).write_text(
            "FoamFile\n{\n    version 2.0;\n    format ascii;\n"
            f"    class dictionary;\n    object {ad};\n}}\n" + govde,
            encoding="utf-8")
    adimlar = [_kos(VAKA, "gmshToFoam turek_hron_2b.msh > log.gmshToFoam 2>&1",
                    tmo=1200)]
    sinir = kalite = None
    if adimlar[-1]["rc"] == 0:
        _yama_tipleri(VAKA)
        sinir = _boundary_oku(VAKA)
        kalite = _kos(VAKA, "checkMesh -constant > log.checkMesh 2>&1", tmo=900)
        kalite = {"rc": kalite["rc"], **_checkmesh_oku(VAKA)}
    return _ozetle(msh, adimlar, sinir, kalite)


def _boundary_oku(vaka: Path) -> dict:
    p = vaka / "constant" / "polyMesh" / "boundary"
    if not p.exists():
        return {"okunabildi": False, "neden": "boundary yok"}
    t = p.read_text(errors="replace")
    y = {}
    for m in re.finditer(r"(\w+)\s*\{[^{}]*?type\s+(\w+);[^{}]*?nFaces\s+(\d+);",
                         t, re.S):
        y[m.group(1)] = {"tip": m.group(2), "nFaces": int(m.group(3))}
    return {"okunabildi": True, "yamalar": y}


def _checkmesh_oku(vaka: Path) -> dict:
    p = vaka / "log.checkMesh"
    if not p.exists():
        return {"hucre": None, "mesh_ok": False, "neden": "log yok"}
    t = p.read_text(errors="replace")
    h = re.search(r"cells:\s+(\d+)", t)
    # BICIM GERCEK CIKTIDAN OKUNDU: checkMesh non-ortho'yu "Max:" ile
    # yaziyor, skewness'i "= " ile. Ilk surum "= " ariyordu ve
    # SKEWNESS SATIRINI yakalayip iki metrigi de AYNI sayi gosterdi.
    no = re.search(r"non-orthogonality\s+Max:\s*([\d.]+)", t)
    sk = re.search(r"Max skewness = ([\d.]+)", t)
    return {"hucre": int(h.group(1)) if h else None,
            "mesh_ok": "Mesh OK" in t,
            "max_nonortho": float(no.group(1)) if no else None,
            "max_skewness": float(sk.group(1)) if sk else None,
            "kuyruk": t[-350:]}


def _ozetle(msh, adimlar, sinir, kalite) -> dict:
    y = (sinir or {}).get("yamalar", {})
    yan = y.get("yanlar", {})
    #  yamasi ARTIK YOK (silindir + bayrak olarak ayrildi).
    # Kapi olcutu ikisinin TOPLAMINA bakar.
    govde = {"nFaces": (y.get("silindir", {}).get("nFaces", 0)
                        + y.get("bayrak", {}).get("nFaces", 0))}
    hucre = (kalite or {}).get("hucre")
    oran = (yan.get("nFaces", 0) / hucre) if (hucre and yan) else None
    tek = oran is not None and abs(oran - 2.0) < 1e-9
    empty_kaldi = yan.get("tip") == "empty"
    govde_var = bool(govde and govde.get("nFaces", 0) > 0)
    return {
        "vaka": "Turek-Hron 2B ağı — gmsh + gmshToFoam yolu",
        "_neden": ("Ag kapisi snappy'nin `empty` yamali agi REDDETTIGINI "
                   "olctu ve tek alternatif 'elle blockMesh O-grid' SANILDI. "
                   "Ucuncu yol vardi ve depo onu zaten kullaniyor: gmsh. "
                   "Sinanmadan bir yol kapali ilan edilirse, kapanan yol o "
                   "degil ONU DENEMEK olur."),
        "msh": msh,
        "of_adimlari": adimlar,
        "sinir": sinir,
        "checkMesh": kalite,
        "yanlar_empty_kaldi": bool(empty_kaldi),
        "govde_yamasi_var": govde_var,
        "empty_yuz_bolu_hucre": None if oran is None else round(oran, 6),
        "z_yonunde_tek_hucre": bool(tek),
        "kapi_gecildi": bool(empty_kaldi and govde_var and tek),
        "verdikt": _hukum(msh, adimlar, sinir, kalite, empty_kaldi,
                          govde_var, oran, tek),
        "_kisit": (
            "BU BETIK AKIS COZMEZ. Ag KURULABILIRLIGINI olcer; kalite "
            "(non-ortho, skewness) kayda gecer ama hukme SOKULMAZ --- "
            "kapiyi gecen bir ag, iyi bir ag demek degildir. Hucre boyu "
            "SECILDI (bayrak kalinligi / 8), ag-bagimsizligi SINANMADI. "
            "Ucgen/dortgen karisimi olabilir: gmsh recombine tam dortgen "
            "GARANTI ETMEZ ve kalan ucgenler prizma hucre uretir."),
        "_uretim": "Üretim: python experiments/turek_hron_gmsh.py",
    }


def _hukum(msh, adimlar, sinir, kalite, empty_kaldi, govde_var, oran, tek) -> str:
    if not msh.get("uretildi"):
        return f"GMSH AĞI ÜRETİLEMEDİ: {msh.get('neden')}"
    s = (f"gmsh: {msh['dugum']} düğüm, {msh['hexa']} hekza + "
         f"{msh['prizma']} prizma. ")
    dusen = [a for a in adimlar if a["rc"] != 0]
    if dusen:
        return s + (f"OPENFOAM ADIMI DÜŞTÜ ({dusen[-1]['komut']}): "
                    f"{dusen[-1]['kuyruk'][:250]}")
    s += f"{(kalite or {}).get('hucre')} hücre, "
    s += (f"non-ortho {(kalite or {}).get('max_nonortho')}, "
          f"skewness {(kalite or {}).get('max_skewness')}. ")
    if not govde_var:
        return s + "GÖVDE YAMASI YOK --- sınıflandırma tutmadı. KAPI GEÇİLMEDİ."
    if not empty_kaldi:
        return s + "ÖN/ARKA `empty` DEĞİL. KAPI GEÇİLMEDİ."
    if not tek:
        return s + (f"Z'DE BÖLÜNME VAR: empty yüz / hücre = {oran} "
                    f"(2,0 olmalı). KAPI GEÇİLMEDİ.")
    return s + ("KAPI GEÇİLDİ: ön/arka `empty`, z'de tek hücre, gövde yaması "
                "var. snappy'nin reddettiği şey gmsh yoluyla KURULABİLİYOR "
                "--- 'elle blockMesh O-grid şart' tahmini ÇÜRÜDÜ. Akış hâlâ "
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
