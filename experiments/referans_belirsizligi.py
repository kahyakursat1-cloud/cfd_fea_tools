"""u_D beyan etmeyen çapalar: hangisi TÜRETİLEBİLİR, hangisi kaynak bekliyor.

NEDEN: on bir çapanın altısı referans belirsizliği (u_D) beyan etmiyor ve o
çapaların ayrılabilirlik hükmü u_val = u_num varsayımıyla, yani İYİMSER
hesaplanıyor. "u_D yok" tek başına bir durum tespiti; eyleme çevrilmesi için
her çapanın NEDEN u_D'siz olduğu ayrılmalıdır.

Deponun kendi yöntemi zaten var ve düz levhada işledi: aynı koşulda İKİ
yerleşik korelasyon değerlendirilip farkları u_D'nin savunulabilir bir ALT
kestirimi sayıldı (1/7-kuvvet %0,3735 ve Schultz-Grunow %0,3610 → %3,36).
Yöntem yalnız o çapaya uygulanmıştı.

Bu betik yöntemi tüm çapalara uygulamayı DENER ve engeli adıyla yazar. Üç
farklı engel çıkıyor ve karıştırılmamalıdır:

  KAYNAK-EKSİK   Çapa tanımı İKİ kaynak adı taşıyor ama tek sayı saklıyor.
                 Yöntem uygulanabilir; eksik olan yalnızca ikinci sayıdır.
                 (naca0012_a0: Ladson + TMR;  ahmed_25: Ahmed 1984 + Meile 2011)
  TEK-KAYNAK     Elde tek tablo değeri var ve ikinci bir yerleşik korelasyon
                 yok. Yöntem uygulanamaz. (Hoerner: küp, disk)
  Re-BANDI       Çapa tek bir Cd taşıyor ama GEÇERLİ OLDUĞU Re aralığını da
                 beyan ediyor. O aralıkta Cd değişiyorsa, değişim tek-sayılı
                 bir çapa için indirgenemez bir u_D'dir. (küre)

Re-BANDI hesabı korelasyon sabitleri gerektirir ve bu betik onları BİRİNCİL
KAYNAKTAN DOĞRULANMAMIŞ sayar: sonuç `_dogrulama_bekliyor` damgasıyla çıkar ve
model-form hesabına OTOMATİK GİRMEZ. Doğrulanmamış bir sayıyı bandın içine
sokmak, bu deponun tekrar tekrar reddettiği şeydir.

    python experiments/referans_belirsizligi.py
Çıktı: referans_belirsizligi.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "referans_belirsizligi.json"

# KAYNAK-EKSIK satirlari icin ARAMA YAPILDI (2026-08-12). Sonuclar burada
# kayitli; capa tanimina yazilip yazilmadigi AYRI bir karardir ve gerekcesi
# her satirda duruyor. "Bulundu" ile "beyan edilebilir" ayni sey degildir.
ARANAN = {
    "naca0012_a0": {
        "sonuc": "BEYAN EDİLDİ",
        "bulunan": ("TMR ayni vakayi ayni agda (897x257) ve ayni modelle (SA) "
                    "YEDI bagimsiz kodla kosup hepsini yayimliyor; tekil deger "
                    "yayimladigi SANILIYORDU."),
        "u_D_pct": 0.796,
        "kaynak_turu": "BIRINCIL (NASA TMR sayfasinin kendisi)",
        "kanit": "tmr_kod_yayilimi.json",
    },
    "ahmed_25": {
        "sonuc": "BULUNDU AMA BEYAN EDİLMEDİ",
        "bulunan": "Meile ve ark. (2011), 25° egim icin cD = 0,299.",
        "capa_degeri": 0.285,
        "fark_pct": 4.79,
        "kaynak_turu": "IKINCIL (CFD dogrulama sayfalari); birincil makale "
                       "metnine erisilemedi",
        "neden_beyan_edilmedi": [
            "Kaynak IKINCIL: sayi birincil makaleden okunmadi.",
            "Iki deger AYNI Re'de DEGIL (Ahmed ~1e6, Meile 2,784e6); fark, "
            "kaynak yayilimi ile Re bagimliligini KARISTIRIR. Duz levhadaki "
            "yontem 'ayni kosulda iki korelasyon' diyordu, bu kosul saglanmiyor.",
        ],
    },
    "disk": {
        "sonuc": "BEYAN EDİLDİ",
        "bulunan": ("NACA TN-253 (Knight, Langley, 1926): 4/8/12 inclik uc disk, "
                    "DOGRUDAN KUVVET olcumu, Re 33.000-670.000. Capanin kostugu "
                    "Re = 2,0e5 tabloda UC diskte birden var."),
        "u_D_pct": 2.99,
        "kaynak_turu": "BIRINCIL (NACA raporunun tam metni + Tablo I-III okundu)",
        "kanit": "capa_birincil_kaynak.json",
        "_tasima": ("Knight blokaj duzeltmesi UYGULAMIYOR ve sonuclarin serbest "
                    "hava icin gecerli OLMADIGINI acikca yaziyor. Capa sinirsiz "
                    "akista kostugu icin tasima sart: S/C->0 ekstrapolasyonu "
                    "1,1396, Maskell(theta=2,5) 1,1324, fark %0,63 -> 1,1360."),
        "_kendi_kendini_sinama": ("Blokaji 9 kat farkli uc disk, duzeltme ONCESI "
                                  "%9,0 ayrisiyordu, SONRASI %2,1. Yayilimin "
                                  "kaynagi gercekten blokajmis."),
    },
    "cube": {
        "sonuc": "BULUNDU AMA REFERANS OLARAK KULLANILAMADI",
        "bulunan": ("Khan, Sooraj, Sharma & Agrawal (2018), Exp. Thermal Fluid "
                    "Sci. 93:257-271 — serbest akista asili kup, Re 500-55.000, "
                    "PIV. Cd = 0,56-0,68 (temel), 0,63-0,89 (degistirilmis iz "
                    "taramasi)."),
        "kaynak_turu": "BIRINCIL ama ucretli duvar; ozet ve kunye okunabildi",
        "neden_beyan_edilmedi": [
            "KOSUL UYUSMUYOR: ust Re'si 5,5e4; kup capasi Re = 2,0e5'te kosuyor.",
            "OLCULEN NICELIK AYNI DEGIL: PIV iz-momentumundan turetilen "
            "surukleme, kuvvet terazisi suruklemesiyle ozdes degildir. Kunt "
            "cisimde iz taramasi sistematik olarak DUSUK okur; kaynagin kendi "
            "iki yontemi bile %27 ayrisiyor.",
            "FARK u_D OLAMAYACAK KADAR BUYUK: Hoerner 1,05 ile ~%40. Bu bir "
            "olcum sacilmasi degil, yontem farkinin imzasi.",
        ],
        "_duzeltme": ("Onceki kayit 'bagimsiz birincil kaynak YOK' diyordu; bu "
                      "YANLISTI. Kaynak var ve birincil — capanin kosuluna ve "
                      "olctugu nicelige uymuyor. Iki ifade ayni sey degil."),
        "_acik_kalan": ("Re >~ 1e5'te serbest akista kup icin KUVVET TERAZISI "
                        "olcumu bulunamadi. Kup literaturunun agirligi ya "
                        "yuzeye-monteli kup (Castro & Robins 1977 — sinir tabaka "
                        "icinde, farkli problem) ya da dusuk-Re parcacik rejimi."),
    },
}

# Kaynak adlarini ayiran isaretler: ";" ve " + ". Virgul KULLANILMAZ —
# "Hoerner, Fluid-Dynamic Drag (1965)" tek kaynaktir ve virgul baslik icindedir.
_AYIRAC = re.compile(r"\s*;\s*")


def _kaynak_sayisi(ref: str) -> int:
    return len([p for p in _AYIRAC.split(ref or "") if p.strip()])


def _re_bandi(metin: str) -> tuple[float, float] | None:
    """'1e3–2e5 (subkritik)' → (1e3, 2e5). Tek deger ya da '>1e4' → None."""
    m = re.search(r"(\d+(?:\.\d+)?e\d+)\s*[–\-]\s*(\d+(?:\.\d+)?e\d+)", metin or "")
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def cd_kure(Re: float) -> float:
    """Clift-Gauvin korelasyonu — SABİTLER BİRİNCİL KAYNAKTAN DOĞRULANMALI.

    Cd = 24/Re·(1 + 0,15·Re^0,687) + 0,42/(1 + 42500·Re^−1,16)

    İlk terim Schiller-Naumann; ikinci terim yüksek-Re platosunu verir.
    Geçerlilik üst sınırı kritik Re'nin (~3·10^5) altıdır; sürükleme krizi
    MODELLENMEZ. Bu betik sonucu doğrulanmamış sayar (bkz. modül docstring).
    """
    return 24.0 / Re * (1 + 0.15 * Re ** 0.687) + 0.42 / (1 + 42500 * Re ** -1.16)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from validation_anchors import ANCHORS

    satirlar = []
    for ad, a in ANCHORS.items():
        if a.get("u_ref_pct") is not None:
            satirlar.append({"capa": ad, "durum": "u_D BEYAN EDİLMİŞ",
                             "u_ref_pct": a["u_ref_pct"]})
            continue
        ref, band = a.get("ref", ""), _re_bandi(a.get("Re", ""))
        n_kaynak = _kaynak_sayisi(ref)
        kayit = {"capa": ad, "kaynak_sayisi": n_kaynak, "ref": ref,
                 "Re": a.get("Re"), "Cd": a.get("Cd")}
        if band and ad == "sphere":
            alt, ust = band
            c_alt, c_ust = cd_kure(alt), cd_kure(ust)
            orta = a.get("Cd") or (c_alt + c_ust) / 2
            yayilim = 100.0 * abs(c_ust - c_alt) / orta
            kayit.update({
                "durum": "Re-BANDI",
                "engel": ("Capa TEK Cd tasiyor ama gecerli oldugu Re araligini "
                          "da beyan ediyor; o aralikta Cd degisiyor."),
                "cd_alt_Re": round(c_alt, 4), "cd_ust_Re": round(c_ust, 4),
                "u_D_alt_kestirim_pct": round(yayilim, 2),
                "_dogrulama_bekliyor": True,
                "_neden_beklemede": ("Clift-Gauvin sabitleri BIRINCIL KAYNAKTAN "
                                     "dogrulanmadi; sayi model-form hesabina "
                                     "OTOMATIK GIRMEZ."),
                "_capraz_kontrol": (
                    f"Korelasyon, capanin TASIDIGI plato degerine ({a.get('Cd')}) "
                    f"bandin IKI ucunda da oturuyor ({round(c_alt, 4)} ve "
                    f"{round(c_ust, 4)}). Bu, sabitlerin yaklasik dogru oldugunun "
                    f"isaretidir ama birincil kaynak dogrulamasi DEGILDIR — "
                    f"yanlis bir formul de tesadufen bir noktada tutabilir, "
                    f"ikisinde birden tutmasi daha zordur."),
                "korelasyon": "Clift-Gauvin (Schiller-Naumann + plato terimi)",
                "_hukmu_degistirir_mi": (
                    "HAYIR. Kure capasi zaten sayisal band cok buyuk oldugu icin "
                    "(%63) hicbir hucreye atanmiyor; u_D eklemek o reddi "
                    "degistirmez. Bu satir bir kapiyi ACMIYOR, bir bosluğu "
                    "ADLANDIRIYOR."),
            })
        elif n_kaynak >= 2:
            kayit.update({
                "durum": "KAYNAK-EKSİK",
                "engel": (f"Capa tanimi {n_kaynak} kaynak adi tasiyor ama TEK "
                          f"sayi sakliyor. Duz levhada isleyen yontem (iki "
                          f"kaynagin farki = u_D alt kestirimi) burada da "
                          f"uygulanabilir; eksik olan yalnizca IKINCI SAYIDIR."),
                "gereken": "ikinci kaynagin Cd degeri kayda gecmeli",
            })
            if ad in ARANAN:
                kayit["arama"] = ARANAN[ad]
        else:
            kayit.update({
                "durum": "TEK-KAYNAK",
                "engel": ("Tek tablo degeri var ve ikinci bir yerlesik "
                          "korelasyon yok; yontem UYGULANAMAZ."),
                "gereken": "bagimsiz ikinci bir olcum/kaynak",
            })
            # ARAMA KAYDI TEK-KAYNAK SATIRLARINA DA ILISIR. Onceki surumde
            # yalniz KAYNAK-EKSIK dalina ilisiyordu, yani "arandi ve bulunamadi"
            # ile "hic aranmadi" AYNI GORUNUYORDU. Kup icin kaynak ARANDI,
            # BULUNDU ve gerekceli olarak REDDEDILDI — bu, aramamakla ayni sey
            # degil ve kayitta gorunmeliydi.
            if ad in ARANAN:
                kayit["arama"] = ARANAN[ad]
        satirlar.append(kayit)

    say = {}
    for s in satirlar:
        say[s["durum"]] = say.get(s["durum"], 0) + 1
    rec = {
        "vaka": "u_D beyan etmeyen çapalar — engel türüne göre ayrım",
        "_neden": ("'u_D yok' tek basina durum tespiti; eyleme cevrilmesi icin "
                   "her capanin NEDEN u_D'siz oldugu ayrilmali."),
        "_yontem": ("Deponun duz levhada kullandigi yontem: ayni kosulda iki "
                    "yerlesik korelasyonun farki, u_D'nin savunulabilir ALT "
                    "kestirimi. Bu betik yontemi tum capalara uygulamayi dener."),
        "satirlar": satirlar,
        "sayim": say,
        "_kisit": ("Hicbir sayi burada model-form bandina YAZILMAZ. Re-BANDI "
                   "kestirimi dogrulama bekliyor; KAYNAK-EKSIK satirlari ise "
                   "literatur isi ister ve o is bu depoda YAPILMADI."),
        "_uretim": "Üretim: python experiments/referans_belirsizligi.py",
    }
    ke = say.get("KAYNAK-EKSİK", 0)
    rec["verdikt"] = (
        f"{len(satirlar)} çapa: {say.get('u_D BEYAN EDİLMİŞ', 0)} beyanlı, "
        f"{ke} KAYNAK-EKSİK (yöntem uygulanabilir, ikinci sayı kayıtlı değil), "
        f"{say.get('TEK-KAYNAK', 0)} TEK-KAYNAK (yöntem uygulanamaz), "
        f"{say.get('Re-BANDI', 0)} Re-BANDI (kestirim var, doğrulama bekliyor). "
        f"Yani u_D boşluğunun tamamı 'ölçülemez' değil: {ke} çapada eksik olan "
        f"ölçüm değil, KAYDA GEÇMEMİŞ bir literatür sayısı.")

    import ortam
    ortam.damgala(rec)
    CIKTI.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")

    print(rec["vaka"] + "\n" + "=" * 76)
    for s in satirlar:
        print(f"{s['capa']:<22}{s['durum']}")
        if s.get("arama"):
            a = s["arama"]
            print(f"{'':<22}  ARAMA: {a['sonuc']} — {a['kaynak_turu']}")
        if s.get("u_D_alt_kestirim_pct"):
            print(f"{'':<22}  Cd {s['cd_alt_Re']} → {s['cd_ust_Re']} "
                  f"= u_D ≥ %{s['u_D_alt_kestirim_pct']} (DOĞRULAMA BEKLİYOR)")
        elif s.get("gereken"):
            print(f"{'':<22}  gereken: {s['gereken']}")
    print("=" * 76)
    print(rec["verdikt"])
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
