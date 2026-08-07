"""Düz levha cilt-sürtünmesi — y⁺ DUYARLILIK çapası (kanonik 2D V&V vakası).

NEDEN BU VAKA: MiniHawk kampanyalarının asıl darboğazı sürtünme sürüklemesiydi
(y⁺=524…4113 ölçüldü, duvar-fonksiyonu bandı ~30-300). Zarf tablosu bunu "sürtünme
çözülmüyor" diye NİTEL söylüyordu. Bu çapa aynı soruyu NİCEL yapar: verilen y⁺'de
cilt-sürtünmesi katsayısı literatürden yüzde kaç sapıyor?

Kurulum: 2D sıfır-basınç-gradyanlı düz levha, U∞=30 m/s, L=1 m → Re_L=2e6 (türbülanslı).
Referans: Cf(x) = 0.0592·Re_x^(-1/5) (1/7-kuvvet yasası, 5e5<Re_x<1e7; Schlichting).
Ölçüm: x=0.5 m'de (Re_x=1e6) duvar kayma gerilmesinden yerel Cf.

Aynı mesh ailesi, YALNIZ ilk hücre yüksekliği değiştirilerek birkaç y⁺ hedefinde
koşulur → "y⁺ ne kadar büyürse Cf hatası ne kadar" eğrisi.

    python experiments/duz_levha_cf.py            # varsayılan y+ taraması
    python experiments/duz_levha_cf.py 30 300     # seçili hedefler

Çıktı: duz_levha_cf.json (kanıt) — kanit.py bunu indeksler.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import windows_to_wsl_path  # noqa: E402

NU, RHO, U_INF, L_PLATE = 1.5e-5, 1.225, 30.0, 1.0
X_OLCUM = 0.5                      # yerel Cf bu istasyonda karşılaştırılır
H_DOMAIN, X_ONE = 0.30, 0.10       # üst sınır yüksekliği, levha önü slip uzunluğu
NX_ON, NX_LEVHA, NY, NY_MIN = 20, 120, 70, 8
BASHRC = "/opt/openfoam11/etc/bashrc"


def cf_referans(re_x: float) -> float:
    """1/7-kuvvet yasası yerel cilt-sürtünmesi (Schlichting); 5e5 < Re_x < 1e7."""
    return 0.0592 * re_x ** -0.2


def _genisleme(h_toplam: float, n: int, ilk: float) -> float:
    """blockMesh simpleGrading oranı (son/ilk hücre) — hedef ilk hücre yüksekliği için.

    δ1 = H(1-r)/(1-rⁿ) bağıntısı r için sayısal çözülür; simpleGrading r^(n-1) ister.
    """
    def f(r):
        return h_toplam * (1 - r) / (1 - r ** n) - ilk
    lo, hi = 1.0001, 1.5
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (0.5 * (lo + hi)) ** (n - 1)


def _ilk_hucre(yplus_hedef: float) -> float:
    """Hedef y⁺ için ilk hücre yüksekliği (x=X_OLCUM istasyonundaki Cf'e göre)."""
    cf = cf_referans(U_INF * X_OLCUM / NU)
    u_tau = math.sqrt(0.5 * U_INF ** 2 * cf)
    return yplus_hedef * NU / u_tau


def delta99() -> float:
    """Türbülanslı sınır tabaka kalınlığı x=X_OLCUM'da (1/7-kuvvet): δ ≈ 0.37 x Re_x^(-1/5)."""
    return 0.37 * X_OLCUM * (U_INF * X_OLCUM / NU) ** -0.2


def hucre_sayisi(ilk: float) -> int | None:
    """Hedef ilk hücreyi ÜRETEBİLECEK y-hücre sayısı; üretilemiyorsa None.

    Genişleme oranı ≥1 olduğundan ilk hücre en KÜÇÜK hücredir → δ1 ≤ H/n zorunlu.
    Bu kısıt sessiz kalırsa yüksek y⁺ hedefleri aynı doymuş mesh'e çöker ve birbirinin
    kopyası olan koşular BAĞIMSIZ veri noktası sanılır (bu script ilk sürümünde tam
    olarak bu oldu: y⁺ 1000/3000/8000 hedefleri hep y⁺=169 verdi).
    """
    n = int(0.75 * H_DOMAIN / ilk)
    if n < NY_MIN:
        return None if ilk > H_DOMAIN / NY_MIN else NY_MIN
    return min(NY, n)


def _yaz(case: Path, yplus_hedef: float, ny: int) -> None:
    for d in ("system", "constant", "0"):
        (case / d).mkdir(parents=True, exist_ok=True)

    def hdr(cls, obj, loc=""):
        l = f'\n    location    "{loc}";' if loc else ""
        return ("FoamFile\n{\n    version 2.0;\n    format ascii;\n"
                f"    class {cls};{l}\n    object {obj};\n}}\n")

    ilk = _ilk_hucre(yplus_hedef)
    g = _genisleme(H_DOMAIN, ny, ilk)
    (case / "system" / "blockMeshDict").write_text(
        hdr("dictionary", "blockMeshDict", "system") +
        "convertToMeters 1;\nvertices\n(\n"
        f"({-X_ONE} 0 0) (0 0 0) ({L_PLATE} 0 0)\n"
        f"({L_PLATE} {H_DOMAIN} 0) (0 {H_DOMAIN} 0) ({-X_ONE} {H_DOMAIN} 0)\n"
        f"({-X_ONE} 0 0.01) (0 0 0.01) ({L_PLATE} 0 0.01)\n"
        f"({L_PLATE} {H_DOMAIN} 0.01) (0 {H_DOMAIN} 0.01) ({-X_ONE} {H_DOMAIN} 0.01)\n"
        ");\nblocks\n(\n"
        f"hex (0 1 4 5 6 7 10 11) ({NX_ON} {ny} 1) simpleGrading (1 {g:g} 1)\n"
        f"hex (1 2 3 4 7 8 9 10) ({NX_LEVHA} {ny} 1) simpleGrading (4 {g:g} 1)\n"
        ");\nedges ();\nboundary\n(\n"
        "  giris   { type patch;  faces ((0 5 11 6)); }\n"
        "  cikis   { type patch;  faces ((2 3 9 8)); }\n"
        "  ust     { type patch;  faces ((5 4 10 11) (4 3 9 10)); }\n"
        "  onslip  { type symmetryPlane; faces ((0 1 7 6)); }\n"
        "  levha   { type wall;   faces ((1 2 8 7)); }\n"
        "  yanlar  { type empty;  faces ((0 1 4 5) (6 7 10 11) (1 2 3 4) (7 8 9 10)); }\n"
        ");\nmergePatchPairs ();\n")

    (case / "constant" / "momentumTransport").write_text(
        hdr("dictionary", "momentumTransport", "constant") +
        "simulationType RAS;\nRAS { model kOmegaSST; turbulence on; printCoeffs on; }\n")
    (case / "constant" / "physicalProperties").write_text(
        hdr("dictionary", "physicalProperties", "constant") +
        f"viscosityModel constant;\nnu [0 2 -1 0 0 0 0] {NU};\n")

    duvar_fn = yplus_hedef >= 20        # y⁺~1 hedefinde düşük-Re çözümü istenir
    nut_wall = ("nutkWallFunction" if duvar_fn else "nutLowReWallFunction")
    k_inf = 1.5 * (0.02 * U_INF) ** 2
    om_inf = k_inf ** 0.5 / (0.09 ** 0.25 * 0.1)
    alanlar = {
        "U": ("volVectorField", "[0 1 -1 0 0 0 0]", f"({U_INF} 0 0)",
              "levha { type noSlip; }"),
        "p": ("volScalarField", "[0 2 -2 0 0 0 0]", "0", "levha { type zeroGradient; }"),
        "k": ("volScalarField", "[0 2 -2 0 0 0 0]", f"{k_inf:g}",
              "levha { type kqRWallFunction; value uniform %g; }" % k_inf),
        "nut": ("volScalarField", "[0 2 -1 0 0 0 0]", "0",
                f"levha {{ type {nut_wall}; value uniform 0; }}"),
        "omega": ("volScalarField", "[0 0 -1 0 0 0 0]", f"{om_inf:g}",
                  "levha { type omegaWallFunction; value uniform %g; }" % om_inf),
    }
    for ad, (cls, boyut, ic, duvar) in alanlar.items():
        giris = ("fixedValue" if ad != "p" else "zeroGradient")
        (case / "0" / ad).write_text(
            hdr(cls, ad, "0") + f"dimensions {boyut};\ninternalField uniform {ic};\n"
            "boundaryField\n{\n"
            + (f"  giris {{ type {giris}; value uniform {ic}; }}\n" if ad != "p"
               else "  giris { type zeroGradient; }\n")
            + ("  cikis { type fixedValue; value uniform 0; }\n" if ad == "p"
               else "  cikis { type zeroGradient; }\n")
            + "  ust { type slip; }\n  onslip { type symmetryPlane; }\n"
            + f"  {duvar}\n  yanlar {{ type empty; }}\n}}\n")

    (case / "system" / "controlDict").write_text(
        hdr("dictionary", "controlDict", "system") +
        "application foamRun;\nsolver incompressibleFluid;\nstartFrom startTime;\n"
        "startTime 0;\nstopAt endTime;\nendTime 1500;\ndeltaT 1;\nwriteControl "
        "timeStep;\nwriteInterval 1500;\nrunTimeModifiable true;\n"
        "functions { wss { type wallShearStress; libs (\"libfieldFunctionObjects.so\"); "
        "writeControl writeTime; patches (levha); } "
        "yp { type yPlus; libs (\"libfieldFunctionObjects.so\"); writeControl writeTime; } }\n")
    (case / "system" / "fvSchemes").write_text(
        hdr("dictionary", "fvSchemes", "system") +
        "ddtSchemes { default steadyState; }\n"
        "gradSchemes { default Gauss linear; }\n"
        "divSchemes { default none; div(phi,U) bounded Gauss linearUpwind grad(U);\n"
        "  div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind;\n"
        "  div(dev2(T(grad(U)))) Gauss linear; }\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
        "interpolationSchemes { default linear; }\n"
        "snGradSchemes { default corrected; }\n"
        "wallDist { method meshWave; }\n")
    (case / "system" / "fvSolution").write_text(
        hdr("dictionary", "fvSolution", "system") +
        "solvers { p { solver GAMG; tolerance 1e-8; relTol 0.01; smoother GaussSeidel; }\n"
        '  "(U|k|omega)" { solver smoothSolver; smoother symGaussSeidel; '
        "tolerance 1e-9; relTol 0.01; } }\n"
        "SIMPLE { nNonOrthogonalCorrectors 0; consistent yes;\n"
        "  residualControl { p 1e-6; U 1e-6; \"(k|omega)\" 1e-6; } }\n"
        "relaxationFactors { equations { U 0.9; \".*\" 0.9; } }\n")


def _kos(case: Path, timeout: int = 1800) -> tuple[bool, str]:
    cu = windows_to_wsl_path(case)
    cmd = (f"source {BASHRC} && cd '{cu}' && blockMesh > log.blockMesh 2>&1 && "
           "foamRun > log.foamRun 2>&1")
    r = linux_run(cmd, timeout)
    return r.returncode == 0, (r.stderr or r.stdout or "")[-300:]


def yakinsadi_mi(case: Path) -> tuple[bool, int]:
    """SIMPLE residualControl'e ulaştı mı, kaç iterasyonda.

    Yakınsamamış bir koşuyu doğrulama veri noktası saymak, bu projede tekrar tekrar
    yakalanan hatanın aynısıdır: sayı üretildi diye sayı güvenilir sanılır. İlk taramada
    y⁺~97 seviyesi 1500 iterasyonu doldurup yakınsamadı ve %-10.7 "sonuç" olarak raporlandı.
    """
    log = case / "log.foamRun"
    if not log.exists():
        return False, 0
    txt = log.read_text(errors="ignore")
    m = re.search(r"SIMPLE solution converged in (\d+)", txt)
    return (True, int(m.group(1))) if m else (False, txt.count("\nTime = "))


def _oku_cf_ve_yplus(case: Path) -> tuple[float | None, float | None]:
    """x=X_OLCUM istasyonunda yerel Cf ve levha ortalama y⁺."""
    zaman = sorted((d for d in case.iterdir()
                    if d.is_dir() and d.name.replace(".", "", 1).isdigit()
                    and float(d.name) > 0), key=lambda d: float(d.name))
    if not zaman:
        return None, None
    wss = zaman[-1] / "wallShearStress"
    if not wss.exists():
        return None, None
    # wallShearStress boundaryField > levha > value nonuniform List<vector>
    txt = wss.read_text(errors="ignore")
    blok = re.search(r"levha\s*\{(.*?)\}", txt, re.S)
    if not blok:
        return None, None
    vekt = re.findall(r"\(([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\)", blok.group(1))
    if not vekt:
        return None, None
    # yüzey merkezleri sırayla x boyunca; ölçüm istasyonuna en yakın hücreyi al
    n = len(vekt)
    i = min(int(n * X_OLCUM / L_PLATE), n - 1)
    tau = abs(float(vekt[i][0])) * RHO          # OpenFOAM kinematik τ döner
    cf = tau / (0.5 * RHO * U_INF ** 2)
    yp = None
    ypf = zaman[-1] / "yPlus"
    if ypf.exists():
        m = re.search(r"levha\s*\{(.*?)\}", ypf.read_text(errors="ignore"), re.S)
        if m:
            v = [float(x) for x in re.findall(r"[-\d.eE+]+", m.group(1))
                 if re.match(r"^[\d.]", x)]
            if v:
                yp = sum(v) / len(v)
    return cf, yp


def main(hedefler: list[float]) -> int:
    kok = HERE.parent / "_duz_levha"
    kok.mkdir(exist_ok=True)
    re_x = U_INF * X_OLCUM / NU
    cf_ref = cf_referans(re_x)
    sonuc, gorulen_mesh = [], {}
    d99 = delta99()
    for yp_h in hedefler:
        case = kok / f"yp{int(yp_h)}"
        ilk = _ilk_hucre(yp_h)
        ny = hucre_sayisi(ilk)
        if ny is None:
            # δ1 alanın kendisiyle kıyaslanabilir hale geldi — bu y⁺ bu alanda ÜRETİLEMEZ.
            sonuc.append({"yplus_hedef": yp_h, "durum": "ulasilamadi",
                          "ilk_hucre_mm": round(ilk * 1e3, 2),
                          "neden": (f"ilk hücre {ilk * 1e3:.0f} mm; {H_DOMAIN * 1e3:.0f} mm "
                                    f"alanda en az {NY_MIN} hücre ile üretilemez")})
            print(f"[y+ hedef {yp_h:g}] ULAŞILAMADI — ilk hücre {ilk * 1e3:.0f} mm "
                  f"(alan {H_DOMAIN * 1e3:.0f} mm)", flush=True)
            continue
        anahtar = (ny, round(ilk, 9))
        if anahtar in gorulen_mesh:
            # Aynı mesh'i ikinci kez koşup BAĞIMSIZ veri noktası gibi raporlamak,
            # tarama eğrisini sahte çözünürlükle şişirir.
            sonuc.append({"yplus_hedef": yp_h, "durum": "kopya_mesh",
                          "ayni_seviye": gorulen_mesh[anahtar]})
            print(f"[y+ hedef {yp_h:g}] KOPYA — y+={gorulen_mesh[anahtar]:g} ile aynı mesh",
                  flush=True)
            continue
        gorulen_mesh[anahtar] = yp_h
        print(f"[y+ hedef {yp_h:g}] ilk hücre {ilk * 1e6:.1f} µm ({ilk / d99:.2f}·δ99), "
              f"ny={ny} — kuruluyor…", flush=True)
        _yaz(case, yp_h, ny)
        ok, hata = _kos(case)
        if not ok:
            print(f"   ÇÖZÜCÜ DÜŞTÜ: {hata[:120]}", flush=True)
            sonuc.append({"yplus_hedef": yp_h, "durum": "cozucu_dustu", "hata": hata[:200]})
            continue
        yakin, iterasyon = yakinsadi_mi(case)
        if not yakin:
            sonuc.append({"yplus_hedef": yp_h, "durum": "yakinsamadi",
                          "iterasyon": iterasyon, "ny": ny,
                          "neden": "SIMPLE residualControl'e ulasilmadi — Cf veri sayilmaz"})
            print(f"   YAKINSAMADI ({iterasyon} iterasyon) — veri sayılmıyor", flush=True)
            continue
        cf, yp = _oku_cf_ve_yplus(case)
        if cf is None:
            sonuc.append({"yplus_hedef": yp_h, "durum": "cf_okunamadi"})
            print("   Cf OKUNAMADI", flush=True)
            continue
        hata_pct = (cf - cf_ref) / cf_ref * 100
        sonuc.append({"yplus_hedef": yp_h, "yplus_olculen": yp, "Cf": round(cf, 6),
                      "Cf_ref": round(cf_ref, 6), "hata_pct": round(hata_pct, 2),
                      "ny": ny, "iterasyon": iterasyon, "ilk_hucre_mm": round(ilk * 1e3, 3),
                      "ilk_hucre_delta99": round(ilk / d99, 3), "durum": "ok"})
        print(f"   y+={yp if yp is None else round(yp, 1)}  Cf={cf:.5f}  "
              f"ref={cf_ref:.5f}  hata %{hata_pct:+.1f}", flush=True)

    gecerli = [s for s in sonuc if s["durum"] == "ok"]
    out = {
        "vaka": (f"Duz levha cilt-surtunmesi, y+ duyarliligi — U={U_INF} m/s, L={L_PLATE} m, "
                 f"olcum x={X_OLCUM} m (Re_x={re_x:.2e})"),
        "kaynak": "OpenFOAM 11 foamRun/incompressibleFluid, kOmegaSST, 2D blockMesh",
        "referans": {"Cf": round(cf_ref, 6),
                     "bagintisi": "Cf = 0.0592 Re_x^(-1/5) (1/7-kuvvet, Schlichting)",
                     "gecerlilik": "5e5 < Re_x < 1e7"},
        "delta99_mm": round(delta99() * 1e3, 2),
        "seviyeler": sonuc,
        "verdikt": _verdikt(gecerli),
        "_not": ("Bu capa MiniHawk kampanyalarinin NITEL bulgusunu ('y+ yuksek, surtunme "
                 "cozulmuyor') NICEL hale getirir: verilen y+'de Cf hatasi yuzde kac."),
        "_uretim": "Üretim: python experiments/duz_levha_cf.py",
    }
    (HERE.parent / "duz_levha_cf.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + out["verdikt"])
    print("-> duz_levha_cf.json")
    return 0 if gecerli else 1


def _verdikt(gecerli: list[dict]) -> str:
    if not gecerli:
        return "⚠️ Hicbir seviye tamamlanmadi — capa uretilemedi."

    def _yp(s):
        return s.get("yplus_olculen") or s["yplus_hedef"]
    iyi = [s for s in gecerli if abs(s["hata_pct"]) <= 5]
    en_kotu = max(gecerli, key=lambda s: abs(s["hata_pct"]))
    if len(iyi) == len(gecerli):
        return (f"GECTI — olculen tum y+ degerlerinde Cf hatasi %5 altinda (en kotu "
                f"y+={_yp(en_kotu):.0f}: %{en_kotu['hata_pct']:+.1f}). Duvar fonksiyonu "
                "bu bantta cilt-surtunmesini dogru veriyor.")
    bant = [s for s in gecerli if 30 <= _yp(s) <= 300]
    bant_iyi = [s for s in bant if abs(s["hata_pct"]) <= 5]
    return (f"⚠️ y+ DUYARLI: {len(iyi)}/{len(gecerli)} seviye %5 bandinda; en kotu "
            f"y+={_yp(en_kotu):.0f} olcumunde Cf hatasi %{en_kotu['hata_pct']:+.1f}. "
            f"Duvar-fonksiyonu gecerlilik bandinda (30-300) {len(bant_iyi)}/{len(bant)} "
            "seviye %5 icinde — bandin disina cikildikca surtunme sistematik sapar.")


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    args = [float(a) for a in sys.argv[1:]] or [1, 30, 100, 300, 1000]
    sys.exit(main(args))
