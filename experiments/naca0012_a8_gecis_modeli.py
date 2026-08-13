"""NACA0012 α=8° — GEÇİŞ MODELİ (kOmegaSSTLM) ile son aday sınanır.

ÖLÇÜM ZİNCİRİ (2026-08-13), her adım bir adayı eledi:
  1. Duvar fonksiyonu y⁺ 16–357 → geçersiz. Düzeltildi (y⁺ 0,04–2,47).
     Taşıma hatası %18,2 → %16,6. Duvar işlemi SAPMAYI AÇIKLAMIYOR.
  2. Çözüm sigFpe ile patlıyordu. Rampalı başlangıçla çözüldü (6000/6000).
     Kararsızlık SAPMAYI AÇIKLAMIYOR.
  3. İterasyon 2000 → 10000: hata %18,1 → %18,2. Yakınsama AÇIKLAMIYOR.
Kalan aday MODEL FORMU: bu doğrulama tam-türbülanslı `kOmegaSST` koşuyor,
oysa makalenin α=8° için bildirdiği %7,8 `kOmegaSSTLM` ile üretildi. Re = 6×10⁶'da
bağlı sınır tabaka önemli bir mesafe laminer kalır; tam-türbülanslı kapanış bunu
görmez ve ayrılmayı yanlış yerde başlatır.

SINANAN İDDİA (koşudan ÖNCE yazılıyor):
    G1  Geçiş modeli çözümü yakınsar (sigFpe yok, hedef iterasyona ulaşır).
    G2  G1 sağlanınca α=8° taşıma hatası %8'in ALTINA iner.
G2 tutarsa sapmanın kaynağı MODEL FORMUDUR ve ilan edilen %8 toleransı bağımsız
olarak doğrulanmış olur. G2 tutmazsa dört aday da elenmiş olur ve tolerans bu
vakada doğrulanamaz; geriye ağ ailesi (TMR referans ağları) kalır.

Aynı ağ, aynı duvar işlemi, aynı rampalı başlangıç — DEĞİŞEN TEK ŞEY kapanış.
Başka bir şey de değişseydi farkın nereden geldiği söylenemezdi.

Üretim: python experiments/naca0012_a8_gecis_modeli.py
Çıktı : naca0012_a8_gecis_modeli.json
"""
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import windows_to_wsl_path  # noqa: E402
from analysis.openfoam_runner import OF_ENV_PREFIX, case_bul, controldict_yamala  # noqa: E402
from validation_suite import NACA0012_NASA, NACA0012Validation  # noqa: E402

KOK = HERE.parent
KANIT = KOK / "naca0012_a8_gecis_modeli.json"
KAYNAK = KOK / "_a8_duvar_cozunur" / "alpha_08"     # yakınsamış duvar-çözümlü çözüm
ALPHA, TOLERANS_PCT, ITER = 8, 8.0, 6000
RHO, V, AREF = 1.225, 50.0, 0.1                      # kord 1 m × açıklık 0,1 m


def _kabuk(k: str, t: int = 7200, timeout: int | None = None) -> str:
    t = timeout if timeout is not None else t
    r = linux_run(f"{OF_ENV_PREFIX} {k}", timeout=t)
    return getattr(r, "stdout", "") or getattr(r, "output", "") or ""


def _katsayilar(case: Path) -> tuple[float | None, float | None]:
    """forces.dat son satırı → Cl, Cd (α ile döndürülür)."""
    f = next((x for x in case.rglob("forces.dat")), None)
    if not f:
        return None, None
    sat = [x for x in f.read_text(encoding="utf-8", errors="replace").splitlines()
           if x.strip() and not x.startswith("#")]
    if not sat:
        return None, None
    n = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+e?[-+]?\d*", sat[-1])]
    fx, fz = n[1] + n[4], n[3] + n[6]
    a = math.radians(ALPHA)
    q = 0.5 * RHO * V ** 2 * AREF
    return (-fx * math.sin(a) + fz * math.cos(a)) / q, (fx * math.cos(a) + fz * math.sin(a)) / q


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    v = NACA0012Validation(str(KOK / "_a8_gecis"))
    v.NU = V / 6.0e6
    v.RE = 6.0e6
    v.n_prof, v.n_norm, v.grading = 200, 200, 120_000   # duvar-çözümlü ağla AYNI
    v.nut_wall, v.k_wall = "nutLowReWallFunction", "kLowReWallFunction"
    v.ras_model = "kOmegaSSTLM"                          # DEĞİŞEN TEK ŞEY
    v.force_gentle = True
    v.end_time = 30                                      # önce kur, sonra rampala
    print("1) kurulum (kOmegaSSTLM, duvar-çözümlü)...", flush=True)
    try:
        v.run(ALPHA)
    except Exception as e:                                        # noqa: BLE001
        print(f"kurulum koşusu düştü (beklenebilir): {type(e).__name__}", flush=True)

    hedef = case_bul(KOK / "_a8_gecis")
    if hedef is None:
        print("hedef vaka kurulamadı")
        return 1
    h, k = windows_to_wsl_path(hedef), windows_to_wsl_path(KAYNAK)

    print("2) rampalı başlangıç: yakınsamış duvar-çözümlü çözümden mapFields...", flush=True)
    _kabuk(f"cd '{h}' && ls -d [1-9]* 2>/dev/null | xargs -r rm -rf && "
           "rm -rf postProcessing log.s", timeout=600)
    mf = _kabuk(f"cd '{h}' && mapFields '{k}' -consistent -sourceTime latestTime "
                "2>&1 | tail -6", timeout=1800)
    esleme_ok = "FOAM FATAL" not in mf
    print(mf[-300:], flush=True)

    controldict_yamala(hedef, end_time=ITER, start_from="startTime", yplus_ekle=True)

    print(f"3) çözülüyor (kOmegaSSTLM, endTime={ITER})...", flush=True)
    _kabuk(f"cd '{h}' && foamRun -solver incompressibleFluid > log.s 2>&1", timeout=10800)

    log = (hedef / "log.s").read_text(encoding="utf-8", errors="replace")
    zaman = re.findall(r"^Time = ([0-9.eE+-]+)", log, re.M)   # birim ekini AT
    son = int(float(zaman[-1])) if zaman else 0
    fpe = "sigFpe" in log
    g1 = esleme_ok and not fpe and son >= ITER

    cl, cd_ = _katsayilar(hedef)
    cl_ref, cd_ref, kaynak = NACA0012_NASA[ALPHA]
    h_cl = 100 * abs(cl - cl_ref) / abs(cl_ref) if cl is not None else None
    h_cd = 100 * abs(cd_ - cd_ref) / abs(cd_ref) if cd_ is not None else None
    g2 = h_cl is not None and h_cl < TOLERANS_PCT

    yp = None
    for f in hedef.rglob("yPlus.dat"):
        s = [x for x in f.read_text(encoding="utf-8", errors="replace").splitlines()
             if "airfoil" in x]
        if s:
            p = s[-1].split()
            yp = {"min": float(p[2]), "max": float(p[3]), "ort": float(p[4])}

    if not g1:
        verdikt = (f"⚠️ G1 TUTMADI: {son}/{ITER} iterasyon"
                   f"{', sigFpe' if fpe else ''}. G2 SINANAMAZ.")
    elif g2:
        verdikt = (f"✅ G1 ve G2 TUTTU: geçiş modeliyle α=8° taşıma hatası "
                   f"%{h_cl:.1f} < %{TOLERANS_PCT} (tam-türbülanslıda %16,6 idi). "
                   "SAPMANIN KAYNAĞI MODEL FORMUYDU; %8 toleransı bağımsız "
                   "olarak doğrulandı.")
    else:
        verdikt = (f"⚠️ G1 tuttu, G2 TUTMADI: hata %{h_cl:.1f} ≥ %{TOLERANS_PCT} "
                   f"(tam-türbülanslıda %16,6). Dört aday da elendi — duvar işlemi, "
                   "kararsızlık, yakınsama, kapanış. Geriye AĞ AİLESİ kalıyor "
                   "(makalenin sonucu NASA TMR ağlarında üretildi). %8 toleransı "
                   "bu vakada doğrulanamaz.")

    o = {"vaka": f"NACA0012 α={ALPHA}° kOmegaSSTLM, duvar-çözümlü + rampalı",
         "sinanan_iddia": {"G1": "geçiş modeli yakınsar",
                           "G2": f"α=8° taşıma hatası < %{TOLERANS_PCT}",
                           "_not": "İddialar koşudan ÖNCE docstring'de sabitlendi."},
         "degisen_tek_sey": "RASModel: kOmegaSST -> kOmegaSSTLM",
         "elenen_adaylar": {
             "duvar_islemi": "y⁺ 357→2,5 düzeltildi, hata %18,2→%16,6",
             "kararsizlik": "sigFpe rampalı başlangıçla çözüldü",
             "yakinsama": "2000→10000 iterasyon, hata %18,1→%18,2"},
         "olculen": {"son_iterasyon": son, "sigFpe": fpe, "Cl": cl, "Cd": cd_,
                     "Cl_ref": cl_ref, "Cd_ref": cd_ref, "Cl_hata_pct": h_cl,
                     "Cd_hata_pct": h_cd, "yplus": yp, "ref_kaynak": kaynak},
         "karsilastirma_tam_turbulansli": {"Cl_hata_pct": 16.6, "Cd_hata_pct": 225.0},
         "G1": g1, "G2": g2 if g1 else None, "verdikt": verdikt,
         "_uretim": "Üretim: python experiments/naca0012_a8_gecis_modeli.py"}
    KANIT.write_text(json.dumps(o, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + verdikt)
    print(f"-> {KANIT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
