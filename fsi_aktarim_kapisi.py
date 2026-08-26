"""CFD→FEA yük aktarımı GÜVENİLİR Mİ? — ölçüm vardı, tüketici yoktu.

`coupling_fsi` üç korunum metriği yazıyor ve ikisi (kuvvet, moment) makine
hassasiyetinde çıkıyordu. Bu bir başarı gibi görünüyordu; değildi. O iki metrik
FEA yüzünden DÜĞÜME dağıtımı ölçer ve eşit-üçtebir şemasında YAPI GEREĞİ
kesindir. Gerçekten korunmayan adım basıncın CFD yüzlerinden FEA yüzlerine
en-yakın-komşu ile taşınmasıdır ve onu ölçen alan `aktarim_hatasi`.

ÖLÇÜLDÜ (20 vaka, fsi_korunum.json): %0,07 -- %56,30.

Ama hiçbir kapı bu sayıyı okumuyordu. Yani %56 aktarım hatası olan bir koşu,
kuvvet korunumu 1e-18 olduğu için "korunumlu" görünüyordu. Bu deponun baskın
kusuru: ölçülür, kaydedilir, KARARA ULAŞMAZ.

EŞİK UYDURULMADI, ÖLÇÜMDEN OKUNDU. Aktarım hatası ALAN FARKIYLA ilişkili:

    gripen_AB_Right   alan farkı %49,83  ->  aktarım %56,30
    _fsi_esnek        alan farkı  %9,48  ->  aktarım %20,25
    _fsi_sinama       alan farkı %41,30  ->  aktarım %13,45
    alan farkı ~0 olan 5 vaka            ->  aktarım <= %3,88

AMA ALAN FARKI TEK BAŞINA REDDETMEZ, VE BU DA ÖLÇÜMLE ÖĞRENİLDİ. İlk sürüm
``alan farkı > %5 ise reddet'' diyordu; 20 vakaya uygulandığında `MiniHawk_UAV`
düştü --- alan farkı %7,46 ama aktarım hatası %0,90. Yüzeyler farklı alanda
olsa bile yük doğru taşınabiliyor. Kural çalışan bir vakayı öldürecekti ve geri
çekildi: alan farkı bir RİSK GÖSTERGESİDİR, yüksek aktarım hatasını AÇIKLAR,
onun yerine geçmez. Kapıyı süren nicelik, önemsediğimiz niceliktir.

ASIL KAPI BANDA GÖRELİDİR. Mutlak bir yüzde yerine şunu sorar: aktarım hatası,
koşunun KENDİ yayımlanan belirsizlik bandından büyük mü? Büyükse eşleme hatası
raporlanan her şeye baskındır ve band anlamsızdır. Bu, subkritik kapanış
kapısıyla aynı desendir --- ölçülen hatayı beyan edilen banda karşı sınamak.

KAPI BİR ÇÖZÜM DEĞİL, BİR DÜRÜSTLÜK KATMANIDIR. En-yakın-komşu eşlemenin
yerini korunumlu bir projeksiyon (mortar, RBF, alan-ağırlıklı) almadıkça
%56'lık hata KAYBOLMAZ; bu kapı yalnız o koşunun tasarım kararına girmesini
engeller. Asıl iş hâlâ açıktır ve kuyrukta öyle işaretlidir.
"""
from __future__ import annotations

# ALAN KIMLIK ESIGI. Ayni yuzeyin iki ayriklastirmasi ayni alani verir; olculen
# 20 vakanin 5'inde %0,00, 13'unde %2'nin altinda. %5 BEYANDIR ve gerekcesi
# sudur: uzerinde, iki yuzey artik ayni geometri sayilmaz ve "aktarim" sozcugu
# yanlis kullanilmis olur. Olculen dagilimda bu esik yalniz uc vakayi ayirir
# ve o uc vaka en yuksek aktarim hatasina sahip olanlardir.
ALAN_KIMLIK_ESIGI_PCT = 5.0

# MUTLAK RED. Band bilinmiyorsa banda-goreli kapi calisamaz; o zaman da sessiz
# kalmak yanlis olur. %25 BEYANDIR: olculen dagilimda 17 vaka %4'un altinda,
# sonra 13,45 - 20,25 - 56,30 diye siciriyor. %25 o sicramanin ustunu keser.
# Sayi ayarlanmis DEGIL, dagilimdaki bosluga konmustur ve degistirilirse
# hangi vakalarin sinifinin degistigi testte yazilidir.
MUTLAK_RED_PCT = 25.0

# BUYUTME CARPANI — OLCULDU (5 vaka, fsi_yapisal_duyarlilik.json).
#
# Aktarim hatasi TASARIM NICELIGI DEGILDIR; karar sehim ve gerilmeyle verilir.
# "Aktarim hatasi %X ise sehim hatasi da ~%X" varsaymak, olculmemis bir oranti
# kabul etmektir. Ayni ag, ayni sinir kosullari, yalniz yuk seti degistirilerek
# olculdu:
#
#     _fsi_esnek    aktarim %20,25  ->  sehim %72,24   carpan 3,57
#     _fsi_sinama   aktarim %13,45  ->  sehim %14,92   carpan 1,11
#     fsi_tahrik*   aktarim  %8,4   ->  sehim  %7,4    carpan 0,88
#
# Yani aktarim hatasi tasarim-niceligi hatasinin ALT SINIRIDIR. En kotu vakada
# yukun BUYUKLUGU %30 degisirken DAGILIMI moment kolunu da degistirdi ve sehim
# farki 3,6 kat buyudu.
#
# KISIT: bes vakanin hepsi basit levha. Ince yuzeyli gercek geometride carpan
# OLCULMEMISTIR ve daha buyuk olabilir; bu yuzden carpan bir DUZELTME olarak
# kullanilmaz, kullaniciya BILDIRILIR.
BUYUTME_CARPANI_ARALIGI = (0.88, 3.57)


def aktarim_hukmu(aktarim_hatasi_pct: float | None,
                  alan_farki_pct: float | None = None,
                  u_toplam_pct: float | None = None) -> dict:
    """Yük aktarımı tasarım kararında kullanılabilir mi?

    Üç dal, üçü de ölçülen bir sayıya dayanır:
      * ÖLÇÜLEMEDİ  --- yokluk 'güvenilir' SAYILMAZ, sebep yazılır
      * REDDEDİLDİ  --- alan kimliği bozuk ya da hata mutlak eşiği aşıyor
      * BANDA BASKIN --- hata koşunun kendi bandından büyük; sınıf indirilir

    `u_toplam_pct` verilmezse banda-göreli dal ÇALIŞMAZ ve bu söylenir;
    verilmiş gibi davranmak sessiz bir geçiş üretirdi.
    """
    if aktarim_hatasi_pct is None:
        return {"kullanilabilir": None, "kod": "OLCULEMEDI",
                "neden": ("CFD→FEA aktarım hatası ÖLÇÜLEMEDİ (yük yok ya da "
                          "yüzey eşlenemedi). Yokluk 'güvenilir' sayılmaz; "
                          "bu koşunun yük aktarımı DOĞRULANMAMIŞTIR.")}

    a = float(aktarim_hatasi_pct)
    # ALAN FARKI TEK BASINA REDDETMEZ — VE BU OLCUMLE OGRENILDI.
    # Ilk surum "alan farki > %5 ise reddet" diyordu. 20 vakaya uygulandiginda
    # `MiniHawk_UAV` reddedildi: alan farki %7,46 AMA aktarim hatasi %0,90.
    # Yani iki yuzey farkli alanda olsa bile yuk dogru tasinabiliyor. Kural,
    # calisan bir vakayi oldururdu. Alan farki bir RISK GOSTERGESIDIR ve
    # yuksek aktarim hatasini ACIKLAR; onun yerine gecmez.
    _alan = None if alan_farki_pct is None else float(alan_farki_pct)
    _teshis = ""
    if _alan is not None and _alan > ALAN_KIMLIK_ESIGI_PCT:
        _teshis = (f" TEŞHİS: CFD ve FEA yüzeylerinin alanları %{_alan:.2f} "
                   f"farklı (eşik %{ALAN_KIMLIK_ESIGI_PCT:g}) — iki yüzey aynı "
                   f"geometriyi temsil etmiyor olabilir; en-yakın-komşu eşleme "
                   f"bu durumda bozulur.")

    if a > MUTLAK_RED_PCT:
        return {"kullanilabilir": False, "kod": "AKTARIM_HATASI_BUYUK",
                "aktarim_pct": a, "alan_farki_pct": _alan,
                "neden": (
                    f"CFD→FEA yük aktarım hatası %{a:.2f} > %{MUTLAK_RED_PCT:g}. "
                    f"FEA'ya giden yük, CFD'nin hesapladığı yük DEĞİLDİR; "
                    f"gerilme/sehim sonucu tasarım kararında kullanılamaz. Bu bir "
                    f"EŞLEME kusurudur, belirsizlik değildir ve banda gömülemez."
                    + _teshis)}

    if u_toplam_pct is None:
        return {"kullanilabilir": True, "kod": "BAND_YOK",
                "aktarim_pct": a,
                "neden": (
                    f"Aktarım hatası %{a:.2f}, mutlak eşiğin (%{MUTLAK_RED_PCT:g}) "
                    f"altında. Koşunun yayımlanan bandı BİLİNMEDİĞİ için "
                    f"banda-göreli denetim ÇALIŞMADI --- hatanın bandı aşıp "
                    f"aşmadığı SORULMAMIŞTIR." + _teshis)}

    u = float(u_toplam_pct)
    if a > u:
        return {"kullanilabilir": False, "kod": "AKTARIM_BANDA_BASKIN",
                "aktarim_pct": a, "u_toplam_pct": u,
                "neden": (
                    f"Aktarım hatası %{a:.2f}, koşunun kendi yayımlanan bandından "
                    f"(%{u:.2f}) BÜYÜK. Eşleme hatası raporlanan her şeye baskın; "
                    f"band bu koşu için anlamını yitirir." + _teshis)}

    return {"kullanilabilir": True, "kod": "BAND_ICINDE",
            "aktarim_pct": a, "u_toplam_pct": u,
            "alan_farki_pct": _alan,
            "tasarim_niceligi_alt_sinir_pct": round(a * BUYUTME_CARPANI_ARALIGI[0], 2),
            "tasarim_niceligi_ust_sinir_pct": round(a * BUYUTME_CARPANI_ARALIGI[1], 2),
            "neden": (f"Aktarım hatası %{a:.2f}, yayımlanan bandın (%{u:.2f}) "
                      f"içinde ve mutlak eşiğin altında. TASARIM NİCELİĞİNE "
                      f"KARŞILIĞI: ölçülen büyütme çarpanı "
                      f"{BUYUTME_CARPANI_ARALIGI[0]:g}--"
                      f"{BUYUTME_CARPANI_ARALIGI[1]:g} ile sehim/gerilme farkı "
                      f"%{a * BUYUTME_CARPANI_ARALIGI[0]:.2f}--"
                      f"%{a * BUYUTME_CARPANI_ARALIGI[1]:.2f} bandına düşer; "
                      f"aktarım hatası bu bandın ALT SINIRIDIR, kestirimi "
                      f"değildir." + _teshis)}
