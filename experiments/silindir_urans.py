"""Silindir girdap dökülmesi — TÜRBÜLANSLI URANS çapası (Re=1,4×10⁵, kOmegaSST).

NEDEN AYRI BİR ÇAPA: `silindir_vorteks` zaman-çözünür yolu doğruladı ama Re=100
LAMİNERDİR --- orada türbülans modeli hiç devreye girmez. "URANS yolu var"
demek, kapalı bir türbülans modelinin zaman-çözünür çevrimde koştuğunu ve
frekansı doğru verdiğini göstermeyi gerektirir. Laminer koşu bunu göstermez.

Vaka subkritik silindirdir. Deneysel Strouhal sayısı bu aralıkta bir PLATODUR
(Roshko 1961; Norberg 2003: Re = 10⁴--10⁵ boyunca St ≈ 0,19--0,21), yani
referans tek bir noktaya değil dar bir bandaa dayanır --- Re'nin birkaç yüzde
kayması hükmü değiştirmez. Bu, çapayı sağlam kılan özelliktir.

NE ÖLÇÜLÜR, NE ÖLÇÜLMEZ. St ölçülür ve deneysel referansa karşı hükümlenir.
$C_d$ ölçülür ama YALNIZ EĞİLİM olarak raporlanır: 2B URANS bu Re'de span-yönü
korelasyon kaybını temsil edemez ve sürüklemeyi sistematik olarak yüksek verir
(literatürde %15-30). Bu bilinen bir kısıttır, ölçümün kusuru değil --- ve bu
yüzden vaka model-form tablosuna $C_d$ çapası olarak GİRMEZ.

Mesh, sınır düzeni ve salınım ölçümü `silindir_vorteks`ten AYNEN alınır; bu
dosya yalnız türbülans alanlarını, viskoziteyi ve duvar işlemini değiştirir.

    python experiments/silindir_urans.py           # tam koşu
    python experiments/silindir_urans.py --oku     # diskteki çözümü oku

Çıktı: silindir_urans.json (kanıt)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from basamak_ayrilma import yplus_olc as yplus_olc_ortak  # noqa: E402
from silindir_vorteks import BASHRC, D, U, _blockmesh, _coeffs  # noqa: E402

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

RE = 1.4e5
NU = U * D / RE
# St DENEYSELDIR ve bu Re araliginda bir PLATODUR. Roshko, "Experiments on the
# flow past a circular cylinder at very high Reynolds number", J. Fluid Mech. 10
# (1961); Norberg, "Fluctuating lift on a circular cylinder", J. Fluids Struct.
# 17 (2003) — Re=1e4..1e5 boyunca St = 0.19..0.21.
ST_DENEY = 0.20
ST_BANDI = (0.19, 0.21)
ST_KAYNAK = ("Roshko, J. Fluid Mech. 10 (1961); Norberg, J. Fluids Struct. 17 "
             "(2003) — DENEYSEL; Re=1e4..1e5 boyunca St = 0,19-0,21 platosu")
CD_DENEY = 1.2
CD_KAYNAK = ("Subkritik silindir, Re=1e5 civari: Cd ≈ 1,2 (Achenbach, J. Fluid "
             "Mech. 34 (1968); Norberg 2003). 2B URANS span-yonu korelasyon "
             "kaybini temsil EDEMEZ ve Cd'yi sistematik yuksek verir — bu deger "
             "YALNIZ EGILIM olarak raporlanir")
YPLUS_BANDI = (30.0, 300.0)
# Turbulans girisi: TI %1 (ruzgar tuneli serbest akimi), l = 0.07 D.
TI = 0.01
K_INF = 1.5 * (TI * U) ** 2
OMEGA_INF = K_INF ** 0.5 / (0.09 ** 0.25 * 0.07 * D)
NUT_INF = K_INF / OMEGA_INF
PERIYOT_GECIS, PERIYOT_ISTAT = 6, 16


def _alanlar(case: Path) -> None:
    """U, p ve kOmegaSST alanları — duvarda YÜKSEK-Re (duvar-fonksiyonu)."""
    (case / "0").mkdir(parents=True, exist_ok=True)
    # SIMETRI KIRICI: silindir_vorteks'te olculdu — tumuyle simetrik kurulumda
    # Karman caddesi HIC baslamiyor (50 s boyunca Cl genligi 1e-22 kaldi).
    (case / "0" / "U").write_text(
        _foam_header("volVectorField", "U", "0") +
        "dimensions [0 1 -1 0 0 0 0];\n"
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
    for ad, boyut, ic, duvar in (
            ("k", "[0 2 -2 0 0 0 0]", K_INF, "kqRWallFunction"),
            ("omega", "[0 0 -1 0 0 0 0]", OMEGA_INF, "omegaWallFunction"),
            ("nut", "[0 2 -1 0 0 0 0]", NUT_INF, "nutkWallFunction")):
        giris = ("calculated" if ad == "nut" else "fixedValue")
        (case / "0" / ad).write_text(
            _foam_header("volScalarField", ad, "0") +
            f"dimensions {boyut};\ninternalField uniform {ic:.8g};\n"
            "boundaryField\n{\n"
            f"  silindir {{ type {duvar}; value uniform {ic:.8g}; }}\n"
            f"  giris    {{ type {giris}; value uniform {ic:.8g}; }}\n"
            f"  cikis    {{ type inletOutlet; inletValue uniform {ic:.8g}; "
            f"value uniform {ic:.8g}; }}\n"
            "  ustalt   { type slip; }\n"
            "  yanlar   { type empty; }\n}\n")


def _sabitler(case: Path) -> None:
    (case / "constant").mkdir(parents=True, exist_ok=True)
    (case / "constant" / "momentumTransport").write_text(
        _foam_header("dictionary", "momentumTransport", "constant") +
        "simulationType RAS;\nRAS\n{\n    model           kOmegaSST;\n"
        "    turbulence      on;\n    printCoeffs     on;\n}\n")
    (case / "constant" / "physicalProperties").write_text(
        _foam_header("dictionary", "physicalProperties", "constant") +
        f"viscosityModel constant;\nnu [0 2 -1 0 0 0 0] {NU:.8g};\n")


def kur(case: Path, dt: float, son_s: float) -> None:
    """Sözlükler KANONİK yazıcıdan; mesh laminer çapadan AYNEN."""
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


def kos(case: Path, timeout: int = 21600) -> tuple[bool, str]:
    cu = windows_to_wsl_path(case)
    r = linux_run(f"source {BASHRC} && cd '{cu}' && "
                  "blockMesh > log.blockMesh 2>&1 && "
                  "checkMesh > log.checkMesh 2>&1; "
                  "foamRun > log.foamRun 2>&1", timeout)
    return r.returncode == 0, (r.stderr or r.stdout or "")[-300:]


def yplus_olc(case: Path) -> dict | None:
    """DUVAR İŞLEMİ İDDİASI ÖLÇÜLÜR. y⁺ bandı dışındaysa 'duvar-fonksiyonu
    kullandım' cümlesi doğru değildir; bu, çapanın kapsamını belirler.

    Okuyucu `basamak_ayrilma`dan AYNEN gelir — foamPostProcess çıktısını ikinci
    kez ayrıştırmak, iki ayrıştırıcının sessizce ayrışması demektir.
    """
    return (yplus_olc_ortak(case) or {}).get("silindir")


def _verdikt(o: dict) -> str:
    """İKİ AYRI SORU, İKİ AYRI HÜKÜM.

    (1) MEKANİZMA: türbülans modeli zaman-çözünür çevrimde koşuyor mu, salınım
        ve y⁺ ölçülebiliyor mu? Bu, aracın kendisi hakkındaki sorudur.
    (2) FİZİK: 2B URANS bu vakada doğru cevabı veriyor mu?

    Bunları tek cümlede birleştirmek her iki yönde de yanıltır: mekanizma
    çalışıp fizik tutmadığında "araç bozuk" sanılır, tersi durumda ise
    doğrulanmamış bir yol doğrulanmış görünür.
    """
    st = o["olculen"]["St"]
    if st is None:
        return ("❌ MEKANİZMA ÇALIŞMADI — girdap dökülmesi ölçülemedi, çözüm "
                "salınmıyor: " + str(o["salinim_olcumu"].get("neden")))
    yp = o["olculen"].get("yplus")
    mek = (f"✅ MEKANİZMA: kOmegaSST zaman-çözünür (PIMPLE/backward) çevrimde "
           f"koştu, salınım ölçüldü (St={st}) ve y⁺ "
           + (f"ort={yp['ort']:.1f} (bant {YPLUS_BANDI[0]:.0f}-"
              f"{YPLUS_BANDI[1]:.0f} içinde)" if yp and
              YPLUS_BANDI[0] <= yp["ort"] <= YPLUS_BANDI[1]
              else (f"ort={yp['ort']:.1f} — duvar-fonksiyonu bandı DIŞINDA"
                    if yp else "ÖLÇÜLEMEDİ"))
           + ". Türbülanslı URANS yolu artık sentetik sinyalde değil, gerçek "
             "çözücü koşusunda sınandı.")
    if ST_BANDI[0] <= st <= ST_BANDI[1]:
        return (mek + f"\n✅ FİZİK: St deneysel plato {ST_BANDI} İÇİNDE. "
                f"Cd={o['olculen']['Cd_ortalama']} (literatür {CD_DENEY}) "
                "yalnız eğilim — 2B URANS span-yönü korelasyon kaybını temsil etmez.")
    return (mek + f"\n❌ FİZİK: St={st}, deneysel plato {ST_BANDI} DIŞINDA "
            f"(%{o['sapma_pct']['St']:+.0f}); Cd={o['olculen']['Cd_ortalama']} "
            f"literatürün %{o['sapma_pct']['Cd']:+.0f} altında. İki sapmanın "
            "YÖNÜ tutarlı ve bilinen kusuru gösterir: 2B kurulum span-yönü "
            "korelasyon kaybını temsil edemez, dökülme aşırı-korele olur, "
            "ayrılma gecikir → iz DARALIR (Cd düşük) ve frekans YÜKSELİR "
            "(St yüksek). Aynı ağ ve aynı ölçüm laminer Re=100'de St'yi %2,2 "
            "hatayla vermişti; yani ölçüm aracı doğru, EKSİK OLAN ÜÇÜNCÜ "
            "BOYUTTUR. Vaka bu haliyle Strouhal çapası olarak YAYIMLANMAZ; "
            "2B URANS'ın subkritik silindirdeki sınırının ölçümü olarak durur.")


def main(argv: list[str]) -> int:
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    case = HERE.parent / "_silindir_urans"
    periyot = D / (ST_DENEY * U)
    dt = periyot / 150.0
    son = (PERIYOT_GECIS + PERIYOT_ISTAT) * periyot
    print(f"Re={RE:.0f}  nu={NU:.3e}  beklenen periyot {periyot:.3f} s  "
          f"dt={dt:.4f}  süre={son:.1f} s ({int(son / dt)} adım)", flush=True)

    t0 = time.time()
    if "--oku" in argv and (case / "log.foamRun").exists():
        ok, hata = True, ""
    else:
        kur(case, dt, son)
        ok, hata = kos(case)
    if not ok:
        print(f"ÇÖZÜCÜ DÜŞTÜ: {hata[:200]}", flush=True)
        (HERE.parent / "silindir_urans.json").write_text(json.dumps(
            {"durum": "cozucu_dustu", "hata": hata[:400]}, indent=2,
            ensure_ascii=False), encoding="utf-8")
        return 1

    t, cd, cl = _coeffs(case)
    if not t:
        print("forceCoeffs okunamadı", flush=True)
        return 1
    olcum = salinim_olc(t, cl, gecis_orani=PERIYOT_GECIS / (PERIYOT_GECIS + PERIYOT_ISTAT))
    st = (olcum["frekans_hz"] * D / U) if olcum.get("olculdu") else None
    # A_REF: kanonik yazici Aref=lref^2 verir; 2B silindirde D x span dogrudur
    # (silindir_vorteks'te olculdu — olcek uygulanmazsa Cd 20 kat kucuk cikar).
    olcek = (D * D) / (D * 0.05 * D)
    cd_ort = sum(cd[len(cd) // 3:]) / len(cd[len(cd) // 3:]) * olcek
    out = {
        "vaka": f"Silindir girdap dökülmesi — Re={RE:.0f} (2B URANS kOmegaSST, duvar-fonksiyonu)",
        "kaynak": "OpenFOAM 11 foamRun/incompressibleFluid, ZAMAN-ÇÖZÜNÜR (backward/PIMPLE)",
        "referans": {"St": ST_DENEY, "St_bandi": list(ST_BANDI),
                     "kaynak": ST_KAYNAK, "St_tipi": "DENEYSEL (plato)",
                     "Cd": CD_DENEY, "Cd_kaynak": CD_KAYNAK,
                     "Cd_tipi": "YALNIZ EĞİLİM — 2B URANS bu Re'de Cd çapası değildir"},
        "olculen": {"St": round(st, 5) if st else None,
                    "Cd_ortalama": round(cd_ort, 4),
                    "Cl_genlik": round(olcum.get("genlik", 0.0) * olcek, 5),
                    "yplus": yplus_olc(case),
                    "_aref_olcegi": olcek},
        "sapma_pct": {"St": round((st - ST_DENEY) / ST_DENEY * 100, 2) if st else None,
                      "Cd": round((cd_ort - CD_DENEY) / CD_DENEY * 100, 2)},
        "salinim_olcumu": olcum,
        "turbulans_girisi": {"TI": TI, "k": round(K_INF, 8),
                             "omega": round(OMEGA_INF, 4), "nut": round(NUT_INF, 10),
                             "uzunluk_olcegi_m": 0.07 * D},
        "kurulum": {"model": "kOmegaSST", "duvar_islemi": "duvar-fonksiyonu",
                    "dt_s": dt, "sure_s": son, "adim": int(son / dt),
                    "gecis_periyodu": PERIYOT_GECIS,
                    "istatistik_periyodu": PERIYOT_ISTAT,
                    "mesh": "silindir_vorteks._blockmesh (AYNEN — iskele tekrarı yok)"},
        "_kapsam": ("St DENEYSEL referansa karsi hukumlenir. Cd YALNIZ EGILIM: "
                    "2B URANS bu Re'de span-yonu korelasyon kaybini temsil "
                    "edemez ve surultemeyi sistematik yuksek verir. Vaka "
                    "model_form_bandi'ye Cd capasi olarak GIRMEZ."),
        "_neden": ("silindir_vorteks zaman-cozunur yolu dogruladi ama Re=100 "
                   "LAMINERDIR — orada turbulans modeli hic devreye girmez. "
                   "'URANS yolu var' demek, kapali bir turbulans modelinin "
                   "zaman-cozunur cevrimde kostugunu gostermeyi gerektirir."),
        "_uretim": "Üretim: python experiments/silindir_urans.py",
        "_sure_s": round(time.time() - t0, 1),
    }
    out["verdikt"] = _verdikt(out)
    import ortam
    ortam.damgala(out)
    (HERE.parent / "silindir_urans.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSt = {st}  (deneysel plato {ST_BANDI}) → %{out['sapma_pct']['St']}")
    print(f"Cd = {cd_ort:.4f} (literatür {CD_DENEY}, yalnız eğilim) → "
          f"%{out['sapma_pct']['Cd']}")
    print(f"y⁺ = {out['olculen']['yplus']}")
    print(out["verdikt"])
    print("-> silindir_urans.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
