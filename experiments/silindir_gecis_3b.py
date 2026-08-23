"""Silindir 3B, GEÇİŞ modeli (kOmegaSSTLM) — hipotezin ucuz sınavı.

ÖLÇÜLEN HİPOTEZ: subkritik Re'de künt cisimde bağlı sınır tabaka LAMİNERDİR;
tam-türbülanslı kapanış onu türbülans sayar, ayrılmayı geciktirir, izi daraltır
ve Cd'yi düşük verir. Aynı ağ ve aynı kurulumla ölçüldü:

    3B URANS (kOmegaSST)     Cd −26,88 %   St +29,74 %
    3B DES   (kOmegaSSTDES)  Cd −39,16 %   St +38,16 %

Sapmanın ÇÖZÜNÜRLÜK ya da DUVAR İŞLEMİ olmadığı da ölçüldü: aynı ağ önce
duvar-fonksiyonuyla (y⁺=0,009) sonra düşük-Re ile (y⁺=0,78) koşuldu ve cevap
%1'den az değişti. Geriye KAPANIŞ kalıyor.

BU KOŞU O AÇIKLAMANIN SINANMASIDIR. Açıklama doğruysa geçiş modeli
(Langtry-Menter) bağlı tabakayı laminer başlatır ve İKİ sapma birden
düzelmelidir --- Cd yukarı, St aşağı. Yalnız biri düzelirse açıklama eksiktir
ve geri çekilmelidir. Bir hipotezi doğrulayacak deney, onu yanlışlayabilecek
deneydir.

NEDEN BU, LES'TEN ÖNCE: fiziksel doğru kurulum duvar-çözümlü LES'tir ve
84,7 M hücre / 62,9 GB ile bu makinede sığmaz. Geçiş modeli AYNI ağda koşar
(403.200 hücre) ve hipotezi doğrudan sınar --- iş istasyonu beklemeden.

DEĞİŞEN TEK ŞEY KAPANIŞTIR: mesh, alanlar, zaman adımı, span, çözücü ayarları
3B URANS koşusundan AYNEN gelir. Başka bir fark olsaydı sapma değişiminin
nereden geldiği söylenemezdi.

    python experiments/silindir_gecis_3b.py [--oku]
Çıktı: silindir_gecis_3b.json
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

CIKTI = KOK / "silindir_gecis_3b.json"
MODEL = "kOmegaSSTLM"
# SERBEST-AKIS TURBULANS SIDDETI — GECISI TETIKLEYEN SEY.
# Olculdu 2026-08-23: TI=%1 ile gammaInt her yerde ~1 kaldi
# (min 0,9869, ortalama 1,0000), yani gecis modeli HIC DEVREYE
# GIRMEDI ve tam-turbulansli kOmegaSST'ye dejenere oldu. Sinav
# SONUCSUZDU. Subkritik silindir deneyleri ~%0,1 Tu'da yapilir;
# yuksek Tu gecisi hemen tetikler.
TI_VARSAYILAN = 0.001


def _rethetat(Tu_pct: float) -> float:
    """Serbest-akış ReThetat — Menter (2006) korelasyonu.

    Tu ≤ %1,3 için Re_θt = 1173,51 − 589,428·Tu + 0,2196/Tu²
    Bu sayı UYDURULMAZ: türbülans şiddetinden türer ve şiddet zaten koşunun
    girdisidir (TI = 0,01 → Tu = %1).
    """
    Tu = max(Tu_pct, 0.027)
    if Tu <= 1.3:
        return 1173.51 - 589.428 * Tu + 0.2196 / Tu ** 2
    return 331.5 * (Tu - 0.5658) ** -0.671


def _gecis_alanlari(case: Path, ti: float) -> float:
    """gammaInt ve ReThetat alanlarını yaz — silindir yama adlarıyla.

    3B kurulumda `yanlar` yok; `on`/`arka` cyclic yamaları var (URANS 3B
    betiği bunu alan dosyalarında değiştiriyor). Aynı dönüşümü burada da
    uyguluyoruz ki alanlar ağla tutarlı olsun.
    """
    from silindir_urans import _foam_header

    ret0 = _rethetat(100.0 * ti)
    ortak = ("  silindir { type zeroGradient; }\n"
             "  giris    { type fixedValue; value uniform %s; }\n"
             "  cikis    { type inletOutlet; inletValue uniform %s; "
             "value uniform %s; }\n"
             "  ustalt   { type slip; }\n"
             "  on   { type cyclic; }\n  arka { type cyclic; }\n")
    (case / "0" / "gammaInt").write_text(
        _foam_header("volScalarField", "gammaInt", "0") +
        "dimensions [0 0 0 0 0 0 0];\ninternalField uniform 1;\n"
        "boundaryField\n{\n" + ortak % ("1", "1", "1") + "}\n")
    r = f"{ret0:.2f}"
    (case / "0" / "ReThetat").write_text(
        _foam_header("volScalarField", "ReThetat", "0") +
        f"dimensions [0 0 0 0 0 0 0];\ninternalField uniform {r};\n"
        "boundaryField\n{\n" + ortak % (r, r, r) + "}\n")
    return ret0


def aralik_denetimi(case: Path) -> dict:
    """GEÇİŞ MODELİ GERÇEKTEN DEVREYE GİRDİ Mİ? — sonucu okumadan ÖNCE.

    `kOmegaSSTLM` bir kapanış SEÇİMİ değil, bir kapanış İMKÂNIDIR: aralıklılık
    (gammaInt) her yerde 1 kalırsa üretim terimleri sönmez ve model tam-türbülanslı
    kOmegaSST'ye DEJENERE olur. O halde Cd/St sapması kapanış hakkında hiçbir şey
    söylemez --- aynı kapanışı ikinci kez ölçmüş olursunuz.

    ÖLÇÜLDÜ 2026-08-23: Tu=%1 ile gammaInt min 0,9869 / ortalama 1,0000 / laminer
    hücre oranı %0,0. Sınav SONUÇSUZDU ve "hipotez çürüdü" diye yazılsaydı YANLIŞ
    olurdu. Bu denetim o hatayı elle değil KODLA engeller.
    """
    zamanlar = sorted((d for d in case.iterdir()
                       if d.is_dir() and d.name.replace(".", "").isdigit()),
                      key=lambda d: float(d.name))
    if len(zamanlar) < 2 or not (zamanlar[-1] / "gammaInt").exists():
        return {"okunabildi": False, "_neden": "gammaInt alanı yok"}
    ham = (zamanlar[-1] / "gammaInt").read_text(errors="replace")
    i = ham.find("internalField")
    j = ham.find("(", i)
    k = ham.find(")", j)
    if j < 0 or k < 0:
        return {"okunabildi": False, "_neden": "internalField ayrıştırılamadı"}
    g = [float(s) for s in ham[j + 1:k].split()]
    laminer = sum(1 for x in g if x < 0.5) / len(g)
    return {"okunabildi": True, "zaman_s": float(zamanlar[-1].name),
            "n": len(g), "min": round(min(g), 4),
            "ortalama": round(sum(g) / len(g), 4), "max": round(max(g), 4),
            "laminer_hucre_orani_pct": round(100.0 * laminer, 2),
            "devreye_girdi": min(g) < 0.5,
            "_olcut": ("gammaInt < 0,5 olan hücre VARSA model devrededir; "
                       "yoksa tam-türbülanslı kOmegaSST'ye dejenere olmuştur "
                       "ve koşu KAPANIŞ hakkında delil DEĞİLDİR.")}


def kur(case: Path, ti: float = TI_VARSAYILAN) -> float:
    """3B URANS kurulumunu AYNEN al, yalnız KAPANIŞI değiştir."""
    import silindir_urans as s2
    import silindir_urans_3b as s3

    # ZAMAN ADIMI VE SURE URANS 3B ILE AYNI FORMULDEN — sabit olarak
    # kopyalamak iki kosuyu sessizce ayristirirdi.
    periyot = s3.D / (s3.ST_DENEY * s3.U)
    s3.kur(case, dt=periyot / 150.0,
           son_s=(s3.PERIYOT_GECIS + s3.PERIYOT_ISTAT) * periyot)
    # KAPANIS DEGISTIRILIYOR — tek fark bu.
    (case / "constant" / "momentumTransport").write_text(
        s2._foam_header("dictionary", "momentumTransport", "constant") +
        f"simulationType RAS;\nRAS\n{{\n    model           {MODEL};\n"
        "    turbulence      on;\n    printCoeffs     on;\n}\n")
    return _gecis_alanlari(case, ti)


def _verdikt(gecerli: bool, aralik: dict, olcum: dict, etiket: str) -> str:
    """Hükmü aralıklılık denetimine BAĞLA — sapmadan hüküm çıkarmadan önce."""
    s = olcum["sapma_pct"]
    if not gecerli:
        return ("SINAV SONUÇSUZ — hipotez ÇÜRÜMEDİ. Geçiş modeli devreye "
                f"girmedi (gammaInt min {aralik.get('min')}, laminer hücre "
                f"%{aralik.get('laminer_hucre_orani_pct')}), yani kapanış "
                "tam-türbülanslı kOmegaSST'ye dejenere oldu ve ölçülen "
                f"sapma (Cd %{s['Cd']}, St %{s['St']}) KAPANIŞ hakkında "
                "delil değildir. Sebep: serbest-akış türbülans şiddeti "
                "geçişi hemen tetikliyor; subkritik silindir deneyleri "
                "~%0,1 Tu'da yapılır.")
    iyi_cd = abs(s["Cd"]) < 26.88
    iyi_st = abs(s["St"]) < 29.74
    if iyi_cd and iyi_st:
        hkm = ("HİPOTEZ DESTEKLENDİ — geçiş modeli devrede ve İKİ sapma da "
               "tam-türbülanslı kapanışa göre küçüldü.")
    elif iyi_cd or iyi_st:
        hkm = ("HİPOTEZ EKSİK — geçiş modeli devrede ama sapmalardan yalnız "
               "biri düzeldi; laminer-bağlı-tabaka açıklaması tek başına "
               "yetmiyor ve o haliyle GERİ ÇEKİLMELİDİR.")
    else:
        hkm = ("HİPOTEZ ÇÜRÜDÜ — geçiş modeli devrede (laminer hücre "
               f"%{aralik.get('laminer_hucre_orani_pct')}) ve buna rağmen "
               "hiçbir sapma düzelmedi; sapmanın kaynağı kapanışın "
               "türbülanslılığı DEĞİLDİR.")
    return f"{hkm} Cd %{s['Cd']}, St %{s['St']}{' [' + etiket.strip('_') + ']' if etiket else ''}"


def main(argv: list[str]) -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    import silindir_urans_3b as s3

    ti_ad = ""
    if "--ti" in argv:
        ti_ad = f"_ti{float(argv[argv.index(chr(45)*2+chr(116)+chr(105)) + 1]):g}"
    case = KOK / f"_silindir_gecis_3b{ti_ad}"
    t0 = time.time()
    if "--oku" in argv and (case / "log.foamRun").exists():
        print("mevcut koşu okunuyor (--oku)", flush=True)
        ret0 = None
    else:
        print(f"Kurulum: 3B URANS ağı + KAPANIŞ = {MODEL}", flush=True)
        ti = TI_VARSAYILAN
        if "--ti" in argv:
            ti = float(argv[argv.index("--ti") + 1])
        ret0 = kur(case, ti)
        print(f"  Tu = %{100*ti:g}", flush=True)
        print(f"  ReThetat(Tu=%{100*ti:g}) = {ret0:.1f}", flush=True)
        ok, mesaj = s3.kos(case)
        if not ok:
            print("KOŞU DÜŞTÜ:", mesaj[-400:])
            return 1

    # OLCUM TEK KAYNAKTAN: URANS 3B betiginin `olc_ham`i. Ikinci bir uygulama
    # yazmak iki kosuyu kiyaslanamaz yapardi — sapma farkinin OLCUTTEN mi
    # KAPANISTAN mi geldigi soylenemezdi.
    t, cd, cl = s3._coeffs(case)
    if not t:
        print("forceCoeffs okunamadi")
        return 1
    # SINAVIN GECERLILIGI, SONUCUNDAN ONCE SORULUR.
    aralik = aralik_denetimi(case)
    gecerli = bool(aralik.get("devreye_girdi"))
    print("aralıklılık:", json.dumps(aralik, ensure_ascii=False)[:220], flush=True)
    o = s3.olc_ham(t, cd, cl)
    olcum = {"St": round(o["St"], 5) if o["St"] else None,
             "Cd_ortalama": round(o["Cd"], 4),
             "Cl_genlik": round(o["Cl_genlik"], 5),
             "sapma_pct": {"St": o["St_sapma_pct"], "Cd": o["Cd_sapma_pct"]},
             "salinim": o["olcum"]}
    ref = {"St": s3.ST_DENEY, "St_bandi": list(s3.ST_BANDI), "Cd": s3.CD_DENEY}
    print(json.dumps(olcum, ensure_ascii=False, indent=1)[:600], flush=True)
    kayit = {
        "vaka": f"Silindir 3B, geçiş modeli ({MODEL}) — kapanış hipotezinin sınavı",
        "_neden": ("Subkritik Re'de bagli sinir tabaka LAMINERDIR; tam-turbulansli "
                   "kapanis onu turbulans sayar ve Cd'yi dusuk verir. Bu kosu o "
                   "aciklamayi SINAR: dogruysa IKI sapma birden duzelmeli."),
        "kurulum": {"model": MODEL, "ReThetat_serbest": ret0,
                    "ag": "3B URANS ile AYNI (403.200 hücre)",
                    "_degisen_tek_sey": "KAPANIŞ"},
        "olculen": olcum, "referans": ref,
        "kiyas": {"3B URANS (kOmegaSST)": {"Cd_pct": -26.88, "St_pct": 29.74},
                  "3B DES (kOmegaSSTDES)": {"Cd_pct": -39.16, "St_pct": 38.16}},
        "aralik_denetimi": aralik,
        "sinav_gecerli": gecerli,
        "verdikt": _verdikt(gecerli, aralik, olcum, ti_ad),
        "sure_dk": round((time.time() - t0) / 60, 1),
        "_uretim": "Üretim: python experiments/silindir_gecis_3b.py",
    }
    import ortam
    ortam.damgala(kayit)
    # AD Tu'YU TASIR. Sabit ad kullanilsaydi %0,1 kosusu, sonucsuz kalan
    # %1 kosusunun kaydini EZERDI — ve sonucsuzluk kaydi tam da bu
    # calismanin en ogretici parcasi. (Ayni hata girdi_uq_kos'ta olculdu.)
    yol = KOK / f"silindir_gecis_3b{ti_ad}.json" if ti_ad else CIKTI
    yol.write_text(json.dumps(kayit, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"-> {yol.name}")
    print(kayit["verdikt"][:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
