"""Disk ve küp çapaları için BİRİNCİL deney literatürü — arama ve değerlendirme.

İki çapa da referansını tek bir el kitabından (Hoerner 1965) alıyordu ve
`referans_belirsizligi.json` ikisini de "TEK-KAYNAK / yöntem uygulanamaz" diye
işaretlemişti: ikinci bir kaynak olmadan u_D türetilemez.

BULUNAN
-------
disk : NACA TN-253, Montgomery Knight, Langley, Aralık 1926 — AÇIK ERİŞİM,
       TABLOLU. Beş-ayaklı kapalı-boğaz atmosferik tünelde 4/8/12 inç üç disk,
       DOĞRUDAN KUVVET ölçümü (tel süspansiyon + tünel sürükleme terazisi, tare
       ölçümü yapılmış). Re = 33.000–670.000, karakteristik uzunluk disk çapı.
       Cd = D/(qS), S = disk alanı (frontal) — çapanın tanımıyla AYNI.
       Beyan edilen ölçüm hatası: 50 noktanın 47'sinde < %1.

       Disk çapası Re = 30·0,1/1,5e-5 = 2,0e5'te koşuyor; TN-253'ün tablosu bu
       Re'yi ÜÇ diskte birden taşıyor. Koşul eşleşmesi tam.

küp  : Khan, Sooraj, Sharma & Agrawal (2018), Experimental Thermal and Fluid
       Science 93:257–271, doi:10.1016/j.expthermflusci.2017.12.013 — serbest
       akışta asılı küp, Re 500–55.000, PIV. KULLANILAMADI, gerekçe aşağıda.

TN-253'ÜN KENDİ UYARISI (bu betiğin varlık sebebi)
--------------------------------------------------
Knight blokaj düzeltmesi UYGULAMIYOR ve bunu açıkça söylüyor: sonuçlar "yalnız
bu tünelin karakteristiği olarak sunulur, sınırsız hava uzayında hareket eden
dairesel bir diskin karakteristiği olarak değil". Üç eğri arasındaki fark da
zaten blokaja atfediliyor.

Çapa ise SINIRSIZ akışta koşuyor. Yani TN-253'ün ham sayısı doğrudan referans
OLAMAZ; serbest-havaya taşınması gerekir. Bu betik taşımayı İKİ BAĞIMSIZ
yöntemle yapar ve ikisinin uyuşup uyuşmadığına bakar — tek yöntem kendi
varsayımını doğrulayamaz.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent

TUNEL_CAP_INC = 60.0          # "five-foot closed throat"; diskler tünelle eşmerkezli
NU = 1.5e-5
CAPA_HIZ, CAPA_CAP = 30.0, 0.1
CAPA_RE = CAPA_HIZ * CAPA_CAP / NU

HOERNER_DISK = 1.17           # çapanın hâlihazırdaki referansı
OLCULEN_DISK = 1.20956        # validation_anchors_runs/_anchor_disk/sonuc.json

# NACA TN-253 Tablo I-III, aynen. (Re, Cd)
TN253 = {
    12.0: [(98_000, 1.500), (146_000, 1.280), (195_000, 1.270), (293_000, 1.274),
           (390_000, 1.281), (488_000, 1.236), (585_000, 1.287), (682_000, 1.298)],
    8.0: [(65_000, 1.158), (130_000, 1.167), (195_000, 1.182), (260_000, 1.186),
          (325_000, 1.186), (390_000, 1.189), (455_000, 1.187)],
    4.0: [(33_000, 1.098), (65_000, 1.125), (98_000, 1.141), (130_000, 1.159),
          (163_000, 1.162), (195_000, 1.159), (228_000, 1.177)],
}

# Knight'ın kendisi 12 inçlik diskin Re=100.000 civarında "kararsız veya kritik"
# bir akış ürettiğini yazıyor; 98.000'deki 1,500 o yüzden aykırı. Çapanın Re'si
# 2,0e5 olduğu için o nokta zaten interpolasyona girmiyor.


def _interpolasyon(seri, re_hedef):
    for (r0, c0), (r1, c1) in zip(seri, seri[1:]):
        if r0 <= re_hedef <= r1:
            return c0 + (c1 - c0) * (re_hedef - r0) / (r1 - r0)
    raise ValueError(f"Re={re_hedef:g} tablo aralığı dışında")


def _dogrusal_uydurma(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    egim = sxy / sxx
    return egim, my - egim * mx


def main():
    caplar = sorted(TN253)
    tikama = [(d / TUNEL_CAP_INC) ** 2 for d in caplar]          # S/C, daireler eşmerkezli
    ham = [_interpolasyon(TN253[d], CAPA_RE) for d in caplar]

    # YÖNTEM 1 — sıfır-blokaja doğrusal ekstrapolasyon. Knight'ın kendi
    # açıklamasının doğrudan uygulanışı: farkı blokaj üretiyorsa, blokaj→0
    # kesişimi serbest-hava değeridir. Varsayım: küçük S/C'de doğrusallık.
    egim, kesisim = _dogrusal_uydurma(tikama, ham)

    # YÖNTEM 2 — Maskell (1963) katı-blokaj düzeltmesi, künt cisim için θ=2,5.
    # Yerleşik ve BAĞIMSIZ: her diski KENDİ başına düzeltir, aralarındaki farkı
    # kullanmaz. Üç farklı blokajlı disk aynı değere çöküyorsa düzeltme çalışıyor
    # demektir — bu, yöntemin kendi kendini sınamasıdır.
    theta = 2.5
    maskell = [c / (1.0 + theta * c * s) for c, s in zip(ham, tikama)]
    maskell_ort = sum(maskell) / len(maskell)
    maskell_yayilim_pct = 100.0 * (max(maskell) - min(maskell)) / maskell_ort
    ham_yayilim_pct = 100.0 * (max(ham) - min(ham)) / (sum(ham) / len(ham))

    yontem_farki_pct = 100.0 * abs(kesisim - maskell_ort) / maskell_ort
    # İki yöntem uyuşuyorsa serbest-hava değeri için tek bir sayı verilebilir.
    serbest_hava = 0.5 * (kesisim + maskell_ort)

    # u_D: deponun ilan ettiği yöntem — AYNI KOŞULDA iki bağımsız kaynağın farkı,
    # savunulabilir ALT kestirim. Ahmed'de bu yöntem Re uyuşmadığı için
    # UYGULANAMAMIŞTI; burada Re birebir eşleşiyor (TN-253 tablosu 2,0e5'i
    # taşıyor), yani engel gerçekten kalktı.
    u_d_pct = 100.0 * abs(HOERNER_DISK - serbest_hava) / min(HOERNER_DISK, serbest_hava)

    sonuc = {
        "vaka": "disk + küp çapaları: bağımsız BİRİNCİL kaynak araması",
        "_tarih": "2026-08-19",
        "capa_kosulu": {"hiz_m_s": CAPA_HIZ, "cap_m": CAPA_CAP, "Re": CAPA_RE,
                        "akis": "sınırsız (CFD uzak-alan)"},
        "disk": {
            "kaynak": ("NACA TN-253, Montgomery Knight, Langley Memorial "
                       "Aeronautical Laboratory, Aralık 1926 — 'Wind Tunnel "
                       "Standardization Disk Drag' (NTRS 19930087643)"),
            "erisim": "AÇIK ERİŞİM, tam metin + Tablo I-III okundu",
            "yontem": ("doğrudan kuvvet: tel süspansiyon + tünel sürükleme "
                       "terazisi, ayrı tare ölçümü; Cd = D/(qS), S = disk alanı"),
            "Re_araligi": "33.000 – 670.000 (karakteristik uzunluk = disk çapı)",
            "kaynagin_beyan_ettigi_hata_pct": 1.0,
            "_hata_notu": "50 noktanın 3'ü hariç tekrar ölçümler %1 içinde uyuşuyor",
            "KAYNAGIN_KENDI_UYARISI": (
                "Blokaj düzeltmesi UYGULANMAMIŞ. Knight: sonuçlar 'yalnız bu "
                "tünelin karakteristiği olarak sunulur, sınırsız hava uzayında "
                "hareket eden dairesel bir diskin karakteristiği olarak değil'. "
                "Üç eğri arasındaki fark da blokaja atfediliyor."),
            "capa_Re_sinde_ham_degerler": [
                {"disk_inc": d, "tikama_S_C": round(s, 5), "Cd_ham": round(c, 4)}
                for d, s, c in zip(caplar, tikama, ham)],
            "ham_yayilim_pct": round(ham_yayilim_pct, 2),
            "serbest_havaya_tasima": {
                "yontem_1_dogrusal_ekstrapolasyon": {
                    "Cd_S_C_sifir": round(kesisim, 4),
                    "egim": round(egim, 3),
                    "varsayim": "küçük S/C'de Cd–blokaj ilişkisi doğrusal"},
                "yontem_2_maskell_1963": {
                    "theta": theta,
                    "duzeltilmis": [round(m, 4) for m in maskell],
                    "ortalama": round(maskell_ort, 4),
                    "duzeltme_sonrasi_yayilim_pct": round(maskell_yayilim_pct, 2),
                    "_kendi_kendini_sinama": (
                        f"Blokajı 9 kat farklı üç disk düzeltmeden ÖNCE "
                        f"%{ham_yayilim_pct:.1f} ayrışıyordu, SONRA "
                        f"%{maskell_yayilim_pct:.1f}. Düzeltme farkı gerçekten "
                        "yiyor — yani ham yayılımın kaynağı blokajdır.")},
                "iki_yontem_farki_pct": round(yontem_farki_pct, 2),
                "serbest_hava_Cd": round(serbest_hava, 4)},
            "hoerner_ile_kiyas": {
                "hoerner": HOERNER_DISK,
                "TN253_serbest_hava": round(serbest_hava, 4),
                "fark_pct": round(u_d_pct, 2)},
            "u_D_alt_kestirim_pct": round(u_d_pct, 2),
            "u_D_sinif": ("ALT SINIR — aynı Re'de iki bağımsız kaynağın farkı "
                          "(Hoerner el kitabı vs TN-253 blokaj-düzeltilmiş). "
                          "TN-253 tarafı TÜRETİLMİŞ: blokaj düzeltmesi kaynağın "
                          "kendisinde yok, bu betikte uygulandı."),
            "olculen_cfd": OLCULEN_DISK,
            "sapma_hoernere_pct": round(100 * (OLCULEN_DISK - HOERNER_DISK)
                                        / HOERNER_DISK, 2),
            "sapma_TN253e_pct": round(100 * (OLCULEN_DISK - serbest_hava)
                                      / serbest_hava, 2),
            "verdikt": "TEK-KAYNAK ENGELİ KALKTI — u_D beyan edilebilir",
        },
        "kup": {
            "kaynak": ("Khan, M.H.; Sooraj, P.; Sharma, A.; Agrawal, A. (2018), "
                       "'Flow around a cube for Reynolds numbers between 500 and "
                       "55,000', Experimental Thermal and Fluid Science 93:257–271, "
                       "doi:10.1016/j.expthermflusci.2017.12.013"),
            "erisim": "ÜCRETLİ DUVAR — yalnız özet ve künye okunabildi",
            "yontem": "PIV; sürükleme iz-momentum (wake survey) ile TÜRETİLİYOR",
            "bildirilen_Cd": "0,56–0,68 (temel yöntem); 0,63–0,89 (değiştirilmiş iz taraması)",
            "verdikt": "BULUNDU AMA REFERANS OLARAK KULLANILAMADI",
            "gerekce": [
                "KOŞUL UYUŞMUYOR: üst Re'si 5,5e4; küp çapası Re = 2,0e5'te "
                "koşuyor. Kaynak çapanın rejimini kapsamıyor.",
                "ÖLÇÜLEN NİCELİK AYNI DEĞİL: PIV iz-momentumundan türetilen "
                "sürükleme, kuvvet terazisi sürüklemesiyle özdeş değildir; künt "
                "cisimde güçlü 3B iz ve düzlem-dışı momentum akısı nedeniyle iz "
                "taraması sistematik olarak DÜŞÜK okur. Kaynağın kendi iki "
                "yöntemi bile %27 ayrışıyor (0,68 vs 0,89).",
                "FARK u_D OLAMAYACAK KADAR BÜYÜK: Hoerner 1,05 ile arasındaki "
                "fark ~%40. Bu, iki ölçümün saçılması değil, tanım/yöntem "
                "farkının imzasıdır; u_D diye yazmak sahte-kesinlik olurdu.",
            ],
            "_duzeltme": ("Önceki kayıt küp için 'bağımsız birincil kaynak YOK' "
                          "diyordu. Bu YANLIŞTI — kaynak var ve birincil. Doğru "
                          "ifade: kaynak var, çapanın koşuluna ve ölçtüğü "
                          "niceliğe uymuyor."),
            "acik_kalan": ("Re ≳ 1e5'te serbest akışta küp için KUVVET TERAZİSİ "
                           "ölçümü hâlâ bulunamadı. Küp literatürünün ağırlığı "
                           "ya yüzeye-monteli küp (Castro & Robins 1977, sınır "
                           "tabaka içinde — farklı problem) ya da parçacık "
                           "rejiminde düşük Re."),
        },
    }

    sonuc["verdikt"] = (
        f"disk: TEK-KAYNAK engeli KALKTI — NACA TN-253 (birincil, kuvvet "
        f"terazisi, koşula eşleşik Re) blokaj-düzeltilerek serbest havaya "
        f"taşındı (Cd={serbest_hava:.4f}); Hoerner 1,17 ile farkı u_D olarak "
        f"beyan edildi (%{u_d_pct:.2f}). küp: birincil kaynak BULUNDU (Khan vd. "
        f"2018) ama çapanın Re'sini kapsamıyor ve iz-taramasıyla ölçüyor — "
        f"referans olamadı, u_D beyan EDİLMEDİ.")
    yol = KOK / "capa_birincil_kaynak.json"
    yol.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Çapa Re = {CAPA_RE:,.0f}\n")
    print("NACA TN-253, Re = 2,0e5'te ham (blokaj düzeltmesiz):")
    for d, s, c in zip(caplar, tikama, ham):
        print(f"  {d:4.0f} inç  S/C = {s:.4f}  Cd = {c:.4f}")
    print(f"  ham yayılım: %{ham_yayilim_pct:.1f}\n")
    print(f"Yöntem 1 (S/C→0 ekstrapolasyon) : Cd = {kesisim:.4f}")
    print(f"Yöntem 2 (Maskell θ=2,5)        : Cd = {maskell_ort:.4f} "
          f"(düzeltme sonrası yayılım %{maskell_yayilim_pct:.1f})")
    print(f"  iki yöntem farkı: %{yontem_farki_pct:.2f}  → serbest hava "
          f"Cd = {serbest_hava:.4f}\n")
    print(f"Hoerner {HOERNER_DISK} vs TN-253 {serbest_hava:.4f} → u_D ≈ %{u_d_pct:.2f}")
    print(f"Ölçülen CFD {OLCULEN_DISK}: Hoerner'a %"
          f"{100*(OLCULEN_DISK-HOERNER_DISK)/HOERNER_DISK:+.2f}, "
          f"TN-253'e %{100*(OLCULEN_DISK-serbest_hava)/serbest_hava:+.2f}")
    print(f"\nyazıldı: {yol}")


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    main()
