"""Subkritik silindir için FİZİKSEL OLARAK doğru kurulumun bütçesi — ölçülür, tahmin edilmez.

Neden gerekli: 2026-08-12'de 10,5 saatlik kOmegaSSTDES koşusu geçersiz çıktı
(duvar fonksiyonları y⁺≈1 ağında). "Doğrusunu yapalım" demek, önce doğrusunun
NE olduğunu ve bu makinede SIĞIP SIĞMADIĞINI bilmeyi gerektirir.

Fizik: Re = 1,4e5 subkritik. Bağlı sınır tabaka LAMİNERDİR, ayrılma ~80°'de olur
ve Cd ≈ 1,2 ile St ≈ 0,2 oradan doğar. Tam-türbülanslı bir RANS kapanışı
(kOmegaSST tabanlı DES dahil) bu tabakayı türbülanslı sayar, ayrılmayı geciktirir,
izi daraltır: Cd DÜŞÜK, St YÜKSEK çıkar. Depodaki iki bağımsız ölçüm de bu imzayı
taşıyor — URANS 3B (duvar fonksiyonu GEÇERLİ, y⁺≈47): Cd %-27, St %+30;
DES (duvar işlemi bozuk): Cd %-40, St %+38. Yani sapmanın gövdesi duvar
işleminden değil MODEL FORMUNDAN geliyor.

Geçiş-duyarlı DES bu OpenFOAM 11 derlemesinde YOK (ölçüldü: geçerli LES modelleri
DeardorffDiffStress, Smagorinsky, SpalartAllmaras{DES,DDES,IDDES}, WALE,
dynamicKEqn, dynamicLagrangian, kEqn, kOmegaSSTDES). Geriye kalan fiziksel doğru
yol duvar-çözümlü LES'tir (WALE tercih edilir: saf kaymada ν_t → 0, laminer
bölgede sahte türbülans viskozitesi üretmez).

Bu betik o yolun ağ gereksinimini duvar birimlerinden hesaplar ve makinenin
belleğiyle karşılaştırır. Çıktı bir sayı değil, bir YAPILABİLİRLİK HÜKMÜDÜR.

Üretim: python experiments/silindir_les_fizibilite.py
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

D = 1.0
U = 1.0
RE = 140_000.0
NU = U * D / RE
SPAN_D = math.pi                    # Lz/D — mevcut çapayla aynı
BELLEK_KB_HUCRE = 0.779             # ÖLÇÜLDÜ (bellek_katsayisi.json)


def _makine_gb() -> float:
    """Makinenin TOPLAM RAM'ini ÖLÇ — varsayma.

    İlk sürüm 16.0 GB varsayıyordu; ölçülünce 13,7 GB çıktı. Bütçe hükmü bir
    varsayıma dayanamaz: bugün bu dosyanın kendisi 'tahmin etme, ölç' diye
    yazıldı ve makine kapasitesi de o kurala tabidir.
    """
    import ctypes

    class _M(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    m = _M()
    m.dwLength = ctypes.sizeof(_M)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullTotalPhys / 1024 ** 3


MAKINE_GB = _makine_gb()            # ÖLÇÜLDÜ, varsayılmadı

# Duvar-çözümlü LES'in KABUL EDİLEN çözünürlük ölçütü (Piomelli & Balaras 2002;
# Georgiadis et al., AIAA J. 48 (2010) — WRLES kılavuzu):
DX_ARTI = 50.0    # akış yönünde
DZ_ARTI = 20.0    # açıklık yönünde
DY_ARTI = 1.0     # ilk hücre (duvar-normal)


def _u_tau() -> float:
    """Düz-levha korelasyonundan sürtünme hızı — mertebe kestirimi."""
    cf = 0.058 * RE ** -0.2
    return U * math.sqrt(cf / 2.0)


def hesapla() -> dict:
    utau = _u_tau()
    l_v = NU / utau                                  # viskoz uzunluk
    dx = DX_ARTI * l_v
    dz = DZ_ARTI * l_v
    dy1 = DY_ARTI * l_v

    n_cevre = math.ceil(math.pi * D / dx)             # silindir çevresi
    n_span = math.ceil(SPAN_D * D / dz)
    # Duvar-normal: ilk hücreden uzak-alana geometrik büyüme
    n_radyal = math.ceil(math.log(0.05 * D / dy1) / math.log(1.05)) + 40

    hucre = n_cevre * n_span * n_radyal
    bellek_gb = hucre * BELLEK_KB_HUCRE / 1024 ** 2
    return {"u_tau_ms": round(utau, 5), "viskoz_uzunluk_m": l_v,
            "dx_m": dx, "dz_m": dz, "ilk_hucre_m": dy1,
            "n_cevre": n_cevre, "n_span": n_span, "n_radyal": n_radyal,
            "hucre": hucre, "bellek_GB": round(bellek_gb, 2)}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    b = hesapla()
    mevcut = 2_434_320                                # kOmegaSSTDES koşusu
    kat = b["hucre"] / mevcut
    sigar = b["bellek_GB"] <= MAKINE_GB

    verdikt = (
        f"Duvar-çözümlü LES {b['hucre']:,} hücre ({b['bellek_GB']:.1f} GB) "
        f"gerektiriyor — mevcut DES ağının {kat:.0f} KATI. "
        + ("Bu makinede SIĞIYOR." if sigar else
           f"Bu makinede SIĞMIYOR ({MAKINE_GB:.0f} GB). Subkritik silindirde "
           "Cd/St'yi deneysel banda getirmek bu donanımda YAPILAMAZ; "
           "kOmegaSSTDES'in sapması bir çözünürlük eksiği değil MODEL-FORM "
           "sınırıdır ve öyle raporlanmalıdır.")
    )

    o = {
        "vaka": f"Subkritik silindir (Re={RE:.0f}) duvar-çözümlü LES bütçesi",
        "fizik": ("Subkritik rejimde bağlı sınır tabaka LAMİNER; ayrılma ~80°. "
                  "Tam-türbülanslı RANS kapanışı ayrılmayı geciktirir → Cd düşük, "
                  "St yüksek. Depodaki iki ölçüm de bu imzayı taşıyor."),
        "olculen_imza": {
            "URANS_3B_kOmegaSST": {"yplus_ort": 47.27, "duvar_islemi": "GEÇERLİ",
                                   "Cd_sapma_pct": -26.88, "St_sapma_pct": 29.74},
            "DES_kOmegaSSTDES": {"yplus_ort": 0.0091, "duvar_islemi": "GEÇERSİZ",
                                 "Cd_sapma_pct": -39.61, "St_sapma_pct": 37.61},
            "_yorum": ("Duvar işlemi GEÇERLİ olan koşu da aynı yönde sapıyor; "
                       "duvar işlemini düzeltmek sapmayı kapatmaz."),
        },
        "mevcut_modeller": ["DeardorffDiffStress", "Smagorinsky",
                            "SpalartAllmarasDDES", "SpalartAllmarasDES",
                            "SpalartAllmarasIDDES", "WALE", "dynamicKEqn",
                            "dynamicLagrangian", "kEqn", "kOmegaSSTDES"],
        "gecis_duyarli_DES": False,
        "_model_kaynagi": "OpenFOAM 11'e geçersiz model adı verilerek SORULDU",
        "olcut": {"dx_arti": DX_ARTI, "dz_arti": DZ_ARTI, "dy_arti": DY_ARTI,
                  "kaynak": "Piomelli & Balaras 2002; Georgiadis ve ark. 2010 — WRLES"},
        "butce": b,
        "makine_GB_olculen": round(MAKINE_GB, 1),
        "mevcut_DES_hucre": mevcut,
        "kat": round(kat, 1),
        "sigar_mi": sigar,
        "verdikt": verdikt,
        "_kapsam": ("Düz-levha korelasyonundan MERTEBE kestirimi; silindirde "
                    "u_tau çevresel olarak değişir ve ayrılma sonrası düşer. "
                    "Sayı bir üst-sınır değil, doğru MERTEBEdir."),
        "_uretim": "Üretim: python experiments/silindir_les_fizibilite.py",
    }
    hedef = HERE.parent / "silindir_les_fizibilite.json"
    hedef.write_text(json.dumps(o, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(json.dumps(b, indent=2))
    print("\n" + verdikt)
    print(f"-> {hedef.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
