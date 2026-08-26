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

"UCUZ ARA ADIM" İDDİASI ÖLÇÜLDÜ VE GERİ ÇEKİLDİ. Betiğin ilk sürümü şöyle
diyordu: "geçiş modeli AYNI ağda koşar (403.200 hücre) ve hipotezi doğrudan
sınar --- iş istasyonu beklemeden." DÖRT KOŞU bunun yanlış olduğunu gösterdi.
Sırayla sınanan ve düşen açıklamalar:

  1. Serbest-akış şiddeti (Tu). ÇÜRÜDÜ --- Tu %1 ve %0,1 koşuları gammaInt
     minimumunu 0,9869 ve 0,9867 verdi. On kat girdi farkı, sonuçta fark yok.
  2. `nut` duvar işlemi (`nutkWallFunction` log-yasası dayatıyor). TEK BAŞINA
     YETMEDİ --- `nutLowReWallFunction`'a çevrildi, model YİNE girmedi
     (0,9872) ve dahası Cd %−26,88'den %−62,63'e düştü.
  3. AĞ. ÖLÇÜLDÜ ve sebep bu çıktı: y⁺ = 24,9. Bu O-grid duvar FONKSİYONU
     için tasarlanmış ve bunu kendisi beyan ediyor (`YPLUS_BANDI` = 30--300).
     Düşük-Re alanlarını böyle bir ağa koymak ilk hücreyi TAMPON TABAKAYA
     bırakır: ne duvar fonksiyonu geçerlidir (y⁺<30) ne düşük-Re (y⁺>1).

Yani bu, bir KAPANIŞ değil AĞ meselesidir ve bu ağda kapatılamaz. Kapı
(`ag_onkosulu`) artık koşudan önce reddediyor. Depoda aynı eşikli kapı ZATEN
vardı (`gecis_modeli_onkosulu`); bu betik `CFDCase`/`build_case` yolundan
geçmediği için ona hiç uğramadı --- CLAUDE.md'nin "iki-hızlı" uyarısı tam bu.

Sınav duvar-çözünür bir silindir ağı ister ve o ağ da elde VAR: `silindir_des_3b`
bütçesi aynı O-grid üreteciyle y⁺=0,78'i 2,43 M hücrede kuruyor. Ucuz değil
(URANS ağının ~6 katı) ama 84,7 M hücrelik LES'in yanında ulaşılabilir.

KIYASIN GEÇERLİLİK KOŞULU: LM'yi bir ağda koşup onu BAŞKA duvar işlemli bir
koşuyla kıyaslamak iki şeyi birden değiştirir. Bu yüzden kontrol koşusu
vardır --- `--model kOmegaSST` aynı ağ ve aynı duvar işlemiyle koşar, fark
yalnız kapanışa kalır.

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


def kur_des_agi(case: Path, model: str = MODEL,
                periyot_sayisi: int | None = None) -> tuple[float, dict]:
    """DUVAR-ÇÖZÜNÜR ağda kur — geçiş modelinin gerçekten koşabileceği tek ağ.

    URANS O-grid'i duvar fonksiyonu için tasarlanmış (y⁺ 24,9 ölçüldü) ve
    geçiş modelini taşıyamıyor. DES çapası aynı O-grid üreteciyle y⁺=0,78'i
    2,43 M hücrede kuruyor; ağ ELDE VAR, yalnız 6 kat pahalı.

    `periyot_sayisi` verilirse koşu KISALTILIR. Bu bir SONUÇ koşusu değil
    ARALIKLILIK SONDASIDIR: üç açıklama arka arkaya düştükten sonra 8,5
    saatlik bir koşuya girmeden önce modelin devreye girip girmediğine
    bakmak, aynı hatayı dördüncü kez pahalıya yapmamaktır. Sonda geçerse
    tam koşu ayrıca sürülür; istatistik penceresi kısaltılmış bir koşudan
    St/Cd okumak zaten meşru değildir.
    """
    import silindir_des_3b as sd

    # dt DES BUTCESINDEN gelir, burada TURETILMEZ. Kendi formulumu yazsaydim
    # iki kosu farkli zaman adimiyla kosar ve fark KAPANISTAN mi ADIMDAN mi
    # geldigi soylenemezdi --- bu betigin daha once tam da bu sekilde
    # ayrisan bir surumu oldu (Tu iki kaynaktan geliyordu).
    from des_fizibilite import butce
    periyot = sd.D / (sd.ST_DENEY * sd.U)
    n_per = periyot_sayisi or (sd.PERIYOT_GECIS + sd.PERIYOT_ISTAT)
    dt = butce(sd.DZ_D, bos_gb=1e9)["dt_s"]
    kurulum = sd.kur(case, dt=dt, son_s=n_per * periyot, dz_D=sd.DZ_D)
    # KAPANIS DEGISTIRILIYOR. `sd.kur` zaten duvar-cozunur alan yaziyor
    # (`duvar_cozunur=True`), o yuzden burada nut'a DOKUNULMAZ --- ikinci kez
    # yazmak iki kurulumun sessizce ayrismasi demek olurdu.
    (case / "constant" / "momentumTransport").write_text(
        sd._foam_header("dictionary", "momentumTransport", "constant") +
        f"simulationType RAS;\nRAS\n{{\n    model           {model};\n"
        "    turbulence      on;\n    printCoeffs     on;\n}\n")
    kurulum["periyot_sayisi"] = n_per
    kurulum["sonda_mu"] = periyot_sayisi is not None
    if model != MODEL:
        return None, kurulum
    import silindir_urans as s2
    return _gecis_alanlari(case, s2.TI), kurulum


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


def ag_onkosulu(model: str, ag: str = "urans") -> str:
    """Bu AĞ geçiş modelini taşıyabilir mi? — mesh'in KENDİ beyanından.

    ÖLÇÜLDÜ, ve pahalıya: `nut` duvar işlemi düzeltildikten sonra model YİNE
    devreye girmedi (gammaInt min 0,9872) ve dahası Cd %−26,88'den %−62,63'e
    düştü. Sebep ağdı --- ölçülen y⁺ 24,9. Bu O-grid duvar FONKSİYONU için
    tasarlanmış ve bunu kendisi beyan ediyor: `silindir_urans.YPLUS_BANDI`
    = (30, 300). Düşük-Re alanlarını böyle bir ağa koymak ilk hücreyi TAMPON
    TABAKAYA bırakır --- ne duvar fonksiyonu geçerlidir (y⁺<30) ne düşük-Re
    (y⁺>1). İki koşu bu yüzden geçersizdi.

    Depoda bu kapı ZATEN vardı (`gecis_modeli_onkosulu`, y⁺ hedefi > 5 ise
    reddeder) ama bu betik `CFDCase`/`build_case` yolundan geçmediği için ona
    hiç uğramadı. CLAUDE.md'nin ``iki-hızlı'' uyarısı tam buydu: kendi case
    iskelesini yazan kök betikler, `analysis/` katmanındaki kapılardan da
    muaf kalıyor. Kapı burada AYNI EŞİKLE tekrar kuruluyor, eşik kanonik
    katmandan okunuyor.
    """
    if model != MODEL:
        return ""
    from analysis.openfoam_runner import GECIS_YPLUS_TAVANI
    if ag == "des":
        # DES modulu duvar-COZUNUR oldugunu KENDI beyan ediyor ve olculen
        # y+ 0,78 bunu dogruluyor (silindir_des_3b.json). Kapinin bu agda
        # susmasinin sebebi bir SAYIDIR, varsayim degil.
        import silindir_des_3b as sd
        if max(sd.YPLUS_BANDI_COZUNUR) <= GECIS_YPLUS_TAVANI:
            return ""
        return (f"{model} için DES ağının beyan ettiği bant "
                f"{sd.YPLUS_BANDI_COZUNUR}, tavanı "
                f"({GECIS_YPLUS_TAVANI:g}) aşıyor.")
    import silindir_urans as s2
    alt = min(s2.YPLUS_BANDI)
    if alt > GECIS_YPLUS_TAVANI:
        return (f"{model} y⁺≲{GECIS_YPLUS_TAVANI:g} ister; bu ağ duvar "
                f"FONKSİYONU için tasarlandı ve bunu kendisi beyan ediyor "
                f"(YPLUS_BANDI={s2.YPLUS_BANDI}). ÖLÇÜLDÜ: düşük-Re alanları "
                f"bu ağa konunca y⁺ 24,9 çıktı (tampon tabaka --- iki "
                f"işlemin de dışı) ve Cd %−26,88'den %−62,63'e düştü. "
                f"Bu bir KAPANIŞ değil AĞ meselesidir: duvar-çözünür silindir "
                f"ağı `silindir_des_3b` bütçesinden kurulur (y⁺=0,78, "
                f"2,43 M hücre) --- aynı O-grid üreteci n_radyal/grading ile "
                f"onu zaten üretebiliyor.")
    return ""


def _verdikt(gecerli: bool, aralik: dict, olcum: dict, etiket: str,
             model: str = MODEL, yplus: dict | None = None,
             ag: str = "urans", esik_pct: float | None = None) -> str:
    """Hükmü aralıklılık denetimine BAĞLA — sapmadan hüküm çıkarmadan önce.

    MODEL DE ARGÜMANDIR. İlk sürüm bunu almıyordu ve kontrol koşusuna
    (kOmegaSST, geçiş alanı YOK) ``geçiş modeli devreye girmedi'' diyordu ---
    hiç istenmemiş bir modelin devreye girmemesi bir bulgu değildir.
    """
    s = olcum["sapma_pct"]
    yp = (yplus or {}).get("ort")
    yp_s = f"y⁺ ort={yp:.1f}" if yp else "y⁺ ölçülemedi"
    if model != MODEL:
        return (f"KONTROL KOŞUSU ({model}, geçiş modeli YOK): Cd %{s['Cd']}, "
                f"St %{s['St']}, {yp_s}. Bu koşu bir hipotez sınamaz; LM "
                f"koşusunun duvar işlemini EŞİTLER, böylece iki koşu "
                f"arasındaki fark yalnız kapanışa kalır.")
    if not gecerli:
        return ("SINAV SONUÇSUZ — hipotez ÇÜRÜMEDİ. Geçiş modeli devreye "
                f"girmedi (gammaInt min {aralik.get('min')}, laminer hücre "
                f"%{aralik.get('laminer_hucre_orani_pct')}), yani kapanış "
                "tam-türbülanslı kOmegaSST'ye dejenere oldu ve ölçülen "
                f"sapma (Cd %{s['Cd']}, St %{s['St']}) KAPANIŞ hakkında "
                f"delil değildir. ÜÇ AÇIKLAMA SINANDI: (1) serbest-akış "
                f"şiddeti — ÇÜRÜDÜ, Tu %1 ve %0,1 gammaInt minimumunu 0,9869 "
                f"ve 0,9867 verdi; (2) `nut` duvar işlemi — TEK BAŞINA "
                f"YETMEDİ, nutLowRe'ye çevrildi ve model yine girmedi "
                f"(0,9872); (3) AĞ — ölçülen {yp_s}, oysa geçiş modeli "
                f"y⁺≲1 ister. Üçüncüsü bu ağda kapatılamaz: bu bir KAPANIŞ "
                "değil AĞ meselesidir.")
    # KIYAS AYNI AGDA YAPILIR. Ilk surum sabit sayilara (26,88 / 29,74)
    # kiyasliyordu; onlar URANS aginin (403.200 hucre, duvar fonksiyonu)
    # sayilari. Duvar-cozunur DES aginda (2,43 M) kosan bir sonucu onlarla
    # kiyaslamak IKI SEYI birden degistirir --- ag ve kapanis --- ve farkin
    # hangisinden geldigi soylenemez. Bu, betigin kendi docstring'inde
    # savundugu kuralin ihlaliydi.
    taban = _TABAN.get(ag, _TABAN["urans"])
    iyi_cd, cd_coz = _duzeldi_mi(s["Cd"], taban["Cd_pct"], esik_pct)
    iyi_st, st_coz = _duzeldi_mi(s["St"], taban["St_pct"], esik_pct)
    tb = (f"kıyas tabanı: {taban['ad']} (Cd %{taban['Cd_pct']}, "
          f"St %{taban['St_pct']}) --- AYNI AĞ")
    if iyi_cd and iyi_st:
        hkm = ("HİPOTEZ DESTEKLENDİ — geçiş modeli devrede ve İKİ sapma da "
               "aynı ağdaki tam-türbülanslı kapanışa göre AYIRT EDİLEBİLİR "
               "biçimde küçüldü.")
    elif iyi_cd or iyi_st:
        hangi = "Cd" if iyi_cd else "St"
        oteki = "St" if iyi_cd else "Cd"
        hkm = (f"HİPOTEZ EKSİK — geçiş modeli devrede ve {hangi} düzeldi, ama "
               f"{oteki} DÜZELMEDİ. Laminer-bağlı-tabaka açıklaması iki sapmayı "
               f"birden düzeltmeyi öngörüyordu; tek başına yetmiyor ve o haliyle "
               f"GERİ ÇEKİLMELİDİR.")
    else:
        hkm = ("HİPOTEZ ÇÜRÜDÜ — geçiş modeli devrede (laminer hücre "
               f"%{aralik.get('laminer_hucre_orani_pct')}) ve buna rağmen "
               "hiçbir sapma AYIRT EDİLEBİLİR biçimde düzelmedi; sapmanın "
               "kaynağı kapanışın türbülanslılığı DEĞİLDİR.")
    ek = f" [{etiket.strip('_')}]" if etiket else ""
    return (f"{hkm} Cd %{s['Cd']} ({cd_coz}), St %{s['St']} ({st_coz}). "
            f"{tb}.{ek}")


# KIYAS TABANLARI — AG BASINA. Her satir o agda AYNI kurulumla kosulmus
# tam-turbulansli kapanistir; farkin yalniz KAPANISTAN gelmesinin kosulu bu.
_TABAN = {
    "urans": {"ad": "3B URANS kOmegaSST (403.200 hücre, duvar fonksiyonu)",
              "Cd_pct": -26.88, "St_pct": 29.74},
    "des": {"ad": "3B DES kOmegaSSTDES (2,43 M hücre, duvar-çözünür)",
            "Cd_pct": -39.16, "St_pct": 38.16},
}


def _duzeldi_mi(yeni_pct: float, taban_pct: float,
                esik_pct: float | None) -> tuple[bool, str]:
    """Sapma küçüldü mü --- VE fark AYIRT EDİLEBİLİR mi?

    İlk sürüm yalnız `abs(yeni) < abs(taban)` soruyordu. Bu, ölçüm
    gürültüsünün içindeki bir oynamayı ``düzelme'' sayar: St sapması 29,74'ten
    28,58'e gittiğinde 1,16 puanlık fark, periyot saçılması %5,06 olan bir
    seride ayırt edilemez. Bir hipotezi böyle bir farkla desteklemek, olmayan
    bir kanıt üretmektir.
    """
    fark = abs(taban_pct) - abs(yeni_pct)
    if esik_pct is None:
        return fark > 0, "eşik YOK — ayırt edilebilirlik sorulmadı"
    if abs(fark) <= esik_pct:
        return False, (f"fark {abs(fark):.2f} puan, ayırt eşiğinin "
                       f"(%{esik_pct:.2f}) İÇİNDE — değişmedi sayılır")
    return fark > 0, (f"fark {fark:+.2f} puan, eşiğin (%{esik_pct:.2f}) dışında")


def kosu_suresi_dk(case: Path, duvar_saati_s: float) -> float:
    """Koşunun GERÇEK süresi — çözücünün kendi saatinden, betiğinkinden değil.

    `--oku` ile kayıt yeniden üretildiğinde betiğin duvar saati YENİDEN başlar
    ve `sure_dk` dakikalar mertebesine düşer. Ölçüldü: 16,9 saatlik bir koşunun
    kaydı yeniden okununca `sure_dk = 1,5` yazıldı --- yani kanıt dosyası,
    ölçtüğünü iddia ettiği koşunun süresini DEĞİL, kendi okuma süresini
    taşıyordu. Bu, raporun avladığı ``sabit metin, değişen veri'' sınıfının
    ikizi: DEĞİŞEN metin, ölçülmeyen veri.

    `ExecutionTime` OpenFOAM'ın koşu boyunca biriktirdiği süredir ve yeniden
    okumadan etkilenmez.
    """
    log = case / "log.foamRun"
    if log.exists():
        import re as _re
        d = _re.findall(r"ExecutionTime = ([0-9.]+)", log.read_text(errors="replace"))
        if d:
            return round(float(d[-1]) / 60.0, 1)
    return round(duvar_saati_s / 60.0, 1)


def _ayirt_esigi(t_ser: list, cd_ser: list, s3) -> float | None:
    """İki koşunun farkı ÖRNEKLEMEDEN ayırt edilebilir mi? — seriden.

    Sabit bir yüzde eşiği yazmak, bandı ölçmeden hüküm vermek olurdu.
    Ölçüt `silindir_dt_sondasi.cozunurluk_tabani` ile AYNI: pencere
    periyotlara bölünür, periyot ortalamalarının standart hatası alınır,
    2 standart hata eşiktir. İki yerde iki ayrı ölçüt yazmak, aynı sorunun
    iki farklı cevabını üretirdi.
    """
    from silindir_dt_sondasi import cozunurluk_tabani

    periyot = s3.D / (s3.ST_DENEY * s3.U)
    c = cozunurluk_tabani(t_ser, cd_ser, periyot, s3.PERIYOT_GECIS * periyot)
    return c["ayirt_esigi_pct"] if c.get("olculdu") else None


def _sonda_verdikti(gecerli: bool, aralik: dict, kurulum: dict | None) -> str:
    """Sonda TEK soruyu yanıtlar: model devreye girdi mi?

    St/Cd'ye BAKMAZ ve bakmamalıdır --- kısaltılmış bir istatistik
    penceresinden okunan sapma, sapmanın kendisi hakkında değil pencerenin
    kısalığı hakkında bilgi verir.
    """
    n = (kurulum or {}).get("periyot_sayisi")
    if gecerli:
        return (f"SONDA GEÇTİ — geçiş modeli devreye girdi (gammaInt min "
                f"{aralik.get('min')}, laminer hücre "
                f"%{aralik.get('laminer_hucre_orani_pct')}) ve bu, dört "
                f"koşudur olmayan şeydi. Duvar-çözünür ağ engeli kaldırdı. "
                f"TAM KOŞU ARTIK MEŞRU: sonda {n} periyottur ve St/Cd "
                f"veremez.")
    return (f"SONDA GEÇMEDİ — geçiş modeli {n} periyotta da devreye girmedi "
            f"(gammaInt min {aralik.get('min')}, laminer hücre "
            f"%{aralik.get('laminer_hucre_orani_pct')}). Duvar-çözünür ağ "
            f"TEK BAŞINA yetmedi; tam koşuya girmek için bir sebep YOK. "
            f"Bu, sondanın var oluş sebebidir: dördüncü açıklama da 8,5 "
            f"saate değil 1 saate mal oldu.")


def main(argv: list[str]) -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    import silindir_urans_3b as s3

    model = MODEL
    if "--model" in argv:
        model = argv[argv.index("--model") + 1]
    ag = "urans"
    if "--ag" in argv:
        ag = argv[argv.index("--ag") + 1]
    sonda = None
    if "--sonda" in argv:
        sonda = int(argv[argv.index("--sonda") + 1])
    # AD, KOSUYU AYIRT EDEN HER SEYI TASIR. Sabit ad kullanildiginda farkli
    # ayarli iki calisma birbirini EZER — bu depoda olculdu (girdi_uq_kos).
    etiket = ("_dr" + ("" if ag == "urans" else f"_{ag}")
              + ("" if model == MODEL else f"_{model}")
              + ("" if sonda is None else f"_sonda{sonda}"))
    case = KOK / f"_silindir_gecis_3b{etiket}"
    t0 = time.time()
    ti_ad = etiket
    kurulum_des = None
    if "--oku" in argv and (case / "log.foamRun").exists():
        print("mevcut koşu okunuyor (--oku)", flush=True)
        ret0 = None
    else:
        print(f"Kurulum: {ag} ağı + KAPANIŞ = {model} (duvar-çözünür)",
              flush=True)
        # AG ON KOSULU KURULUMDAN DA ONCE: reddedilecek bir agi once kurup
        # sonra reddetmek, 2,4 M hucrelik blockMesh'i bosuna calistirmak olur.
        _ag = ag_onkosulu(model, ag)
        if _ag:
            print("AĞ ÖN KOŞULU REDDETTİ:", _ag)
            return 3
        if ag == "des":
            ret0, kurulum_des = kur_des_agi(case, model, sonda)
            print(f"  ağ: {kurulum_des['hucre_kestirim']:,} hücre (kestirim), "
                  f"{kurulum_des['periyot_sayisi']} periyot"
                  + ("  [ARALIKLILIK SONDASI]" if kurulum_des["sonda_mu"] else ""),
                  flush=True)
        else:
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
        if ag == "des":
            import silindir_des_3b as _sd
            ok, mesaj = _sd.kos(case)
        else:
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
    yp = None
    try_yp = getattr(s3, "yplus_olc", None) or getattr(
        __import__("silindir_urans"), "yplus_olc", None)
    if try_yp:
        yp = try_yp(case)
        olcum["yplus"] = yp
    sonda_mu = bool((kurulum_des or {}).get("sonda_mu"))
    kayit = {
        "vaka": (f"Silindir 3B ({ag} ağı), {model}"
                 + (" — ARALIKLILIK SONDASI" if sonda_mu
                    else " — kapanış hipotezinin sınavı")),
        "_neden": ("Subkritik Re'de bagli sinir tabaka LAMINERDIR; tam-turbulansli "
                   "kapanis onu turbulans sayar ve Cd'yi dusuk verir. Bu kosu o "
                   "aciklamayi SINAR: dogruysa IKI sapma birden duzelmeli."),
        "kurulum": {"model": model, "ReThetat_serbest": ret0, "ag_tipi": ag,
                    "ag": (kurulum_des or
                           {"aciklama": "3B URANS ile AYNI (403.200 hücre)"}),
                    "_degisen_tek_sey": "KAPANIŞ"},
        "olculen": olcum, "referans": ref,
        "kiyas": {"3B URANS (kOmegaSST)": {"Cd_pct": -26.88, "St_pct": 29.74},
                  "3B DES (kOmegaSSTDES)": {"Cd_pct": -39.16, "St_pct": 38.16}},
        "aralik_denetimi": aralik,
        "sinav_gecerli": gecerli and not sonda_mu,
        "sonda": sonda_mu,
        "verdikt": (_sonda_verdikti(gecerli, aralik, kurulum_des) if sonda_mu
                    else _verdikt(gecerli, aralik, olcum, ti_ad, model,
                                  yp, ag, _ayirt_esigi(t, cd, s3))),
        # SURE COZUCUNUN SAATINDEN. Betigin duvar saati `--oku` ile
        # sifirlanir ve 16,9 saatlik bir kosu "1,5 dk" diye kaydedilir.
        "sure_dk": kosu_suresi_dk(case, time.time() - t0),
        "cozucu_saati_kaynagi": "log.foamRun ExecutionTime",
        "_uretim": "Üretim: python experiments/silindir_gecis_3b.py",
    }
    if sonda_mu:
        # SONDA BIR SONUC KOSUSU DEGILDIR. Istatistik penceresi kisaltilmis
        # bir kosudan St/Cd okumak mesru degil; sayilar kayitta DURUR ama
        # "olculen sapma" olarak SUNULMAZ.
        kayit["_kisit"] = (
            "ARALIKLILIK SONDASI: koşu KISALTILMIŞTIR "
            f"({kurulum_des['periyot_sayisi']} periyot). Tek yanıtladığı soru "
            "geçiş modelinin devreye girip girmediğidir. St/Cd sayıları "
            "kayıtta durur ama SONUÇ DEĞİLDİR — istatistik penceresi yetersiz.")
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
