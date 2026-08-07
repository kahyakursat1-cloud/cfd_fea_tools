"""Silindir girdap dökülmesi — ZAMAN-ÇÖZÜNÜR yolun kanonik çapası (Re=100).

NEDEN BU VAKA: v1.2'de URANS case yazıcısı ve frekans ölçümü eklendi ama
ikisi de yalnız SENTETİK sinyalde doğrulanmıştı. Gerçek bir çözücü koşusunda
sınanmadan "URANS yolu var" demek, bu deponun reddettiği türden bir iddia
olurdu.

Silindir bunun için doğru vaka: Re=100'de girdap dökülmesi kararlıdır, tek
frekanslıdır ve Strouhal sayısı DENEYSEL olarak bilinir --- Williamson (1989)
Re=100 için St=0,164 verir. Yani ölçtüğümüz frekansın doğru olup olmadığını
söyleyecek bağımsız bir referans var.

Re=100 LAMİNERDİR: türbülans modeli yoktur, dolayısıyla bu bir URANS değil
zaman-çözünür laminer çözümdür. Ölçtüğü şey model-form hatası değil, ZAMAN
AYRIKLAŞTIRMASININ ve akış çözümünün doğruluğudur. Bu ayrım önemli ve kanıt
dosyasında yazılıdır --- vaka `model_form_bandi`'ye çapa olarak GİRMEZ.

Boyutsuz kurulum: D=1 m, U=1 m/s, nu=0,01 → Re=100. Periyot 1/St ≈ 6,1 s.

    python experiments/silindir_vorteks.py           # tam koşu
    python experiments/silindir_vorteks.py --oku     # diskteki çözümü oku

Çıktı: silindir_vorteks.json (kanıt)
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import windows_to_wsl_path  # noqa: E402
from analysis.openfoam_runner import (  # noqa: E402
    CFDCase,
    _foam_header,
    _write_control_dict,
    _write_fv_schemes,
    _write_fv_solution,
)
from urans_kapisi import salinim_olc  # noqa: E402

D = 1.0            # silindir çapı (m)
U = 1.0            # serbest akım (m/s)
NU = 0.01          # m²/s → Re = U·D/nu = 100
RE = U * D / NU
# St DENEYSELDIR: Williamson, "Oblique and parallel modes of vortex shedding in
# the wake of a circular cylinder at low Reynolds numbers", J. Fluid Mech. 206
# (1989) — paralel-dokulme duzeltmesiyle Re=100'de St = 0.164.
ST_DENEY = 0.164
ST_KAYNAK = ("Williamson, J. Fluid Mech. 206 (1989) — DENEYSEL, "
             "paralel-dökülme düzeltmeli")
# Cd SAYISALDIR, deneysel DEGIL. Re=100'de dogrudan kuvvet olcumu zordur
# (Tritton 1959 verilerinde sacilma yuksek); yerlesik referans iki spektral/DNS
# calismasindan gelir: Henderson, "Details of the drag curve near the onset of
# vortex shedding", Phys. Fluids 7 (1995) ~1.35; Park, Kwon & Choi, KSME Int. J.
# 12 (1998) ~1.33. Bu AYRIM onemli — capa raporu St'yi deneysel, Cd'yi sayisal
# referansa karsi olctugunu SOYLEMELI.
CD_DENEY = 1.33
CD_KAYNAK = ("Park, Kwon & Choi, KSME Int. J. 12 (1998) ≈1.33; Henderson, "
             "Phys. Fluids 7 (1995) ≈1.35 — SAYISAL (DNS/spektral) referans, "
             "deneysel değil; bant ±%5 alınır")
R_FAR = 20.0       # far-field yarıçapı (D katı)
N_RADYAL, N_CEVRE = 70, 60     # blok başına; toplam 4·70·60 = 16.800 hücre
RADYAL_GRADING = 40.0          # duvara sıkıştırma (son/ilk hücre oranı)
PERIYOT_GECIS, PERIYOT_ISTAT = 6, 16
BASHRC = "/opt/openfoam11/etc/bashrc"


def _blockmesh() -> str:
    """Silindir etrafında 4 bloklu O-grid (2B, tek hücre kalınlık).

    Köşeler 45°+90k'de: blok kenarları akış eksenine denk gelmez, böylece
    dökülme simetri düzlemine kilitlenmez. Yapılandırılmış O-grid seçildi
    çünkü duvar-normali sıkıştırma doğrudan denetlenebilir --- girdap
    dökülmesinde ayrılma noktasının çözünürlüğü frekansı belirler.
    """
    ri, ro, z = D / 2.0, R_FAR * D / 2.0, 0.05 * D
    aci = [math.radians(45 + 90 * k) for k in range(4)]
    v = []
    for zz in (-z / 2, z / 2):
        for r in (ri, ro):
            for a in aci:
                # DUZLEM x-z, KALINLIK y. Kanonik forceCoeffs yazicisi kaldirma
                # yonunu (-fz, 0, fx) ile x-z duzleminde aliyor (ucak
                # konvansiyonu: y aciklik ekseni). Ilk kurulum x-y duzlemindeydi
                # ve Cl TAM SIFIR cikti — kuvvet `empty` yonunde olculuyordu.
                # Mesh'i konvansiyona uydurmak, yaziciyi dallandirmaktan iyi.
                v.append(f"({r * math.cos(a):.8f} {zz:.8f} {r * math.sin(a):.8f})")
    # indis: z0-ic 0..3, z0-dis 4..7, z1-ic 8..11, z1-dis 12..15
    bloklar, arclar, ic_yuz, on, arka = [], [], [], [], []
    giris, cikis, ust_alt = [], [], []
    for k in range(4):
        k2 = (k + 1) % 4
        i0, i1, o0, o1 = k, k2, 4 + k, 4 + k2
        j0, j1, p0, p1 = 8 + k, 8 + k2, 12 + k, 12 + k2
        # KOSE SIRASI: alt yuz normali +y (kalinlik ekseni) olmali. Duzlem
        # x-y'den x-z'ye tasinirken el degisti ve blockMesh "inside-out" ile
        # dustu; sira ters cevrildi. x1 yonu RADYAL kalir (grading orada).
        bloklar.append(f"hex ({i0} {i1} {o1} {o0} {j0} {j1} {p1} {p0}) "
                       f"({N_CEVRE} {N_RADYAL} 1) "
                       f"simpleGrading (1 {RADYAL_GRADING:g} 1)")
        for r, a_, b_, c_, d_ in ((ri, i0, i1, j0, j1), (ro, o0, o1, p0, p1)):
            am = (aci[k] + aci[k2]) / 2 if k < 3 else aci[k] + math.radians(45)
            for x0, x1, zz in ((a_, b_, -z / 2), (c_, d_, z / 2)):
                arclar.append(f"arc {x0} {x1} ({r * math.cos(am):.8f} "
                              f"{zz:.8f} {r * math.sin(am):.8f})")
        ic_yuz.append(f"({i0} {j0} {j1} {i1})")
        # DIŞ ÇEMBER ÜÇE BÖLÜNÜR. Tek yama + `inletOutlet`/`totalPressure`
        # akımı SÜRDÜREMEDİ: en hızlı akış 0,074 m/s'ye düştü (serbest akım
        # 1 m/s), Cd 2,29'dan negatife indi — akım silindirin etrafında durdu.
        # Ölçüldü, tahmin edilmedi. Standart dış-aero kurulumu girişi ve çıkışı
        # AYIRIR; üst/alt kayma (slip) sınırıdır.
        (giris if k == 1 else cikis if k == 3 else ust_alt).append(
            f"({o0} {o1} {p1} {p0})")
        on.append(f"({j0} {j1} {p1} {p0})")
        arka.append(f"({i0} {o0} {o1} {i1})")
    return (_foam_header("dictionary", "blockMeshDict", "system") +
            "convertToMeters 1;\nvertices\n(\n" + "\n".join(v) + "\n);\n"
            "blocks\n(\n" + "\n".join(bloklar) + "\n);\n"
            "edges\n(\n" + "\n".join(arclar) + "\n);\n"
            "boundary\n(\n"
            "  silindir { type wall;  faces (" + " ".join(ic_yuz) + "); }\n"
            "  giris    { type patch; faces (" + " ".join(giris) + "); }\n"
            "  cikis    { type patch; faces (" + " ".join(cikis) + "); }\n"
            "  ustalt   { type patch; faces (" + " ".join(ust_alt) + "); }\n"
            "  yanlar   { type empty; faces (" + " ".join(on + arka) + "); }\n"
            ");\nmergePatchPairs ();\n")


def _alanlar(case: Path) -> None:
    """U ve p — laminer, türbülans alanı YOK (Re=100)."""
    (case / "0").mkdir(parents=True, exist_ok=True)
    (case / "0" / "U").write_text(
        _foam_header("volVectorField", "U", "0") +
        "dimensions [0 1 -1 0 0 0 0];\n"
        # SİMETRİ KIRICI (%5 çapraz bileşen). Tümüyle simetrik mesh + simetrik
        # başlangıç + simetrik sınırda girdap dökülmesi HİÇ başlamaz: ilk
        # koşuda 50 s boyunca Cl genliği 1e-22 kaldı. Kármán caddesi bir
        # KARARSIZLIKTIR ve tetikleyici ister; bu bileşen geçiş penceresinde
        # kendiliğinden kaybolur.
        f"internalField uniform ({U} 0 {0.05 * U});\n"
        "boundaryField\n{\n"
        "  silindir { type noSlip; }\n"
        f"  giris    {{ type fixedValue; value uniform ({U} 0 0); }}\n"
        f"  cikis    {{ type inletOutlet; inletValue uniform ({U} 0 0); "
        f"value uniform ({U} 0 0); }}\n"
        "  ustalt   { type slip; }\n"
        "  yanlar   { type empty; }\n}\n")
    (case / "0" / "p").write_text(
        _foam_header("volScalarField", "p", "0") +
        "dimensions [0 2 -2 0 0 0 0];\n"
        "internalField uniform 0;\n"
        "boundaryField\n{\n"
        "  silindir { type zeroGradient; }\n"
        "  giris    { type zeroGradient; }\n"
        "  cikis    { type fixedValue; value uniform 0; }\n"
        "  ustalt   { type slip; }\n"
        "  yanlar   { type empty; }\n}\n")


def _sabitler(case: Path) -> None:
    (case / "constant").mkdir(parents=True, exist_ok=True)
    (case / "constant" / "momentumTransport").write_text(
        _foam_header("dictionary", "momentumTransport", "constant") +
        "simulationType laminar;\n")
    (case / "constant" / "physicalProperties").write_text(
        _foam_header("dictionary", "physicalProperties", "constant") +
        f"viscosityModel constant;\nnu [0 2 -1 0 0 0 0] {NU};\n")


def kur(case: Path, dt: float, son_s: float) -> None:
    """Case'i yaz — sözlükler KANONİK yazıcıdan gelir (iki-hızlı katman yok)."""
    (case / "system").mkdir(parents=True, exist_ok=True)
    (case / "system" / "blockMeshDict").write_text(_blockmesh())
    _alanlar(case)
    _sabitler(case)
    c = CFDCase(name=case.name, stl_path=str(case), velocity=U, rho=1.0, nu=NU,
                transient=True, delta_t=dt, end_time_s=son_s, n_outer=2,
                max_courant=2.0)
    _write_control_dict(case, c, "silindir", D)
    _write_fv_schemes(case, transient=True)
    _write_fv_solution(case, compressible=False, transient=True, n_outer=2)


def kos(case: Path, timeout: int = 10800) -> tuple[bool, str]:
    cu = windows_to_wsl_path(case)
    r = linux_run(f"source {BASHRC} && cd '{cu}' && "
                  "blockMesh > log.blockMesh 2>&1 && "
                  "checkMesh > log.checkMesh 2>&1; "
                  "foamRun > log.foamRun 2>&1", timeout)
    return r.returncode == 0, (r.stderr or r.stdout or "")[-300:]


def _coeffs(case: Path) -> tuple[list[float], list[float], list[float]]:
    """forceCoeffs.dat → (t, Cd, Cl). Sütun düzeni başlıktan okunur."""
    ff = sorted(case.glob("postProcessing/forceCoeffs1/*/forceCoeffs.dat"))
    if not ff:
        return [], [], []
    t, cd, cl = [], [], []
    icd = icl = None
    for satir in ff[-1].read_text(errors="ignore").splitlines():
        s = satir.strip()
        if s.startswith("#"):
            basliklar = s.lstrip("# ").split()
            if "Cd" in basliklar:
                icd, icl = basliklar.index("Cd"), basliklar.index("Cl")
            continue
        p = s.split()
        if icd is None or len(p) <= max(icd, icl):
            continue
        try:
            t.append(float(p[0])); cd.append(float(p[icd])); cl.append(float(p[icl]))
        # sessiz-yutma: kabul — yarım yazılmış son satır olağandır; hiçbiri
        # okunamazsa aşağıdaki `if not t` hükmü "ölçülemedi" der
        except ValueError:
            continue
    return t, cd, cl


def main(argv: list[str]) -> int:
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    case = HERE.parent / "_silindir_vorteks"
    # Beklenen periyot DENEYSEL St'den; koşu süresi ona göre boyutlanır.
    periyot = D / (ST_DENEY * U)
    dt = periyot / 100.0
    son = (PERIYOT_GECIS + PERIYOT_ISTAT) * periyot
    print(f"Re={RE:.0f}  beklenen periyot {periyot:.3f} s  dt={dt:.4f}  "
          f"süre={son:.1f} s ({int(son / dt)} adım)", flush=True)

    t0 = time.time()
    if "--oku" in argv and (case / "log.foamRun").exists():
        ok, hata = True, ""
    else:
        kur(case, dt, son)
        ok, hata = kos(case)
    if not ok:
        print(f"ÇÖZÜCÜ DÜŞTÜ: {hata[:200]}", flush=True)
        (HERE.parent / "silindir_vorteks.json").write_text(json.dumps(
            {"durum": "cozucu_dustu", "hata": hata[:400]}, indent=2,
            ensure_ascii=False), encoding="utf-8")
        return 1

    t, cd, cl = _coeffs(case)
    if not t:
        print("forceCoeffs okunamadı", flush=True)
        return 1
    olcum = salinim_olc(t, cl, gecis_orani=PERIYOT_GECIS / (PERIYOT_GECIS + PERIYOT_ISTAT))
    st = (olcum["frekans_hz"] * D / U) if olcum.get("olculdu") else None
    # A_REF DÜZELTMESİ. Kanonik yazıcı forceCoeffs'a Aref=lref² veriyor (3B
    # araç için doğru: bbox karesi). 2B silindirde doğru referans D×SPAN'dır ve
    # span blockMesh'teki tek-hücre kalınlığıdır (0,05·D). Ölçek uygulanmazsa
    # Cd yirmi kat küçük çıkar — ilk raporda 0,066 yazdı, literatür 1,33.
    span = 0.05 * D
    olcek = (D * D) / (D * span)
    cd_ort = sum(cd[len(cd) // 3:]) / len(cd[len(cd) // 3:]) * olcek
    out = {
        "vaka": f"Silindir girdap dökülmesi — Re={RE:.0f} (2B laminer, D={D} m, U={U} m/s)",
        "kaynak": "OpenFOAM 11 foamRun/incompressibleFluid, ZAMAN-ÇÖZÜNÜR (backward/PIMPLE)",
        "referans": {"St": ST_DENEY, "kaynak": ST_KAYNAK,
                     "St_tipi": "DENEYSEL",
                     "Cd": CD_DENEY, "Cd_kaynak": CD_KAYNAK,
                     "Cd_tipi": "SAYISAL (DNS/spektral) — deneysel değil"},
        "olculen": {"St": round(st, 5) if st else None,
                    "Cd_ortalama": round(cd_ort, 4),
                    "Cl_genlik": round(olcum.get("genlik", 0.0) * olcek, 5),
                    "_aref_olcegi": olcek,
                    "_aref_notu": ("kanonik yazici Aref=lref^2 verir (3B bbox "
                                   "karesi); 2B silindirde dogru referans D x span")},
        "sapma_pct": {"St": round((st - ST_DENEY) / ST_DENEY * 100, 2) if st else None,
                      "Cd": round((cd_ort - CD_DENEY) / CD_DENEY * 100, 2)},
        "salinim_olcumu": olcum,
        "kurulum": {"hucre": 4 * N_RADYAL * N_CEVRE, "dt_s": dt,
                    "sure_s": son, "adim": int(son / dt),
                    "gecis_periyodu": PERIYOT_GECIS,
                    "istatistik_periyodu": PERIYOT_ISTAT},
        "_kapsam": ("Re=100 LAMINERDIR: turbulans modeli yok. Bu vaka ZAMAN "
                    "ayriklastirmasinin ve akis cozumunun dogrulugunu olcer, "
                    "MODEL-FORM hatasini DEGIL — model_form_bandi'ye capa olarak "
                    "GIRMEZ."),
        "_neden": ("URANS case yazicisi ve frekans olcumu v1.2'de eklendi ama "
                   "yalniz SENTETIK sinyalde dogrulanmisti. Gercek cozucu "
                   "kosusunda sinanmadan 'URANS yolu var' demek, bu deponun "
                   "reddettigi turden bir iddia olurdu."),
        "_uretim": "Üretim: python experiments/silindir_vorteks.py",
        "_sure_s": round(time.time() - t0, 1),
    }
    out["verdikt"] = _verdikt(out)
    # ORTAM DAMGASI URETIM ANINDA: sonradan eklenen damga, sayinin hangi
    # yiginda DOGDUGUNU degil en son ne zaman bakildigini soyler.
    import ortam
    ortam.damgala(out)
    (HERE.parent / "silindir_vorteks.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSt = {st}  (deney {ST_DENEY}) → %{out['sapma_pct']['St']}")
    print(f"Cd = {cd_ort:.4f} (literatür {CD_DENEY}) → %{out['sapma_pct']['Cd']}")
    print(out["verdikt"])
    print("-> silindir_vorteks.json")
    return 0


def _verdikt(o: dict) -> str:
    st = o["olculen"]["St"]
    if st is None:
        return ("❌ Girdap dökülmesi ÖLÇÜLEMEDİ — çözüm salınmıyor: "
                + str(o["salinim_olcumu"].get("neden")))
    s = abs(o["sapma_pct"]["St"])
    sc = abs(o["sapma_pct"]["Cd"])
    if s <= 10 and sc <= 15:
        return (f"✅ Zaman-çözünür yol DOĞRULANDI: St={st} vs Williamson "
                f"{ST_DENEY} → %{o['sapma_pct']['St']}; Cd sapması "
                f"%{o['sapma_pct']['Cd']}. Frekans ölçümü ve case yazıcısı "
                "gerçek çözücü koşusunda çalışıyor.")
    return (f"⚠️ St={st} vs deney {ST_DENEY} → %{o['sapma_pct']['St']} "
            f"(Cd %{o['sapma_pct']['Cd']}) — ağ ya da zaman çözünürlüğü "
            "yetersiz olabilir; sapma bu haliyle yayımlanmaz")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
