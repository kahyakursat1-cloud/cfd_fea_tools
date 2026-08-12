"""Silindir girdap dökülmesi — ölçek-ÇÖZÜNÜRLÜKLÜ (DES) çapa.

NEDEN: 3B URANS koşusu kendi açıklamamızı çürüttü. Üçüncü boyut GEOMETRİK
olarak eklendi ama fizik eklenmedi --- span-yönü dekorelasyon oluşmadı ($C_L$
salınım genliği yalnız %2,6 düştü) çünkü URANS dalgalanmayı MODELLER, çözmez.
Teşhis boyut değil ÇÖZÜNÜRLÜK SINIFI'ydı ve yol haritası oradan beri
"kalan iş: ölçek-çözünürlüklü bir çapa" diyor. Bu koşu o iştir.

EŞLEŞİK KARŞILAŞTIRMA KORUNUR. Türbülans modeli `kOmegaSSTDES`: URANS
koşularının temel modeliyle AYNI (kOmegaSST), değişen tek şey çözünürlük
sınıfı. Başka bir model ailesine geçilseydi (ör. Smagorinsky) sapma
değişiminin modelden mi çözünürlükten mi geldiği söylenemezdi.

SINANAN İDDİA --- koşudan ÖNCE yazılıyor:
    İ1  Span dekorelasyonu OLUŞUR: $C_L$ salınım genliği URANS'a göre
        BELİRGİN düşer. (URANS 2B→3B geçişinde yalnız %2,6 düştü; burada
        eşik olarak %20 düşüş önceden sabitleniyor.)
    İ2  $St$ deneysel platoya (0,19--0,21) yaklaşır.
    İ3  $C_d$ deneysel değere (≈1,2) yaklaşır --- URANS 3B'de %-27 sapmıştı.
İ1 tutup İ2/İ3 tutmazsa mekanizma çalışmış ama nicelik tutmamıştır ve bu
SÖYLENİR. İ1 tutmazsa çözünürlük hâlâ yetersizdir ve o da söylenir.

AĞ: `silindir_vorteks._blockmesh` yine TEK kaynak. DES için iki şey değişir ---
duvarda y⁺≈1 (DES'in RANS kolu çözünür olmalı) ve izde DÜZGÜN radyal dağılım.
Dağılım `des_fizibilite` bütçesinden TÜRETİLİR, elle yazılmaz: iki dosyanın
ayrışması, bütçenin ölçtüğü koşudan başka bir koşu koşmak demek olurdu.

    python experiments/silindir_des_3b.py --duman   # 1 periyot, kaba: kurulum sınaması
    python experiments/silindir_des_3b.py           # tam koşu (~16 saat)
    python experiments/silindir_des_3b.py --oku     # diskteki çözümü oku
Çıktı: silindir_des_3b.json
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from basamak_ayrilma import yplus_olc as yplus_olc_ortak  # noqa: E402
from des_fizibilite import butce  # noqa: E402
from silindir_urans import (  # noqa: E402
    CD_DENEY,
    CD_KAYNAK,
    NU,
    RE,
    ST_BANDI,
    ST_DENEY,
    ST_KAYNAK,
    YPLUS_BANDI,
    _alanlar,
    _foam_header,
)
from silindir_vorteks import R_FAR, D, U, _blockmesh, _coeffs  # noqa: E402

from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import windows_to_wsl_path  # noqa: E402
from analysis.openfoam_runner import (  # noqa: E402
    OF_ENV_PREFIX,
    CFDCase,
    _write_control_dict,
    _write_fv_schemes,
    _write_fv_solution,
)
from urans_kapisi import salinim_olc  # noqa: E402

DZ_D = 0.05                 # bütçede boş belleğe SIĞAN en ince çözünürlük
CEKIRDEK = 4
PERIYOT_GECIS, PERIYOT_ISTAT = 6, 16
GENLIK_DUSUS_ESIGI = 20.0   # İ1: önceden sabitlenen eşik [%]
KANIT = HERE.parent / "silindir_des_3b.json"
CASE_KOK = HERE.parent / "_silindir_des"


def _radyal_grading(b: dict) -> tuple[int, str]:
    """Bütçenin üç bölgesini blockMesh çok-bölgeli sözdizimine çevir.

    (uzunluk-kesri  hücre-kesri  blok-içi-oran) üçlüleri. Oranlar SON/İLK
    hücre oranıdır --- OpenFOAM'ın `simpleGrading` tanımı budur.
    """
    # Δz BUTCENIN KENDI SATIRINDAN gelir, modul sabitinden DEGIL: duman
    # kosusu farkli bir Δz kullaniyor ve sabit okunsaydi ag ile butce
    # AYRISIRDI — yani butcenin olctugu kosudan baska bir kosu koşulurdu.
    dz = b["dz_D"] * D
    r = b["radyal_bolgeler"]
    h0 = b["ilk_hucre_m"]
    toplam = R_FAR * D / 2.0 - D / 2.0
    l1 = r["sikistirma_kalinlik_m"]
    r1_son = D / 2.0 + l1
    l2 = max(0.0, 5.0 * D - r1_son)
    l3 = toplam - l1 - l2
    n1, n2, n3 = r["n_sikistirma"], r["n_duzgun"], r["n_disa"]
    n = n1 + n2 + n3
    # Blok-ici oranlar: 1. bolge h0'dan dz'ye, 3. bolge dz'den disa buyume
    o1 = dz / h0
    o3 = (1.10 ** max(0, n3 - 1)) if n3 else 1.0
    parcalar = [(l1 / toplam, n1 / n, o1), (l2 / toplam, n2 / n, 1.0),
                (l3 / toplam, n3 / n, o3)]
    g = " ".join(f"({a:.6f} {c:.6f} {o:.6f})" for a, c, o in parcalar if a > 0)
    return n, f"({g})"


def _sabitler(case: Path) -> None:
    """DES sözlüğü — temel model URANS ile AYNI (kOmegaSST)."""
    (case / "constant").mkdir(parents=True, exist_ok=True)
    (case / "constant" / "momentumTransport").write_text(
        _foam_header("dictionary", "momentumTransport", "constant") +
        "simulationType LES;\nLES\n{\n"
        "    model           kOmegaSSTDES;\n"
        "    turbulence      on;\n    printCoeffs     on;\n"
        # maxDeltaxyz yapilandirilmis O-grid'de dogru olcudur: cubeRootVol
        # cok-en-boy-oranli duvar hucrelerinde filtre genisligini KUCUK
        # gosterir ve DES'i duvarda erken LES kipine sokar (MSD/GIS).
        "    delta           maxDeltaxyz;\n"
        "    maxDeltaxyzCoeffs { deltaCoeff 1; }\n"
        "}\n")
    (case / "constant" / "physicalProperties").write_text(
        _foam_header("dictionary", "physicalProperties", "constant") +
        f"viscosityModel constant;\nnu [0 2 -1 0 0 0 0] {NU:.8g};\n")


def kur(case: Path, dt: float, son_s: float, dz_D: float = DZ_D) -> dict:
    b = butce(dz_D, bos_gb=1e9)
    n_rad, grading = _radyal_grading(b)
    span = math.pi * D
    nz = b["n_span"]
    (case / "system").mkdir(parents=True, exist_ok=True)
    (case / "system" / "blockMeshDict").write_text(
        _blockmesh(span=span, nz=nz, cyclic=True, n_radyal=n_rad,
                   radyal_grading=grading, n_cevre=b["n_cevre"] // 4))
    _alanlar(case)
    _sabitler(case)
    for f in (case / "0").iterdir():
        t = f.read_text(encoding="utf-8")
        for eski in ("  yanlar   { type empty; }\n", "  yanlar { type empty; }\n"):
            t = t.replace(eski, "  on   { type cyclic; }\n"
                                "  arka { type cyclic; }\n")
        f.write_text(t, encoding="utf-8")
    c = CFDCase(name=case.name, stl_path=str(case), velocity=U, rho=1.0, nu=NU,
                transient=True, delta_t=dt, end_time_s=son_s, n_outer=2,
                max_courant=2.0)
    _write_control_dict(case, c, "silindir", D)
    _write_fv_schemes(case, transient=True)
    _write_fv_solution(case, compressible=False, transient=True, n_outer=2)
    (case / "system" / "decomposeParDict").write_text(
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n"
        '    class dictionary;\n    location "system";\n'
        "    object decomposeParDict;\n}\n"
        f"numberOfSubdomains {CEKIRDEK};\nmethod scotch;\n")
    return {"dz_D": dz_D, "n_radyal": n_rad, "n_span": nz,
            "n_cevre": b["n_cevre"], "hucre_kestirim": b["hucre"],
            "ilk_hucre_m": b["ilk_hucre_m"], "grading": grading}


def kos(case: Path, timeout: int = 86400) -> tuple[bool, str]:
    """Ortam KANONİK ön ekten; `HWLOC_COMPONENTS=-gl` olmadan mpirun asılır."""
    cu = windows_to_wsl_path(case)
    r = linux_run(
        f"{OF_ENV_PREFIX} cd '{cu}' && "
        "blockMesh > log.blockMesh 2>&1 && "
        "checkMesh > log.checkMesh 2>&1; "
        "decomposePar -force > log.decomposePar 2>&1 && "
        f"mpirun -np {CEKIRDEK} foamRun -parallel > log.foamRun 2>&1 && "
        "reconstructPar -latestTime > log.reconstructPar 2>&1", timeout)
    return r.returncode == 0, (r.stderr or r.stdout or "")[-500:]


def _verdikt(o: dict, urans3b: dict | None) -> str:
    """Önceden sabitlenen üç iddia tek tek sınanır."""
    st = o["olculen"]["St"]
    if st is None:
        return ("❌ Girdap dökülmesi ÖLÇÜLEMEDİ: "
                + str(o["salinim_olcumu"].get("neden")))
    if not urans3b:
        return (f"⚠️ DES koştu (St={st}) ama 3B URANS kanıtı yok — İ1 "
                "SINANAMADI (silindir_urans_3b.json gerekli)")
    gu = (urans3b.get("olculen") or {}).get("Cl_genlik")
    gd = o["olculen"]["Cl_genlik"]
    dusus = 100.0 * (gu - gd) / gu if gu else None
    d_st, d_cd = o["sapma_pct"]["St"], o["sapma_pct"]["Cd"]
    u_st = (urans3b.get("sapma_pct") or {}).get("St")
    u_cd = (urans3b.get("sapma_pct") or {}).get("Cd")
    i1 = dusus is not None and dusus >= GENLIK_DUSUS_ESIGI
    i2 = u_st is not None and abs(d_st) < abs(u_st)
    i3 = u_cd is not None and abs(d_cd) < abs(u_cd)
    bas = (f"DES (Δz/D={DZ_D}, {o['kurulum']['n_span']} span hücresi): "
           f"St={st} (%{d_st:+.0f}), Cd={o['olculen']['Cd_ortalama']} "
           f"(%{d_cd:+.0f}), C_L genliği {gd} (URANS 3B {gu}, "
           f"düşüş %{dusus:.1f}) | İ1={i1} İ2={i2} İ3={i3}")
    if i1 and i2 and i3:
        return ("✅ ÜÇ İDDİA DA TUTTU: " + bas + ". Çözünürlük sınıfı teşhisi "
                "SINANDI ve tuttu — dekorelasyon DES ile oluştu ve iki sapma "
                "birden düzeldi.")
    if i1:
        return ("⚠️ MEKANİZMA ÇALIŞTI, NİCELİK TUTMADI: " + bas +
                f". Salınım genliği eşiği (%{GENLIK_DUSUS_ESIGI}) aşarak "
                "düştü, yani span dekorelasyonu bu kez OLUŞTU; ancak "
                f"{'St' if not i2 else ''}{'/' if not i2 and not i3 else ''}"
                f"{'Cd' if not i3 else ''} URANS'a göre düzelmedi. Teşhis "
                "doğru yönde ama bu çözünürlük yetmiyor.")
    return ("❌ DEKORELASYON YİNE OLUŞMADI: " + bas +
            f". C_L genliği eşiği (%{GENLIK_DUSUS_ESIGI}) aşacak kadar "
            "düşmedi. Δz/D bu değerde hâlâ yetersiz ya da engel span "
            "çözünürlüğünden başka bir yerde.")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    duman = "--duman" in sys.argv
    oku = "--oku" in sys.argv
    dz = 0.10 if duman else DZ_D
    periyot_s = D / (ST_DENEY * U)
    b = butce(dz, bos_gb=1e9)
    dt = b["dt_s"]
    periyot = 1 if duman else (PERIYOT_GECIS + PERIYOT_ISTAT)
    son_s = periyot * periyot_s

    case = CASE_KOK / ("duman" if duman else "tam")
    if not oku:
        case.mkdir(parents=True, exist_ok=True)
        kurulum = kur(case, dt, son_s, dz)
        print(f"kurulum: Δz/D={dz} · {kurulum['hucre_kestirim']:,} hücre "
              f"(kestirim) · dt={dt}s · {periyot} periyot = {son_s:.1f}s",
              flush=True)
        t0 = time.time()
        ok, mesaj = kos(case)
        gecen = time.time() - t0
        print(f"koşu {'BİTTİ' if ok else 'DÜŞTÜ'} — {gecen / 3600:.2f} saat",
              flush=True)
        if not ok:
            print(mesaj)
            return 1
    else:
        kurulum = {"dz_D": dz}
        gecen = 0.0

    t, cd_seri, cl_seri = _coeffs(case)
    if not t:
        print("forceCoeffs okunamadı", flush=True)
        return 1
    sal = salinim_olc(t, cl_seri,
                      gecis_orani=PERIYOT_GECIS / (PERIYOT_GECIS + PERIYOT_ISTAT))
    st = (round(sal["frekans_hz"] * D / U, 5) if sal.get("olculdu") else None)
    # A_REF OLCEGI URANS 3B ILE AYNI OLMALI: kanonik yazici Aref=lref^2 verir,
    # silindirde dogru referans D x Lz'dir. Olcek uygulanmazsa DES ile URANS
    # farkli referans alanlarda karsilastirilir ve "genlik dustu" hukmu
    # olcek farkindan gelir — yani tam da olculmek istenen sey kirlenir.
    span = math.pi * D
    olcek = (D * D) / (D * span)
    kuyruk = cd_seri[len(cd_seri) // 3:]
    cd = round(sum(kuyruk) / len(kuyruk) * olcek, 4)
    yp = (yplus_olc_ortak(case) or {}).get("silindir")

    o = {
        "vaka": f"Silindir girdap dökülmesi — DES (Re={RE:.0f}, Δz/D={dz})",
        "kaynak": "kOmegaSSTDES — URANS çapalarının TEMEL MODELİYLE aynı",
        "sinanan_iddia": {
            "I1": (f"Span dekorelasyonu OLUŞUR: C_L genliği URANS 3B'ye göre "
                   f"≥%{GENLIK_DUSUS_ESIGI} düşer"),
            "I2": "St deneysel platoya yaklaşır (URANS 3B'den daha az sapma)",
            "I3": "Cd deneysel değere yaklaşır (URANS 3B'den daha az sapma)",
            "_not": "İddialar koşudan ÖNCE modül docstring'inde sabitlendi.",
        },
        "referans": {"St": ST_DENEY, "St_bandi": list(ST_BANDI),
                     "kaynak": ST_KAYNAK, "Cd": CD_DENEY,
                     "Cd_kaynak": CD_KAYNAK},
        "olculen": {"St": st, "Cd_ortalama": cd,
                    "Cl_genlik": round(sal.get("genlik", 0.0) * olcek, 5),
                    "yplus": yp, "_aref_olcegi": olcek},
        "sapma_pct": {
            "St": round(100 * (st - ST_DENEY) / ST_DENEY, 2) if st else None,
            "Cd": round(100 * (cd - CD_DENEY) / CD_DENEY, 2) if cd else None},
        "salinim_olcumu": sal,
        "kurulum": {**kurulum, "dt_s": dt, "periyot": periyot,
                    "sure_s": son_s, "cekirdek": CEKIRDEK,
                    "yplus_bandi": list(YPLUS_BANDI),
                    "model": "kOmegaSSTDES", "delta": "maxDeltaxyz"},
        "_sure_saat": round(gecen / 3600, 2),
        "_kapsam": ("Tek Re (140.000), tek span uzunlugu (piD), tek "
                    "cozunurluk. DES sonucu span uzunluguna ve Δz'ye "
                    "duyarlidir; bu kosu o duyarliligi OLCMEZ."),
        "_uretim": "Üretim: python experiments/silindir_des_3b.py",
    }
    u3 = HERE.parent / "silindir_urans_3b.json"
    urans3b = json.loads(u3.read_text(encoding="utf-8")) if u3.exists() else None
    o["verdikt"] = _verdikt(o, urans3b)

    import ortam
    ortam.damgala(o)
    hedef = KANIT if not duman else KANIT.with_name("silindir_des_3b_duman.json")
    hedef.write_text(json.dumps(o, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print("\n" + o["verdikt"])
    print(f"-> {hedef.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
