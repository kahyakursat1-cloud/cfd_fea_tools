"""Zaman adımı cevabı sürüklüyor mu? — çapa ailesini yeniden koşmadan önce.

NEDEN: bütün geçici silindir çapaları dt = periyot/150'de koştu ve `maxCo 2`
beyanı ATILDI (yazım hatası: `adjustableTimeStep` OpenFOAM anahtarı değil).
Ölçülen kararlı Courant maksimumu 4,8--5,2, yani beyanın ~2,5 katı. Ortalama
0,22 olduğu için ihlal yereldir ve PIMPLE 2 dış düzelticiyle Co≈5 kendiliğinden
geçersiz değildir --- ama SINANMADAN da geçerli sayılamaz.

SORU KRİTİK YOLDA: geçiş modeli koşusu Cd'yi %77 YÜKSEK veriyor. Bu sapmayı
kapanışa yazmadan önce zaman adımı elenmelidir; Co≈5'te aşırı-tahmin makul bir
alternatif açıklamadır.

NEDEN AİLEYİ YENİDEN KOŞMUYORUZ: `adjustTimeStep yes` + Co≤2 dt'yi ~2,5 kat
küçültür ve aile (URANS 3B + DES + geçiş) ~30 saatten ~75--100 saate çıkar.
Bunu bir HİPOTEZE dayanarak harcamak, bu çalışmada üç kez düşülen tuzağın
aynısıdır (Tu, `nut`, ``ucuz ara adım'' --- üçü de ölçümle çürüdü).

BU SONDA UCUZ AĞDA KOŞAR. URANS 3B (403.200 hücre) aynı ayarlarla ÖLÇÜLMÜŞ bir
taban taşıyor (Cd 0,8775 · St 0,25948) ve dt/2 ile yeniden koşmak ~2,8 saattir.

ÖLÇÜT UYDURULMAZ, SERİNİN KENDİ SAÇILMASINDAN ÇIKAR. Taban kanıtı bir salınım
bandı taşımıyor; sabit bir yüzde eşiği yazmak da bandı ölçmeden hüküm vermek
olurdu. Kullanılan ölçüt istatistikseldir: periyodik bir sinyalin PENCERE
ORTALAMASI da bir örneklem ortalamasıdır. Pencere periyotlara bölünür, periyot
ortalamalarının standart hatası alınır, ve iki koşunun farkı 2 standart hatanın
altındaysa fark ÖRNEKLEMEDEN ayırt edilemez --- zaman adımına yazılamaz.

    python experiments/silindir_dt_sondasi.py [--bolen 2] [--oku]
Çıktı: silindir_dt_sondasi.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

TABAN_KANIT = KOK / "silindir_urans_3b.json"
CIKTI = KOK / "silindir_dt_sondasi.json"


def taban() -> dict:
    """Kıyas tabanı KANIT DOSYASINDAN — ezberden değil.

    Sayıyı buraya sabit yazmak, taban yeniden koşulduğunda sondayı sessizce
    eskitirdi.
    """
    if not TABAN_KANIT.exists():
        return {}
    d = json.loads(TABAN_KANIT.read_text(encoding="utf-8"))
    o, k = d.get("olculen") or {}, d.get("kurulum") or {}
    return {"Cd": o.get("Cd_ortalama"), "St": o.get("St"),
            "Cl_genlik": o.get("Cl_genlik"), "dt_s": k.get("dt_s"),
            "hucre": k.get("hucre"), "model": k.get("model")}


def kur(case: Path, bolen: int) -> dict:
    """URANS 3B kurulumunun AYNISI, yalnız zaman adımı bölünmüş."""
    import silindir_urans_3b as s3

    periyot = s3.D / (s3.ST_DENEY * s3.U)
    dt = periyot / (150.0 * bolen)
    son_s = (s3.PERIYOT_GECIS + s3.PERIYOT_ISTAT) * periyot
    s3.kur(case, dt=dt, son_s=son_s)
    return {"dt_s": dt, "bolen": bolen, "adim": round(son_s / dt),
            "son_s": son_s, "_degisen_tek_sey": "ZAMAN ADIMI"}


def cozunurluk_tabani(t_ser: list, cd_ser: list, periyot_s: float,
                      gecis_s: float) -> dict:
    """İki ortalama AYIRT EDİLEBİLİR Mİ? — serinin kendi saçılmasından.

    Taban kanıtı bir salınım bandı taşımıyor, dolayısıyla farkı ``tabanın
    bandına'' karşı sınamak mümkün değil. Uydurma bir yüzde eşiği yazmak da
    bu çalışmanın reddettiği şey. Doğru yardımcı ölçüt istatistikseldir:
    periyodik bir sinyalin PENCERE ORTALAMASI da bir örneklem ortalamasıdır ve
    kendi belirsizliği vardır.

    Yöntem: istatistik penceresi periyotlara bölünür, her periyodun ortalaması
    alınır, bu ortalamaların standart hatası hesaplanır. İki koşunun
    ortalamaları arasındaki fark 2 standart hatanın altındaysa, fark
    ÖRNEKLEMEDEN ayırt edilemez --- zaman adımı etkisi değil.
    """
    import statistics as st

    pencere = [(a, b) for a, b in zip(t_ser, cd_ser) if a >= gecis_s]
    if len(pencere) < 20 or periyot_s <= 0:
        return {"olculdu": False, "_neden": "istatistik penceresi yetersiz"}
    t0 = pencere[0][0]
    kova: dict[int, list[float]] = {}
    for a, b in pencere:
        kova.setdefault(int((a - t0) / periyot_s), []).append(b)
    ort = [st.mean(v) for v in kova.values() if len(v) >= 5]
    if len(ort) < 3:
        return {"olculdu": False, "_neden": f"yalnız {len(ort)} tam periyot"}
    genel = st.mean(ort)
    sh = st.stdev(ort) / len(ort) ** 0.5
    return {"olculdu": True, "n_periyot": len(ort),
            "periyot_ortalamalari_sd": round(st.stdev(ort), 5),
            "standart_hata": round(sh, 5),
            "ayirt_esigi_pct": round(200.0 * sh / abs(genel), 3),
            "_olcut": ("2 standart hata; altındaki fark örneklemeden ayırt "
                       "EDİLEMEZ ve zaman adımına yazılamaz")}


def hukum(t: dict, y: dict, salinim_genlik_pct: float | None) -> str:
    """Farkı KOŞUNUN KENDİ bandına karşı sına, uydurma yüzdeye karşı değil."""
    if t.get("Cd") is None or y.get("Cd") is None:
        return "ÖLÇÜLEMEDİ — taban ya da sonda Cd'si yok; hüküm YOK."
    d_cd = 100.0 * abs(y["Cd"] - t["Cd"]) / abs(t["Cd"])
    d_st = (100.0 * abs(y["St"] - t["St"]) / abs(t["St"])
            if t.get("St") and y.get("St") else None)
    st_s = f", St %{d_st:.2f}" if d_st is not None else ""
    if salinim_genlik_pct is None:
        return (f"EŞİK YOK — dt {t['dt_s']:.5f}→{y['dt_s']:.5f}: Cd farkı "
                f"%{d_cd:.2f}{st_s}. Ayırt eşiği hesaplanamadı (yetersiz "
                f"periyot); fark ÖLÇÜTE KARŞI sınanamadı, hüküm ASKIDA.")
    if d_cd <= salinim_genlik_pct:
        return (f"ZAMAN ADIMI CEVABI SÜRÜKLEMİYOR — dt yarıya inince Cd farkı "
                f"%{d_cd:.2f}{st_s}, ayırt eşiğinin "
                f"(%{salinim_genlik_pct:.2f}, 2 standart hata) İÇİNDE. "
                f"Çapa ailesini yeniden "
                f"koşmak için sebep YOK; Co≈5 bu vakada sonucu belirlemiyor. "
                f"Bu, ~100 saatlik tekrarı ~3 saatlik ölçümle eleyen karardır.")
    return (f"ZAMAN ADIMI CEVABI SÜRÜKLÜYOR — dt yarıya inince Cd farkı "
            f"%{d_cd:.2f}{st_s}, ayırt eşiğini "
            f"(%{salinim_genlik_pct:.2f}, 2 standart hata) AŞIYOR. "
            f"Geçici çapaların MUTLAK "
            f"değerleri zaman çözünürlüğüne duyarlıdır; aile Co≤2 ile yeniden "
            f"koşulmalı ve geçiş modelinin %77'lik aşırı-tahmini KAPANIŞA "
            f"yazılmadan önce bu ayrılmalıdır.")


def main(argv: list[str]) -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    import silindir_urans_3b as s3

    from analysis.openfoam_runner import courant_olc

    bolen = int(argv[argv.index("--bolen") + 1]) if "--bolen" in argv else 2
    case = KOK / f"_silindir_dt{bolen}"
    t0 = time.time()
    tb = taban()
    if tb.get("Cd") is None:
        print("TABAN YOK: silindir_urans_3b.json üretilmemiş")
        return 1
    print(f"taban: Cd={tb['Cd']} St={tb['St']} dt={tb['dt_s']:.5f}", flush=True)

    kurulum = None
    if "--oku" in argv and (case / "log.foamRun").exists():
        print("mevcut koşu okunuyor (--oku)", flush=True)
    else:
        kurulum = kur(case, bolen)
        print(f"sonda: dt={kurulum['dt_s']:.5f} ({kurulum['adim']} adım, "
              f"böleni {bolen})", flush=True)
        ok, mesaj = s3.kos(case)
        if not ok:
            print("KOŞU DÜŞTÜ:", mesaj[-400:])
            return 1

    t, cd, cl = s3._coeffs(case)
    if not t:
        print("forceCoeffs okunamadı")
        return 1
    o = s3.olc_ham(t, cd, cl)
    y = {"Cd": round(o["Cd"], 4), "St": round(o["St"], 5) if o["St"] else None,
         "Cl_genlik": round(o["Cl_genlik"], 5),
         "dt_s": (kurulum or {}).get("dt_s") or tb["dt_s"] / bolen}
    # BAND TABANIN KENDI SALINIMINDAN. Sonda kendi bandini kullansaydi, farki
    # kendi gurultusune karsi sinamis olurdu --- kiyas tabana yapiliyor.
    tbd = json.loads(TABAN_KANIT.read_text(encoding="utf-8"))
    sal = ((tbd.get("olculen") or {}).get("salinim")
           or (tbd.get("olculen") or {}).get("olcum") or {})
    genlik = sal.get("genlik_pct")
    # AYIRT ESIGI SERININ KENDISINDEN. Taban kaniti salinim bandi tasimiyor;
    # uydurma yuzde yerine istatistiksel cozunurluk kullaniliyor.
    periyot_s = s3.D / (s3.ST_DENEY * s3.U)
    coz = cozunurluk_tabani(t, cd, periyot_s,
                            s3.PERIYOT_GECIS * periyot_s)
    if genlik is None and coz.get("olculdu"):
        genlik = coz["ayirt_esigi_pct"]
    kayit = {
        "vaka": f"Silindir 3B — ZAMAN ADIMI sondası (dt/{bolen})",
        "_neden": ("Butun gecici capalar dt=periyot/150'de kostu ve `maxCo 2` "
                   "ATILDI (yazim hatasi). Kararli Courant maksimumu 4,8-5,2. "
                   "Gecis modelinin %77 asiri-tahmini KAPANISA yazilmadan once "
                   "zaman adimi elenmelidir."),
        "taban": tb, "sonda": y, "kurulum": kurulum,
        "taban_salinim_genlik_pct": genlik,
        "cozunurluk": coz,
        "courant": {"taban": None, "sonda": courant_olc(case)},
        "verdikt": hukum(tb, y, genlik),
        "sure_dk": round((time.time() - t0) / 60, 1),
        "_kisit": ("Tek ag (403.200 hucre, duvar fonksiyonu) ve tek bolen. "
                   "Zaman-adimi duyarliligi AGA BAGLIDIR; bu sonuc DES agina "
                   "(2,43 M hucre, duvar-cozunur) dogrudan tasinmaz, yalniz "
                   "oraya tirmanip tirmanmamaya karar verdirir."),
        "_uretim": "Üretim: python experiments/silindir_dt_sondasi.py",
    }
    import ortam
    ortam.damgala(kayit)
    CIKTI.write_text(json.dumps(kayit, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{kayit['verdikt']}")
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
