"""Ölçek-çözünürlüklü (DES) çapanın bütçesi — "gerekir" değil, KAÇ hücre.

NEDEN: 3B URANS koşusu kendi açıklamamızı çürüttü. Span yönünde dekorelasyon
OLUŞMADI (C_L salınım genliği 1,312 → 1,278; yalnız %2,6 düşüş) çünkü URANS
dalgalanmayı MODELLER, çözmez. Doğru teşhis "iz daralması" değil çözünürlük
SINIFIYDI ve yol haritası oradan beri "kalan iş: DES/LES çapası" diyor. Bu bir
temenniydi; bütçesi hiç ölçülmedi.

Ahmed duvar-çözünür hücresinde işe yarayan desen aynen uygulanıyor: "pahalı"
demek yerine hücre/bellek/süre bütçesini ÖLÇÜLEN katsayılarla kestirmek ve bu
donanımda ulaşılabilir mi diye sayıyla cevaplamak.

BÜTÇENİN GİRDİLERİ --- hangisi ölçüm, hangisi kural, ayrı tutulur:
  ÖLÇÜM   u_tau: 3B URANS koşusunun y⁺ ortalamasından geri çözüldü (47,27)
  ÖLÇÜM   hücre başına bellek: 0,779 kB (bellek_katsayisi.json, 3 koşu, R²=0,96)
  ÖLÇÜM   çözüm hızı: 403.200 hücre × 3.300 adım / 2,0 saat, 4 çekirdek
  ÖLÇÜM   boş bellek: bu makinede ölçüldü
  KURAL   ayrılan kesme tabakasında izotropi: azimut adımı ≥ span adımı
  KURAL   duvarda y⁺≈1 (DES'in RANS kolu duvarda çözünür olmalı)
  KURAL   radyal büyüme oranı ≤ 1,1
  KURAL   dökülme periyodu başına ≥ 200 adım (URANS koşusu 150 kullanıyordu)
  KURAL   22 periyot: 6 geçiş + 16 istatistik (deponun 2B çapasındaki bölme)

NE SÖYLEMEZ: bu betik DES'in doğru cevabı vereceğini söylemez. Δz/D'nin hangi
değerinde span dekorelasyonunun gerçekten oluşacağı ancak koşu ile bilinir;
burada ölçülen tek şey, hangi çözünürlüğün bu donanımda ULAŞILABİLİR olduğudur.

    python experiments/des_fizibilite.py
Çıktı: des_fizibilite.json
"""
from __future__ import annotations

import ctypes
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "des_fizibilite.json"

D, U = 1.0, 1.0
RE = 140_000.0
NU = U * D / RE
ST = 0.20                     # deneysel plato (Roshko 1961; Norberg 2003)
SPAN_D = math.pi              # Lz = πD (3B URANS koşusuyla AYNI)

# 3B URANS kosusundan OLCULEN: ilk hucre yuksekligi ve o hucredeki y+.
ILK_HUCRE_M = 0.012667        # radyal grading 40, 70 hucre, 0.5->10 m
YPLUS_OLCULEN = 47.268
N_CEVRE_MEVCUT = 240          # 4 blok x 60

BUYUME = 1.10                 # radyal genisleme siniri
WAKE_YARICAP_D = 5.0          # izin cozunur tutuldugu bolge
DIS_YARICAP_M = 10.0
PERIYOT_ADIM = 200            # dokulme periyodu basina en az adim
PERIYOT = 22                  # 6 gecis + 16 istatistik

KB_HUCRE = 0.779              # OLCULEN (bellek_katsayisi.json)
HIZ_HUCRE_ADIM_SAAT = 403_200 * 3_300 / 2.0   # OLCULEN throughput, 4 cekirdek


def _bos_bellek_gb() -> float:
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    s = MS()
    s.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
    return s.ullAvailPhys / 1e9


def u_tau() -> float:
    """y⁺ = y·u_τ/ν → ölçülen y⁺ ve hücre MERKEZİNDEN geri çöz."""
    return YPLUS_OLCULEN * NU / (ILK_HUCRE_M / 2.0)


def _radyal_hucre(dz: float, h0: float) -> dict:
    """Duvardan uzağa üç bölge: sıkıştırma → düzgün iz → dışa büyüme."""
    # 1) h0'dan dz'ye BUYUME oraniyla
    n1 = max(1, math.ceil(math.log(dz / h0) / math.log(BUYUME)))
    kalinlik1 = h0 * (BUYUME ** n1 - 1) / (BUYUME - 1)
    r1 = D / 2.0 + kalinlik1
    # 2) dz ile duzgun, izin cozunur tutuldugu yaricapa kadar
    r2 = WAKE_YARICAP_D * D
    n2 = max(0, math.ceil((r2 - r1) / dz)) if r2 > r1 else 0
    # 3) disa dogru buyume
    kalan = DIS_YARICAP_M - max(r1, r2)
    n3 = (max(1, math.ceil(math.log(1 + kalan * (BUYUME - 1) / dz)
                           / math.log(BUYUME))) if kalan > 0 else 0)
    return {"n_sikistirma": n1, "n_duzgun": n2, "n_disa": n3,
            "n_toplam": n1 + n2 + n3, "sikistirma_kalinlik_m": round(kalinlik1, 4)}


def butce(dz_D: float, bos_gb: float) -> dict:
    dz = dz_D * D
    ut = u_tau()
    h0 = 2.0 * NU / ut                      # y⁺=1 → hücre MERKEZİ ν/u_τ'da
    rad = _radyal_hucre(dz, h0)
    n_cevre = max(N_CEVRE_MEVCUT, math.ceil(math.pi * D / dz))
    n_z = math.ceil(SPAN_D * D / dz)
    hucre = n_cevre * rad["n_toplam"] * n_z

    periyot_s = D / (ST * U)
    dt = min(dz / U, periyot_s / PERIYOT_ADIM)   # CFL≈1 iz bölgesinde
    adim = math.ceil(PERIYOT * periyot_s / dt)

    bellek_gb = hucre * KB_HUCRE / 1e6
    saat = hucre * adim / HIZ_HUCRE_ADIM_SAAT
    return {
        "dz_D": dz_D,
        "ilk_hucre_m": round(h0, 8),
        "ilk_hucre_mm": round(h0 * 1000, 4),
        "n_cevre": n_cevre, "n_radyal": rad["n_toplam"], "n_span": n_z,
        "radyal_bolgeler": rad,
        "hucre": hucre,
        "dt_s": round(dt, 5),
        "adim": adim,
        "bellek_gb": round(bellek_gb, 2),
        "bos_bellek_gb": round(bos_gb, 2),
        "bellege_sigar_mi": bool(bellek_gb < bos_gb),
        "sure_saat": round(saat, 1),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    bos = _bos_bellek_gb()
    ut = u_tau()
    satirlar = [butce(x, bos) for x in (0.10, 0.05, 0.025)]
    sigan = [s for s in satirlar if s["bellege_sigar_mi"]]

    rec = {
        "vaka": "DES çapası fizibilitesi — silindir, Re=140.000",
        "_neden": ("3B URANS span dekorelasyonunu URETEMEDI (C_L genligi yalniz "
                   "%2,6 dustu) ve dogru teshis cozunurluk SINIFIYDI. Yol "
                   "haritasi o gunden beri 'kalan is: DES/LES capasi' diyor; "
                   "bu bir temenniydi, butcesi hic olculmedi."),
        "olculen_girdiler": {
            "u_tau_ms": round(ut, 5),
            "u_tau_kaynagi": (f"3B URANS y⁺ ort={YPLUS_OLCULEN} ve ilk hücre "
                              f"{ILK_HUCRE_M} m'den geri çözüldü"),
            "nu_m2s": NU,
            "kb_hucre": KB_HUCRE,
            "kb_hucre_kaynagi": "bellek_katsayisi.json (3 koşu, R²=0,96)",
            "hucre_adim_saat": HIZ_HUCRE_ADIM_SAAT,
            "hiz_kaynagi": "3B URANS: 403.200 hücre × 3.300 adım / 2,0 saat (4 çekirdek)",
            "bos_bellek_gb": round(bos, 2),
        },
        "kurallar": {
            "izotropi": "azimut adımı ≥ span adımı (ayrılan kesme tabakasında)",
            "duvar": "y⁺≈1 — DES'in RANS kolu duvarda çözünür olmalı",
            "buyume": BUYUME,
            "periyot_basina_adim": PERIYOT_ADIM,
            "periyot": f"{PERIYOT} (6 geçiş + 16 istatistik — 2B çapanın bölmesi)",
        },
        "satirlar": satirlar,
        "_ne_soylemez": ("DES'in DOGRU cevabi verecegini SOYLEMEZ. Hangi Δz/D'de "
                         "span dekorelasyonunun gercekten olusacagi ancak kosu "
                         "ile bilinir; burada olculen tek sey hangi cozunurlugun "
                         "bu donanimda ULASILABILIR oldugudur."),
        "_kisit": ("Sure kestirimi hucre basina maliyeti DOGRUSAL varsayar ve "
                   "URANS throughput'undan olceklenir; DES ayni cozucu ailesinde "
                   "kosar ama alt-agi modeli ve daha siki CFL farkli davranabilir. "
                   "Bellek katsayisi 0,779 kB/hucre URANS kosularindan olculdu."),
        "_uretim": "Üretim: python experiments/des_fizibilite.py",
    }
    # MEVCUT 3B URANS agi: nz=24, Lz=piD -> Δz/D = pi/24 = 0,131. Yani "0,1"
    # satiri zaten CURUYEN kosudan yalnizca biraz ince; anlamli adim 0,05'tir.
    rec["mevcut_urans_dz_D"] = round(SPAN_D / 24, 4)
    rec["mevcut_urans_hucre"] = 403_200
    if sigan:
        en_ince = min(sigan, key=lambda s: s["dz_D"])
        kat = en_ince["hucre"] / 403_200
        rec["onerilen"] = en_ince["dz_D"]
        rec["verdikt"] = (
            f"ULAŞILABİLİR. Çürüyen 3B URANS koşusunun span adımı "
            f"Δz/D={rec['mevcut_urans_dz_D']} idi; anlamlı adım Δz/D="
            f"{en_ince['dz_D']} ({rec['mevcut_urans_dz_D'] / en_ince['dz_D']:.1f}× "
            f"ince): {en_ince['hucre']:,} hücre ({kat:.1f}× mevcut), "
            f"{en_ince['bellek_gb']} GB (boş {en_ince['bos_bellek_gb']} GB), "
            f"{en_ince['sure_saat']} saat. Ahmed duvar-çözünür hücresinin "
            f"AKSİNE bu çapa bu donanımda koşulabilir — engel bellek değil "
            f"SÜREdir ve bir gecede biter.")
    else:
        rec["verdikt"] = ("ULAŞILAMAZ: denenen çözünürlüklerin hiçbiri boş "
                          "belleğe sığmıyor.")

    import ortam
    ortam.damgala(rec)
    CIKTI.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")

    print(rec["vaka"] + "\n" + "=" * 78)
    print(f"u_τ = {ut:.5f} m/s   ν = {NU:.3e} m²/s   "
          f"y⁺=1 ilk hücre = {satirlar[0]['ilk_hucre_mm']} mm")
    print(f"{'Δz/D':>7}{'hücre':>12}{'Δt [s]':>9}{'adım':>8}"
          f"{'bellek':>9}{'sığar':>7}{'süre [sa]':>11}")
    for s in satirlar:
        print(f"{s['dz_D']:>7}{s['hucre']:>12,}{s['dt_s']:>9}{s['adim']:>8}"
              f"{s['bellek_gb']:>8.2f}G{'evet' if s['bellege_sigar_mi'] else 'HAYIR':>7}"
              f"{s['sure_saat']:>11.1f}")
    print("=" * 78)
    print(rec["verdikt"])
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
