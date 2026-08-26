"""`lifting.wall_function` fizibilitesi — gerekçe veriyle birlikte yaşamalı.

BU DOSYA BİR KUSURDAN DOĞDU. Hücrenin kayıtlı engeli ``referans belirsizliği
(%15) baskın'' diyordu ve o cümle ELLE yazılmıştı. AR6 çapasının referansı
2026-08-19'da Ladson TM-4074 ölçümüne taşınıp `u_ref_pct` %15'ten %1,0'a
inince cümle yanlış hâle geldi ama kimse güncellemedi --- yol haritası
aylarca çürümüş bir engeli taşıdı.

İKİNCİ KUSUR ÖLÇÜMÜN KENDİSİNDEYDİ ve KOLAY yöne kayıyordu. İlk sürüm yüzey
çözünürlüğünü 0,005c varsaydı; gerçek çapaların kullandığı bant ölçülünce
(h/L: Ahmed 0,0114 … küp 0,0234) varsayımın 2--4 kat ince olduğu, yani
bütçeyi 4--16 kat şişirdiği görüldü. Şişmiş bütçe ``sığmıyor'' der --- yani
varsayım tam da işine gelen hükmü destekliyordu. Ölçüm tek değer yerine bir
EĞRİ üretecek biçimde düzeltildi.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

import lifting_wf_fizibilite as F  # noqa: E402


def test_ESKI_gerekce_veriden_okunur_sabit_yazilmaz():
    """Engel cümlesi `u_ref_pct` ile birlikte değişmeli.

    Kanit dosyasi eski gerekcenin GECERLI olup olmadigini AYRI bir alanda
    tasir; boylece cumle degil VERI hukum verir.
    """
    import validation_anchors as va
    u = va.ANCHORS["naca0012_wing_ar6"]["u_ref_pct"]
    r = F.olc()
    assert r["referans_belirsizligi_pct"] == u
    assert r["eski_gerekce_gecerli_mi"] is (u >= 15.0)
    if u < 15.0:
        assert "CURUDU" in r["verdikt"], \
            "u_ref düştü ama verdikt eski gerekçeyi hâlâ geçerli sayıyor"


def test_model_form_gerekce_metni_de_GUNCEL():
    """Aynı çürük cümle `model_form_bandi`de de duruyordu."""
    src = (KOK / "experiments" / "model_form_bandi.py").read_text(
        encoding="utf-8")
    bas = src.index('"lifting.wall_function": (')
    blok = src[bas:src.index("),", bas)]
    # OLCUT IDDIAYA UYMALI. Ilk surum "%15 baskin" dizgisinin YOKLUGUNU sart
    # kosuyordu ve dustu --- cunku yeni metin o cumleyi CURUTMEK icin ALINTILIYOR.
    # Aranan sey ifadenin yoklugu degil, IDDIA EDILMEMESI: eski gerekce
    # geciyorsa yaninda curutuldugu de gecmeli.
    if "%15" in blok:
        assert "CURUDU" in blok or "curudu" in blok.lower(), \
            "eski gerekçe hâlâ İDDİA olarak duruyor"
    assert "lifting_wf_fizibilite" in blok, "gerekçe ölçüme bağlı değil"
    assert "OLCULDU" in blok, "gerekçe ölçüme değil metne dayanıyor"


def test_DUVAR_FONKSIYONU_duvar_cozunurden_UCUZ():
    """Fiziğin gerektirdiği yön: y⁺ 30 bandı y⁺ 1'den daha az katman ister.

    Ters çıkarsa model yanlıştır --- ve bu ölçümün bütün hükmü o farka
    dayanıyor (düşen koşu duvar-çözünür ağ örüyordu).
    """
    r = F.olc()
    wf, wr = r["duvar_fonksiyonu_butcesi"], r["duvar_cozunur_butcesi"]
    assert wf["h_bolu_kiris"] == wr["h_bolu_kiris"], \
        "iki bütçe farklı çözünürlükte kıyaslanıyor — fark ağdan gelir"
    assert wf["katman_sayisi"] < wr["katman_sayisi"]
    assert wf["hucre_kestirimi"] < wr["hucre_kestirimi"]
    assert r["ucuzlama_carpani"] > 1.0


def test_ILK_HUCRE_yplus_ile_DOGRU_ORANTILI():
    """y⁺ 30 kat büyürse ilk hücre de 30 kat büyümeli; ölçek hatası tüm
    bütçeyi kaydırır ve sessizdir."""
    ilk1, _ = F.ilk_hucre(30.0, 3.0, 1.0)
    ilk30, _ = F.ilk_hucre(30.0, 3.0, 30.0)
    assert ilk30 / ilk1 == pytest.approx(30.0, rel=1e-9)


def test_COZUNURLUK_EGRISI_tekduze_azaliyor():
    """Kaba ağ daha az hücre demeli. Eğri tekdüze değilse bütçe modeli
    bozuktur ve 'sığan en ince çözünürlük' anlamsızlaşır."""
    e = F.olc()["cozunurluk_egrisi"]
    h = [b["h_bolu_kiris"] for b in e]
    n = [b["hucre_kestirimi"] for b in e]
    assert h == sorted(h)
    assert n == sorted(n, reverse=True), f"eğri tekdüze değil: {n}"


def test_TEK_DEGER_degil_EGRI_uretiliyor():
    """İlk sürüm tek bir varsayılan çözünürlükle hüküm veriyordu ve varsayım
    hükmü belirliyordu. Eğri, hükmü okurun denetleyebileceği hâle getirir."""
    r = F.olc()
    assert len(r["cozunurluk_egrisi"]) >= 4
    assert "_capalarin_kullandigi_bant" in r, \
        "varsayılan çözünürlük neye göre seçildi, kayıtta yok"


def test_SIGAN_COZUNURLUK_gercekten_sigiyor():
    """`bellege_sigan_en_ince` alanı kendi ölçütüyle tutarlı olmalı."""
    r = F.olc()
    en = r["bellege_sigan_en_ince"]
    if en is None:
        assert all(not b["bellege_sigar_mi"] for b in r["cozunurluk_egrisi"])
        assert "SIGMIYOR" in r["verdikt"]
        return
    assert en["bellege_sigar_mi"] and en["bellek_gb"] < en["bos_bellek_gb"]
    # DAHA INCE olan hicbiri sigmamali --- yoksa "en ince" yanlis
    daha_ince = [b for b in r["cozunurluk_egrisi"]
                 if b["h_bolu_kiris"] < en["h_bolu_kiris"]]
    assert all(not b["bellege_sigar_mi"] for b in daha_ince)


def test_KISIT_GCI_seviyesini_soyluyor():
    """Bütçe TEK seviyenin; GCI üç seviye ister ve en ince olan budur.
    Bu söylenmezse okur 'sığıyor' diye okur."""
    r = F.olc()
    assert "GCI" in r["_kisit"] and "UC seviye" in r["_kisit"]
    assert "MERTEBE" in r["_kisit"], "kestirim taahhüt gibi okunmamalı"


def test_KAYIT_dosyasi_verdiktle_TUTARLI():
    p = KOK / "lifting_wf_fizibilite.json"
    if not p.exists():
        pytest.skip("lifting_wf_fizibilite.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    en = d["bellege_sigan_en_ince"]
    if en is None:
        assert "SIGMIYOR" in d["verdikt"]
    else:
        assert str(en["kiris_basina_hucre"]) in d["verdikt"], \
            "verdikt sığan çözünürlüğü yazmıyor"


def test_RAPOR_YOL_HARITASI_kanittan_sapmiyor():
    """Yol haritası çürümüş bir engeli aylarca taşıdı; sayısı artık pinli."""
    tex = KOK / "docs" / "teknik_rapor.tex"
    kanit = KOK / "lifting_wf_fizibilite.json"
    if not (tex.exists() and kanit.exists()):
        pytest.skip("rapor ya da kanıt yok")
    t = tex.read_text(encoding="utf-8")
    d = json.loads(kanit.read_text(encoding="utf-8"))
    en = d["bellege_sigan_en_ince"]
    if en is not None:
        assert str(en["kiris_basina_hucre"]) in t, \
            "sığan çözünürlük raporda yok"
    # CURUYEN GEREKCE RAPORDA DA CURUK ISARETLI OLMALI
    if not d["eski_gerekce_gecerli_mi"]:
        assert "çürüdü" in t, "rapor eski gerekçeyi hâlâ geçerli sayıyor"
    assert str(d["ucuzlama_carpani"]).replace(".", "{,}") in t
