"""Silindir 3B, GEÇİŞ modeli (kOmegaSSTLM) — hipotezin ucuz sınavı.

ÖLÇÜLEN HİPOTEZ: subkritik Re'de künt cisimde bağlı sınır tabaka LAMİNERDİR;
tam-türbülanslı kapanış onu türbülans sayar, ayrılmayı geciktirir, izi daraltır
ve Cd'yi düşük verir. Aynı ağ ve aynı kurulumla ölçüldü:

    3B URANS (kOmegaSST)     Cd −26,88 %   St +29,74 %
    3B DES   (kOmegaSSTDES)  Cd −39,16 %   St +38,16 %

Sapmanın ÇÖZÜNÜRLÜK ya da DUVAR İŞLEMİ olmadığı da ölçüldü: aynı ağ önce
duvar-fonksiyonuyla (y⁺=0,009) sonra düşük-Re ile (y⁺=0,78) koşuldu ve cevap
%1'den az değişti. Geriye KAPANIŞ kalıyor.

    O ölçüm kOmegaSST İÇİNDİR ve bu koşuya taşınamaz. Tam-türbülanslı bir
    kapanış için duvar işlemi cevabı %1 oynatır; GEÇİŞ modeli için ise
    modelin çalışıp çalışmamasını belirler --- `nutkWallFunction` log-yasası
    dayattığı sürece laminer bölge kurulamaz. Aynı ayarın iki kapanışta iki
    farklı ağırlığı vardır ve birinin ölçümü öbürüne delil değildir.

BU KOŞU O AÇIKLAMANIN SINANMASIDIR. Açıklama doğruysa geçiş modeli
(Langtry-Menter) bağlı tabakayı laminer başlatır ve İKİ sapma birden
düzelmelidir --- Cd yukarı, St aşağı. Yalnız biri düzelirse açıklama eksiktir
ve geri çekilmelidir. Bir hipotezi doğrulayacak deney, onu yanlışlayabilecek
deneydir.

NEDEN BU, LES'TEN ÖNCE: fiziksel doğru kurulum duvar-çözümlü LES'tir ve
84,7 M hücre / 62,9 GB ile bu makinede sığmaz. Geçiş modeli AYNI ağda koşar
(403.200 hücre) ve hipotezi doğrudan sınar --- iş istasyonu beklemeden.

DEĞİŞEN ŞEY KAPANIŞTIR --- VE DUVAR İŞLEMİ ONA DAHİLDİR. İlk iki sürüm
yalnız model ADINI çevirdi ve "değişen tek şey kapanış" dedi. Yanlıştı:
3B kurulum `nutkWallFunction` miras alıyordu, o da log-yasasını dayatıyor
ve laminer bölgede nut'ın sıfıra inmesini imkânsız kılıyor. İki koşu
(Tu %1 ve %0,1) gammaInt minimumunu 0,9869 ve 0,9867 verdi --- on kat girdi
farkı, sonuçta fark YOK. Sebep Tu değil, duvar işlemiydi. Mesh, zaman adımı,
span ve span çözücü ayarları hâlâ 3B URANS koşusundan AYNEN gelir.

KIYASIN GEÇERLİLİK KOŞULU: LM'yi duvar-çözünür ağda koşup onu
DUVAR-FONKSİYONLU kOmegaSST ile kıyaslamak iki şeyi birden değiştirirdi.
Bu yüzden kontrol koşusu da vardır --- `--model kOmegaSST` aynı duvar
işlemiyle koşar ve fark yalnız kapanışa kalır.

    python experiments/silindir_gecis_3b.py [--oku]
    python experiments/silindir_gecis_3b.py --model kOmegaSST   # kontrol
Çıktı: silindir_gecis_3b_dr.json (ve kontrol için _dr_kOmegaSST)
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
# TURBULANS SIDDETI ARTIK BURADA AYARLANMIYOR — VE BU BIR DUZELTMEDIR.
#
# Once "Tu gecisi hemen tetikliyor" diye bir `--ti` anahtari eklendi ve %0,1
# ile kosuldu. Sonuc: gammaInt min 0,9867 --- %1'deki 0,9869 ile AYNI. On kat
# girdi farki sonuca yansimadi, aciklama CURUDU.
#
# Dahasi anahtarin kendisi kusurluydu: yalniz ReThetat korelasyonunu
# besliyordu, `k`/`omega` alanlari ise `silindir_urans.TI`den geliyordu. Yani
# vakada IKI FARKLI turbulans siddeti vardi (ReThetat %0,1'e gore, k %1'e
# gore) --- hangi sayinin sonucu surukledigi soylenemezdi. Anahtar kaldirildi:
# Tu TEK KAYNAKTAN, `silindir_urans.TI`den gelir.
#
# Gercek sebep `nut` duvar islemi cikti (`gecis_kurulum_denetimi`).


def _rethetat(Tu_pct: float) -> float:
    """Serbest-akış ReThetat — Menter (2006) korelasyonu.

    Tu ≤ %1,3 için Re_θt = 1173,51 − 589,428·Tu + 0,2196/Tu²
    Bu sayı UYDURULMAZ: türbülans şiddetinden türer ve şiddet zaten koşunun
    girdisidir. ŞİDDET TEK KAYNAKTAN GELİR (`silindir_urans.TI`); bir ara
    sürümde yalnız bu korelasyonu besleyen ayrı bir anahtar vardı ve vakada
    iki farklı Tu oluştu (ReThetat %0,1'e, k %1'e göre) --- hangi sayının
    sonucu sürüklediği söylenemezdi. Anahtar kaldırıldı.
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
    # OLCUM KANONIK KATMANDAN. Ilk surum ayni hesabi BURADA da yaziyordu ve
    # bu, deponun avladigi kusurun ta kendisiydi: ayni nicelik iki yerde
    # olculurse esik degistiginde biri sessizce eskir. Burada kalan tek sey
    # KAYIT BICIMI --- kanit dosyasinin alan adlari.
    from analysis.openfoam_runner import GECIS_ARALIKLILIK_ESIGI, gecis_devrede_mi
    a = gecis_devrede_mi(case)
    if not a.get("okunabildi"):
        return {"okunabildi": False, "_neden": a.get("_neden")}
    return {**{k: v for k, v in a.items() if k != "devrede"},
            "devreye_girdi": a["devrede"],
            "_olcut": (f"gammaInt < {GECIS_ARALIKLILIK_ESIGI} olan hücre VARSA "
                       "model devrededir; yoksa tam-türbülanslı kOmegaSST'ye "
                       "dejenere olmuştur ve koşu KAPANIŞ hakkında delil "
                       "DEĞİLDİR.")}


def kur(case: Path, model: str = MODEL) -> float:
    """3B URANS kurulumunu al, KAPANIŞI --- duvar işlemi DAHİL --- değiştir.

    İLK SÜRÜM YALNIZ MODEL ADINI ÇEVİRİYORDU ve ``değişen tek şey KAPANIŞ''
    diyordu. Yanlıştı: `nut`un duvar işlemi de kapanışın parçasıdır. 3B
    kurulum `nutkWallFunction` miras alıyor, o da log-yasasını dayatıyor ve
    laminer bölgede nut'ın sıfıra inmesini imkânsız kılıyor. İki koşu
    (Tu %1 ve %0,1) bu yüzden gammaInt minimumunu 0,9869 ve 0,9867 verdi ---
    on kat girdi farkı, sonuçta fark yok. `silindir_urans` bunun anahtarını
    (`duvar_cozunur`) ZATEN taşıyordu; 3B çağrısı onu geçirmiyordu.
    """
    import silindir_urans as s2
    import silindir_urans_3b as s3

    # ZAMAN ADIMI VE SURE URANS 3B ILE AYNI FORMULDEN — sabit olarak
    # kopyalamak iki kosuyu sessizce ayristirirdi.
    periyot = s3.D / (s3.ST_DENEY * s3.U)
    s3.kur(case, dt=periyot / 150.0,
           son_s=(s3.PERIYOT_GECIS + s3.PERIYOT_ISTAT) * periyot)
    # DUVAR-COZUNUR ALANLARI YENIDEN YAZ (k, omega, nut). 3B'nin `yanlar`
    # ikamesini de tekrarlamak sart, yoksa foamRun yama bulamayip duser.
    s2._alanlar(case, duvar_cozunur=True)
    for f in (case / "0").iterdir():
        t = f.read_text(encoding="utf-8")
        for eski in ("  yanlar   { type empty; }\n", "  yanlar { type empty; }\n"):
            t = t.replace(eski, "  on   { type cyclic; }\n  arka { type cyclic; }\n")
        f.write_text(t, encoding="utf-8")
    (case / "constant" / "momentumTransport").write_text(
        s2._foam_header("dictionary", "momentumTransport", "constant") +
        f"simulationType RAS;\nRAS\n{{\n    model           {model};\n"
        "    turbulence      on;\n    printCoeffs     on;\n}\n")
    if model not in ("kOmegaSSTLM",):
        return None                       # kontrol kosusu: gecis alani yok
    return _gecis_alanlari(case, s2.TI)


def _verdikt(gecerli: bool, aralik: dict, olcum: dict, etiket: str) -> str:
    """Hükmü aralıklılık denetimine BAĞLA — sapmadan hüküm çıkarmadan önce."""
    s = olcum["sapma_pct"]
    if not gecerli:
        return ("SINAV SONUÇSUZ — hipotez ÇÜRÜMEDİ. Geçiş modeli devreye "
                f"girmedi (gammaInt min {aralik.get('min')}, laminer hücre "
                f"%{aralik.get('laminer_hucre_orani_pct')}), yani kapanış "
                "tam-türbülanslı kOmegaSST'ye dejenere oldu ve ölçülen "
                f"sapma (Cd %{s['Cd']}, St %{s['St']}) KAPANIŞ hakkında "
                "delil değildir. SEBEP BURADA İDDİA EDİLMEZ: ilk açıklama "
                "(serbest-akış şiddeti) SINANDI ve ÇÜRÜDÜ — Tu %1 ve %0,1 "
                "koşuları gammaInt minimumunu 0,9869 ve 0,9867 verdi, on kat "
                "girdi farkı sonuca yansımadı. Ölçülen sebep `nut` duvar "
                "işlemidir; `gecis_kurulum_denetimi` onu koşudan ÖNCE söyler.")
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

    model = MODEL
    if "--model" in argv:
        model = argv[argv.index("--model") + 1]
    # AD, KOSUYU AYIRT EDEN HER SEYI TASIR. Sabit ad kullanildiginda farkli
    # ayarli iki calisma birbirini EZER — bu depoda olculdu (girdi_uq_kos).
    etiket = "_dr" + ("" if model == MODEL else f"_{model}")
    case = KOK / f"_silindir_gecis_3b{etiket}"
    t0 = time.time()
    ti_ad = etiket
    if "--oku" in argv and (case / "log.foamRun").exists():
        print("mevcut koşu okunuyor (--oku)", flush=True)
        ret0 = None
    else:
        print(f"Kurulum: 3B URANS ağı + KAPANIŞ = {model} (duvar-çözünür)",
              flush=True)
        ret0 = kur(case, model)
        if ret0 is not None:
            import silindir_urans as _s2
            print(f"  Tu = %{100*_s2.TI:g} (TEK KAYNAK: silindir_urans.TI)",
                  flush=True)
            print(f"  ReThetat = {ret0:.1f}", flush=True)
        # KURULUM DENETIMI KOSUDAN ONCE. 85 dakikayi, dosyadan okunabilen bir
        # uyumsuzluga harcamanin anlami yok --- ilk iki kosu tam bunu yapti.
        from analysis.openfoam_runner import gecis_kurulum_denetimi
        kd = gecis_kurulum_denetimi(case)
        print(f"  kurulum denetimi: uygun={kd['uygun']} {kd.get('nut_duvar')}",
              flush=True)
        if model == MODEL and kd["uygun"] is False:
            print("KURULUM REDDEDİLDİ:", kd["_neden"])
            return 2
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
