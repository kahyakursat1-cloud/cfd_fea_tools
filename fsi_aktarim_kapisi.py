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

KAPI BİR ÇÖZÜM DEĞİL, BİR DÜRÜSTLÜK KATMANIDIR: %56'lık aktarım hatası bu
kapıyla KAYBOLMAZ, yalnız o koşunun tasarım kararına girmesi engellenir.

AMA ÇÖZÜMÜN NE OLDUĞU DEĞİŞTİ (2026-08-28, ölçümden). Bu satır bir turdur
``mortar/RBF gerekir'' diyordu. Baryentrik ağırlıklar doğrusal alanları
birebir ürettiği için birinci moment bir KİMLİKLE korunur:

    T_düğüm - T_cfd  ==  Σ_f dF_f ⊗ δ_f ,   δ_f = Σ_k w_k x_k - x_cfd,f

24/24 vakada ≤1e-10 tuttu ve eşleme payı 19 vakada %1'in altında, en kötü
%24,10 (alıcı yüzeyi ON İKİ üçgen olan vaka). Yani şema değiştirmek
gerekmiyor; alıcı yüzeyin verici yüzeyi ÇÖZMESİ yetiyor. Açık kalan iş
mortar değil, aktarım yüzeyi çözünürlüğünün bir kural hâline getirilmesi.
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
                  u_toplam_pct: float | None = None,
                  moment_artigi_pct: float | None = None,
                  is_artigi_pct: float | None = None,
                  esleme_is_payi_pct: float | None = None) -> dict:
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

    # HAKIM ARTIK: UC METRIGIN EN BUYUGU.
    #
    # KAPI ATIL KALMISTI. Korunumlu semaya gecince `aktarim_hatasi_pct`
    # KIMLIK GEREGI sifir oldu (agirliklar 1'e toplanir) --- 24/24 vakada
    # tam 0,0000. Kapi o sayiya bakiyordu, yani artik HER kosuyu geciriyordu:
    # savunma duruyor, uretim yolu ona bos bir sayi besliyor. Bu deponun
    # tekrarlayan kusuru ve bu kez KAPININ KENDISINDE.
    #
    # Gercek artik moment ve ISE tasindi (en kotu %13,54 ve %102,64) ve
    # oraya bakan yoktu. Kapi artik UCUNUN EN BUYUGUNU yonetici alir ---
    # muhafazakar yon budur; en kucugu almak kapiyi yine susturur.
    _bilesenler = {"kuvvet": float(aktarim_hatasi_pct)}
    if moment_artigi_pct is not None:
        _bilesenler["moment"] = float(moment_artigi_pct)
    # IS BILESENI OLARAK **ESLEME PAYI** ALINIR, TOPLAM ARTIK DEGIL.
    #
    # DUZELTME (2026-08-28), OLCUMDEN. `arayuz_isi_hatasi` iki SEMAYI
    # kiyaslar: dugum momenti (URETIMDEKI korunumlu sema) ve yuz momenti
    # (TERK EDILMIS tutarli sema, FEA yuzunde YENIDEN INTEGRE edilmis).
    # Ayni vakada terk edilmis semanin toplam kuvvetinin ISARETI bile ters
    # cikabiliyor. Yani o sayiyi yonetici artik yapmak, URETIMI terk
    # edilmis semanin hatasiyla suclamaktir.
    #
    # Dogru referans CFD tarafidir ve orada bir KIMLIK vardir:
    #     T_dugum - T_cfd == sum_f dF_f (x) delta_f
    # 24/24 vakada <=1e-10 tuttu. Ayrisim (fsi_korunum.json):
    #     gripen_AB_Right  toplam %76,72  ESLEME %0,0023
    #     _fsi_esnek       toplam %102,64 ESLEME %24,10
    # Toplama bakan bir kapi gripen'i REDDEDERDI --- oysa oradaki eslemenin
    # hatasi on binde iki. _fsi_esnek ise gercekten reddi hak ediyor.
    if esleme_is_payi_pct is not None:
        _bilesenler["esleme_isi"] = float(esleme_is_payi_pct)
    elif is_artigi_pct is not None:
        # GERI DUSUS: ayrisim yoksa toplam kullanilir ama bu MUHAFAZAKAR
        # olmaktan cok FAZLA SIKIdir ve hukumde acikca soylenir.
        _bilesenler["arayuz_isi_TOPLAM"] = float(is_artigi_pct)
    _hakim_ad = max(_bilesenler, key=lambda k: _bilesenler[k])
    a = _bilesenler[_hakim_ad]
    # KIMLIK UYARISI: kuvvet artigi tam sifirsa o sayi BILGI TASIMAZ.
    _kimlik = (_bilesenler["kuvvet"] < 1e-9 and len(_bilesenler) == 1)
    if _kimlik:
        return {"kullanilabilir": None, "kod": "OLCUT_ATIL",
                "aktarim_pct": 0.0, "hakim_metrik": "kuvvet",
                "neden": (
                    "Kuvvet aktarım artığı tam SIFIR --- korunumlu şemada bu "
                    "bir KİMLİKTİR (ağırlıklar 1'e toplanır), bir bulgu "
                    "değil. Tek başına bu sayıya bakan bir kapı ATILDIR ve "
                    "her koşuyu geçirir. Moment ve arayüz işi artıkları "
                    "VERİLMEDİ, dolayısıyla yük aktarımı hakkında hüküm "
                    "verilemez.")}
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
    # AYRISIM VARSA TOPLAM DA YAZILIR --- ama TESHIS olarak, HUKUM olarak
    # degil. Okur toplami gorup uretime yazmasin diye fark ACIKCA soylenir.
    if esleme_is_payi_pct is not None and is_artigi_pct is not None:
        _teshis += (
            f" AYRIŞIM: arayüz işi TOPLAM artığı %{float(is_artigi_pct):.2f}, "
            f"bunun eşleme payı %{float(esleme_is_payi_pct):.2f}. Hüküm "
            f"EŞLEME payına bakar; toplamın kalanı terk edilmiş (tutarlı) "
            f"şemanın FEA yüzünde yeniden integre etmesinden gelir ve "
            f"üretim yolunda YOKTUR.")
    elif is_artigi_pct is not None:
        _teshis += (
            f" UYARI: arayüz işi ayrışımı VERİLMEDİ, toplam artık "
            f"(%{float(is_artigi_pct):.2f}) yönetici alındı. Bu kapıyı "
            f"gereğinden SIKI yapar --- ölçülen 24 vakada toplamın en "
            f"kötüsü %102,64 iken eşleme payı %24,10 idi ve 19'unda %1'in "
            f"altındaydı. `esleme_is_payi_pct` verilirse hüküm keskinleşir.")

    if a > MUTLAK_RED_PCT:
        return {"kullanilabilir": False, "kod": "AKTARIM_HATASI_BUYUK",
                "aktarim_pct": a, "alan_farki_pct": _alan,
                "hakim_metrik": _hakim_ad, "bilesenler": _bilesenler,
                "neden": (
                    f"Yük aktarımında hâkim artık ({_hakim_ad}) %{a:.2f} > "
                    f"%{MUTLAK_RED_PCT:g}. "
                    f"FEA'ya giden yük, CFD'nin hesapladığı yük DEĞİLDİR; "
                    f"gerilme/sehim sonucu tasarım kararında kullanılamaz. Bu bir "
                    f"EŞLEME kusurudur, belirsizlik değildir ve banda gömülemez."
                    + _teshis)}

    if u_toplam_pct is None:
        return {"kullanilabilir": True, "kod": "BAND_YOK",
                "aktarim_pct": a, "hakim_metrik": _hakim_ad,
                "bilesenler": _bilesenler,
                "neden": (
                    f"Hâkim artık ({_hakim_ad}) %{a:.2f}, mutlak eşiğin "
                    f"(%{MUTLAK_RED_PCT:g}) "
                    f"altında. Koşunun yayımlanan bandı BİLİNMEDİĞİ için "
                    f"banda-göreli denetim ÇALIŞMADI --- hatanın bandı aşıp "
                    f"aşmadığı SORULMAMIŞTIR." + _teshis)}

    u = float(u_toplam_pct)
    if a > u:
        return {"kullanilabilir": False, "kod": "AKTARIM_BANDA_BASKIN",
                "aktarim_pct": a, "u_toplam_pct": u,
                "hakim_metrik": _hakim_ad, "bilesenler": _bilesenler,
                "neden": (
                    f"Hâkim artık ({_hakim_ad}) %{a:.2f}, koşunun kendi yayımlanan "
                    f"bandından "
                    f"(%{u:.2f}) BÜYÜK. Eşleme hatası raporlanan her şeye baskın; "
                    f"band bu koşu için anlamını yitirir." + _teshis)}

    return {"kullanilabilir": True, "kod": "BAND_ICINDE",
            "aktarim_pct": a, "u_toplam_pct": u,
                "hakim_metrik": _hakim_ad, "bilesenler": _bilesenler,
            "alan_farki_pct": _alan,
            "tasarim_niceligi_alt_sinir_pct": round(a * BUYUTME_CARPANI_ARALIGI[0], 2),
            "tasarim_niceligi_ust_sinir_pct": round(a * BUYUTME_CARPANI_ARALIGI[1], 2),
            "neden": (f"Hâkim artık ({_hakim_ad}) %{a:.2f}, yayımlanan bandın (%{u:.2f}) "
                      f"içinde ve mutlak eşiğin altında. TASARIM NİCELİĞİNE "
                      f"KARŞILIĞI: ölçülen büyütme çarpanı "
                      f"{BUYUTME_CARPANI_ARALIGI[0]:g}--"
                      f"{BUYUTME_CARPANI_ARALIGI[1]:g} ile sehim/gerilme farkı "
                      f"%{a * BUYUTME_CARPANI_ARALIGI[0]:.2f}--"
                      f"%{a * BUYUTME_CARPANI_ARALIGI[1]:.2f} bandına düşer; "
                      f"aktarım hatası bu bandın ALT SINIRIDIR, kestirimi "
                      f"değildir." + _teshis)}
