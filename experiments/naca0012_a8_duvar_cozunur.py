"""NACA0012 α=8°, DUVAR-ÇÖZÜMLÜ — ölçülen kusurun düzeltilebilir olup olmadığını sınar.

ÖLÇÜLEN KUSUR (2026-08-13): α=8°, Re=6×10⁶ koşusunda y⁺ yüzey boyunca
16,2–356,7 arasında değişiyor ve duvar fonksiyonunun geçerli bandının (30–300)
DIŞINA taşıyor. Alt uç tampon katmandır ve log yasası orada geçersizdir; α=8'de
ayrılmanın başladığı bölge tam orasıdır. İmza: 10.000 iterasyonun 9.966'sında
`bounding omega`. Sonuç: Cl %18 düşük, Cd %250 yüksek — ve iterasyonu 5 katına
çıkarmak DÜZELTMEDİ (%18,1 → %18,2), yani yakınsama sorunu değil.

SINANAN İDDİA (koşudan ÖNCE yazılıyor):
    D1  Duvar-çözümlü kurulum y⁺'ı ≲5 bandına indirir (ölçülür, varsayılmaz).
    D2  D1 sağlanınca α=8° taşıma hatası ilan edilen %8 toleransının ALTINA iner.
D1 tutmazsa ağ hedefi tutturamamıştır ve gradasyon yeniden seçilmelidir.
D2 tutmazsa sapmanın kaynağı duvar işlemi DEĞİLDİR ve %8 toleransı bu vakada
bağımsız olarak doğrulanamaz — bu da açıkça söylenir.

Silindir DES'inde AYNI kusur bulunmuştu ama düzeltmek sonucu değiştirmemişti
(subkritik rejimde model formu baskındı). Burada beklenti farklı: ayrılma yeri
duvar işlemine doğrudan duyarlıdır. Hangi sonuç çıkarsa ölçüm konuşur.

Üretim: python experiments/naca0012_a8_duvar_cozunur.py
Çıktı : naca0012_a8_duvar_cozunur.json
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
from validation_suite import NACA0012_NASA, NACA0012Validation  # noqa: E402

KOK = HERE.parent
KANIT = KOK / "naca0012_a8_duvar_cozunur.json"
ALPHA = 8
RE_HEDEF = 6.0e6
TOLERANS_LIFT_PCT = 8.0
YPLUS_HEDEF = 5.0          # duvar-çözümlü üst sınır

# Duvar-normal ag: y+~1 icin ilk hucre ~1e-5 m gerekiyor (mevcut ~3e-3).
# Gradasyon ve hucre sayisi ARTIRILIR; degerler ALGEBRAYLA DEGIL olcumle
# dogrulanir (D1) — kestirim tutmazsa iddia dusmus olur ve bu raporlanir.
N_NORMAL = 200
GRADING = 120_000


def _yplus_olc(case: Path) -> dict | None:
    """Cozum oturduktan sonra yPlus function object ile OLC."""
    # Yama ve arama KANONİK yardımcılardan; her betiğin kendi vaka-sözlüğü
    # yazıcısını taşıması iskele tekrarını sayan denetimi büyütüyordu.
    controldict_yamala(case, end_time=20_020, start_from="latestTime",
                       yplus_ekle=True)
    cu = windows_to_wsl_path(case)
    r = linux_run(f"{OF_ENV_PREFIX} cd '{cu}' && foamRun -solver incompressibleFluid "
                  "> log.yplus 2>&1; find postProcessing -name 'yPlus.dat' | head -1 "
                  "| xargs -r tail -1", timeout=1200)
    cikti = getattr(r, "stdout", "") or getattr(r, "output", "") or ""
    m = re.search(r"airfoil\s+([\d.e+-]+)\s+([\d.e+-]+)\s+([\d.e+-]+)", cikti)
    if not m:
        return None
    return {"min": float(m.group(1)), "max": float(m.group(2)),
            "ort": float(m.group(3))}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    v = NACA0012Validation(str(KOK / "_a8_duvar_cozunur"))
    v.NU = v.V * v.C / RE_HEDEF
    v.RE = RE_HEDEF
    v.n_prof, v.n_norm, v.grading = 200, N_NORMAL, GRADING
    v.nut_wall = "nutLowReWallFunction"      # duvarda nut = 0
    v.k_wall = "kLowReWallFunction"          # viskoz alt-katman k profili
    v.force_gentle = True
    v.end_time = 6000
    print(f"koşuyor: α={ALPHA}° Re={RE_HEDEF:.1e} n_norm={N_NORMAL} grading={GRADING}",
          flush=True)
    r = v.run(ALPHA)

    cl_ref, cd_ref, kaynak = NACA0012_NASA[ALPHA]
    cl, cd = r.get("Cl_sim"), r.get("Cd_sim")
    h_cl = 100 * abs(cl - cl_ref) / abs(cl_ref) if cl is not None else None
    h_cd = 100 * abs(cd - cd_ref) / abs(cd_ref) if cd is not None else None

    case = case_bul(KOK / "_a8_duvar_cozunur")
    yp = _yplus_olc(case)
    d1 = yp is not None and yp["max"] <= YPLUS_HEDEF
    d2 = h_cl is not None and h_cl < TOLERANS_LIFT_PCT

    if yp is None:
        verdikt = "⚠️ y⁺ ÖLÇÜLEMEDİ — D1 sınanamadı."
    elif not d1:
        verdikt = (f"⚠️ D1 TUTMADI: y⁺ max {yp['max']:.1f} > {YPLUS_HEDEF} "
                   f"(min {yp['min']:.2f}, ort {yp['ort']:.1f}). Ağ duvar-çözümlü "
                   "hedefi tutturamadı; gradasyon/hücre sayısı yeniden seçilmeli. "
                   "D2 bu koşuyla SINANAMAZ.")
    elif d2:
        verdikt = (f"✅ D1 ve D2 TUTTU: y⁺ ≤ {yp['max']:.2f} (duvar-çözümlü) ve "
                   f"α=8° taşıma hatası %{h_cl:.1f} < %{TOLERANS_LIFT_PCT}. "
                   "Sapmanın kaynağı DUVAR İŞLEMİYDİ ve düzeltildi; ilan edilen "
                   "tolerans bu koşulda BAĞIMSIZ olarak doğrulandı.")
    else:
        verdikt = (f"⚠️ D1 tuttu (y⁺ max {yp['max']:.2f}) ama D2 TUTMADI: taşıma "
                   f"hatası %{h_cl:.1f} ≥ %{TOLERANS_LIFT_PCT}. Duvar işlemi "
                   "düzeltildiği hâlde sapma sürüyor — kaynak duvar işlemi "
                   "DEĞİL. Silindir DES'indeki model-form sonucuyla aynı yönde.")

    o = {"vaka": f"NACA0012 α={ALPHA}° duvar-çözümlü (Re={RE_HEDEF:.1e})",
         "sinanan_iddia": {"D1": f"y⁺ ≤ {YPLUS_HEDEF} (ölçülür)",
                           "D2": f"α=8° taşıma hatası < %{TOLERANS_LIFT_PCT}",
                           "_not": "İddialar koşudan ÖNCE docstring'de sabitlendi."},
         "onceki_kusur": {"yplus_min": 16.18, "yplus_max": 356.7,
                          "duvar_islemi": "nutkWallFunction",
                          "Cl_hata_pct": 18.2, "Cd_hata_pct": 248.0,
                          "_not": "iterasyon 2000→10000 düzeltmedi"},
         "kurulum": {"n_prof": 200, "n_norm": N_NORMAL, "grading": GRADING,
                     "nut_wall": "nutLowReWallFunction",
                     "k_wall": "kLowReWallFunction", "end_time": 6000},
         "olculen": {"Cl": cl, "Cd": cd, "Cl_ref": cl_ref, "Cd_ref": cd_ref,
                     "Cl_hata_pct": h_cl, "Cd_hata_pct": h_cd,
                     "yplus": yp, "ref_kaynak": kaynak},
         "D1": d1, "D2": d2, "verdikt": verdikt,
         "_uretim": "Üretim: python experiments/naca0012_a8_duvar_cozunur.py"}
    KANIT.write_text(json.dumps(o, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + verdikt)
    print(f"-> {KANIT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
