"""Girdi belirsizliği yayılımı (input UQ) bu donanımda kaç koşu eder.

HAKEM İSTEDİ (#9): belirsizlik bugün SAYISAL (GCI/LSR) ve MODEL-FORM
bileşenlerinden kuruluyor; GİRDİ belirsizliği (hız, açı, yoğunluk, geometri
ölçeği) yayılmıyor. Monte Carlo / LHS / polinom kaos ile yapılmalı.

ÜÇÜNCÜ BİLEŞEN. Bu, mevcut iki bileşenin yerine geçmez; yanına gelir:
    u_toplam² = u_sayısal² + u_model² + u_girdi²
Bugün üçüncü terim SIFIR sayılıyor --- ölçülmediği için değil, hiç
sorulmadığı için. Sıfır saymak, girdiyi kesin bilindiği varsaymaktır.

BÜTÇE ÖLÇÜLEN MALİYETTEN KURULUR, kestirilmez: koşu arşivindeki aşama
telemetrisinden koşu başına duvar süresi okunur.

NE ÖLÇÜLEMEZ: girdi dağılımlarının KENDİSİ. Hızın ±%2 mi ±%10 mu belirsiz
olduğu kullanıcının vakasına bağlıdır ve bu dosya bir dağılım UYDURMAZ;
yalnız KAÇ koşu gerektiğini ve NE KADAR SÜRECEĞİNİ verir.

    python experiments/girdi_uq_butcesi.py
Çıktı: girdi_uq_butcesi.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "girdi_uq_butcesi.json"

# Hattin GERCEKTEN degistirebildigi girdiler (run_vehicle_analysis imzasi).
# Bir degiskeni buraya yazmak, hattin onu parametre olarak kabul ettigi
# anlamina gelir — test bunu dogruluyor.
ADAY_GIRDILER = {
    "velocity": "serbest akım hızı — rüzgâr tüneli/uçuş koşulu belirsizliği",
    "alpha_deg": "hücum açısı — montaj/trim belirsizliği",
    "rho": "hava yoğunluğu — irtifa ve sıcaklık",
}

# Ortak orneklem kurallari.
LHS_KAT = 10          # yaygin pratik: 10 x boyut
PC_MERTEBE = 2        # ikinci mertebe polinom kaos
PC_FAZLA = 2.0        # en-kucuk-kareler icin taban sayisinin kati
MC_N = 500            # ~%5 bagil hata (std kestirimi icin kaba)


def _kosu_maliyeti() -> dict:
    """Koşu başına duvar süresi — ARŞİVDEN, kestirimle değil."""
    sureler, hucreler = [], []
    for sj in sorted((KOK / "vehicle_runs").glob("*/sonuc.json")):
        d = json.loads(sj.read_text(encoding="utf-8"))
        a = d.get("asama_sureleri")
        if not a or d.get("status") != "ok":
            continue
        sureler.append(sum(x.get("sure_s", 0) for x in a))
        h = (d.get("mesh") or {}).get("cells")
        if h:
            hucreler.append(h)
    if not sureler:
        return {}
    sureler.sort()
    return {
        "n_kosu": len(sureler),
        "medyan_s": round(sureler[len(sureler) // 2], 1),
        "min_s": round(sureler[0], 1), "max_s": round(sureler[-1], 1),
        "medyan_hucre": (sorted(hucreler)[len(hucreler) // 2] if hucreler else None),
        "_kaynak": "koşu arşivi, aşama telemetrisi (asama_sureleri)",
    }


def pc_taban(d: int, p: int = PC_MERTEBE) -> int:
    """Polinom kaos taban sayısı: (d+p)! / (d! p!)."""
    return math.comb(d + p, p)


def yontemler(d: int) -> list[dict]:
    return [
        {"yontem": "LHS (tarama)", "n": LHS_KAT * d,
         "ne_verir": "birinci-mertebe duyarlılık ve kaba band",
         "_not": f"{LHS_KAT}×boyut yaygın pratiktir, kanıt değil"},
        {"yontem": f"Polinom kaos (mertebe {PC_MERTEBE})",
         "n": int(pc_taban(d) * PC_FAZLA),
         "ne_verir": "band + Sobol duyarlılık indeksleri",
         "_not": f"taban {pc_taban(d)}, en-küçük-kareler için ×{PC_FAZLA:g}"},
        {"yontem": f"Monte Carlo (n={MC_N})", "n": MC_N,
         "ne_verir": "dağılımın kendisi, kuyruk dahil",
         "_not": "std kestiriminde ~%5 bağıl hata; kuyruk için daha fazlası"},
    ]


def olc() -> dict:
    m = _kosu_maliyeti()
    d = len(ADAY_GIRDILER)
    tablo = []
    for y in yontemler(d):
        s = y["n"] * (m.get("medyan_s") or 0)
        tablo.append({**y, "toplam_saat": round(s / 3600, 2),
                      "bir_gecede_mi": s <= 12 * 3600,
                      "bir_saatte_mi": s <= 3600})
    ulasilabilir = [t for t in tablo if t["bir_gecede_mi"]]
    en_ucuz = min(tablo, key=lambda t: t["toplam_saat"]) if tablo else None

    return {
        "vaka": "Girdi belirsizliği yayılımı — koşu bütçesi",
        "_neden": ("u_toplam bugun sayisal ve model-form bilesenlerinden "
                   "kuruluyor; GIRDI belirsizligi hic yayilmiyor ve ucuncu "
                   "terim SIFIR sayiliyor — olculmedigi icin degil, hic "
                   "sorulmadigi icin."),
        "girdiler": ADAY_GIRDILER,
        "boyut": d,
        "kosu_maliyeti": m,
        "yontemler": tablo,
        "bir_gecede_ulasilabilir": [t["yontem"] for t in ulasilabilir],
        "verdikt": (
            (f"ULAŞILABİLİR: {d} girdi için {len(ulasilabilir)}/{len(tablo)} "
             f"yöntem bir gecede biter. En ucuzu {en_ucuz['yontem']} — "
             f"{en_ucuz['n']} koşu × {m['medyan_s'] / 60:.1f} dk = "
             f"{en_ucuz['toplam_saat']:.1f} saat. Koşu maliyeti ARŞİVDEN "
             f"ölçüldü ({m['n_kosu']} koşu, medyan {m['medyan_hucre']:,} hücre)."
             ).replace(",", ".")
            if ulasilabilir else
            f"ULAŞILAMAZ: hiçbir yöntem bir gecede bitmiyor "
            f"(en ucuz {en_ucuz['toplam_saat']:.1f} saat)"),
        "_kisit": (
            "Butce KOSU SAYISI verir, GIRDI DAGILIMI vermez. Hizin +-%2 mi "
            "+-%10 mu belirsiz oldugu kullanicinin vakasina baglidir ve bu "
            "dosya bir dagilim UYDURMAZ. Ayrica: maliyet 310 bin hucrelik "
            "`standart` kosulardan olculdu; UQ calismasinin AYNI agda kosmasi "
            "gerekir ki sayisal hata ORTAK-KIP olsun ve girdi etkisinden "
            "ayrilabilsin. Daha ince agda maliyet hucre sayisiyla yaklasik "
            "dogrusal buyur. Son olarak LHS'in 10xboyut kurali bir PRATIKTIR, "
            "kanit degil; yakinsama kosu sayisi artirilarak SINANMALIDIR."),
        "_uretim": "Üretim: python experiments/girdi_uq_butcesi.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    m = r["kosu_maliyeti"]
    print("Girdi belirsizliği yayılımı — bütçe\n")
    print(f"girdiler ({r['boyut']}): {', '.join(r['girdiler'])}")
    print(f"koşu maliyeti: medyan {m['medyan_s'] / 60:.1f} dk "
          f"(aralık {m['min_s'] / 60:.1f}–{m['max_s'] / 60:.1f}), "
          f"{m['n_kosu']} koşudan, medyan {m['medyan_hucre']:,} hücre\n"
          .replace(",", "."))
    print(f"{'yöntem':<30}{'koşu':>6}{'saat':>8}  ne verir")
    for y in r["yontemler"]:
        im = "✓" if y["bir_gecede_mi"] else " "
        print(f"{y['yontem']:<30}{y['n']:>6}{y['toplam_saat']:>8.1f} {im} "
              f"{y['ne_verir']}")
    print(f"\n{r['verdikt']}")
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
