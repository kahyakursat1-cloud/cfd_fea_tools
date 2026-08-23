"""Silindir girdap dökülmesi — ÜÇ BOYUTLU türbülanslı URANS çapası.

NEDEN: 2B URANS çapası (`silindir_urans`) mekanizmayı doğruladı ama fiziği
tutturamadı --- $St$ deneysel platonun (0,19-0,21) %37 üstünde, $C_d$ ise
%14 altında çıktı. Açıklama yazıldı: 2B kurulum span-yönü korelasyon kaybını
temsil edemez, dökülme aşırı-korele olur, iz DARALIR; dar iz hem sürüklemeyi
düşürür hem frekansı yükseltir.

BU KOŞU O AÇIKLAMANIN SINANMASIDIR. Açıklama doğruysa üçüncü boyut eklendiğinde
İKİ sapma birden düzelmelidir --- $St$ aşağı, $C_d$ yukarı. Yalnız biri
düzelirse açıklama eksiktir ve geri çekilmelidir. Bir hipotezi doğrulayacak
deney, onu yanlışlayabilecek deneydir; bu koşunun değeri buradan gelir.

Span uzunluğu $L_z = \\pi D$: subkritik silindir için yerleşik seçim (Breuer,
Int. J. Heat Fluid Flow 21 (2000); Travin ve ark., Theor. Comput. Fluid Dyn. 20
(2006)). Daha kısa span dökülmeyi yapay olarak korele tutar --- yani tam da
ölçmek istediğimiz etkiyi bastırır.

Mesh 2B çapadan DEVRALINIR (`silindir_vorteks._blockmesh`, span/nz/cyclic
parametreleriyle). Kesit zaten doğrulanmıştı: laminer $Re=100$'de $St$ hatası
%2,15. Meshi ikinci kez yazmak, iki meshin sessizce ayrışması demektir.

    python experiments/silindir_urans_3b.py --kalibre  # 2 periyot: süre ölçümü
    python experiments/silindir_urans_3b.py            # tam koşu
    python experiments/silindir_urans_3b.py --oku      # diskteki çözümü oku

Çıktı: silindir_urans_3b.json (kanıt)
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
from silindir_urans import (  # noqa: E402
    CD_DENEY,
    CD_KAYNAK,
    NU,
    RE,
    ST_BANDI,
    ST_DENEY,
    ST_KAYNAK,
    TI,
    YPLUS_BANDI,
    _alanlar,
    _sabitler,
)
from silindir_vorteks import D, U, _blockmesh, _coeffs  # noqa: E402

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

SPAN = math.pi * D          # Lz = πD (Breuer 2000; Travin ve ark. 2006)
NZ = 24                     # span-yönü hücre (Δz ≈ 0,13 D)
CEKIRDEK = 4
PERIYOT_GECIS, PERIYOT_ISTAT = 6, 16
KALIBRE_PERIYOT = 2         # süre ölçümü için kısa koşu


def kur(case: Path, dt: float, son_s: float) -> None:
    """Case'i yaz — mesh 3B, geri kalan her şey 2B çapayla AYNI.

    Alanlar ve türbülans sözlükleri `silindir_urans`tan olduğu gibi gelir:
    değişen tek şeyin ÜÇÜNCÜ BOYUT olması, karşılaştırmanın geçerlilik
    koşuludur. İki koşu arasında başka bir fark olsaydı sapma değişiminin
    nereden geldiği söylenemezdi.
    """
    (case / "system").mkdir(parents=True, exist_ok=True)
    (case / "system" / "blockMeshDict").write_text(
        _blockmesh(span=SPAN, nz=NZ, cyclic=True))
    _alanlar(case)
    _sabitler(case)
    # CYCLIC YAMALAR ALAN DOSYALARINDA DA TANIMLI OLMALI. `_alanlar` 2B için
    # `yanlar { type empty; }` yaziyor; 3B'de o yama YOK, yerine on/arka var.
    # Duzeltilmezse foamRun "cannot find patchField entry for on" ile duser.
    for f in (case / "0").iterdir():
        t = f.read_text(encoding="utf-8")
        t = t.replace("  yanlar   { type empty; }\n",
                      "  on   { type cyclic; }\n  arka { type cyclic; }\n")
        t = t.replace("  yanlar { type empty; }\n",
                      "  on   { type cyclic; }\n  arka { type cyclic; }\n")
        f.write_text(t, encoding="utf-8")
    c = CFDCase(name=case.name, stl_path=str(case), velocity=U, rho=1.0, nu=NU,
                transient=True, delta_t=dt, end_time_s=son_s, n_outer=2,
                max_courant=2.0)
    _write_control_dict(case, c, "silindir", D)
    _write_fv_schemes(case, transient=True)
    _write_fv_solution(case, compressible=False, transient=True, n_outer=2)
    # PARALEL: 3B mesh 2B'nin NZ katı (403.200 hücre). Seri kosum saatlere
    # cikar; decomposePar bu koşuyu laptop butcesinde tutar.
    (case / "system" / "decomposeParDict").write_text(
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n"
        '    class dictionary;\n    location "system";\n'
        "    object decomposeParDict;\n}\n"
        f"numberOfSubdomains {CEKIRDEK};\nmethod scotch;\n")


def kos(case: Path, timeout: int = 43200) -> tuple[bool, str]:
    """Paralel koşum — ortam KANONİK ön ekten gelir.

    İlk sürüm `source .../bashrc` ile kendi ortamını kuruyordu ve `mpirun`
    SÜRESİZ ASILDI: hiçbir zaman adımı yazılmadı, log boş kaldı. Neden depoda
    zaten kayıtlıydı --- hwloc'un GL bileşeni WSLg'de X sunucusuna bağlanmaya
    çalışıp donuyor (`OF_ENV_PREFIX`, `HWLOC_COMPONENTS=-gl`). Ortamı ikinci
    kez kurmak, çözülmüş bir hatayı yeniden üretmek demek.
    """
    cu = windows_to_wsl_path(case)
    r = linux_run(
        f"{OF_ENV_PREFIX} cd '{cu}' && "
        "blockMesh > log.blockMesh 2>&1 && "
        "checkMesh > log.checkMesh 2>&1; "
        "decomposePar -force > log.decomposePar 2>&1 && "
        f"mpirun -np {CEKIRDEK} foamRun -parallel > log.foamRun 2>&1 && "
        "reconstructPar -latestTime > log.reconstructPar 2>&1", timeout)
    return r.returncode == 0, (r.stderr or r.stdout or "")[-400:]


def _verdikt(o: dict, iki_b: dict | None) -> str:
    """HİPOTEZ SINANIYOR: iki sapma birden düzeldi mi?

    2B koşunun açıklaması "iz daralması"ydı ve İKİ tahmin içeriyordu: St
    yüksek, Cd düşük. Üçüncü boyut eklendiğinde ikisinin de düzelmesi gerekir.
    Yalnız biri düzelirse açıklama eksiktir ve bu SÖYLENMELİDİR --- kısmen
    doğrulanan bir açıklamayı doğrulanmış saymak, tam olarak bu deponun
    avladığı davranıştır.
    """
    st = o["olculen"]["St"]
    if st is None:
        return ("❌ Girdap dökülmesi ÖLÇÜLEMEDİ: "
                + str(o["salinim_olcumu"].get("neden")))
    d_st, d_cd = o["sapma_pct"]["St"], o["sapma_pct"]["Cd"]
    bandda = ST_BANDI[0] <= st <= ST_BANDI[1]
    s = (f"3B (Lz={SPAN / D:.2f}D, {NZ} span hücresi): St={st} "
         f"(%{d_st:+.0f}), Cd={o['olculen']['Cd_ortalama']} (%{d_cd:+.0f})")
    if not iki_b:
        return ("⚠️ " + s + " — 2B kanıt bulunamadı, hipotez SINANAMADI "
                "(karşılaştırma için silindir_urans.json gerekli)")
    d_st2, d_cd2 = iki_b["sapma_pct"]["St"], iki_b["sapma_pct"]["Cd"]
    st_iyi = abs(d_st) < abs(d_st2)
    cd_iyi = abs(d_cd) < abs(d_cd2)
    kiyas = (f" | 2B: St %{d_st2:+.0f}, Cd %{d_cd2:+.0f}")
    if st_iyi and cd_iyi and bandda:
        return ("✅ HİPOTEZ DOĞRULANDI + ÇAPA GEÇTİ: " + s + kiyas +
                ". Üçüncü boyut eklenince İKİ sapma birden düzeldi ve St "
                f"deneysel plato {ST_BANDI} içine girdi — 'iz daralması' "
                "açıklaması sınandı ve tuttu.")
    if st_iyi and cd_iyi:
        return ("⚠️ HİPOTEZ DOĞRULANDI, ÇAPA GEÇMEDİ: " + s + kiyas +
                ". İki sapma da küçüldü, yani 'iz daralması' açıklaması doğru "
                f"yönde; ancak St hâlâ deneysel plato {ST_BANDI} DIŞINDA. "
                "Span çözünürlüğü ya da URANS'ın kendisi yetersiz.")
    if st_iyi or cd_iyi:
        hangi = "St" if st_iyi else "Cd"
        oteki = "Cd" if st_iyi else "St"
        # CURUTMENIN NEDENI DE OLCULUR. Span-yonu dekorelasyon GERCEKTEN olustu
        # mu? Olusmussa Cl salinim genligi belirgin DUSMELIDIR (dokulme artik
        # span boyunca ayni fazda degildir). Genlik neredeyse ayni kaldiysa
        # ucuncu boyut GEOMETRIK olarak eklendi ama FIZIK eklenmedi.
        ga, gb = o["olculen"]["Cl_genlik"], (iki_b["olculen"] or {}).get("Cl_genlik")
        _g = ""
        if gb:
            dus = (gb - ga) / gb * 100
            _g = (f" ÖLÇÜLDÜ: Cl salınım genliği {gb:.3f} → {ga:.3f} "
                  f"(yalnız %{dus:.1f} düşüş). Span-yönü dekorelasyon "
                  + ("OLUŞMADI" if dus < 15 else "kısmen oluştu")
                  + " — URANS dalgalanmayı MODELLER, çözmez; ağa üçüncü boyutu "
                    "eklemek span boyunca fazı ayırmaya yetmiyor. Doğru "
                    "açıklama 'iz daralması' değil, çözünürlük sınıfının "
                    "kendisidir: dekorelasyon DES/LES gerektirir.")
        return ("❌ HİPOTEZ KISMEN ÇÜRÜDÜ: " + s + kiyas +
                f". Yalnız {hangi} düzeldi, {oteki} düzelmedi. 'İz daralması' "
                "açıklaması İKİ sapmayı birden öngörüyordu; tek yönde tutması "
                "yetmez ve rapordaki gerekçe GERİ ÇEKİLİR." + _g)
    return ("❌ HİPOTEZ ÇÜRÜDÜ: " + s + kiyas +
            ". Üçüncü boyut hiçbir sapmayı düzeltmedi — 2B kurulumun "
            "span-yönü korelasyonu açıklaması YANLIŞ. Neden başka yerdedir.")


def olc_ham(t, cd, cl) -> dict:
    """Kuvvet tarihçesinden St, Cd ve salınım ölçümü — TEK KAYNAK.

    NEDEN AYRI FONKSIYON: geçiş-modeli koşusu (`silindir_gecis_3b`) AYNI
    ölçümü yapmak zorunda; ikinci bir uygulama yazmak iki koşuyu kıyaslanamaz
    yapardı --- sapma farkının ölçütten mi kapanıştan mı geldiği söylenemezdi.
    `main` de bu fonksiyonu çağırır, yani tek bir uygulama vardır.
    """
    olcum = salinim_olc(t, cl,
                        gecis_orani=PERIYOT_GECIS / (PERIYOT_GECIS + PERIYOT_ISTAT))
    st = (olcum["frekans_hz"] * D / U) if olcum.get("olculdu") else None
    # A_REF: kanonik yazici Aref=lref^2 verir; silindirde dogru referans D x Lz.
    olcek = (D * D) / (D * SPAN)
    cd_ort = sum(cd[len(cd) // 3:]) / len(cd[len(cd) // 3:]) * olcek
    return {"olcum": olcum, "St": st, "olcek": olcek, "Cd": cd_ort,
            "Cl_genlik": olcum.get("genlik", 0.0) * olcek,
            "St_sapma_pct": (round((st - ST_DENEY) / ST_DENEY * 100, 2)
                             if st else None),
            "Cd_sapma_pct": round((cd_ort - CD_DENEY) / CD_DENEY * 100, 2)}


def main(argv: list[str]) -> int:
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    kalibre = "--kalibre" in argv
    case = HERE.parent / ("_silindir_3b_kalibre" if kalibre else "_silindir_3b")
    periyot = D / (ST_DENEY * U)
    dt = periyot / 150.0
    son = (KALIBRE_PERIYOT if kalibre else PERIYOT_GECIS + PERIYOT_ISTAT) * periyot
    hucre = 4 * 70 * 60 * NZ
    print(f"Re={RE:.0f}  Lz={SPAN / D:.3f}D  hücre≈{hucre:,}  dt={dt:.4f}  "
          f"süre={son:.1f} s ({int(son / dt)} adım, {CEKIRDEK} çekirdek)"
          + ("  [KALİBRE]" if kalibre else ""), flush=True)

    t0 = time.time()
    if "--oku" in argv and (case / "log.foamRun").exists():
        ok, hata = True, ""
    else:
        kur(case, dt, son)
        ok, hata = kos(case)
    gecen = time.time() - t0
    if not ok:
        print(f"ÇÖZÜCÜ DÜŞTÜ: {hata[:300]}", flush=True)
        (HERE.parent / "silindir_urans_3b.json").write_text(json.dumps(
            {"durum": "cozucu_dustu", "hata": hata[:600], "kalibre": kalibre},
            indent=2, ensure_ascii=False), encoding="utf-8")
        return 1

    if kalibre:
        adim = int(son / dt)
        tam_adim = (PERIYOT_GECIS + PERIYOT_ISTAT) * periyot / dt
        print(f"\n{adim} adım {gecen:.0f} s sürdü → adım başına {gecen / adim:.2f} s.\n"
              f"Tam koşu ({int(tam_adim)} adım) ≈ {gecen / adim * tam_adim / 60:.0f} dk "
              f"({gecen / adim * tam_adim / 3600:.1f} saat).", flush=True)
        return 0

    t, cd, cl = _coeffs(case)
    if not t:
        print("forceCoeffs okunamadı", flush=True)
        return 1
    _o = olc_ham(t, cd, cl)
    olcum, st, olcek, cd_ort = _o["olcum"], _o["St"], _o["olcek"], _o["Cd"]
    iki_b_dosya = HERE.parent / "silindir_urans.json"
    iki_b = (json.loads(iki_b_dosya.read_text(encoding="utf-8"))
             if iki_b_dosya.exists() else None)
    if iki_b and iki_b.get("sapma_pct", {}).get("St") is None:
        iki_b = None
    out = {
        "vaka": (f"Silindir girdap dökülmesi — Re={RE:.0f}, ÜÇ BOYUTLU URANS "
                 f"(kOmegaSST, Lz={SPAN / D:.2f}D, {NZ} span hücresi)"),
        "kaynak": "OpenFOAM 11 foamRun/incompressibleFluid, PIMPLE/backward, paralel",
        "hipotez": ("2B koşunun açıklaması 'iz daralması'ydı ve İKİ tahmin "
                    "içeriyordu: St YÜKSEK, Cd DÜŞÜK. Üçüncü boyut eklenince "
                    "ikisinin de düzelmesi gerekir. Yalnız biri düzelirse "
                    "açıklama EKSİKTİR ve geri çekilmelidir."),
        "referans": {"St": ST_DENEY, "St_bandi": list(ST_BANDI),
                     "kaynak": ST_KAYNAK, "St_tipi": "DENEYSEL (plato)",
                     "Cd": CD_DENEY, "Cd_kaynak": CD_KAYNAK},
        "olculen": {"St": round(st, 5) if st else None,
                    "Cd_ortalama": round(cd_ort, 4),
                    "Cl_genlik": round(olcum.get("genlik", 0.0) * olcek, 5),
                    "yplus": (yplus_olc_ortak(case) or {}).get("silindir"),
                    "_aref_olcegi": olcek},
        "sapma_pct": {"St": round((st - ST_DENEY) / ST_DENEY * 100, 2) if st else None,
                      "Cd": round((cd_ort - CD_DENEY) / CD_DENEY * 100, 2)},
        "iki_boyutlu_kiyas": ({"St_sapma_pct": iki_b["sapma_pct"]["St"],
                               "Cd_sapma_pct": iki_b["sapma_pct"]["Cd"],
                               "_dosya": iki_b_dosya.name} if iki_b else None),
        "salinim_olcumu": olcum,
        "kurulum": {"model": "kOmegaSST", "duvar_islemi": "duvar-fonksiyonu",
                    "span_D": round(SPAN / D, 4), "nz": NZ,
                    "span_kaynak": ("Lz=πD — Breuer, Int. J. Heat Fluid Flow 21 "
                                    "(2000); Travin ve ark., Theor. Comput. Fluid "
                                    "Dyn. 20 (2006). Daha kısa span dökülmeyi "
                                    "yapay olarak korele tutar."),
                    "hucre": hucre, "dt_s": dt, "sure_s": son,
                    "adim": int(son / dt), "cekirdek": CEKIRDEK,
                    "turbulans_yogunlugu": TI,
                    "yplus_bandi": list(YPLUS_BANDI),
                    "mesh": "silindir_vorteks._blockmesh(span, nz, cyclic) — AYNI kesit"},
        "_kapsam": ("Cd YALNIZ EGILIM olarak degil, hipotez sinamasinin "
                    "PARCASI olarak okunur: yonu tahmin edilmisti. Vaka "
                    "model_form_bandi'ye Cd capasi olarak yine de GIRMEZ "
                    "(zaman-cozunur, duvar-fonksiyonu)."),
        "_uretim": "Üretim: python experiments/silindir_urans_3b.py",
        "_sure_s": round(gecen, 1),
    }
    out["verdikt"] = _verdikt(out, iki_b)
    import ortam
    ortam.damgala(out)
    (HERE.parent / "silindir_urans_3b.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSt = {st}  (plato {ST_BANDI}) → %{out['sapma_pct']['St']}")
    print(f"Cd = {cd_ort:.4f} (literatür {CD_DENEY}) → %{out['sapma_pct']['Cd']}")
    print(f"y⁺ = {out['olculen']['yplus']}")
    print(out["verdikt"])
    print("-> silindir_urans_3b.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
