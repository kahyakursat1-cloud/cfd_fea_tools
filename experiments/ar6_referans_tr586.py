"""AR6 kanat çapası: NACA TR-586 Tablo I okundu — üç engelin durumu DEĞİŞTİ.

VAKA. `naca0012_wing_ar6` çapası hâlâ YARI-ANALİTİK bir referansa dayanıyor
(düz-plaka Cf + form + lifting-line, ±%15). u_D=%15 baskın bileşen olduğu için
ağ ne kadar inceltilirse inceltilsin u_val %15'in altına inemiyor ve model
hatası AYRILAMIYOR. Referans değişmeden bu çapa kapanmaz.

Önceki araştırma (capa_referans_denetimi.json) NACA TR-460'ı en güçlü aday
bulmuş ve üç somut engel yazmıştı: (1) değerler grafik, tablo değil;
(2) Re uyuşmazlığı; (3) u_D için ikinci kaynak yok.

BU TURDA OKUNAN. NACA TR-586 (Jacobs & Sherman 1937, NTRS 19930091662) —
TR-460'ın Reynolds-taramalı devamı, açık erişim, tam metin okundu.
  · Şekil 3 NACA 0012'yi test Re = 3.180.000 / 2.380.000 / 1.340.000 /
    660.000 / 330.000 / 170.000'de veriyor.
  · Tablo I ("Important Airfoil Section Characteristics") SAYISAL — aşağıda
    aynen kayıtlı.
  · Modeller 5 inç × 30 inç, yani AR=6 dikdörtgen; sonuçlar sonsuz-AR'ye
    düzeltilmiş SECTION verisi olarak veriliyor.

ENGELLERİN YENİ DURUMU
  (1) GRAFİK/TABLO — ÇÖZÜLDÜ ama KISMEN: Tablo I sayısal, ancak yalnız
      c_d0min (sıfır-taşımadaki EN KÜÇÜK profil sürüklemesi) veriyor. Çapa
      α=4°'de koşuyor ve oradaki polar Tablo I'de YOK; onun için Şekil 3'ün
      sayısallaştırılması gerekir.
  (2) Re UYUŞMAZLIĞI — KESKİNLEŞTİ: tablonun EN DÜŞÜK satırı 0,449 milyon,
      çapa ise 0,3 milyonda koşuyor. Yani çapanın Re'si tablonun ALTINDA.
      Dahası raporun kendi uyarısı: "The drag and pitching-moment results for
      effective Reynolds Numbers below 800,000 become relatively inaccurate
      owing to limitations imposed by the sensitivity of the measuring
      equipment." Veri bu bantta KAYNAĞIN KENDİSİ tarafından güvenilmez
      ilan ediliyor. Çözüm düşük-Re verisi aramak DEĞİL, çapayı yukarı
      ölçeklemek.
  (3) u_D — kaynağın kendi düşük-Re uyarısı sayıyla GÖRÜLÜYOR: 0,871 milyonda
      c_d0min=0,0065, 1,740 milyonda 0,0075. Re DÜŞERKEN sürükleme DÜŞMÜŞ —
      fiziksel beklentinin tersi. Bu, uyarının somut kanıtıdır ve düşük-Re
      satırlarının referans olarak kullanılamayacağını gösterir.

    python experiments/ar6_referans_tr586.py
Çıktı: ar6_referans_tr586.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

NU = 1.5e-5
CAPA_KIRIS_M, CAPA_HIZ = 0.15, 30.0
CAPA_RE = CAPA_HIZ * CAPA_KIRIS_M / NU

# KAYNAGIN KENDI ACCURACY bolumunden: bu esigin ALTINDA surukleme "relatively
# inaccurate" ilan ediliyor. Sayi bizim degil, RAPORUN.
GUVENILIR_RE_TABANI = 800_000

# NACA TR-586 Tablo I, NACA 0012 satirlari — AYNEN. (R_e milyon, c_d0min)
TABLO_I_0012 = [
    (8.370, 0.0069), (8.450, 0.0069), (6.280, 0.0073), (3.540, 0.0077),
    (1.740, 0.0075), (0.871, 0.0065), (0.449, 0.0105),
]

# Sekil 3'un (NACA 0012) TEST Reynolds sayilari — Tablo I'in EFEKTIF
# sutunuyla eslestirilince duzeltmenin buyuklugu dogrudan olculur.
SEKIL3_TEST_RE = [3_180_000, 2_380_000, 1_340_000, 660_000, 330_000, 170_000]


def main() -> int:
    guvenilir = [(re_m, cd) for re_m, cd in TABLO_I_0012
                 if re_m * 1e6 >= GUVENILIR_RE_TABANI]
    supheli = [(re_m, cd) for re_m, cd in TABLO_I_0012
               if re_m * 1e6 < GUVENILIR_RE_TABANI]

    # Monotonluk denetimi: Re DUSERKEN surukleme ARTMALI. Ters donen yer,
    # kaynagin kendi dusuk-Re uyarisinin SAYIYLA gorunur hali.
    sirali = sorted(TABLO_I_0012)           # artan Re
    ters = [(a, b) for a, b in zip(sirali, sirali[1:]) if b[1] > a[1]]

    # TURBULANS CARPANI: Sekil 3'un TEST Re'leri ile Tablo I'in EFEKTIF
    # sutununu esleyerek duzeltmenin buyuklugunu DOGRUDAN olc. Iki liste
    # buyukten kucuge sirali ve birebir esleniyor (Tablo I'de en ustteki iki
    # satir ayni testin tekrari oldugu icin ilki atlanir).
    carpanlar = [
        {"test_Re": t, "efektif_Re": int(e * 1e6), "carpan": round(e * 1e6 / t, 3)}
        for t, e in zip(sorted(SEKIL3_TEST_RE, reverse=True),
                        sorted((r for r, _ in TABLO_I_0012), reverse=True)[1:])
    ]

    # Capayi tabloya tasimak icin gereken kiris (hiz sabit 30 m/s).
    hedefler = [{"R_e_milyon": re_m,
                 "c_d0min": cd,
                 "gereken_kiris_m": round(re_m * 1e6 * NU / CAPA_HIZ, 3),
                 "aciklik_m": round(6 * re_m * 1e6 * NU / CAPA_HIZ, 2),
                 "mach": round(CAPA_HIZ / 340.0, 3)}
                for re_m, cd in guvenilir if re_m < 4.0]

    rec = {
        "vaka": "AR6 kanat çapası — NACA TR-586 Tablo I okundu",
        "_tarih": "2026-08-19",
        "kaynak": ("Jacobs, E. N. & Sherman, A., 'Airfoil Section Characteristics "
                   "as Affected by Variations of the Reynolds Number', NACA "
                   "Report 586 (1937; 1939 baskısı) — NTRS 19930091662"),
        "erisim": "AÇIK ERİŞİM; tam metin + Tablo I doğrudan okundu",
        "model": ("5 inç kiriş × 30 inç açıklık → AR=6 dikdörtgen; sonuçlar "
                  "sonsuz-AR'ye düzeltilmiş SECTION verisi olarak veriliyor"),
        "capa_kosulu": {"kiris_m": CAPA_KIRIS_M, "hiz_m_s": CAPA_HIZ,
                        "Re": CAPA_RE, "alpha_deg": 4.0},
        "tablo_I_naca0012": [{"R_e_milyon": r, "c_d0min": c}
                             for r, c in TABLO_I_0012],
        "kaynagin_dogruluk_uyarisi": {
            "esik_Re": GUVENILIR_RE_TABANI,
            "alinti": ("The drag and pitching-moment results for effective "
                       "Reynolds Numbers below 800,000 become relatively "
                       "inaccurate owing to limitations imposed by the "
                       "sensitivity of the measuring equipment."),
            "supheli_satirlar": [{"R_e_milyon": r, "c_d0min": c} for r, c in supheli],
            "uyari_SAYIYLA_gorunuyor": [
                {"dusuk_Re_milyon": a[0], "dusuk_cd": a[1],
                 "yuksek_Re_milyon": b[0], "yuksek_cd": b[1],
                 "not": ("Re DÜŞERKEN sürükleme DÜŞMÜŞ — fiziksel beklentinin "
                         "tersi; kaynağın düşük-Re uyarısının somut kanıtı")}
                for a, b in ters],
        },
        "engeller": {
            "1_grafik_tablo": {
                "durum": "KISMEN ÇÖZÜLDÜ",
                "cozulen": "Tablo I sayısal; c_d0min değerleri artık kayıtlı.",
                "kalan": ("Tablo I yalnız c_d0min (sıfır-taşıma minimumu) "
                          "veriyor. Çapa α=4°'de koşuyor ve o noktadaki polar "
                          "tabloda YOK — Şekil 3'ün sayısallaştırılması gerekir."),
            },
            "2_Re_uyusmazligi": {
                "durum": "KESKİNLEŞTİ",
                "olcum": (f"Çapa Re = {CAPA_RE:,.0f}; tablonun EN DÜŞÜK satırı "
                          f"{min(r for r, _ in TABLO_I_0012)*1e6:,.0f}. Çapa "
                          "tablonun ALTINDA."),
                "sonuc": ("Çözüm düşük-Re verisi aramak DEĞİL, çapayı yukarı "
                          "ölçeklemek: kaynak o bantta kendi verisini güvenilmez "
                          "ilan ediyor."),
                "olcekleme_secenekleri": hedefler,
            },
            "3_u_D": {
                "durum": "YÖN NETLEŞTİ",
                "not": ("İkinci kaynak hâlâ yok, ama kaynağın kendi doğruluk "
                        "beyanı ve düşük-Re'deki monotonluk ihlali u_D için "
                        "somut zemin veriyor. Güvenilir bantta (Re≥8e5) "
                        "c_d0min 0,0069–0,0077 arasında; bu yayılım Re "
                        "bağımlılığıyla karışık olduğu için doğrudan u_D "
                        "DEĞİLDİR ve öyle beyan EDİLMEZ."),
            },
        },
        "TURBULANS_CARPANI": {
            "_soru": "Bu referans çapa için güvenilir mi?",
            "olcum": carpanlar,
            "carpan": round(sum(c["carpan"] for c in carpanlar) / len(carpanlar), 3),
            "ne_anlama_geliyor": (
                "Tablo I'in Reynolds sütunu ÖLÇÜM DEĞİL. Test Re'si sabit bir "
                "türbülans çarpanıyla (2,64) çarpılmış 'etkin Reynolds sayısı'. "
                "Değişken-yoğunluklu tünel YÜKSEK TÜRBÜLANSLIDIR ve bu kavram "
                "tam o yüzden vardır."),
            "carpanin_kaynagi": (
                "NACA TR-558 (Platt, 'Turbulence Factors of NACA Wind Tunnels as "
                "Determined by Sphere Tests'; TR-586'nın 10 numaralı referansı). "
                "Çarpan, türbülanssız akıştaki kritik KÜRE Reynolds sayısının "
                "tünel içindekine oranıdır — yani bir kürenin geçiş noktasından "
                "türetilip kanat profiline TAŞINAN bir düzeltmedir."),
            "neden_engel": (
                "Çapanın BAĞIMSIZ DEĞİŞKENİNDE %164'lük model-tabanlı bir "
                "düzeltme demek. Deponun ilan ettiği kural — 'sayı ya kaynağın "
                "kendisinden gelir ya hiç yazılmaz; türetilmişse sınıfı "
                "söylenir' — burada referansı REDDEDER: yalnız c_d0min değil, "
                "hangi Re'ye ait olduğu da türetilmiştir."),
        },
        "TR824_DENENDI_VE_ELENDI": {
            "kunye": ("Abbott, I. H., von Doenhoff, A. E. & Stivers, L. S., "
                      "'Summary of Airfoil Data', NACA Report 824 (1945) — "
                      "NTRS 19930090976, 261 sayfa, tam metin indirildi"),
            "neden_hedeflendi": ("DÜŞÜK-TÜRBÜLANSLI BASINÇLI TÜNEL (LTPT) "
                                 "verisi; türbülans çarpanına gerek yok."),
            "BULGU": ("NACA 0012 BU RAPORDA YOK. Bölüm V ('Aerodynamic "
                      "Characteristics of Various Airfoil Sections') 90 kesit "
                      "listeliyor ve dört-haneli simetrik olarak yalnız 0006 ile "
                      "0009 var. LTPT'de %12 kalınlıktaki simetrik kesitler "
                      "laminer-akış serisidir (63₁-012, 64₁-012, 65₁-012), "
                      "klasik 0012 değil."),
            "sonuc": "UYGUN DEĞİL — kaynak kaliteli ama aranan kesiti içermiyor",
        },
        "DOGRU_KAYNAK_ZATEN_DEPODA": {
            "kunye": ("Ladson, C. L., NASA TM-4074 (1988) — Langley "
                      "DÜŞÜK-TÜRBÜLANSLI BASINÇLI TÜNEL, NACA 0012"),
            "nerede": ("`naca0012_a0` çapasının referansı olarak ZATEN kayıtlı "
                       "(Cd=0,0081 @ Re=6e6, u_ref=%0,796)."),
            "anlami": ("Aranan düşük-türbülanslı NACA 0012 kaynağı bulunamadığı "
                       "için değil, BAŞKA BİR ÇAPADA durduğu için görülmemişti. "
                       "AR6 çapasının sorunu 'iyi referans yok' DEĞİL; sorun "
                       "çapanın KOŞUL SEÇİMİ: Ladson Re≥2e6'da 2B kesit verisi "
                       "verirken çapa Re=3e5'te 3B AR=6 kanat koşuyor."),
        },
        "onerilen_yol": (
            "ARTIK KAYNAK ARAMA İŞİ DEĞİL, ÇAPA TASARIMI İŞİ. İki adım: "
            "(a) Çapayı Ladson'ın bandına taşı — 30 m/s'de kiriş ≥1,0 m ile "
            "Re ≥ 2e6, Ma=0,088 (sıkışamaz zarf içinde). Ağ maliyeti değişmez: "
            "çözünürlük kirişe GÖRELİdir, mutlak boyuta değil. "
            "(b) α=4° taşıma vakasında referansı iki terime ayır — profil "
            "sürüklemesi LADSON'DAN (ölçülmüş), indüklenen sürükleme "
            "lifting-line'dan (modellenmiş, e≈0,9). Böylece BASKIN terim "
            "ölçülmüş olur ve mevcut ±%15'lik tümüyle-analitik referans düşer; "
            "kalan u_D yalnız indüklenen terimin modelinden gelir. "
            "Ek olarak α=0° koşusu doğrudan kıyas verir (simetrik kesitte "
            "taşıma sıfır → indüklenen sürükleme sıfır → arada model yok), ama "
            "o vaka `lifting` hücresini BESLEMEZ çünkü taşıma yoktur."),
        "_geri_alinan_oneri": (
            "Bu betiğin ilk sürümü 'çapayı Re=1,74e6'ya taşı ve TR-586'yı "
            "referans al' diyordu. GERİ ALINDI: türbülans çarpanı ölçülünce "
            "görüldü ki taşınacak hedef Re'nin KENDİSİ 2,64'lük bir düzeltme "
            "taşıyor. Ölçekleme fikri (kiriş 0,87 m, Ma=0,088, ağ maliyeti "
            "değişmez) ve α=0° koşusu fikri (simetrik kesitte indüklenen "
            "sürükleme sıfır → arada model olmadan doğrudan kıyas) HÂLÂ "
            "geçerli; değişen yalnız hangi kaynağın hedef alınacağı."),
        "verdikt": (
            "TR-586 ÇAPA REFERANSI OLARAK KULLANILAMAZ. Tablo I okundu ve "
            "değerler kayda geçti, ama Reynolds sütunu ölçüm değil: test "
            "Re × 2,64 (küre testlerinden türetilen türbülans çarpanı). Buna ek "
            "olarak kaynak 8e5 altındaki sürüklemeyi kendi güvenilmez ilan "
            "ediyor ve monotonluk ihlali bunu SAYIYLA doğruluyor (0,871e6 → "
            "0,0065 ama 1,740e6 → 0,0075). Çapa referansı DEĞİŞTİRİLMEDİ. "
            "TR-824 de denendi ve ELENDİ: kaliteli ama NACA 0012'yi İÇERMİYOR "
            "(Bölüm V'te dört-haneli simetrik olarak yalnız 0006 ve 0009 var). "
            "ASIL BULGU: aranan düşük-türbülanslı NACA 0012 kaynağı — Ladson "
            "TM-4074, Langley LTPT — ZATEN DEPODA, `naca0012_a0` çapasının "
            "referansı olarak duruyor. Yani AR6 çapasının sorunu 'iyi referans "
            "yok' DEĞİL, çapanın KOŞUL SEÇİMİ: Ladson Re≥2e6'da 2B kesit verisi "
            "verirken çapa Re=3e5'te 3B AR=6 kanat koşuyor. Bu bir literatür "
            "işi değil, ÇAPA TASARIMI işidir."),
    }
    (KOK / "ar6_referans_tr586.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"çapa Re = {CAPA_RE:,.0f}  |  tablonun en düşüğü = "
          f"{min(r for r, _ in TABLO_I_0012)*1e6:,.0f}\n")
    print("NACA TR-586 Tablo I — NACA 0012:")
    for r, c in sorted(TABLO_I_0012, reverse=True):
        etiket = "" if r * 1e6 >= GUVENILIR_RE_TABANI else "  ← kaynak GÜVENİLMEZ diyor"
        print(f"  R_e = {r:>5.3f}e6   c_d0min = {c:.4f}{etiket}")
    if ters:
        print("\nMONOTONLUK İHLALİ (uyarının sayıyla görünmesi):")
        for a, b in ters:
            print(f"  Re {a[0]:.3f}e6 → cd {a[1]:.4f}  ama  "
                  f"Re {b[0]:.3f}e6 → cd {b[1]:.4f}")
    print("\nTÜRBÜLANS ÇARPANI (Reynolds sütunu ÖLÇÜM DEĞİL):")
    for c in carpanlar:
        print(f"  test {c['test_Re']:>9,} → efektif {c['efektif_Re']:>11,}"
              f"   ×{c['carpan']}")
    print(f"\n{rec['verdikt']}")
    return 0


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
