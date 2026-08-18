"""i18n sözleşmesi: katalog, zarfın GERÇEKTEN yaydığı anahtarları karşılıyor mu.

NEDEN VAR (ölçüldü 2026-08-18): `SINIF` kataloğu Türkçe GÖRÜNEN ADLA
anahtarlanmıştı ("DOĞRULANMIŞ", "ZARF-DIŞI") ama zarf katmanı MAKİNE SABİTİ
yayıyor (VALIDATED, TREND, OUT). Üç sınıfın yalnız biri tesadüfen eşleşiyordu;
diğer ikisi her iki dilde de çevrilmeden geçiyordu ve `genel_metni` alanı tr
ile en'de aynı ham "OUT" dizgisini basıyordu.

Kusur SESSİZ kaldı çünkü `cevir` eksik anahtarda istisna atmaz, anahtarın
kendisini döndürür --- bilgiyi yok etmemek için bilinçli bir tercih, ama bir
testle dengelenmediğinde ayrışmayı görünmez kılıyor. Bu dosya o dengedir:
katalogla üreticiyi karşılaştırır, "çeviri var mı" değil "üretilen anahtarın
karşılığı var mı" diye sorar.
"""
from __future__ import annotations

import mesajlar
import validity_envelope as ve


def _tum_hukumler():
    """Sınıflandırıcıların gerçekten ürettiği hükümler --- elle liste değil."""
    v = []
    for tip in ("ucak", "roket"):
        for a in (0.0, 4.0, 14.0):
            for m in (0.05, 0.5):
                for gci in (True, False):
                    v += ve.classify_cfd(tip, a, m, has_gci_band=gci,
                                         Cl=0.4, Cd=0.05, ag_yeterli=None)
                for e in (0.9, 1.3, None):
                    for band in (1.2, None):
                        v += ve.classify_vlm(a, m, Cl=0.4, CDi=0.01, e_span=e,
                                             panel_bandi_pct=band, vehicle_type=tip)
    for tekil in (True, False):
        for marj in (2.0, 1.0, None):
            v += ve.classify_fea(has_singularity=tekil, buckling_margin=marj)
    return v


def test_sinif_katalogu_zarfin_SABITLERIYLE_anahtarli():
    """Katalog görünen adla değil, üreticinin yaydığı sabitle anahtarlanmalı."""
    assert set(mesajlar.SINIF) == {ve.VALIDATED, ve.TREND, ve.OUT}


def test_sinif_cevirisi_ANAHTARI_geri_dondurmuyor():
    """Bu testi kaçıran kusur tam olarak buydu: sessiz geçiş.

    `cevir` eksik anahtarda anahtarın kendisini döndürür. Türkçede çevirinin
    anahtardan FARKLI olması, kataloğun gerçekten isabet ettiğinin kanıtıdır.
    """
    for k in (ve.VALIDATED, ve.TREND, ve.OUT):
        tr = mesajlar.cevir(mesajlar.SINIF, k, "tr")
        assert tr != k, f"{k} tr'de çevrilmemiş (katalog ıskalıyor)"


def test_her_uretilen_sinif_katalogda_var():
    eksik = {h.klass for h in _tum_hukumler()} - set(mesajlar.SINIF)
    assert not eksik, f"zarf bu sınıfları yayıyor ama katalogda yok: {eksik}"


def test_her_uretilen_nicelik_adi_katalogda_var():
    eksik = {h.quantity for h in _tum_hukumler()} - set(mesajlar.NICELIK)
    assert not eksik, f"katalogda karşılığı olmayan nicelik adı: {eksik}"


def test_her_uretilen_hukum_kodu_IKI_DILDE_de_var():
    kodlar = {h.kod for h in _tum_hukumler() if h.kod}
    for k in sorted(kodlar):
        for dil in ("tr", "en"):
            assert mesajlar.GEREKCE.get(k, {}).get(dil), f"{k} için {dil} yok"


def test_gerekce_metni_PARAMETRELERI_dolduruyor():
    """Yarım cümle yerine kod dönmesi de bir kusurdur; her hüküm kendi
    parametreleriyle sorunsuz biçimlenmeli."""
    for h in _tum_hukumler():
        if not h.kod:
            continue
        for dil in ("tr", "en"):
            m = mesajlar.gerekce_metni(h.kod, dil, **(h.parametreler or {}))
            assert "parametresi eksik" not in m, f"{h.kod} ({dil}): {m}"
            assert m != h.kod, f"{h.kod} ({dil}) çevrilmedi"


def test_iki_dil_GERCEKTEN_farkli_metin_veriyor():
    """tr ve en'in aynı dizgiyi vermesi, çevirinin uygulanmadığının işaretidir."""
    ayni = []
    for h in _tum_hukumler():
        if not h.kod:
            continue
        tr = mesajlar.gerekce_metni(h.kod, "tr", **(h.parametreler or {}))
        en = mesajlar.gerekce_metni(h.kod, "en", **(h.parametreler or {}))
        if tr == en:
            ayni.append(h.kod)
    assert not ayni, f"tr ve en aynı metni veriyor: {sorted(set(ayni))}"
