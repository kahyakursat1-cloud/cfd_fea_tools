"""NACA0012 α=8° — kapanış ve türbülans yoğunluğunu AYIRAN üçlü karşılaştırma.

NEDEN ÜÇ KOŞU: `kOmegaSST → kOmegaSSTLM` geçişi tek bir değişiklik değildir.
Geçiş modeli serbest akış türbülans yoğunluğuna doğrudan bağlıdır ve bu vakada
Tu = %5 (kOmegaSST kararlılığı için seçilmişti) geçiş modeli için YÜKSEKtir:
bypass geçişi hemen tetiklenir ve model tam-türbülanslı gibi davranır. İkisini
birden değiştirip tek sayı raporlamak, farkın hangisinden geldiğini söylememek
demek olurdu. Bu yüzden üç koşu:

    K1  kOmegaSST   , Tu = %5     (referans — zaten ölçüldü, Cl hatası %16,6)
    K2  kOmegaSSTLM , Tu = %5     (yalnız KAPANIŞ değişti)
    K3  kOmegaSSTLM , Tu = %0,15  (kapanış + Tu, geçiş modelinin anlamlı rejimi)

K2−K1 farkı kapanışın tek başına etkisidir. K3−K2 farkı Tu'nun etkisidir.
Ağ, duvar işlemi (nutLowReWallFunction, y⁺≈2,5) ve rampalı başlangıç ÜÇÜNDE DE AYNI.

ÖNCEKİ ADIMLAR — her biri bir adayı eledi (2026-08-13):
  duvar işlemi  y⁺ 16–357 → 0,04–2,47, hata %18,2 → %16,6   AÇIKLAMIYOR
  kararsızlık   sigFpe, rampalı başlangıçla çözüldü          AÇIKLAMIYOR
  yakınsama     2000 → 10000 iterasyon, %18,1 → %18,2        AÇIKLAMIYOR

SINANAN İDDİA (koşulardan ÖNCE yazılıyor):
    U1  K2 ve K3 yakınsar (sigFpe yok, hedef iterasyona ulaşır).
    U2  K3'te α=8° taşıma hatası %8'in ALTINA iner.
    U3  |K2 − K1| < |K3 − K2|, yani Tu'nun etkisi kapanışınkinden BÜYÜKtür.
U2 tutmazsa dört aday da elenmiş olur ve geriye ağ ailesi kalır (makalenin
%7,8'i NASA TMR ağlarında üretildi); %8 toleransı bu vakada doğrulanamaz.
U3, "kapanışı değiştirdik" demenin tek başına yeterli olup olmadığını ölçer.

Üretim: python experiments/naca0012_a8_uclu_karsilastirma.py
Çıktı : naca0012_a8_uclu_karsilastirma.json
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
KANIT = KOK / "naca0012_a8_uclu_karsilastirma.json"
RAMPA_KAYNAK = KOK / "_a8_duvar_cozunur" / "alpha_08"   # K1'in yakınsamış çözümü
ALPHA, TOLERANS_PCT, ITER = 8, 8.0, 6000
RHO, V, AREF, RE = 1.225, 50.0, 0.1, 6.0e6

KOSULAR = [("K2", "kOmegaSSTLM", 0.05), ("K3", "kOmegaSSTLM", 0.0015)]
K1 = {"etiket": "K1", "model": "kOmegaSST", "Tu": 0.05, "Cl_hata_pct": 16.6,
      "Cd_hata_pct": 225.0, "_kaynak": "naca0012_a8_rampali.json"}


def _kabuk(k: str, t: int = 7200) -> str:
    r = linux_run(f"{OF_ENV_PREFIX} {k}", timeout=t)
    return getattr(r, "stdout", "") or getattr(r, "output", "") or ""


def _katsayilar(case: Path) -> tuple[float | None, float | None]:
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


def _kos(etiket: str, model: str, tu: float) -> dict:
    print(f"\n=== {etiket}: {model}, Tu=%{tu * 100:.2f} ===", flush=True)
    v = NACA0012Validation(str(KOK / f"_a8_{etiket}"))
    v.NU, v.RE = V / RE, RE
    v.n_prof, v.n_norm, v.grading = 200, 200, 120_000
    v.nut_wall, v.k_wall = "nutLowReWallFunction", "kLowReWallFunction"
    v.ras_model, v.turb_intensity = model, tu
    v.force_gentle, v.end_time = True, 30
    try:
        v.run(ALPHA)
    except Exception as e:                                       # noqa: BLE001
        print(f"  kurulum koşusu düştü (beklenebilir): {type(e).__name__}", flush=True)

    hedef = case_bul(KOK / f"_a8_{etiket}")
    if hedef is None:
        return {"etiket": etiket, "error": "vaka kurulamadı"}
    h, k = windows_to_wsl_path(hedef), windows_to_wsl_path(RAMPA_KAYNAK)
    _kabuk(f"cd '{h}' && ls -d [1-9]* 2>/dev/null | xargs -r rm -rf && "
           "rm -rf postProcessing log.s")
    mf = _kabuk(f"cd '{h}' && mapFields '{k}' -consistent -sourceTime latestTime 2>&1 | tail -4")
    controldict_yamala(hedef, end_time=ITER, start_from="startTime",
                       yplus_ekle=True)
    _kabuk(f"cd '{h}' && foamRun -solver incompressibleFluid > log.s 2>&1")

    log = (hedef / "log.s").read_text(encoding="utf-8", errors="replace")
    zaman = re.findall(r"^Time = ([0-9.eE+-]+)", log, re.M)
    son = int(float(zaman[-1])) if zaman else 0
    fpe = "sigFpe" in log
    cl, cd_ = _katsayilar(hedef)
    clr, cdr, _ = NACA0012_NASA[ALPHA]
    o = {"etiket": etiket, "model": model, "Tu": tu, "son_iterasyon": son,
         "sigFpe": fpe, "esleme_ok": "FOAM FATAL" not in mf, "Cl": cl, "Cd": cd_,
         "Cl_hata_pct": (100 * abs(cl - clr) / clr) if cl is not None else None,
         "Cd_hata_pct": (100 * abs(cd_ - cdr) / cdr) if cd_ is not None else None,
         "hata": (log[-400:] if fpe else None)}
    print(f"  {etiket}: {son}/{ITER} iter · Cl={cl} hata "
          f"%{o['Cl_hata_pct'] if o['Cl_hata_pct'] is None else round(o['Cl_hata_pct'], 1)}",
          flush=True)
    return o


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sonuc = [K1] + [_kos(*x) for x in KOSULAR]
    g = {x["etiket"]: x for x in sonuc}
    u1 = all(g[e].get("son_iterasyon", 0) >= ITER and not g[e].get("sigFpe")
             for e in ("K2", "K3"))
    h = {e: g[e].get("Cl_hata_pct") for e in ("K1", "K2", "K3")}
    u2 = h["K3"] is not None and h["K3"] < TOLERANS_PCT
    u3 = (None if not u1 or any(h[e] is None for e in h)
          else abs(h["K2"] - h["K1"]) < abs(h["K3"] - h["K2"]))

    if not u1:
        verdikt = "⚠️ U1 TUTMADI: K2 ve/veya K3 yakınsamadı; U2 ve U3 SINANAMAZ."
    elif u2:
        verdikt = (f"✅ U2 TUTTU: geçiş modeli + düşük Tu ile α=8° taşıma hatası "
                   f"%{h['K3']:.1f} < %{TOLERANS_PCT} (K1'de %{h['K1']}). "
                   f"Kapanışın tek başına katkısı {abs(h['K2'] - h['K1']):.1f} puan, "
                   f"Tu'nunki {abs(h['K3'] - h['K2']):.1f} puan. %8 toleransı "
                   "bağımsız olarak doğrulandı.")
    else:
        verdikt = (f"⚠️ U2 TUTMADI: K3 hatası %{h['K3']:.1f} ≥ %{TOLERANS_PCT} "
                   f"(K1 %{h['K1']}, K2 %{h['K2']:.1f}). Duvar işlemi, kararsızlık, "
                   "yakınsama, kapanış ve Tu — beş aday da elendi. Geriye AĞ AİLESİ "
                   "kalıyor: makalenin %7,8'i NASA TMR referans ağlarında üretildi, "
                   "bu ise kendi O-grid'imiz. %8 toleransı bu ağ ailesinde "
                   "DOĞRULANAMAZ.")

    o = {"vaka": f"NACA0012 α={ALPHA}° — kapanış ve Tu AYRIŞTIRILIYOR",
         "sinanan_iddia": {"U1": "K2 ve K3 yakınsar",
                           "U2": f"K3 taşıma hatası < %{TOLERANS_PCT}",
                           "U3": "Tu'nun etkisi kapanışınkinden büyük",
                           "_not": "İddialar koşulardan ÖNCE docstring'de sabitlendi."},
         "sabit_tutulan": {"ag": "n_prof=200, n_norm=200, grading=120000",
                           "duvar": "nutLowReWallFunction + kLowReWallFunction",
                           "baslangic": "mapFields, K1'in yakınsamış çözümünden",
                           "Re": RE, "alpha": ALPHA},
         "kosular": sonuc,
         "fark": {"kapanis_K2_K1": (None if h["K2"] is None else abs(h["K2"] - h["K1"])),
                  "Tu_K3_K2": (None if h["K3"] is None or h["K2"] is None
                               else abs(h["K3"] - h["K2"]))},
         "U1": u1, "U2": u2 if u1 else None, "U3": u3, "verdikt": verdikt,
         "_uretim": "Üretim: python experiments/naca0012_a8_uclu_karsilastirma.py"}
    KANIT.write_text(json.dumps(o, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + verdikt)
    print(f"-> {KANIT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
