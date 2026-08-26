"""2-yönlü FSI çapası: engel DONANIM mı, YETENEK mi, GEOMETRİ AİLESİ mi?

DIŞ HAKEM P3 (2026-08-26): ``2-yönlü FSI hâlâ doğrulanmış sayılmaz --- ilmek
koşuyor, fizik henüz tahrik etmiyor. Uygun vaka için tahmin ~94,1 M hücre,
~73 GB.''

O 94,1 M sayısı gerçektir ama BİR TEK GEOMETRİ AİLESİNE aittir: deponun
kendi araç gövdesi, malzeme ve hız taranarak (`fsi_tahrik_fizibilite.json`,
18 senaryo). Kaydın kendi kısıtı zaten şunu söylüyordu --- ``bu bir DONANIM
sorunundan çok bir GEOMETRİ-AİLESİ sorunudur'' --- ama başka bir aile hiç
değerlendirilmedi.

BU BETİK KANONİK FSI ÇAPALARINI DEĞERLENDİRİR. Turek & Hron (2006) FSI
benchmark'ı tam bu iş için tasarlandı: silindir arkasında esnek bayrak, 2B,
laminer, yayımlanmış referans değerleriyle. Üç varyantı vardır ve
BİRBİRİNDEN ÇOK FARKLI şeyler ister:

  FSI1  kararlı, Re=20, uç sehimi ~0,0227 mm / 350 mm  -> KÜÇÜK, lineer
  FSI2  zamana bağlı, Re=100, uç sehimi ~80 mm         -> BÜYÜK, NLGEOM
  FSI3  zamana bağlı, Re=200, uç sehimi ~35 mm         -> BÜYÜK, NLGEOM

ENGEL TEK DEĞİL VE BÜTÇE DEĞİL. Betik önce YETENEĞİ denetler: yapısal
yazıcı `*STEP`i `NLGEOM` olmadan basıyor mu (yani büyük yer-değiştirme
çözülebiliyor mu), zaman-çözünür kuplaj var mı. Bütçe ancak yetenek varsa
anlamlıdır --- sığan ama koşulamayan bir vaka için hücre sayısı yazmak,
engeli yanlış yere koymaktır.

    python experiments/fsi_capa_ulasilabilirlik.py
Çıktı: fsi_capa_ulasilabilirlik.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "fsi_capa_ulasilabilirlik.json"

# Turek & Hron (2006) benchmark tanimi. Referans degerler YAYIMLANMISTIR;
# burada YALNIZ ulasilabilirlik degerlendirilir, sonuc uretilmez.
CAPALAR = {
    "FSI1": {
        "rejim": "kararlı", "Re": 20, "uc_sehimi_mm": 0.0227,
        "bayrak_L_mm": 350.0, "kanal_L_mm": 2500.0, "kanal_H_mm": 410.0,
        "nlgeom_gerekir": False,
        "_neden": ("Uc sehimi bayrak boyunun %0,0065'i --- kucuk yer-degistirme "
                   "rejimi, lineer statik gecerli."),
        "ne_kapatir": ("Aktarilan yuk + yapisal yanit YAYIMLANMIS bir referansa "
                       "karsi dogrulanir. Bugun hicbir FSI vakasinda bu YOK."),
        "ne_kapatmaz": ("GUCLU iki-yonlu geri besleme: sehim akisi kayda deger "
                        "olcude degistirmez, yani 'fizik tahrik ediyor' "
                        "iddiasini SINAMAZ."),
    },
    "FSI2": {
        "rejim": "zamana bağlı", "Re": 100, "uc_sehimi_mm": 80.0,
        "bayrak_L_mm": 350.0, "kanal_L_mm": 2500.0, "kanal_H_mm": 410.0,
        "nlgeom_gerekir": True,
        "_neden": "Uc sehimi bayrak boyunun %23'u --- buyuk yer-degistirme.",
        "ne_kapatir": "Hakemin istedigi sey: fizikle SURULEN iki-yonlu kuplaj.",
        "ne_kapatmaz": "3B etkiler; benchmark 2B'dir.",
    },
    "FSI3": {
        "rejim": "zamana bağlı", "Re": 200, "uc_sehimi_mm": 35.0,
        "bayrak_L_mm": 350.0, "kanal_L_mm": 2500.0, "kanal_H_mm": 410.0,
        "nlgeom_gerekir": True,
        "_neden": "Uc sehimi bayrak boyunun %10'u --- buyuk yer-degistirme.",
        "ne_kapatir": "FSI2 ile ayni, daha yuksek Re.",
        "ne_kapatmaz": "3B etkiler; benchmark 2B'dir.",
    },
}
# 2B kanal + silindir + bayrak icin cozunurluk: bayrak KALINLIGI (20 mm)
# boyunca en az bu kadar hucre. Ince yapiyi cozmeden FSI anlamsizdir.
BAYRAK_KALINLIK_MM = 20.0
KALINLIK_BASINA_HUCRE = 8
# 2B'de OpenFOAM tek hucre kalinliginda kosar.
KATMAN = 1


def _yapisal_yetenek() -> dict:
    """CalculiX yazıcısı büyük yer-değiştirme çözebiliyor mu?

    KAYNAKTAN OKUNUR, VARSAYILMAZ. `*STEP` satirinin NLGEOM tasiyip
    tasimadigi ve desteklenen analiz tipleri yazicinin KENDISINDEN alinir;
    bir belge cumlesine ya da bu betigin hatirasina degil.
    """
    p = KOK / "analysis" / "calculix_writer.py"
    if not p.exists():
        return {"okunabildi": False, "neden": "calculix_writer.py yok"}
    src = p.read_text(encoding="utf-8", errors="replace")
    nlgeom = "NLGEOM" in src.upper()
    tipler = set()
    try:
        for n in ast.walk(ast.parse(src)):
            if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and n.value in ("STATIC", "FREQUENCY", "BUCKLE",
                                    "DYNAMIC", "MODAL DYNAMIC")):
                tipler.add(n.value)
    except SyntaxError as e:
        return {"okunabildi": False, "neden": f"ayrıştırılamadı: {e}"}
    return {"okunabildi": True, "nlgeom": nlgeom,
            "analiz_tipleri": sorted(tipler),
            "buyuk_yer_degistirme": nlgeom,
            "zaman_cozunur_yapisal": "DYNAMIC" in tipler}


def _butce(c: dict) -> dict:
    """2B kanal için hücre kestirimi --- bayrak kalınlığına göre."""
    h_mm = BAYRAK_KALINLIK_MM / KALINLIK_BASINA_HUCRE
    # Kanal, bayrak cevresinde ince; uzakta kabalasir. Kaba ust sinir olarak
    # TEKDUZE ag alinir ve bunun UST SINIR oldugu yazilir.
    nx = c["kanal_L_mm"] / h_mm
    ny = c["kanal_H_mm"] / h_mm
    n = nx * ny * KATMAN
    import bellek_kapisi
    bel = bellek_kapisi.tahmini_gb(int(n))
    bos = bellek_kapisi.bos_bellek_gb()
    return {"hucre_boyu_mm": round(h_mm, 3),
            "hucre_tekduze_ust_sinir": int(n),
            "bellek_gb": round(bel["gereken_gb"], 3),
            "bos_bellek_gb": round(bos, 2) if bos else None,
            "bellege_sigar_mi": bool(bos is not None and bel["gereken_gb"] < bos)}


def olc() -> dict:
    yetenek = _yapisal_yetenek()
    sonuc = {}
    for ad, c in CAPALAR.items():
        b = _butce(c)
        engeller = []
        if c["nlgeom_gerekir"] and not yetenek.get("nlgeom"):
            engeller.append("YETENEK: büyük yer-değiştirme (NLGEOM) yok")
        if c["rejim"] == "zamana bağlı" and not yetenek.get(
                "zaman_cozunur_yapisal"):
            engeller.append("YETENEK: zaman-çözünür yapısal analiz yok")
        if not b["bellege_sigar_mi"]:
            engeller.append(f"BÜTÇE: {b['bellek_gb']} GB > boş bellek")
        sonuc[ad] = {**c, "butce": b, "engeller": engeller,
                     "ulasilabilir": not engeller}
    return _ozetle(yetenek, sonuc)


def _ozetle(yetenek: dict, sonuc: dict) -> dict:
    ulasilabilir = [a for a, v in sonuc.items() if v["ulasilabilir"]]
    return {
        "vaka": "2-yönlü FSI çapası — engel donanım mı, yetenek mi?",
        "_neden": ("Hakem P3 'uygun vaka ~94,1 M hucre' diyor. O sayi gercek "
                   "ama BIR TEK GEOMETRI AILESINE ait (deponun kendi araci). "
                   "Kaydin kendi kisiti 'bu bir GEOMETRI-AILESI sorunudur' "
                   "diyordu ama baska aile hic degerlendirilmedi."),
        "yapisal_yetenek": yetenek,
        "capalar": sonuc,
        "ulasilabilir_capalar": ulasilabilir,
        "verdikt": _hukum(yetenek, sonuc, ulasilabilir),
        "_kisit": (
            "BUTCE TEKDUZE AG VARSAYIYOR ve bu bir UST SINIRDIR: gercek "
            "kosuda uzak alan kabalasir, hucre sayisi belirgin duser. "
            "'Sigar' hukmu bu yuzden GUVENLI yondedir ama 'sigmaz' hukmu "
            "kesin degildir. Ayrica ULASILABILIR demek KOSULDU demek "
            "DEGILDIR: hicbir Turek-Hron vakasi bu depoda kosulmadi ve "
            "referans degerler burada YALNIZ ulasilabilirlik icin "
            "kullanildi, sonuc uretmek icin degil."),
        "_uretim": "Üretim: python experiments/fsi_capa_ulasilabilirlik.py",
    }


def _hukum(yetenek: dict, sonuc: dict, ulasilabilir: list) -> str:
    s = ("YAPISAL YETENEK: büyük yer-değiştirme (NLGEOM) "
         f"{'VAR' if yetenek.get('nlgeom') else 'YOK'}, zaman-çözünür yapısal "
         f"{'VAR' if yetenek.get('zaman_cozunur_yapisal') else 'YOK'} "
         f"(desteklenen: {', '.join(yetenek.get('analiz_tipleri', []))}). ")
    for ad, v in sonuc.items():
        s += (f"{ad}: "
              + ("ULAŞILABİLİR" if v["ulasilabilir"]
                 else "engel — " + "; ".join(v["engeller"]))
              + f" ({v['butce']['hucre_tekduze_ust_sinir']:,} hücre üst sınır, "
                f"{v['butce']['bellek_gb']} GB). ")
    if not ulasilabilir:
        return s + ("HİÇBİRİ ulaşılabilir değil.")
    kucuk = [a for a in ulasilabilir if not sonuc[a]["nlgeom_gerekir"]]
    if kucuk:
        s += (f"BULGU: {', '.join(kucuk)} bu makinede ULAŞILABİLİR ve engel "
              f"DONANIM DEĞİL --- 94,1 M'lik tahmin deponun kendi araç "
              f"ailesine aitti. Ama {', '.join(kucuk)} hakemin sorduğu şeyi "
              f"KAPATMAZ: küçük sehim rejiminde akış kayda değer ölçüde "
              f"değişmez, yani 'fizik tahrik ediyor' iddiası sınanmaz. "
              f"Kapattığı şey ayrı ve bugün EKSİK: aktarılan yükün ve "
              f"yapısal yanıtın YAYIMLANMIŞ bir referansa karşı "
              f"doğrulanması. Güçlü geri besleme için gereken FSI2/FSI3'ün "
              f"engeli bütçe değil YETENEKTİR (NLGEOM).")
    return s


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
