"""Validasyon çapaları + model-belirsizlik öncülleri (ASME V&V 20 validasyon bacağı).

İki işi var:
1. ANCHORS — literatürden bilinen-doğru referans Cd'ler. validate_pipeline.py bunları
   pipeline'dan geçirip rejim-başına ÖLÇÜLEN hata bandını üretir (compute gerektirir).
2. model_uncertainty_pct — pipeline daha validate edilmeden önce kullanılan LİTERATÜR
   ÖNCÜLÜ: RANS-SST'nin rejim/duvar-çözünürlüğüne göre tipik model hatası. Ölçülen bant
   (validation_band.json) varsa O kullanılır; yoksa bu öncül + açık "validasyon beklemede"
   etiketi döner. Sahte-kesinlik verilmez.

Kaynaklar: küre subkritik Cd≈0.47 (White, Fluid Mechanics; Schlichting). NACA0012 α=0
Cd₀≈0.0081 (Ladson NASA TM-4074 / NASA TMR). Ahmed body 25° Cd≈0.285 (Ahmed 1984; Meile
2011). Rejim model-hatası mertebeleri: RANS-SST harici-aerodinamik V&V literatürü.

u_ref_pct (u_D) BEYAN KURALI: sayı ya kaynağın kendisinden gelir ya da hiç yazılmaz.
Türetilmişse `u_ref_sinif` alanı neyin ölçüldüğünü söyler — örneğin NACA0012 α=0'ın
u_D'si TMR'nin yedi kodunun yayılımıdır (ALT SINIR: deneysel belirsizliği kapsamaz).
Beyan edilmemiş çapaların engeli `referans_belirsizligi.json` içinde adıyla kayıtlı;
"u_D yok" ile "u_D ölçülemez" aynı şey değildir.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

ANCHORS = {
    "sphere": {
        # ASIL ENGEL OLCULDU (2026-08-19). Katman orgusu duzeltildikten SONRA:
        #   y+ 59,08 -> 5,54 (katman 0,535 -> 6,82, hedef kalinligin %96,7'si)
        #   Cd 0,142 -> 0,243 (referansa dogru ama hala yarisi)
        # Yani duvar cozunurlugu 10,7 kat iyilesti ve capa YINE dustu — ama
        # artik BASKA bir nedenle: ince seviye YAKINSAMIYOR. Rezidueller
        # platoya oturuyor (limit cevrimi) ve son %20'de Cd suruklenmesi %46,7
        # (sinir %2). Bu bir kurulum kusuru degil FIZIK: Re=1e5'te kure izi
        # zaman-bagimlidir (ayrilmis, kararsiz), kararli RANS'in yakinsayacagi
        # bir cozum yoktur.
        #
        # Sonuc: kure KARARLI-RANS capasi olarak uygun degil. Kapatilmasi
        # duvar cozunurlugunden degil, URANS'a (ya da zaman-ortalamali bir
        # yaklasima) gecmekten gecer. Bu ARTIK VARSAYIM DEGIL OLCUM.
        "Cd": 0.47, "regime": "bluff", "Re": "1e3–2e5 (subkritik)",
        "aref": "frontal", "ref": "White, Fluid Mechanics; Schlichting BL Theory",
        "u_ref_pct": None,   # ders kitabı değeri; kaynak band beyan etmiyor
    },
    "naca0012_a0": {
        # REJIM ETIKETI YANLISTI ("lifting"): alpha=0'da tasima SIFIRDIR ve bu
        # vaka bagli 2B akistir. model_form_bandi zaten onu attached_2d hucresine
        # yaziyordu, yani iki kaynak celisiyordu; dogru olan attached_2d.
        "Cd": 0.0081, "regime": "attached_2d", "Re": "6e6",
        "aref": "kiriş", "ref": "Ladson NASA TM-4074; NASA Turbulence Modeling Resource",
        # OLCULDU (tmr_kod_yayilimi.json): TMR tekil deger yayimliyor SANILIYORDU;
        # aslinda ayni vakayi ayni agda (897x257) ve ayni modelle (SA) YEDI
        # bagimsiz kodla kosup hepsini yayimliyor. Capanin referansi bir deney
        # degil o TMR degeri oldugu icin, referansin belirsizligi ayni seyi
        # hesaplayan kodlarin yayilimidir: 1σ = %0.796 (tam aralik %2.204).
        # ALT SINIR — kod-arasi yayilim DENEYSEL belirsizligi kapsamaz; TMR bu
        # vakada olculen suruklemenin sinir-tabaka tetiklemesine cok duyarli
        # oldugunu ayrica uyariyor.
        "u_ref_pct": 0.796,
        "u_ref_sinif": "ALT SINIR (kod-arası yayılım, n=7)",
    },
    "ahmed_25": {
        # REFERANS KOSULA ESLESTIRILDI (2026-08-19). Onceki deger 0,285 ve
        # beyan edilen Re "~1e6" idi; ikisi de KOSUYU ANLATMIYORDU.
        #
        # OLCULDU: bu capa V=40 m/s, L=1,044 m ile kosuyor → Re = 2,784e6.
        # Iki yayimlanmis deger var ve FARKLI KOSULLARDA:
        #   Ahmed & Ramm 1984 (SAE 840300): cD=0,2875 @ Re=4,29e6, V=60 m/s
        #   Meile vd. 2011 (CFD Letters 3(1)): cD=0,299 @ Re=2,784e6, V=40 m/s
        # Yani Meile'nin kosulu bu capanin kosuguyla BIREBIR AYNI.
        #
        # Onceki not "iki deger ayni Re'de degil, o yuzden yazilmaz" diyordu.
        # Bu, u_D TURETMEK icin dogru bir gerekcedir ama REFERANS SECIMI icin
        # degil: kostugun kosulda olculmus deger, baska bir kosulda olculmus
        # degerden daha iyi bir referanstir. Sapma %16,2 → %10,8'e iner ve
        # farkin bir kismi model hatasi degil KOSUL UYUSMAZLIGIYDI.
        #
        # KANIT DERECESI: iki BAGIMSIZ ikincil kaynak (SimFlow ve SimScale
        # dogrulama sayfalari) kosullariyla birlikte uyusuyor; birincil makale
        # metinleri ucretli duvar arkasinda ve OKUNAMADI. Bu yuzden u_ref
        # hala beyan EDILMIYOR — iki deger farkli Re'de oldugu icin aradaki
        # fark u_D degil, Re bagimliligiyla karisir.
        "Cd": 0.299, "regime": "bluff", "Re": "2,784e6 (V=40 m/s, L=1,044 m)",
        "aref": "frontal",
        "ref": ("Meile vd. 2011, CFD Letters 3(1) — cD=0,299 @ Re=2,784e6 "
                "(KOSULA ESLESIK); krs. Ahmed & Ramm 1984 SAE 840300, "
                "cD=0,2875 @ Re=4,29e6"),
        "u_ref_pct": None,
    },
    "cube": {
        # BIRINCIL KAYNAK ARANDI VE BULUNDU (2026-08-19) ama REFERANS OLAMADI:
        # Khan vd. 2018, Exp. Thermal Fluid Sci. 93:257-271 — serbest akista
        # asili kup, Re 500-55.000, PIV. Uc ayri engel:
        #   (1) Ust Re'si 5,5e4; bu capa Re = 2,0e5'te kosuyor.
        #   (2) Olculen nicelik ayni degil: PIV iz-momentumundan turetilen
        #       suruklemedir, kuvvet terazisi suruklemesi degil. Kaynagin KENDI
        #       iki yontemi bile %27 ayrisiyor (0,68 vs 0,89).
        #   (3) Hoerner'la fark ~%40 — bu bir olcum sacilmasi degil, yontem
        #       farkinin imzasi. u_D diye yazmak sahte-kesinlik olurdu.
        # Onceki kayit "bagimsiz birincil kaynak YOK" diyordu; bu YANLISTI.
        # Dogrusu: kaynak var, capanin kosuluna ve olctugu nicelige uymuyor.
        # Ayrinti: capa_birincil_kaynak.json
        "Cd": 1.05, "regime": "bluff", "Re": ">1e4 (keskin-kenar, Re-duyarsız)",
        "aref": "frontal", "ref": "Hoerner, Fluid-Dynamic Drag (1965)",
        "u_ref_pct": None,   # Hoerner tablo degeri; band beyan etmiyor
    },
    "disk": {
        # TEK-KAYNAK ENGELI KALKTI (2026-08-19). Bagimsiz BIRINCIL kaynak:
        # NACA TN-253 (Knight, Langley, 1926) — 4/8/12 inclik uc disk, DOGRUDAN
        # KUVVET olcumu (tel suspansiyon + surukleme terazisi + tare), Cd = D/(qS)
        # ve S = disk alani, yani capanin tanimiyla AYNI. Re 33.000-670.000; bu
        # capa Re = 2,0e5'te kosuyor, tablo o Re'yi UC diskte birden tasiyor.
        #
        # ONEMLI: Knight blokaj duzeltmesi UYGULAMIYOR ve bunu acikca soyluyor
        # ("yalniz bu tunelin karakteristigi ... sinirsiz hava uzayinda hareket
        # eden bir diskin degil"). Capa ise sinirsiz akista kosuyor, o yuzden
        # serbest-havaya tasindi. IKI BAGIMSIZ yontem: S/C->0 ekstrapolasyonu
        # 1,1396; Maskell (1963, theta=2,5) 1,1324. Fark %0,63 -> 1,1360.
        # Maskell kendi kendini siniyor: blokaji 9 kat farkli uc disk duzeltme
        # ONCESI %9,0 ayrisiyordu, SONRASI %2,1 — yani ham yayilimin kaynagi
        # gercekten blokaj.
        #
        # Cd DEGISTIRILMEDI. Hoerner 1,17 serbest-hava el kitabi degeri ve
        # capanin kosuluyla uyumlu; TN-253 tarafi ise blokaj duzeltmesi BU
        # DEPODA uygulandigi icin turetilmis. Turetilmis bir sayiyi referans
        # yuvasina koymak, onu u_D olarak beyan etmekten daha kotudur.
        "Cd": 1.17, "regime": "bluff", "Re": ">1e3 (keskin-kenar, Re-duyarsız)",
        "aref": "frontal",
        "ref": ("Hoerner, Fluid-Dynamic Drag (1965); NACA TN-253 (Knight 1926) "
                "— blokaj-düzeltilmiş serbest-hava Cd = 1,136 @ Re = 2,0e5"),
        # Ayni Re'de iki bagimsiz kaynagin farki: |1,17 - 1,1360| / 1,1360.
        # Ahmed'de bu yontem Re uyusmadigi icin uygulanAMAmisti; burada Re
        # birebir eslesiyor, yani engel gercekten kalkti.
        "u_ref_pct": 2.99,
        "u_ref_sinif": ("ALT SINIR (aynı Re'de iki bağımsız kaynağın farkı; "
                        "TN-253 tarafı blokaj-düzeltmesiyle TÜRETİLMİŞ)"),
    },
    "naca0012_a10_2d": {
        # LIFTING HUCRESINI BU MAKINEDE KAPATAN CAPA (2026-08-19).
        #
        # 3B AR6 capasi DORT denemede kapanmadi ve nedeni olculdu: NACA0012'nin
        # firar kenari kirisin ~%0,24'u, AR=6'da aciklik 18 m, ve o incelik tum
        # aciklik boyunca cozulemiyor. Gereken ~97M hucre (~97 GB) — bu makinede
        # de, makul bir RAM yukseltmesinde de yok. Kok neden BELLEK DEGIL
        # GEOMETRI.
        #
        # 2B'de aciklik YOK: yapisal C-grid firar kenarini dogal olarak kumeler
        # ve snappy'nin katman sorunu hic ortaya cikmaz. TMR PLOT3D C-grid
        # ailesi (57k / 229k / 918k hucre) bu makinede ZATEN KOSMUS.
        #
        # OLCULEN (Cd, ki model-form bandinin kullandigi nicelik budur):
        #   seviyeler 0,012086 -> 0,012377 -> 0,012572
        #   p = 0,579 (makul aralik 0,5-3,0 ICINDE), asimptotik oran = 1,0000
        #   GCI_ince = %3,93 ; Richardson Cd = 0,012177
        #   referansa hata: ham %1,72 | Richardson %1,48
        #
        # ONEMLI: kampanyanin kendi verdict'i "mesh bagimsizligi GOSTERILEMEDI,
        # p=-3,165" diyor — ama o hukum Cl ICINDIR (`birincil_nicelik: "Cl"`).
        # Cl'in yakinsama mertebesi ~3,17, tavanin (3,0) kil payi ustunde. Cd
        # bambaska davraniyor ve BAND Cd kullaniyor. Yani "capa gecersiz" degil,
        # "baska nicelik icin verilmis bir hukum".
        #
        # alpha=10 SECILDI, alpha=8 DEGIL: a8'de ham hata %16,8 ve Cd'nin p'si
        # negatif (yakinsama duzensiz). a10 hem hatasi kucuk hem yakinsamasi
        # temiz. Ikisi de kayitli, secim gerekceli.
        "Cd": 0.01236, "regime": "lifting", "Re": "6e6 (2B kesit), α=10°",
        "aref": "kiriş",
        "ref": ("NASA TMR NACA0012 (PLOT3D C-grid, SST, Re=6e6) — "
                "Cd=0,01236, Cl=1,0778"),
        # naca0012_a0 ile AYNI KAYNAK SINIFI: TMR'nin yedi kodunun yayilimi.
        # ALT SINIR cunku kod-arasi yayilim DENEYSEL belirsizligi kapsamaz.
        "u_ref_pct": 0.796,
        "u_ref_sinif": "ALT SINIR (kod-arası yayılım, n=7)",
    },
    "naca0012_wing_ar6": {
        # REFERANS YARI-ANALITIKTEN OLCULMUSE TASINDI (2026-08-19).
        #
        # ESKI: Cd=0,020, tumuyle analitik (duz-plaka Cf + form + lifting-line),
        # u_D = %15. O kadar buyuk bir u_D ile ag ne kadar inceltilirse
        # inceltilsin u_val %15'in ALTINA INEMEZ; capa ilkece kapanamazdi.
        #
        # YENI: referans IKI TERIME ayrildi ve baskin olan OLCUME baglandi
        #   Cd = cd_profil(cl)        <- LADSON TM-4074 (olculmus, 2B kesit)
        #      + CDi = CL^2/(pi e AR) <- lifting-line (modellenmis)
        # Ladson noktalari depoda ZATEN kayitliydi (naca0012_re_eslesme.json,
        # Re=6e6): a=0 -> cd 0,0082 | a=4 -> cl 0,452, cd 0,0092 | a=8 ->
        # cl 0,862, cd 0,0132. O dosya referansin hangi Re'ye ait oldugunu da
        # OLCMUS ve "Re6e6" demis — varsayim degil.
        #
        # Kesit tasima egimi Ladson'in KENDI noktasindan turetildi (a0=6,474
        # /rad), literaturden 2*pi varsayilmadi. Prandtl sonlu-kanat duzeltmesi
        # ZORUNLU: Ladson 2B'dir, AR=6 kanat downwash yuzunden ayni geometrik
        # alfa'da daha AZ tasir. CL(4 derece)=0,330, CDi=0,00623,
        # cd_profil=0,00893 -> Cd = 0,01516.
        #
        # RE DEGISTI: referans Re=6e6'da, capa ise 3e5'te kosuyordu. Kosul
        # eslesmesi icin geometri olceklendi (kiris 0,15 -> 3,0 m, 30 m/s,
        # Ma=0,088). Ag maliyeti degismez — cozunurluk kirise GORELIdir.
        # Ek fayda: Re=3e5 NACA0012 icin GECIS rejimidir ve tam-turbulansli
        # RANS orada yanlistir (deponun naca2412'de olctugu ders); 6e6'da
        # akis tam turbulanslidir ve NASA TMR bu Ladson setini tam bu amacla
        # oneriyor. Ayrinti: ar6_referans_ladson.json
        "Cd": 0.01516, "regime": "lifting", "Re": "6e6 (c=3.0 m, 30 m/s), α=4°",
        "aref": "planform",
        "ref": ("Ladson NASA TM-4074 (Langley LTPT, tripped, Re=6e6) profil "
                "sürüklemesi ÖLÇÜLMÜŞ + Prandtl lifting-line indüklenen "
                "sürükleme MODELLENMİŞ (e=0,90–0,952)"),
        # ALT SINIR: yalniz induklenen terimin model belirsizligini (e bandi)
        # kapsar. Ladson'in DENEYSEL belirsizligi bu depoda dogrulanmadi, o
        # yuzden profil tarafina belirsizlik YAZILMADI.
        "u_ref_pct": 1.0,
        "u_ref_sinif": ("ALT SINIR (yalnız e bandı; Ladson'ın deneysel "
                        "belirsizliği doğrulanmadı)"),
    },
}

# Rejim × duvar-çözünürlüğü → RANS-SST tipik model belirsizliği (%, 1σ mertebesi).
# (wall_resolved=y⁺≲1+katman, wall_function=y⁺≳30). Literatür-öncül; ölçülen bant gelince
# bu DEVRE-DIŞI kalır.
_MODEL_U_PCT = {
    "lifting": {"wall_resolved": 5.0, "wall_function": 12.0},
    "bluff":   {"wall_resolved": 10.0, "wall_function": 20.0},
    # AYRILMIŞ AKIŞ AYRI BİR REJİMDİR ve bunu ölçtük: geriye-basamaklı akışta
    # kOmegaSST yeniden-yapışmayı %11.58 kaçırıyor (Driver & Seegmiller 1985).
    # Bağlı akışın model-form hatasını ayrılmış akışa taşımak, RANS'ın en zayıf
    # olduğu rejimi en güçlü olduğu rejimin bandıyla raporlamak olurdu.
    "separated": {"wall_resolved": 12.0, "wall_function": 25.0},
    # 2B bağlı akış — TMR C-grid ailesinde ÖLÇÜLDÜ (%3.5, y⁺<1).
    "attached_2d": {"wall_resolved": 5.0, "wall_function": 12.0},
}
_BAND_FILE = HERE / "validation_band.json"


def regime_of(vehicle_type: str, preset: dict) -> str:
    """Araç tipini model-belirsizlik rejimine indir: lift üreten → 'lifting', küt → 'bluff'."""
    return "lifting" if preset.get("lift_relevant") else "bluff"


def model_uncertainty_pct(regime: str, wall_resolved: bool) -> dict:
    """Rejim+duvar-çözünürlüğü için model belirsizliği (%). Ölçülen validasyon bandı
    (validation_band.json) varsa onu, yoksa literatür-öncülünü döndürür (kaynak etiketli)."""
    key = "wall_resolved" if wall_resolved else "wall_function"
    if _BAND_FILE.exists():
        try:
            band = json.loads(_BAND_FILE.read_text(encoding="utf-8"))
            v = band.get(regime, {}).get(key)
            if v is not None:
                # KAC CAPADAN geldigi de soylenir: n=1 bir DAGILIM degil, tek
                # olcumdur ve okuyucu bunu bilmelidir.
                n = None
                ay = HERE / "model_form_bandi.json"
                if ay.exists():
                    d = json.loads(ay.read_text(encoding="utf-8"))
                    n = ((d.get("olculen_hucreler") or {})
                         .get(regime, {}).get(key, {}).get("n_capa"))
                return {"u_model_pct": round(float(v), 2),
                        "kaynak": ("ölçülen (validation_band.json"
                                   + (f", n={n} çapa" if n else "") + ")"),
                        "n_capa": n}
        # sessiz-yutma: kabul — ölçülen band okunamazsa ÖNCÜLE düşülür ve
        # kaynak etiketi bunu zaten söyler; sayı uydurulmaz.
        except Exception:
            pass
    # BILINMEYEN REJIM SESSIZCE 'bluff' SAYILIYORDU. Kunt cisim oncululu
    # (%10/20) tanimadigimiz her rejime uygulanmis oluyordu ve etikette bunun
    # izi YOKTU. Artik rejimin taninmadigi ACIKCA yazilir.
    if regime not in _MODEL_U_PCT:
        return {"u_model_pct": _MODEL_U_PCT["bluff"][key],
                "kaynak": (f"literatür-öncül — REJİM TANINMADI ('{regime}'), "
                           "künt cisim önculü uygulandı; bu bir ÖLÇÜM DEĞİL "
                           "ve rejim-uygunluğu DOĞRULANMAMIŞTIR"),
                "rejim_taninmadi": True}
    return {"u_model_pct": _MODEL_U_PCT[regime][key],
            "kaynak": "literatür-öncül (pipeline-validasyonu beklemede)"}


def combine_uncertainty(u_num_pct: float | None, u_model_pct: float | None) -> float | None:
    """Sayısal (GCI) + model belirsizliğini RSS ile birleştir → toplam genişletilmiş U (%)."""
    parts = [u for u in (u_num_pct, u_model_pct) if u is not None]
    if not parts:
        return None
    return round(math.sqrt(sum(u * u for u in parts)), 2)
