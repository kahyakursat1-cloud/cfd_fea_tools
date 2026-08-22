"""FSI tahrik bandı — sehim/açıklık oranı kuplajı sürecek kadar büyük mü.

NEDEN: iki-yönlü kuplaj ilmeği uçtan uca koşuyordu ama iki test vakası da
`sabit-harita` imzası verdi (r₁ = r₀/2 tam, ω: 0,5 → 1,0, r₂/r₀ ≈ 10⁻⁶), yani
`map_fn` girdiye yanıt vermiyordu. Sebep meşruydu: 2,5 mm alüminyum levha
30 m/s'de 0,186 mm sehim yapıyor --- açıklığın %0,06'sı; akış bunu görmüyor.
Araç "senin vakan tek-yönlü yeter" diyordu ve bu DOĞRU bir hükümdü.

Gerçek tahrik için sehim/açıklık %1--3 gerekir. Bu dosya o bandı ARAR ve
aramanın kendisini kaydeder: hangi ayar hangi sehimi verdi, hangisi aracın
kendi geçerlilik kapısından geçti.

İKİ KAPI AYNI ANDA SAĞLANMALI ve zıt yönlere çekerler:

  ALT SINIR (fizik)   — sehim/açıklık %1'in altındaysa akış yapıyı görmez,
                        kuplaj sabit-haritaya döner ve iki-yönlü koşmanın
                        anlamı kalmaz.
  ÜST SINIR (kuram)   — sehim model boyutunun %5'ini aşarsa doğrusal statik
                        FEA'nın küçük-deformasyon varsayımı düşer; aracın
                        kendi kapısı sonucu GEÇERSİZ ilan eder.

Yani tahrik bandı, iki hükmün arasında kalan dar aralıktır.

    python experiments/fsi_tahrik_bandi.py
Çıktı: fsi_tahrik_bandi.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "fsi_tahrik_bandi.json"

# Aracin dogrusal-statik gecerlilik kapisi (vehicle_fea): sehim model
# boyutunun %5'ini asarsa sonuc GECERSIZ.
DOGRUSAL_TAVAN_PCT = 5.0
# Kuplajin FIZIKSEL olarak surulmesi icin gereken alt sinir.
TAHRIK_TABANI_PCT = 1.0


def _kosu_oku(ad: str) -> dict | None:
    rd = KOK / "vehicle_runs" / ad
    sj, fj = rd / "sonuc.json", rd / "fea_sonuc.json"
    if not (sj.exists() and fj.exists()):
        return None
    s = json.loads(sj.read_text(encoding="utf-8"))
    f = json.loads(fj.read_text(encoding="utf-8"))
    if f.get("status") != "ok" or f.get("max_sehim_mm") is None:
        return None
    # ACIKLIK = konsolun UZUNLUGU, en buyuk gabari degil. Mesnet y-min
    # duzlemi oldugu icin acikliK y boyudur; boyutu geometriden okuyoruz,
    # varsaymiyoruz.
    g = s.get("geometry") or {}
    kutu = g.get("bbox_m") or g.get("boyut_m")
    boy_m = (kutu[1] if kutu and len(kutu) == 3 else g.get("lmax_m"))
    sehim_mm = float(f["max_sehim_mm"])
    oran = 100.0 * (sehim_mm / 1000.0) / boy_m if boy_m else None
    return {
        "kosu": ad, "hiz_m_s": s.get("velocity"), "alpha_deg": s.get("alpha_deg"),
        "aciklik_m": boy_m, "sehim_mm": round(sehim_mm, 3),
        "sehim_aciklik_pct": round(oran, 2) if oran else None,
        "normal_kuvvet_N": (f.get("toplam_kuvvet_N") or [None, None, None])[2],
        "max_von_mises_MPa": f.get("max_von_mises_MPa"),
        "dugum": f.get("dugum"), "eleman_tipi": f.get("eleman_tipi"),
        "arac_gecersiz_dedi": f.get("gecersiz"),
        "bandda_mi": (oran is not None
                      and TAHRIK_TABANI_PCT <= oran <= DOGRUSAL_TAVAN_PCT),
    }


def olc(kosular: list[str]) -> dict:
    kayit = [k for k in (_kosu_oku(a) for a in kosular) if k]
    bandda = [k for k in kayit if k["bandda_mi"]]
    asan = [k for k in kayit if k["sehim_aciklik_pct"]
            and k["sehim_aciklik_pct"] > DOGRUSAL_TAVAN_PCT]
    zayif = [k for k in kayit if k["sehim_aciklik_pct"]
             and k["sehim_aciklik_pct"] < TAHRIK_TABANI_PCT]
    return {
        "vaka": "FSI tahrik bandı — sehim/açıklık kuplajı sürüyor mu",
        "_neden": ("Iki-yonlu ilmek kosuyordu ama iki test vakasi da SABIT-HARITA "
                   "imzasi verdi: sehim/aciklik %0,06 idi ve akis yapiyi gormedi."),
        "dogrusal_tavan_pct": DOGRUSAL_TAVAN_PCT,
        "tahrik_tabani_pct": TAHRIK_TABANI_PCT,
        "kosular": kayit,
        "bandda": [k["kosu"] for k in bandda],
        "tavani_asan": [f"{k['kosu']} (%{k['sehim_aciklik_pct']})" for k in asan],
        "tabanin_altinda": [f"{k['kosu']} (%{k['sehim_aciklik_pct']})" for k in zayif],
        "verdikt": (
            (f"TAHRIK BANDI BULUNDU: {', '.join(k['kosu'] for k in bandda)} — "
             f"sehim/açıklık %{bandda[0]['sehim_aciklik_pct']}, hem fiziksel "
             f"tabanın (%{TAHRIK_TABANI_PCT}) üstünde hem doğrusal tavanın "
             f"(%{DOGRUSAL_TAVAN_PCT}) altında.")
            if bandda else
            (f"BAND BULUNAMADI: {len(asan)} koşu doğrusal tavanı AŞTI, "
             f"{len(zayif)} koşu tahrik tabanının ALTINDA kaldı. "
             f"İki-yönlü kuplajın fiziksel olarak sürüldüğü bir vaka HENÜZ YOK.")
            if kayit else "ÖLÇÜLEMEDİ — FEA sonucu olan koşu yok"),
        "_kisit": (
            "Sehim/aciklik kuplajin surulmesi icin GEREK sarttir, YETER sart "
            "degildir: asil kanit Aitken artik dizisinin sabit-harita imzasini "
            "VERMEMESIDIR. Bu dosya yalnizca aday vakayi secer; hukum kuplaj "
            "kosusundan gelir. Ayrica sehim DOGRUSAL statik cozumden okundu — "
            "tavana yakin degerlerde gercek sehim bundan kucuktur (gerilme "
            "sertlesmesi), yani oran bir UST kestirimdir."),
        "_uretim": "Üretim: python experiments/fsi_tahrik_bandi.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    adlar = [p.name for p in sorted((KOK / "vehicle_runs").glob("*"))
             if (p / "fea_sonuc.json").exists()]
    r = olc(adlar)
    print("FSI tahrik bandı\n")
    print(f"{'koşu':<24}{'V':>6}{'açıklık':>9}{'sehim':>9}{'sehim/açıklık':>15}  hüküm")
    for k in r["kosular"]:
        h = ("BANDDA" if k["bandda_mi"] else
             "tavanı aşıyor" if (k["sehim_aciklik_pct"] or 0) > DOGRUSAL_TAVAN_PCT
             else "tabanın altında")
        print(f"{k['kosu'][:23]:<24}{k['hiz_m_s'] or 0:>6.0f}"
              f"{(k['aciklik_m'] or 0)*1000:>8.0f}mm{k['sehim_mm']:>8.2f}mm"
              f"{k['sehim_aciklik_pct'] or 0:>14.2f}%  {h}")
    print(f"\n{r['verdikt']}")
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
