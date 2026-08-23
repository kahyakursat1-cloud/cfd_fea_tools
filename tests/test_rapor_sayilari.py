"""Raporun sayıları KANITLA tutarlı mı — tek kaynak kuralı.

HAKEM İNCELEMESİ BULDU: model-form hücre sayısı raporun dört ayrı yerinde elle
yazılıydı ve birbirini tutmuyordu (2/7, 3/7, 1/4). Dahası taban da yanlıştı —
`attached_2d` rejimi eklendiğinde toplam yediden sekize çıkmış ama hiçbir metin
güncellenmemişti.

Bu, raporun kendi savunduğu ilkeye aykırıdır ve tam olarak avladığı kusur
sınıfıdır: sabit metin, değişen veri. Metni koddan üretmek en temizi olurdu ama
rapor LaTeX ve elle yazılıyor; o yüzden kural TESTLE bağlanır — `.tex` içindeki
her hücre-sayısı ifadesi `model_form_bandi.json`'daki özetle uyuşmalı.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

TEX = KOK / "docs" / "teknik_rapor.tex"
KANIT = KOK / "model_form_bandi.json"


@pytest.fixture(scope="module")
def ozet():
    if not KANIT.exists():
        pytest.skip("model_form_bandi.json yok (python experiments/model_form_bandi.py)")
    d = json.loads(KANIT.read_text(encoding="utf-8"))
    if "ozet" not in d:
        pytest.skip("kanıt eski sürüm — özet alanı yok")
    return d["ozet"]


@pytest.fixture(scope="module")
def tex():
    if not TEX.exists():
        pytest.skip("teknik_rapor.tex yok")
    return TEX.read_text(encoding="utf-8")


def test_ozet_kendi_icinde_TUTARLI(ozet):
    """Çapalı + öncül = toplam. Tutmuyorsa bir hücre iki kez ya da hiç
    sayılmıştır ve rapordaki her tekrar o hatayı taşır."""
    assert ozet["tutarli"], ozet
    assert ozet["capali"] + ozet["oncul"] == ozet["toplam_hucre"]
    assert ozet["olcum"] + ozet["ust_sinir"] == ozet["capali"]


def test_olcum_ve_UST_SINIR_ayri_sayiliyor(ozet):
    """İkisi aynı şey değildir: üst sınır, model hatasının GÖRÜLEMEDİĞİ
    hücredir ve muhafazakâr yönde alınır. Tek sayıda toplamak, ölçülmemiş
    bir kesinlik yayımlamaktır."""
    assert set(ozet["olcum_hucreleri"]) & set(ozet["ust_sinir_hucreleri"]) == set()
    assert sorted(ozet["olcum_hucreleri"] + ozet["ust_sinir_hucreleri"]) \
        == ozet["capali_hucreler"]


def test_raporda_ESKI_taban_sayisi_gecmiyor(tex, ozet):
    """`attached_2d` eklendiğinde toplam 7'den 8'e çıktı; 'yedi hücre' diyen
    her cümle artık yanlıştır."""
    n = ozet["toplam_hucre"]
    yanlis = [k for k in ("yedi hücre", "yedi hücresinden", "dört hücresinden")
              if k in tex]
    assert not yanlis, (f"model-form tablosu {n} hücreli ama raporda hâlâ "
                        f"eski taban geçiyor: {yanlis}")


def test_raporda_capali_orani_KANITLA_uyusuyor(tex, ozet):
    """`N/M hücre çapalı` biçimindeki her ifade özetle aynı sayıları vermeli."""
    bulunan = re.findall(r"(\d+)\s*/\s*(\d+)\s*hücre çapalı", tex)
    assert bulunan, "rapor çapalı-oran ifadesi taşımıyor (bölüm kaldırıldı mı?)"
    for capali, toplam in bulunan:
        assert int(toplam) == ozet["toplam_hucre"], \
            f"raporda /{toplam} yazıyor, kanıtta {ozet['toplam_hucre']}"
        assert int(capali) == ozet["capali"], \
            f"raporda {capali} çapalı yazıyor, kanıtta {ozet['capali']}"


def test_sozel_tekrarlar_da_AYNI_sayiyi_soyluyor(tex, ozet):
    """Sayı rakamla değil yazıyla geçtiğinde de aynı olmalı; hakem çelişkiyi
    tam olarak bu tekrarlarda buldu."""
    # Sayi-kelime tablosu TEK KAYNAKTAN (_YAZI). Yerel kopyada 6 eksikti ve
    # capali 5'ten 6'ya cikinca test KeyError ile patladi — yani tabloyu
    # eksik tutmak, denetimi sessizce cikarilamaz hale getiriyordu.
    top, cap = _YAZI[ozet["toplam_hucre"]], _YAZI[ozet["capali"]]
    kaliplar = re.findall(r"(\w+) hücrenin \\textbf\{(\w+)\}ü", tex)
    for bulunan_top, bulunan_cap in kaliplar:
        assert bulunan_top == top, f"'{bulunan_top} hücrenin' — beklenen '{top}'"
        assert bulunan_cap == cap, f"'{bulunan_cap}ü' — beklenen '{cap}'"


_YAZI = {0: "sıfır", 1: "bir", 2: "iki", 3: "üç", 4: "dört", 5: "beş",
         6: "altı", 7: "yedi", 8: "sekiz"}


def _tr_kucult(s: str) -> str:
    """Turkce-dogru kucult. str.lower() 'İ'yi 'i'+birlesen-nokta yapar, 'iki'
    ile esitlenmez. Rapor sayiyi VURGU icin buyuk yazabilir ('kalan İKİ
    hücre'); test bicimlemeye degil SAYIYA baglanmali."""
    return s.replace("İ", "i").replace("I", "ı").lower()


def test_olcum_ve_ust_sinir_AYRIMI_da_tutarli(tex, ozet):
    """HAKEM YİNE BULDU: "beşi çapa taşır; üçü ölçüm, biri üst sınır" — toplamı
    DÖRT ediyordu.

    Önceki testler yalnız `N/M hücre çapalı` ve `N hücrenin M'i` kalıplarını
    denetliyordu; ölçüm/üst-sınır AYRIMINI hiç okumuyorlardı. Dipnot ise
    "rapordaki her tekrarı testle bağlıdır" diyordu --- yani rapor kendi
    denetim iddiasını aşan bir alan taşıyordu. Bu test o alanı kapatır.
    """
    # SAYI KELIMESI + TURKCE EK. Ek serbest birakilir ('üçü', 'ikisi'), ama
    # sayinin KENDISI listeden gelmek zorunda — genel \w+ kalibi "kalan is
    # hucre" gibi ilgisiz ifadeleri de yakaliyordu.
    _s = "|".join(_YAZI.values())
    kaliplar = re.findall(
        rf"({_s})\w*\s+ölçüm[,+]\s*(?:\\textbf\{{)?({_s})\w*\s+üst\s*\n?\s*sınır",
        tex)
    kaliplar += re.findall(r"(\d+) ölçüm \+ (\d+) üst sınır", tex)
    assert kaliplar, "rapor ölçüm/üst-sınır ayrımını hiç yazmıyor mu?"
    for a, b in kaliplar:
        _a = str(ozet["olcum"]) if a.isdigit() else _YAZI[ozet["olcum"]]
        _b = str(ozet["ust_sinir"]) if b.isdigit() else _YAZI[ozet["ust_sinir"]]
        assert a == _a, f"'{a} ölçüm' — beklenen '{_a}'"
        assert b == _b, f"'{b} üst sınır' — beklenen '{_b}'"


def test_test_sayilari_AYNI_KOSUDA_olculdu(tex):
    """HAKEM SORDU: "coverage açıkken neden 23 test daha az?"

    Ölçüldü: fark YOKTU. İki sayı farklı zamanlarda ölçülüp yan yana
    konmuştu ve aradaki boşluk gerçek bir olgu gibi görünüyordu --- birlikte
    okunan iki sayı birlikte ölçülmelidir. Betik artık ikisini de tek çağrıda
    ölçüyor; bu test raporun ikisini de o ölçümden aldığını bağlar.
    """
    olcum_dosyasi = KOK / "rapor_sayilari.json"
    if not olcum_dosyasi.exists():
        pytest.skip("rapor_sayilari.json yok")
    d = json.loads(olcum_dosyasi.read_text(encoding="utf-8"))
    if d.get("gecen_test_cov") is None:
        pytest.skip("test sayıları ölçülmedi (python experiments/rapor_sayilari.py --test)")
    # KIRMIZI SÜİTTEN ALINAN SAYI RAPORA GİRMEZ. Ölçüm dosyası düşen test
    # sayısını da taşır; hükmü burada veriyoruz. Üretici sayıyı saklamıyor
    # (saklamak kilitlenme üretiyordu), yalnız kırmızılığı görünür kılıyor.
    assert d.get("suit_yesil", True), (
        f"süit kırmızı ({d.get('dusen_test')} düşen); rapordaki test sayısı "
        "bu ölçümle doğrulanamaz. Önce düşen testleri düzeltin.")
    for anahtar in ("gecen_test", "gecen_test_cov"):
        beklenen = f"{d[anahtar]:,}".replace(",", ".")
        assert beklenen in tex, f"{anahtar}={d[anahtar]} raporda geçmiyor"
    # Fark varsa aciklanmali; yoksa "ayni kosuda olculdu" ibaresi durmali.
    if d["gecen_test"] == d["gecen_test_cov"]:
        assert "aynı koşuda" in tex, \
            "iki sayı eşit ama raporda birlikte ölçüldükleri yazmıyor"


def test_ozet_kendi_icinde_TOPLANIYOR(ozet):
    """ölçüm + üst sınır = çapalı; çapalı + öncül = toplam. Kanıtın kendisi
    tutarsızsa raporu ona bağlamanın anlamı kalmaz."""
    assert ozet["olcum"] + ozet["ust_sinir"] == ozet["capali"]
    assert ozet["capali"] + ozet["oncul"] == ozet["toplam_hucre"]


def test_yol_haritasindaki_KALAN_hucre_sayisi_dogru(tex, ozet):
    """v1.3 satırı "kalan beş hücre" diyordu; 8-5=3 olmuştu."""
    kalan = ozet["toplam_hucre"] - ozet["capali"]
    # "kalan is hucre x cekirdek x RAM" gibi ifadeler sayi DEGILDIR; kalip
    # yalniz sayi kelimelerini ve rakamlari kabul eder.
    _s = "|".join(_YAZI.values())
    bulunan = re.findall(rf"kalan\s+({_s}|\d+)\s+hücre", tex, re.IGNORECASE)
    assert bulunan, "yol haritası kalan-hücre ifadesi taşımıyor"
    for b in bulunan:
        assert _tr_kucult(b) in (_YAZI[kalan], str(kalan)), \
            f"'kalan {b} hücre' — beklenen '{_YAZI[kalan]}' ({kalan})"


def test_ozet_cumlesi_UCUNU_de_ayirt_ediyor(ozet):
    c = ozet["cumle"]
    assert "ölçüm" in c and "üst sınır" in c and "öncül" in c
    assert str(ozet["toplam_hucre"]) in c


# ── Raporun KENDİ HAKKINDA yazdığı sayılar ──────────────────────────────────

SAYILAR = KOK / "rapor_sayilari.json"


@pytest.fixture(scope="module")
def olcum():
    if not SAYILAR.exists():
        pytest.skip("rapor_sayilari.json yok (python experiments/rapor_sayilari.py)")
    return json.loads(SAYILAR.read_text(encoding="utf-8"))


def _satir_sayilari(tex: str) -> list[int]:
    """Raporda geçen 'kod satırı' değerlerinin tümü (nokta binlik ayracı)."""
    ham = re.findall(r"(\d{2}\.\d{3}) satır Python", tex)
    ham += re.findall(r"analysis/\}\) & (\d{2}\.\d{3}) &", tex)
    return [int(x.replace(".", "")) for x in ham]


def test_kod_satiri_raporda_TEK_deger(tex):
    """Hakem bulgusu: kapakta 31.322, kalite tablosunda 31.307 yazıyordu.
    On beş satırlık fark önemsiz; AYRIŞMANIN KENDİSİ önemli, çünkü rapor tam
    da bunu avlayan bir sistemi anlatıyor."""
    d = _satir_sayilari(tex)
    assert len(d) >= 2, f"kod satırı ifadesi bulunamadı ({d})"
    assert len(set(d)) == 1, f"rapor farklı satır sayıları söylüyor: {sorted(set(d))}"


def test_kod_satiri_OLCUMDEN_sapmiyor(tex, olcum):
    """Tolerans var (rapor her commit'te derlenmiyor) ama sapma büyürse söyle."""
    d = _satir_sayilari(tex)
    gercek = olcum["kod_satiri"]
    sapma = abs(d[0] - gercek) / gercek * 100
    assert sapma < 3.0, (f"rapor {d[0]} satır diyor, ölçüm {gercek} "
                         f"(%{sapma:.1f} sapma) — `python experiments/"
                         "rapor_sayilari.py` ile güncelleyin")


def test_test_dosyasi_sayisi_OLCUMLE_uyusuyor(tex, olcum):
    m = re.search(r"Test dosyası & (\d+) &", tex)
    assert m, "kalite tablosunda test dosyası satırı yok"
    assert int(m.group(1)) == olcum["test_dosyasi"], (
        f"rapor {m.group(1)}, ölçüm {olcum['test_dosyasi']} test dosyası")


def test_ELLE_yazilmis_bolum_atfi_KALMADI(tex):
    r"""Bölüm numaraları eklendikçe kayar; elle yazılan atıf sessizce yanlışa
    döner. Hakem incelemesinde beş atıftan DÖRDÜ yanlıştı: \S7 topoloji yerine
    ASME'yi, \S6B mentor yerine zarfı, \S2--\S5 yanlış aralığı, \S2.4 yanlış
    alt bölümü gösteriyordu. Atıflar artık \ref ile bağlı ve derleyici
    çözülmemiş atıfı kendisi söyler."""
    elle = re.findall(r"\\S\s*\d", tex)
    assert not elle, f"elle yazılmış bölüm atfı: {elle} — \\ref kullanın"


def _sayilar(s: str) -> set:
    r"""Metindeki AYIRT EDICI sayilar. Tek/cift haneli tam sayilar (5, 15)
    ambiguous — atlanir; ondalikli ya da 3+ haneli olanlar alinir. LaTeX
    aralik makrosu ve ondalik ayraci normalize edilir: rapor '4,68\,M' yazar,
    kanit '4,68 M' — denetim BICIMLEMEYE degil SAYIYA bakmali."""
    t = s.replace(r"\,", "").replace(r"\%", "%").replace(",", ".")
    return set(re.findall(r"\d+\.\d+|\d{3,}", t))


def test_ACIK_hucrelerin_gerekcesi_kanittan_geliyor(tex):
    """Sayı kapısı gerekçeleri OKUMUYOR; bu yüzden kanıta dayanmayan bir
    gerekçe raporda serbestçe durabiliyordu (2026-08-20: küt hücre için
    'küre izi kararsız', taşıma hücresi için 'iki çapa da duvar-çözümlü'
    yazılmıştı — ikisi de kanıt dosyasında YOK).

    KURAL: her açık hücrenin rapordaki gerekçesi, kanıttaki gerekçenin
    ÖLÇÜLEN sayılarına dayanmalı. Tümünü istemek aşırı katı olur (kanıt
    metni yan sayılar da taşır); en az ikisi aranır.
    """
    if not KANIT.exists():
        pytest.skip("model_form_bandi.json yok")
    d = json.loads(KANIT.read_text(encoding="utf-8"))
    acik = d.get("oncul_kalan_hucreler") or []
    if not acik:
        pytest.skip("açık hücre kalmamış")
    rapor = _sayilar(tex)
    for h in acik:
        kanit = _sayilar(h.get("kapanmasi_icin", ""))
        ortak = kanit & rapor
        assert len(ortak) >= 2, (
            f"{h['rejim']}.{h['duvar']} gerekçesi kanıttan gelmiyor: "
            f"kanıttaki ölçülen sayılar {sorted(kanit)}, raporda bulunan "
            f"{sorted(ortak)}")


def test_OLCER_sayilari_rapora_bagli(tex):
    """KURAL: raporun ölçer tablosu CANLI ölçerlerle uyuşmalı.

    ÖLÇÜLDÜ (2026-08-21, raporun baştan sona okunması): bayatlayan her sayı
    BAĞLANMAMIŞ olandı. Hücre sayıları `test_ozet_kendi_icinde_TUTARLI` ile
    bağlıydı ve temiz kaldı; bağlanmamış olanlar üç yerde birden şaştı:
      * arka uç sayacı metinde 3, tabloda 9, canlı ölçerde 1 — rapor kendi
        içinde de çelişiyordu;
      * bellek kapısı "katsayı henüz ölçülmemiştir" diyordu, oysa ölçülmüştü;
      * kapanış kutusu "üç hücre öncül" derken aynı paragraf "ikisi" diyordu.
    """
    import subprocess
    import sys

    r = subprocess.run([sys.executable, str(KOK / "arka_uc_sayaci.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(KOK))
    m = re.search(r"atlayan çağrı:\s*(\d+)\s*satır", r.stdout or "")
    if not m:
        pytest.skip("arka_uc_sayaci çıktısı okunamadı")
    canli = int(m.group(1))

    # Rapor AYNI sayiyi kac farkli deger olarak yaziyor?
    yazilanlar = {int(x) for x in re.findall(r"atlayan çağrı 36'dan \textbf\{(\d+)\}", tex)}
    yazilanlar |= {int(x) for x in re.findall(r"Sayaç 36'dan \textbf\{(\d+)\}", tex)}
    yazilanlar |= {int(x) for x in
                   re.findall(r"ortak katmanı atlayan çağrı & (\d+) \(36", tex)}
    assert yazilanlar, "rapor arka uç sayacını hiç yazmıyor mu?"
    assert len(yazilanlar) == 1, (
        f"rapor AYNI sayacı farklı değerlerle yazıyor: {sorted(yazilanlar)}")
    assert yazilanlar == {canli}, (
        f"raporda {sorted(yazilanlar)}, canlı ölçerde {canli}")


def test_rapor_OLCULMEDI_demeyen_seyi_olculmemis_saymiyor(tex):
    """Bellek katsayısı ÖLÇÜLDÜ; rapor artık aksini söylememeli.

    Eski metin "hücre başına bellek katsayısı henüz ölçülmemiştir" diyordu ve
    hemen altındaki kutu ölçüldüğünü anlatıyordu — aynı sayfada birbirini
    çürüten iki cümle.
    """
    assert "bellek katsayısı henüz ölçülmemiştir" not in tex
    # ve olculen katsayilar rapora YAZILI olmali
    assert "1{,}656" in tex, "meshleme katsayısı raporda yok"
    assert "0{,}779" in tex, "çözüm katsayısı raporda yok"


def test_rapor_YPLUS_KAPSAMI_kanit_dosyasindan_sapmiyor(tex):
    """Kapsam tablosu elle yazılamaz — kanıt dosyasıyla birebir tutmalı.

    Bu deponun tekrar tekrar ürettiği kusur: sabit metin, değişen veri.
    Kapsam yüzdeleri çapa koşuları yenilendiğinde değişir; tablo değişmezse
    rapor sessizce eskir.
    """
    import json
    p = KOK / "model_form_bandi.json"
    if not p.exists():
        pytest.skip("model_form_bandi.json üretilmemiş")
    kayit = json.loads(p.read_text(encoding="utf-8"))
    olculen = [c for c in kayit["capalar"] if c.get("yplus_kapsam_pct") is not None]
    assert olculen, "kanıt dosyası hiç kapsam taşımıyor"

    for c in olculen:
        # LaTeX ondaligi virgulle yaziyor: \%65{,}8
        beklenen = rf"\%{c['yplus_kapsam_pct']:.1f}".replace(".", "{,}")
        assert beklenen in tex, (
            f"{c['capa']} kapsamı ({beklenen}) raporda yok — kanıt yenilendi, "
            f"tablo eskidi")

    # OLCUMUN KENDI KAPSAMI: "3 / 12" ikilisi raporda GECMELI. Tek sayiyi
    # aramak kacamak olurdu — 12 rapordaki baska bir sayiyla eslesirdi.
    ozet = kayit["yplus_kapsam_ozeti"]
    assert re.search(rf"{ozet['toplam_capa']}\s*\n?\s*çapanın "
                     rf"{ozet['olculen_capa']}'ünde", tex), (
        f"ölçümün kendi kapsamı ({ozet['olculen_capa']}/{ozet['toplam_capa']}) "
        f"raporda yazılı değil")
    # ESIK DAYATILMIYOR beyani rapordan sessizce dusmemeli
    assert r"eşiği bir \emph{öneridir}" in tex


def test_rapor_RHO_kanit_dosyasindan_sapmiyor(tex):
    """ρ ve bileşenleri elle yazılamaz — kanıt dosyasıyla birebir tutmalı."""
    import json
    p = KOK / "eslesik_korelasyon.json"
    if not p.exists():
        pytest.skip("eslesik_korelasyon.json üretilmemiş")
    h = json.loads(p.read_text(encoding="utf-8"))["hucreler"]
    olculen = {k: v for k, v in h.items() if v.get("rho") is not None}
    assert olculen, "kanıt dosyası hiç ρ taşımıyor"
    for ad, v in olculen.items():
        for sayi in (v["rho"], v["ortak_bias_pct"], v["sacilma_pct"]):
            latex = f"{abs(sayi):.2f}".replace(".", "{,}")
            assert latex in tex, f"{ad}: {latex} raporda yok — kanıt yenilendi, metin eskidi"
    # BAND GENISLETILMEDI karari rapordan sessizce dusmemeli
    assert "band genişletilmedi" in tex.lower()


def test_rapor_ORTAM_damgasiz_kanit_sayisi_CANLI_olcumle_ayni(tex):
    """Sayı elle yazılıydı ve 22 bayattı (68 ≠ 90) — hem de raporun kendi
    yeniden-üretilebilirlik bölümünde. Tam olarak bu deponun avladığı kusur.
    """
    # SAYIM URETICININ KENDI OLCUTUYLE: kanit.py `_ortam` alanina bakar ve
    # `ortam.fark(...)["ayni"] is None` olanlari damgasiz sayar. Burada baska
    # bir olcut kurmak (ornegin manifest kaydinda "ortam" anahtari aramak)
    # iki kaynak yaratir ve olculen sey ayrisir — ilk yazimda tam bu oldu
    # (107 cikti, cunku manifest kaydinda oyle bir anahtar YOK).
    import kanit
    import ortam as _o
    bugun = _o.parmak_izi()
    damgasiz = sum(
        1 for k in kanit.manifest() if k["sinif"] == "kanit"
        and _o.fark(json.loads((KOK / k["dosya"]).read_text(encoding="utf-8-sig"))
                    .get("_ortam"), bugun)["ayni"] is None)
    m = re.search(r"kanit\.py -\{\}-ortam\} bugün (\d+) kanıtın", tex)
    assert m, "rapor ortam kapsamını hiç yazmıyor mu?"
    assert int(m.group(1)) == damgasiz, (
        f"raporda {m.group(1)}, canlı ölçümde {damgasiz} damgasız kanıt")


def test_rapor_CAPA_cozucu_surumunu_kanittan_yaziyor(tex):
    import json
    p = KOK / "kosu_ortam_kapsami.json"
    if not p.exists():
        pytest.skip("kosu_ortam_kapsami.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    _YAZI = {1: "bir", 2: "iki", 3: "üç", 4: "dört", 5: "beş"}
    assert f"{_YAZI[d['capa_cozucu_tam']]} başarılı çapanın" in tex.lower() \
        or f"{_YAZI[d['capa_cozucu_tam']]} başarılı çapanın" in tex, \
        f"raporda çapa sayısı ({d['capa_cozucu_tam']}) kanıtla uyuşmuyor"


def test_rapor_FSI_AKTARIM_tablosu_kanittan_sapmiyor(tex):
    """Aktarım artıkları elle yazılamaz — koşular yenilenince değişir."""
    import json
    p = KOK / "fsi_korunum.json"
    if not p.exists():
        pytest.skip("fsi_korunum.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    tabloda = re.findall(
        r"\\texttt\{([A-Za-z0-9_\\]+)\} & [\d.]+ & [\d.]+ & "
        r"\\%(\d+)\{,\}(\d+) & \\%(\d+)\{,\}(\d+)", tex)
    assert tabloda, "rapor FSI aktarım tablosunu taşımıyor"
    kayit = {v["vaka"]: v for v in d["vakalar"]}
    for ad, ai, af, bi, bf in tabloda:
        vaka = ad.replace("\\_", "_")
        assert vaka in kayit, f"{vaka} kanıtta yok"
        assert float(f"{ai}.{af}") == pytest.approx(
            kayit[vaka]["aktarim_hatasi_pct"], abs=0.06), vaka
        assert float(f"{bi}.{bf}") == pytest.approx(
            kayit[vaka]["alan_farki_pct"], abs=0.06), vaka
    # SIFIR-YUK dersi rapordan sessizce dusmemeli
    assert "kusursuz korunum" in tex


def test_rapor_FSI_TAHRIK_bandi_kanittan_sapmiyor(tex):
    """Tahrik tablosu koşular yenilenince değişir; elle yazılamaz."""
    import json
    p = KOK / "fsi_tahrik_bandi.json"
    if not p.exists():
        pytest.skip("fsi_tahrik_bandi.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    kayit = {k["kosu"]: k for k in d["kosular"]}
    satir = re.findall(
        r"\\texttt\{([A-Za-z0-9_\\]+)\}\s*& (\d+) & (\d+)\{,\}(\d+)\\,mm\s*& "
        r"(?:\\textbf\{)?\\%(\d+)\{,\}(\d+)", tex)
    assert satir, "rapor FSI tahrik tablosunu taşımıyor"
    for ad, v, si, sf, oi, of in satir:
        k = kayit[ad.replace("\\_", "_")]
        assert int(v) == round(k["hiz_m_s"])
        assert float(f"{si}.{sf}") == pytest.approx(k["sehim_mm"], abs=0.02)
        assert float(f"{oi}.{of}") == pytest.approx(k["sehim_aciklik_pct"], abs=0.02)
    # BANDIN IKI UCU da yazili olmali
    assert str(int(d["tahrik_tabani_pct"])) in tex and r"\%5" in tex
    # HUKUM: yakinsadi ama sebebi fizik degil
    assert "sebebi fizik değil" in tex


def test_rapor_HUKUM_TAZELIGI_kanittan_sapmiyor(tex):
    """Bayat/toplam oranı koşular yenilendikçe değişir; elle yazılamaz."""
    import json
    p = KOK / "hukum_tazeligi.json"
    if not p.exists():
        pytest.skip("hukum_tazeligi.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    m = re.search(r"(\d+) kayıtlı koşunun (\d+)'inde", tex)
    assert m, "rapor hüküm-tazeliği oranını yazmıyor"
    assert int(m.group(1)) == d["toplam_kosu"], \
        f"raporda {m.group(1)} koşu, kanıtta {d['toplam_kosu']}"
    assert int(m.group(2)) == d["bayat"], \
        f"raporda {m.group(2)} bayat, kanıtta {d['bayat']}"
    # YON rapordan sessizce dusmemeli — gevseyen bayatlik tehlikeli olandir
    assert "daha gevşek" in tex


def test_rapor_KOSULLAMA_butcesi_kanittan_sapmiyor(tex):
    """Bütçe tablosu σ_iç'e karesel bağlı; çapa eklendikçe değişir."""
    import json
    p = KOK / "model_form_kosullama.json"
    if not p.exists():
        pytest.skip("model_form_kosullama.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    satir = re.findall(r"(\d+) puan & ([\d.]+) & ([\d.]+) & ([\d.]+) ", tex)
    assert satir, "rapor koşullama bütçe tablosunu taşımıyor"
    kayit = {int(x["ayirt_edilecek_fark_puan"]): x for x in d["butce"]["fark_basina"]}
    for fark, hb, mt, bd in satir:
        k = kayit[int(fark)]
        assert int(hb) == k["hucre_basina_capa"], fark
        assert int(mt.replace(".", "")) == k["toplam_MEVCUT_TABLO"], fark
        assert int(bd.replace(".", "")) == k["toplam_BIR_DEGISKEN_DAHA"], fark
    # VERI-GUDUMLU orani rapordan sessizce dusmemeli
    assert f"{d['veri_gudumlu_hucre']}/{d['mevcut_hucre']}" in tex


def test_rapor_ORTOTROPIK_capa_kanittan_sapmiyor(tex):
    """Altıncı FEA çapasının sayıları elle yazılamaz."""
    import json
    p = KOK / "fea_validation_ortotropik.json"
    if not p.exists():
        pytest.skip("fea_validation_ortotropik.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    hata = f"{d['fem']['delta_hata_pct']:.1f}".replace(".", "{,}")
    assert rf"\%{hata}" in tex or rf"\textbf{{\%{hata}}}" in tex, \
        f"ortotropik hata (%{hata}) raporda yok"
    kat = f"{d['ayirt_edicilik']['kat']:.1f}".replace(".", "{,}")
    assert kat in tex, f"ayırt edicilik katı ({kat}) raporda yok"
    # KAPSAM DISI kalanlar rapordan sessizce dusmemeli
    for terim in ("temas", "plastisite", "NLGEOM", "delaminasyon"):
        assert terim in tex, f"kapsam-dışı terim raporda yok: {terim}"


def test_rapor_MMA_kiyasi_kanittan_sapmiyor(tex):
    """OC/MMA sayıları koşu yenilendiğinde değişir; elle yazılamaz."""
    import json
    p = KOK / "mma_vs_oc.json"
    if not p.exists():
        pytest.skip("mma_vs_oc.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    for kural in ("oc", "mma"):
        son = f"{d[kural]['son_obj']:.4f}".replace(".", "{,}")
        assert son in tex, f"{kural} son amacı ({son}) raporda yok"
        bosa = f"{d[kural]['bosa_giden_hareket_pct']:.1f}".replace(".", "{,}")
        assert bosa in tex, f"{kural} boşa giden hareket (%{bosa}) raporda yok"
    # ASIL AYRIM rapordan sessizce dusmemeli
    assert "savunulabilir" in tex.lower()
    assert "limit çevrimi" in tex.lower() or r"limit \emph{çevriminde}" in tex


def test_rapor_SUBKRITIK_sapmalari_kanittan(tex):
    """Silindir sapmaları koda ve rapora ayrı ayrı yazılı; ayrışmamalı."""
    import sys
    sys.path.insert(0, str(KOK))
    from validity_envelope import SUBKRITIK_OLCUM
    for v in SUBKRITIK_OLCUM.values():
        cd = f"{abs(v['Cd_pct']):.2f}".replace(".", "{,}")
        assert cd in tex, f"Cd sapması ({cd}) raporda yok"
    # BAND GENISLETILMEDI karari rapordan sessizce dusmemeli
    assert "genişletilmedi" in tex
