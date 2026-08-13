"""NACA0012 α=8° duvar-çözümlü, RAMPALI başlangıç — sigFpe patlamasını aşmak için.

ÖLÇÜLEN KUSUR (2026-08-13): duvar-çözümlü ağ hedefi tutturdu (y⁺ 1,97–5,31,
öncesi 16,2–356,7) ama çözüm Time = 27'de `sigFpe` ile patladı. Yığın izi
basınç çözücüsünü gösteriyor: `correctPressure → GAMGSolver → PCG::solve →
sumProd`. Bu yakınsama yavaşlığı değil, düz akış başlangıcından kalkarken
basınç matrisinin koşullanmasının bozulmasıdır — ilk hücre ~10⁻⁵ m iken
çevresel aralık ~5×10⁻³ m, en-boy oranı ~500.

ÇÖZÜM: başlangıç alanını fizikselleştir. Duvar-fonksiyonu ağında zaten oturmuş
bir çözüm var (10.000 iterasyon, rezidüeller 1e-8). `mapFields` ile duvar-çözümlü
ağa taşınır ve oradan sürülür. Sınır koşulları HEDEF vakadan gelir, yani
düşük-Re duvar işlemi korunur; taşınan yalnız iç alandır.

SINANAN İDDİA (koşudan ÖNCE yazılıyor):
    E1  Rampalı başlangıç sigFpe'yi önler ve çözüm hedef iterasyona ulaşır.
    E2  E1 sağlanınca α=8° taşıma hatası %8'in ALTINA iner.
E1 tutmazsa kararsızlık başlangıç alanından DEĞİL ağ kalitesinden gelir ve
gradasyon düşürülmelidir. E2 tutmazsa sapmanın kaynağı duvar işlemi DEĞİLDİR —
silindir DES'indeki model-form sonucuyla aynı yön — ve bu açıkça söylenir.

Üretim: python experiments/naca0012_a8_rampali.py
Çıktı : naca0012_a8_rampali.json
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import windows_to_wsl_path  # noqa: E402
from analysis.openfoam_runner import OF_ENV_PREFIX, case_bul, controldict_yamala  # noqa: E402
from validation_suite import NACA0012_NASA  # noqa: E402

KOK = HERE.parent
KANIT = KOK / "naca0012_a8_rampali.json"
HEDEF = KOK / "_a8_duvar_cozunur" / "alpha_08"          # duvar-çözümlü ağ
KAYNAK = KOK / "_re_esleme" / "Re6e6_a8_uzun" / "alpha_08"   # oturmuş kaba çözüm
ALPHA, TOLERANS_LIFT_PCT, YPLUS_HEDEF = 8, 8.0, 5.0
ITERASYON = 6000


def _kabuk(komut: str, timeout: int = 5400) -> str:
    r = linux_run(f"{OF_ENV_PREFIX} {komut}", timeout=timeout)
    return getattr(r, "stdout", "") or getattr(r, "output", "") or ""


def _forces_oku(case: Path) -> tuple[float | None, float | None]:
    """Son forceCoeffs/forces satırından Cl, Cd."""
    for ad in ("coefficient.dat", "forceCoeffs.dat"):
        for f in case.rglob(ad):
            sat = [x for x in f.read_text(encoding="utf-8", errors="replace").splitlines()
                   if x.strip() and not x.startswith("#")]
            if sat:
                p = sat[-1].split()
                # OpenFOAM 11 coefficient.dat: Time Cd Cd(f) Cd(r) Cl Cl(f) Cl(r) CmPitch ...
                try:
                    return float(p[4]), float(p[1])
                # sessiz-yutma: kabul — bu dosya beklenen sütun düzenini taşımıyor
                # (OpenFOAM sürümleri coefficient.dat ile forceCoeffs.dat arasında sütun
                # sayısını değiştiriyor). Yutulan hata KAYBOLMUYOR: sonraki aday dosya
                # denenir, hiçbiri tutmazsa (None, None) döner ve çağıran "katsayı
                # okunamadı" diye raporlar.
                except (IndexError, ValueError):
                    continue
    return None, None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not (HEDEF / "system").is_dir() or not (KAYNAK / "system").is_dir():
        print("kaynak veya hedef vaka yok — önce duvar-çözümlü kurulum koşulmalı")
        return 1

    h, k = windows_to_wsl_path(HEDEF), windows_to_wsl_path(KAYNAK)
    # Hedefi temizle: yalnız 0/ kalsin, eski (patlamis) zamanlar gitsin
    print("1) hedef vaka temizleniyor...", flush=True)
    _kabuk(f"cd '{h}' && ls -d [1-9]* 2>/dev/null | xargs -r rm -rf && rm -rf "
           "postProcessing log.s log.yplus", timeout=600)

    print("2) mapFields: kaba çözüm -> duvar-çözümlü ağ...", flush=True)
    mf = _kabuk(f"cd '{h}' && mapFields '{k}' -consistent -sourceTime latestTime "
                "2>&1 | tail -12", timeout=1800)
    print(mf[-600:], flush=True)
    esleme_ok = "FOAM FATAL" not in mf

    # Vaka sözlüğü yaması KANONİK yardımcıdan; her betiğin kendi yazıcısını
    # taşıması iskele tekrarını sayan denetimi büyütüyordu.
    controldict_yamala(HEDEF, end_time=ITERASYON, start_from="startTime",
                       yplus_ekle=True)

    print(f"3) çözülüyor (endTime={ITERASYON})...", flush=True)
    _kabuk(f"cd '{h}' && foamRun -solver incompressibleFluid > log.s 2>&1", timeout=7200)

    log = (HEDEF / "log.s").read_text(encoding="utf-8", errors="replace") \
        if (HEDEF / "log.s").exists() else ""
    # OpenFOAM "Time = 6000s" yazar; birim ekini AT (ilk surum float() de patladi)
    zaman = re.findall(r"^Time = ([0-9.eE+-]+)", log, re.M)
    son = int(float(zaman[-1])) if zaman else 0
    fpe = "sigFpe" in log or "Foam::sigFpe" in log
    e1 = (not fpe) and son >= ITERASYON

    cl, cd_ = _forces_oku(HEDEF)
    cl_ref, cd_ref, kaynak = NACA0012_NASA[ALPHA]
    h_cl = 100 * abs(cl - cl_ref) / abs(cl_ref) if cl is not None else None
    h_cd = 100 * abs(cd_ - cd_ref) / abs(cd_ref) if cd_ is not None else None
    e2 = h_cl is not None and h_cl < TOLERANS_LIFT_PCT

    yp = None
    for f in HEDEF.rglob("yPlus.dat"):
        sat = [x for x in f.read_text(encoding="utf-8", errors="replace").splitlines()
               if "airfoil" in x]
        if sat:
            p = sat[-1].split()
            yp = {"min": float(p[2]), "max": float(p[3]), "ort": float(p[4])}

    if not esleme_ok:
        verdikt = "❌ mapFields BAŞARISIZ — rampalı başlangıç kurulamadı."
    elif not e1:
        verdikt = (f"⚠️ E1 TUTMADI: çözüm {son}/{ITERASYON} iterasyonda durdu"
                   f"{' (sigFpe)' if fpe else ''}. Kararsızlık başlangıç alanından "
                   "DEĞİL ağ kalitesinden geliyor; gradasyon düşürülmeli. "
                   "E2 SINANAMAZ.")
    elif e2:
        verdikt = (f"✅ E1 ve E2 TUTTU: çözüm {son} iterasyona ulaştı, y⁺ "
                   f"{yp['max'] if yp else '?'}, α=8° taşıma hatası %{h_cl:.1f} < "
                   f"%{TOLERANS_LIFT_PCT}. Sapmanın kaynağı DUVAR İŞLEMİYDİ ve "
                   "düzeltildi; %8 toleransı bağımsız olarak doğrulandı.")
    else:
        verdikt = (f"⚠️ E1 tuttu ama E2 TUTMADI: taşıma hatası %{h_cl:.1f} ≥ "
                   f"%{TOLERANS_LIFT_PCT}. Duvar işlemi düzeltildiği hâlde sapma "
                   "sürüyor — kaynak duvar işlemi DEĞİL. Silindir DES'indeki "
                   "model-form sonucuyla aynı yönde.")

    o = {"vaka": f"NACA0012 α={ALPHA}° duvar-çözümlü, RAMPALI başlangıç",
         "sinanan_iddia": {"E1": "rampalı başlangıç sigFpe'yi önler",
                           "E2": f"α=8° taşıma hatası < %{TOLERANS_LIFT_PCT}",
                           "_not": "İddialar koşudan ÖNCE docstring'de sabitlendi."},
         "yontem": {"kaynak": str(KAYNAK.relative_to(KOK)),
                    "hedef": str(HEDEF.relative_to(KOK)),
                    "arac": "mapFields -consistent -sourceTime latestTime",
                    "_not": "Sınır koşulları HEDEF'ten; taşınan yalnız iç alan."},
         "onceki_kusur": {"son_zaman": 27, "hata": "sigFpe (basınç çözücüsü)",
                          "yplus": {"min": 1.965, "max": 5.312}},
         "olculen": {"son_iterasyon": son, "sigFpe": fpe, "Cl": cl, "Cd": cd_,
                     "Cl_ref": cl_ref, "Cd_ref": cd_ref, "Cl_hata_pct": h_cl,
                     "Cd_hata_pct": h_cd, "yplus": yp, "ref_kaynak": kaynak},
         "E1": e1, "E2": e2 if e1 else None, "verdikt": verdikt,
         "_uretim": "Üretim: python experiments/naca0012_a8_rampali.py"}
    KANIT.write_text(json.dumps(o, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + verdikt)
    print(f"-> {KANIT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
