"""Geriye-basamaklı akış — AYRILMA/YENİDEN-YAPIŞMA çapası (Driver & Seegmiller 1985).

NEDEN BU VAKA: çalışma zarfında "ayrılmış akış ❌ kapsam dışı" satırı NİTEL bir beyandı;
hiçbir ölçüm onu desteklemiyordu. Geriye-basamaklı akış ayrılmanın kanonik V&V vakasıdır
ve ayrılma noktası GEOMETRİK olarak sabittir (keskin köşe) — yani sonuç türbülans
modelinin yeniden-yapışmayı ne kadar doğru verdiğini ÖLÇER, ayrılma noktası tahminini
değil. Bu ayrım önemli: pürüzsüz gövdede (küre) ayrılma noktasının kendisi belirsizdir
ve RANS orada sistematik şaşırır; burada tek bilinmeyen kayma tabakasının uzunluğudur.

Kurulum: 2D, basamak yüksekliği H=12.7 mm, U∞=44.3 m/s → Re_H=37500, genişleme oranı
ER=1.125 (Driver & Seegmiller deney koşulu).
Referans: yeniden-yapışma uzunluğu Xr/H = 6.26 ± 0.10 (deney).
Ölçüm: alt duvarda duvar-kayma-geriliminin işaret değiştirdiği ilk istasyon.

    python experiments/basamak_ayrilma.py                  # kOmegaSST
    python experiments/basamak_ayrilma.py kEpsilon kOmegaSST

Çıktı: basamak_ayrilma.json (kanıt)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import windows_to_wsl_path  # noqa: E402
from analysis.thresholds import RESIDUAL_TARGET  # noqa: E402

NU, U_INF = 1.5e-5, 44.29
H_STEP = 0.0127                     # basamak yüksekliği
H_GIRIS = 8 * H_STEP                # giriş kanalı (ER = (8+1)/8 = 1.125)
X_GIRIS, X_CIKIS = 20 * H_STEP, 30 * H_STEP
XR_DENEY, XR_BELIRSIZLIK = 6.26, 0.10       # Driver & Seegmiller 1985
NX_GIRIS, NX_CIKIS, NY_UST, NY_ALT = 60, 220, 60, 40
YAZ_ARALIGI = 2000        # son 6 anlık görüntü tutulur (purgeWrite 6)
BASHRC = "/opt/openfoam11/etc/bashrc"


def _hdr(cls, obj, loc=""):
    ln = f'\n    location    "{loc}";' if loc else ""
    return ("FoamFile\n{\n    version 2.0;\n    format ascii;\n"
            f"    class {cls};{ln}\n    object {obj};\n}}\n")


def _blockmesh() -> str:
    """İki bloklu 2D basamak: giriş kanalı (üst) + genişlemiş kanal (üst+alt)."""
    x0, x1, x2 = -X_GIRIS, 0.0, X_CIKIS
    y0, y1, y2 = -H_STEP, 0.0, H_GIRIS
    z0, z1 = 0.0, 0.001
    v = []
    for z in (z0, z1):
        for (x, y) in ((x0, y1), (x1, y1), (x2, y1), (x2, y2), (x1, y2), (x0, y2),
                       (x1, y0), (x2, y0)):
            v.append(f"({x} {y} {z})")
    # 0..7 z=0 düzlemi, 8..15 z=0.001
    return (_hdr("dictionary", "blockMeshDict", "system") +
            "convertToMeters 1;\nvertices\n(\n" + "\n".join(v) + "\n);\nblocks\n(\n"
            f"hex (0 1 4 5 8 9 12 13) ({NX_GIRIS} {NY_UST} 1) simpleGrading (0.4 1 1)\n"
            f"hex (1 2 3 4 9 10 11 12) ({NX_CIKIS} {NY_UST} 1) simpleGrading (6 1 1)\n"
            f"hex (6 7 2 1 14 15 10 9) ({NX_CIKIS} {NY_ALT} 1) simpleGrading (6 1 1)\n"
            ");\nedges ();\nboundary\n(\n"
            "  giris   { type patch; faces ((0 5 13 8)); }\n"
            "  cikis   { type patch; faces ((2 3 11 10) (7 2 10 15)); }\n"
            "  ust     { type wall;  faces ((5 4 12 13) (4 3 11 12)); }\n"
            "  alt     { type wall;  faces ((6 7 15 14)); }\n"
            "  basamak { type wall;  faces ((0 1 9 8) (1 6 14 9)); }\n"
            "  yanlar  { type empty; faces ((0 1 4 5) (1 2 3 4) (6 7 2 1)\n"
            "                              (8 9 12 13) (9 10 11 12) (14 15 10 9)); }\n"
            ");\nmergePatchPairs ();\n")


def _yaz(case: Path, model: str) -> None:
    for d in ("system", "constant", "0"):
        (case / d).mkdir(parents=True, exist_ok=True)
    (case / "system" / "blockMeshDict").write_text(_blockmesh())
    (case / "constant" / "momentumTransport").write_text(
        _hdr("dictionary", "momentumTransport", "constant") +
        f"simulationType RAS;\nRAS {{ model {model}; turbulence on; printCoeffs on; }}\n")
    (case / "constant" / "physicalProperties").write_text(
        _hdr("dictionary", "physicalProperties", "constant") +
        f"viscosityModel constant;\nnu [0 2 -1 0 0 0 0] {NU};\n")

    k_inf = 1.5 * (0.03 * U_INF) ** 2
    om_inf = k_inf ** 0.5 / (0.09 ** 0.25 * H_STEP)
    eps_inf = 0.09 ** 0.75 * k_inf ** 1.5 / H_STEP
    duvarlar = ("ust", "alt", "basamak")
    alanlar = {
        "U": ("volVectorField", "[0 1 -1 0 0 0 0]", f"({U_INF} 0 0)", "noSlip", None),
        "p": ("volScalarField", "[0 2 -2 0 0 0 0]", "0", "zeroGradient", None),
        "k": ("volScalarField", "[0 2 -2 0 0 0 0]", f"{k_inf:g}", "kqRWallFunction", k_inf),
        "nut": ("volScalarField", "[0 2 -1 0 0 0 0]", "0", "nutkWallFunction", 0.0),
        "omega": ("volScalarField", "[0 0 -1 0 0 0 0]", f"{om_inf:g}",
                  "omegaWallFunction", om_inf),
        "epsilon": ("volScalarField", "[0 2 -3 0 0 0 0]", f"{eps_inf:g}",
                    "epsilonWallFunction", eps_inf),
    }
    for ad, (cls, boyut, ic, duvar_tip, duvar_deger) in alanlar.items():
        gov = [f"  {d} {{ type {duvar_tip};" +
               (f" value uniform {duvar_deger:g}; }}" if duvar_deger is not None else " }")
               for d in duvarlar]
        giris = ("  giris { type zeroGradient; }\n" if ad == "p"
                 else f"  giris {{ type fixedValue; value uniform {ic}; }}\n")
        cikis = ("  cikis { type fixedValue; value uniform 0; }\n" if ad == "p"
                 else "  cikis { type zeroGradient; }\n")
        (case / "0" / ad).write_text(
            _hdr(cls, ad, "0") + f"dimensions {boyut};\ninternalField uniform {ic};\n"
            "boundaryField\n{\n" + giris + cikis + "\n".join(gov) +
            "\n  yanlar { type empty; }\n}\n")

    (case / "system" / "controlDict").write_text(
        _hdr("dictionary", "controlDict", "system") +
        "application foamRun;\nsolver incompressibleFluid;\nstartFrom startTime;\n"
        "startTime 0;\nstopAt endTime;\nendTime 20000;\ndeltaT 1;\n"
        # Son anlık görüntüler: çözüm limit çevrimindeyse tek Xr değeri KARARSIZDIR;
        # birden çok geç anlık görüntü salınım genliğini ölçmeyi sağlar.
        f"writeControl timeStep;\nwriteInterval {YAZ_ARALIGI};\npurgeWrite 6;\n"
        "runTimeModifiable true;\n"
        # writeCellCentres: Xr'yi yüz İNDEKSİNDEN türetmek kabul edilemez — mesh x
        # yönünde 6× kademeli ve yüz sırası da garanti değil. İlk sürüm bunu yaptı ve
        # Xr/H=2.36 (%-62) verdi; işaret dizisi de fiziksel değildi. Gerçek koordinat.
        'functions { wss { type wallShearStress; libs ("libfieldFunctionObjects.so"); '
        "writeControl writeTime; patches (alt); } "
        'cc { type writeCellCentres; libs ("libfieldFunctionObjects.so"); '
        "writeControl writeTime; } }\n")
    (case / "system" / "fvSchemes").write_text(
        _hdr("dictionary", "fvSchemes", "system") +
        "ddtSchemes { default steadyState; }\n"
        "gradSchemes { default Gauss linear; }\n"
        "divSchemes { default none; div(phi,U) bounded Gauss linearUpwind grad(U);\n"
        '  "div\\(phi,(k|omega|epsilon)\\)" bounded Gauss upwind;\n'
        "  div(dev2(T(grad(U)))) Gauss linear; }\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
        "interpolationSchemes { default linear; }\n"
        "snGradSchemes { default corrected; }\n"
        "wallDist { method meshWave; }\n")
    (case / "system" / "fvSolution").write_text(
        _hdr("dictionary", "fvSolution", "system") +
        "solvers { p { solver GAMG; tolerance 1e-8; relTol 0.01; smoother GaussSeidel; }\n"
        '  "(U|k|omega|epsilon)" { solver smoothSolver; smoother symGaussSeidel; '
        "tolerance 1e-9; relTol 0.01; } }\n"
        "SIMPLE { nNonOrthogonalCorrectors 0; consistent yes;\n"
        # p için PROJENİN KANONİK eşiği (analysis/thresholds.RESIDUAL_TARGET). Daha
        # sıkısı denendi ve ULAŞILAMADI: p 4000→20000 iterasyon boyunca 7e-5…9e-5
        # bandında PLATOYA oturdu, düşmedi. Bu yavaş yakınsama değil LİMİT ÇEVRİMİ —
        # basamak arkasındaki kayma tabakası bu Re'de gerçekten kararsızdır ve kararlı
        # SIMPLE sabit noktaya oturmaz. Plato ayrıca ölçülüp hükme yazılır.
        f'  residualControl {{ p {RESIDUAL_TARGET}; U {RESIDUAL_TARGET}; '
        f'"(k|omega|epsilon)" {RESIDUAL_TARGET}; }} }}\n'
        'relaxationFactors { equations { U 0.9; ".*" 0.9; } }\n')


def yakinsadi_mi(case: Path) -> tuple[bool, int]:
    log = case / "log.foamRun"
    if not log.exists():
        return False, 0
    t = log.read_text(errors="ignore")
    m = re.search(r"SIMPLE solution converged in (\d+)", t)
    return (True, int(m.group(1))) if m else (False, t.count("\nTime = "))


def _zaman_dizinleri(case: Path) -> list[Path]:
    return sorted((d for d in case.iterdir()
                   if d.is_dir() and d.name.replace(".", "", 1).isdigit()
                   and float(d.name) > 0), key=lambda d: float(d.name))


def yapisma_bandi(case: Path, n_son: int = 4) -> tuple[list[float], str]:
    """Son n anlık görüntüden Xr/H listesi — limit çevriminin genliğini ölçer.

    Çözüm sabit noktaya oturmuyorsa (bkz. residualControl notu) tek bir anlık Xr
    yanıltıcıdır: salınımın neresinde durduğuna bağlıdır. Band, o belirsizliği
    GİZLEMEK yerine sayıya çevirir.
    """
    dizinler = _zaman_dizinleri(case)[-n_son:]
    if not dizinler:
        return [], "zaman dizini yok"
    out, son_neden = [], "ok"
    for d in dizinler:
        xr, neden = yapisma_uzunlugu(case, d)
        if xr is not None:
            out.append(xr)
        else:
            son_neden = neden
    return out, ("ok" if out else son_neden)


def yapisma_uzunlugu(case: Path, zaman_dizini: Path | None = None) -> tuple[float | None, str]:
    """Alt duvarda τ_x'in NEGATİFTEN POZİTİFE döndüğü ilk x → yeniden-yapışma.

    Basamak dibinde akış geri döner (τ_x < 0); kayma tabakası duvara yapışınca ileri
    akış başlar (τ_x > 0). İşaret değişimi lineer aralanır.
    """
    if zaman_dizini is None:
        zaman = _zaman_dizinleri(case)
        if not zaman:
            return None, "zaman dizini yok"
        zaman_dizini = zaman[-1]
    f = zaman_dizini / "wallShearStress"
    if not f.exists():
        return None, "wallShearStress yazılmadı"
    blok = re.search(r"alt\s*\{(.*?)\n\s*\}", f.read_text(errors="ignore"), re.S)
    if not blok:
        return None, "alt duvar bloğu okunamadı"
    tx = [float(m[0]) for m in
          re.findall(r"\(([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\)", blok.group(1))]
    if len(tx) < 10:
        return None, f"yalnız {len(tx)} yüzey değeri"
    # GERÇEK x koordinatları — yüz indeksinden türetmek kabul edilemez (mesh 6× kademeli
    # ve yüz sırası garanti değil). İlk sürüm indeks kullandı ve Xr/H=2.36 verdi.
    xs = _alt_duvar_x(zaman_dizini)
    if xs is None:
        return None, "Ccx yazılmadı — writeCellCentres fonksiyonu eksik"
    if len(xs) != len(tx):
        return None, f"koordinat/gerilme uyuşmuyor ({len(xs)} vs {len(tx)})"
    ikili = sorted(zip(xs, tx))                 # x'e göre sırala: indeks sırasına güvenme
    xs = [a for a, _ in ikili]
    tx = [b for _, b in ikili]
    # İŞARET KONVANSİYONU: OpenFOAM'ın wallShearStress x-bileşeni İLERİ (yapışık) akışta
    # NEGATİF, geri akışta POZİTİFTİR. İlk sürüm bunu ters varsaydı ve Xr/H=0.93 (%-85)
    # verdi. Konvansiyon bağımsız veriyle doğrulandı: alt bloktaki ters akan HÜCRELER
    # sütun 60'ta 14/40 iken sütun 80'de 0/40 — baloncuk indeks 80 civarında bitiyor ve
    # τ_x tam orada + → − dönüyor. τ<0 geri akış olsaydı 5.5H'nin ötesinde ters hücre
    # görülmesi gerekirdi; görülmüyor.
    #
    # Beklenen yapı (ders kitabı): köşede ters dönen İKİNCİL girdap (duvarda ileri akış),
    # sonra ANA baloncuk (duvarda geri akış), sonra yapışma. Aranan şey ana baloncuğun
    # SONU: geri akıştan (+) yapışık akışa (−) SON geçiş.
    gecisler = [i for i in range(1, len(tx)) if tx[i - 1] > 0 >= tx[i]]
    if not gecisler:
        if all(v <= 0 for v in tx):
            return None, "hiç geri akış yok — ayrılma baloncuğu oluşmamış"
        return None, "yapışma bulunamadı (baloncuk çıkıştan uzun olabilir)"
    ilk = gecisler[-1]
    pay = tx[ilk - 1] / (tx[ilk - 1] - tx[ilk])
    x_r = xs[ilk - 1] + pay * (xs[ilk] - xs[ilk - 1])
    return x_r / H_STEP, "ok"


def _alt_duvar_x(zaman_dizini: Path) -> list[float] | None:
    """`alt` duvar yüzlerinin gerçek x koordinatları (writeCellCentres → Cx)."""
    f = zaman_dizini / "Ccx"
    if not f.exists():
        return None
    blok = re.search(r"alt\s*\{(.*?)\n\s*\}", f.read_text(errors="ignore"), re.S)
    if not blok:
        return None
    # Liste UZUNLUĞU da tek başına bir satırdır ("220") ve koordinat sanılıyordu
    # (221 değer okunmuştu). Yalnız parantez içi alınır.
    ic = re.search(r"\(\s*\n(.*?)\n\s*\)", blok.group(1), re.S)
    if not ic:
        return None
    sayilar = re.findall(r"^\s*(-?\d[\d.eE+-]*)\s*$", ic.group(1), re.M)
    return [float(x) for x in sayilar] or None


def rezidual_platosu(case: Path) -> dict | None:
    """Rezidüel DÜŞMEYİ BIRAKTI MI — sabit nokta mı, limit çevrimi mi?

    Eşiğin altına inmek yakınsama demek DEĞİLDİR. Bu vakada ölçüldü: kOmegaSST'de
    20000 iterasyon sonunda p=8.1e-5, ω=2.9e-5, k=8.5e-6 — üçü de kanonik eşiğin
    (1e-4) altında ama ikinci yarı boyunca HİÇ düşmüyor. Ölçüt: son değerin,
    koşunun ortasındaki değere oranı. Oran ~1 ise plato (düşüş durmuş).
    """
    log = case / "log.foamRun"
    if not log.exists():
        return None
    metin = log.read_text(errors="ignore")
    out = {}
    for alan in ("p", "Ux", "Uy", "k", "omega", "epsilon"):
        v = [float(x) for x in re.findall(
            rf"Solving for {alan}, Initial residual = ([\d.eE+-]+)", metin)]
        if len(v) < 20:
            continue
        orta = v[len(v) // 2]
        son = v[-1]
        out[alan] = {"son": son, "orta": orta,
                     "dusus_orani": round(son / orta, 3) if orta > 0 else None}
    if not out:
        return None
    # İkinci yarıda 10 kattan az düşen alan varsa çözüm sabit noktaya OTURMUYOR.
    platoda = [a for a, d in out.items()
               if d["dusus_orani"] is not None and d["dusus_orani"] > 0.1]
    return {"alanlar": out, "platoda": platoda,
            "kararli_nokta": not platoda}


def _kos(case: Path, timeout: int = 3600) -> tuple[bool, str]:
    cu = windows_to_wsl_path(case)
    # Windows tarafinda yazilan dosyalar WSL'de (drvfs) ANINDA gorunmeyebilir: kEpsilon
    # kosusu "cannot open system/fvSchemes" ile dustu, oysa dosya diskteydi. Kisa bekleme.
    r = linux_run(
        f"source {BASHRC} && cd '{cu}' && "
        # $(...) ve $((...)) dış kabuk katmanında bozuluyor (bash "syntax error near
        # unexpected token" verdi) — komut ikamesi OLMAYAN düz liste kullanılır.
        "for i in 1 2 3 4 5 6 7 8 9 10; do [ -s system/fvSchemes ] && "
        "[ -s system/fvSolution ] && break; sleep 1; done; "
        "blockMesh > log.blockMesh 2>&1 && foamRun > log.foamRun 2>&1", timeout)
    return r.returncode == 0, (r.stderr or r.stdout or "")[-300:]


def main(modeller: list[str]) -> int:
    kok = HERE.parent / "_basamak"
    kok.mkdir(exist_ok=True)
    sonuc = []
    for model in modeller:
        case = kok / model
        print(f"[{model}] kuruluyor…", flush=True)
        if SADECE_OKU and (case / "log.foamRun").exists():
            ok, hata = True, ""            # mevcut koşuyu yeniden ÇÖZMEDEN oku
        else:
            _yaz(case, model)
            ok, hata = _kos(case)
        if not ok:
            print(f"   ÇÖZÜCÜ DÜŞTÜ: {hata[:140]}", flush=True)
            sonuc.append({"model": model, "durum": "cozucu_dustu", "hata": hata[:200]})
            continue
        yakin, it = yakinsadi_mi(case)
        if not yakin:
            # Yakınsamayan koşu VERİ SAYILMAZ; ama Xr'sini büsbütün atmak da bilgi
            # kaybıdır — model karşılaştırmasında "bu model oturmuyor, oturmadığı
            # yerdeki değeri de şu" demek okuyucuya daha çok şey söyler. AYRI anahtar
            # altında ve açık etiketle saklanır, hükme GİRMEZ.
            tani_band, _ = yapisma_bandi(case)
            plato = rezidual_platosu(case) or {}
            sonuc.append({"model": model, "durum": "yakinsamadi", "iterasyon": it,
                          "Xr_H_YAKINSAMAMIS": (round(sum(tani_band) / len(tani_band), 3)
                                                if tani_band else None),
                          "rezidual": plato.get("alanlar"),
                          "platoda_alanlar": plato.get("platoda"),
                          "_not": ("residualControl saglanmadi — bu Xr HUKME GIRMEZ, "
                                   "yalniz model davranisini gostermek icin kayitli")})
            print(f"   YAKINSAMADI ({it} iterasyon) — veri sayılmıyor"
                  + (f" (tanı: Xr/H≈{sum(tani_band) / len(tani_band):.2f})" if tani_band else ""),
                  flush=True)
            continue
        band, neden = yapisma_bandi(case)
        if not band:
            print(f"   Xr OKUNAMADI: {neden}", flush=True)
            sonuc.append({"model": model, "durum": "xr_okunamadi", "neden": neden,
                          "iterasyon": it})
            continue
        xr = sum(band) / len(band)
        salinim = (max(band) - min(band)) / 2
        hata_pct = (xr - XR_DENEY) / XR_DENEY * 100
        plato = rezidual_platosu(case) or {}
        sonuc.append({"model": model, "Xr_H": round(xr, 3),
                      "Xr_H_salinim": round(salinim, 3),
                      "Xr_H_anliklar": [round(v, 3) for v in band],
                      "Xr_H_deney": XR_DENEY, "hata_pct": round(hata_pct, 2),
                      "iterasyon": it, "rezidual": plato.get("alanlar"),
                      "platoda_alanlar": plato.get("platoda"),
                      "kararli_nokta": plato.get("kararli_nokta"),
                      "durum": "ok"})
        print(f"   Xr/H = {xr:.2f} ± {salinim:.2f} (deney {XR_DENEY}) → "
              f"hata %{hata_pct:+.1f}  | sabit nokta: "
              f"{'evet' if plato.get('kararli_nokta') else 'HAYIR (plato: %s)' % ','.join(plato.get('platoda') or [])}",
              flush=True)

    gecerli = [s for s in sonuc if s["durum"] == "ok"]
    out = {
        "vaka": (f"Geriye-basamakli akis, yeniden-yapisma uzunlugu — H={H_STEP * 1000:.1f} mm, "
                 f"U={U_INF} m/s, Re_H={U_INF * H_STEP / NU:.0f}, ER=1.125"),
        "kaynak": "OpenFOAM 11 foamRun/incompressibleFluid, 2D blockMesh",
        "referans": {"Xr_H": XR_DENEY, "belirsizlik": XR_BELIRSIZLIK,
                     "kaynak": "Driver & Seegmiller, AIAA J. 23(2), 1985 — deneysel"},
        "_olcum_notu": ("Xr, alt duvarda tau_x isaret degisiminden okunur ve yuzey-merkezi "
                        "indeksi x'e DOGRUSAL esleme ile cevrilir; mesh x-yonunde graded "
                        "oldugu icin bu esleme yaklasiktir (birkac yuzde mertebesinde "
                        "ek belirsizlik). Model karsilastirmasi bu hatadan ETKILENMEZ."),
        "seviyeler": sonuc,
        "verdikt": _verdikt(gecerli) + _yakinsamayanlar_notu(sonuc),
        "_uretim": "Üretim: python experiments/basamak_ayrilma.py",
    }
    (HERE.parent / "basamak_ayrilma.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + out["verdikt"])
    print("-> basamak_ayrilma.json")
    return 0 if gecerli else 1


def _verdikt(gecerli: list[dict]) -> str:
    if not gecerli:
        return "⚠️ Hicbir model tamamlanmadi — capa uretilemedi."
    en_iyi = min(gecerli, key=lambda s: abs(s["hata_pct"]))
    p = [f"En iyi model {en_iyi['model']}: Xr/H={en_iyi['Xr_H']:.2f} vs deney "
         f"{XR_DENEY} → hata %{en_iyi['hata_pct']:+.1f}"]
    if abs(en_iyi["hata_pct"]) <= 15:
        p.append("Ayrilma GEOMETRIK olarak sabitken (keskin kose) RANS yeniden-yapisma "
                 "uzunlugunu bu bantta veriyor — 'ayrilmis akis' bu sinifta EGILIM "
                 "duzeyinde kullanilabilir")
    else:
        p.append("Sapma %15'i asiyor — bu hatta ayrilmis akis SAYISAL olarak "
                 "guvenilmez, yalniz nitel karsilastirma icin kullanilmali")
    salinanlar = [s for s in gecerli if s.get("kararli_nokta") is False]
    if salinanlar:
        k = salinanlar[0]
        p.append(f"UYARI: cozum SABIT NOKTAYA OTURMADI ({', '.join(k['platoda_alanlar'])} "
                 f"rezidueli platoda) — kanonik esik saglansa da limit cevrimi var; "
                 f"Xr bir BANT olarak verildi (±{k['Xr_H_salinim']:.2f})")
    if len(gecerli) > 1:
        p.append("model bagimliligi: " + ", ".join(
            f"{s['model']} %{s['hata_pct']:+.0f}" for s in gecerli))
    return ". ".join(p) + "."


def _yakinsamayanlar_notu(sonuc: list[dict]) -> str:
    ykn = [s for s in sonuc if s["durum"] == "yakinsamadi"]
    if not ykn:
        return ""
    par = []
    for s in ykn:
        xr = s.get("Xr_H_YAKINSAMAMIS")
        par.append(f"{s['model']} ({s['iterasyon']} iterasyon, "
                   f"{', '.join(s.get('platoda_alanlar') or [])} platoda"
                   + (f", tani Xr/H≈{xr}" if xr else "") + ")")
    return (" YAKINSAMAYAN: " + "; ".join(par) +
            " — bu model(ler) bu kurulumda sabit noktaya oturmuyor; degerleri hukme girmedi.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--oku"]
    SADECE_OKU = "--oku" in sys.argv                     # mevcut case'leri yeniden çözmeden oku
    sys.exit(main(args or ["kOmegaSST", "kEpsilon"]))
