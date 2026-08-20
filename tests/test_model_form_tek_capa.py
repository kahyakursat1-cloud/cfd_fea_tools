"""Model-form bandı: tek çapayla band DARALTILMAZ.

n=1 bir dağılım değil, tek örnektir. Ölçülen değer öncülden küçükse bu "model
daha iyi" demek değil, "bu tek vakada daha iyi çıktı" demektir; model-form
hatası rejim içinde geometriye göre güçlü değişir. Bandı tek ölçümle daraltmak,
bu deponun tam da savaştığı sahte-kesinliktir.

Kural asimetriktir ve bilerek öyledir: ölçüm öncülü AŞARSA her durumda ölçüm
kazanır — o zaman öncül kanıtla yanlışlanmış demektir (yukarı düzeltme hep
kabul, aşağı düzeltme n=1'de değil).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from model_form_bandi import _duvar_islemi, _kosudan_yplus, calistir  # noqa: E402

from validation_anchors import _MODEL_U_PCT  # noqa: E402


def test_tek_capa_bandi_DARALTMAZ():
    rec = calistir()
    for rejim, h in rec["olculen_hucreler"].items():
        for islem, v in h.items():
            oncul = _MODEL_U_PCT.get(rejim, {}).get(islem)
            if v["n_capa"] == 1 and oncul is not None:
                assert v["u_pct"] >= oncul, (
                    f"{rejim}.{islem}: tek çapayla band daraltıldı "
                    f"({v['olculen_pct']} < {oncul})")


def test_olcum_onculu_asarsa_OLCUM_kazanir():
    """Yukarı düzeltme her durumda kabul: öncül kanıtla yanlışlanmıştır."""
    rec = calistir()
    for h in rec["olculen_hucreler"].values():
        for v in h.values():
            if v["oncul_pct"] is not None and v["olculen_pct"] > v["oncul_pct"]:
                assert v["u_pct"] == v["olculen_pct"]
                assert v["oncul_korundu"] is False


def test_korunan_oncul_OLCUMU_de_kaydediyor():
    """Öncül korunduğunda ölçüm kaybolmamalı — sonraki çapa geldiğinde gerekir.

    BU TEST ÖNCE VERİNİN DURUMUNU iddia ediyordu ("en az bir korunan öncül
    hücresi var") ve veri İYİLEŞİNCE kırıldı: çapaların sayısal bandı okunup
    sapmalara eklenince iki hücre de öncülü aştı ve ölçüm kazandı. Kural
    doğruydu, iddia yanlıştı. Artık KURAL sınanıyor: korunan hücre VARSA
    ölçümünü de taşımalı. Yoksa test bir şey iddia etmez."""
    rec = calistir()
    for h in rec["olculen_hucreler"].values():
        for v in h.values():
            if v["oncul_korundu"]:
                assert v["olculen_pct"] > 0
                assert "DARALTILMADI" in v["_anlam"]
                assert v["u_pct"] == v["oncul_pct"]


def test_UST_SINIR_ile_OLCUM_ayirt_ediliyor():
    """Hiçbir çapa farkı kendi sayısal bandından ayıramıyorsa değer ölçülmüş
    bir model hatası DEĞİL, üst sınırdır.

    "Değerlendirilmedi" ile "ayrılamaz" HÂLÂ ayrı tutulur — ama bu ayrım
    hücre ETİKETİYLE değil, `ayrilabilirlik_degerlendirilmedi` sayacıyla
    ifade edilir.

    DÜZELTME (2026-08-19). Bu test önce şunu istiyordu: değerlendirilmemiş
    çapa varsa `_ust_sinir_mi` False olsun. Niyeti doğruydu (ölçmediğimizi
    olumsuz ölçüm gibi göstermemek) ama kodlanışı iki ayrı meseleyi
    karıştırıyordu ve sonucu terse çeviriyordu: ÖLÇÜLDÜ — Ahmed çapası
    yeniden koşup bluff hücresine girdi, ince seviyesi yakınsamadığı için
    sayısal bandı üretilemedi (u_sayisal=None), ve hücre "ÜST SINIR — hiçbir
    çapa ayıramıyor" iken "ölçülen" oldu. Ayrılabilir çapa sayısı hâlâ
    SIFIRDI. Yani EKSİK BİLGİ iddiayı YÜKSELTMİŞTİ.

    Etiket tek yönlü olmalı: en az bir çapa ayırt ettiyse ölçüm, aksi halde
    üst sınır. Bilgi eksikliği hiçbir koşulda iddiayı güçlendiremez.
    """
    rec = calistir()
    for h in rec["olculen_hucreler"].values():
        for v in h.values():
            assert "_ust_sinir_mi" in v
            # Uc durum AYRI SAYILMAYA devam ediyor.
            assert "ayrilabilirlik_degerlendirilmedi" in v
            # Etiket YALNIZ ayrilabilirlige bakar, iki yonlu ve tam.
            assert v["_ust_sinir_mi"] is (v["ayrilabilir_capa"] == 0), (
                f"etiket ayrılabilirlikle tutarsız: ust_sinir="
                f"{v['_ust_sinir_mi']}, ayrilabilir_capa={v['ayrilabilir_capa']}")
    assert "UST SINIR" in rec["_ayrilabilirlik_notu"] or "ayirt edebiliyor"         in rec["_ayrilabilirlik_notu"]


def test_zarf_UST_SINIRI_okuyucuya_soyluyor():
    """Ayrım kanıt dosyasında kalırsa okuyucu üst sınırı ölçüm sanar."""
    src = (KOK / "zarf.py").read_text(encoding="utf-8")
    assert "_ust_sinir_mi" in src
    assert "ÜST SINIR" in src


# ── y⁺ bağı: ölçüm tüketicisine ULAŞIYOR mu ───────────────────────────────

def test_kup_capasinin_yplusu_TUKETICIYE_ULASIYOR():
    """Küp çapasının y⁺'ı ölçülmüştü ama tüketicisine ulaşmıyordu.

    2026-08-19 GÜNCELLEMESİ: test eskiden ARŞİV girdisini ("küp") arıyordu ve
    y⁺'ın hücre-sayısı eşleşmesiyle bağlandığını denetliyordu. O arşiv artık
    ATLANIYOR, çünkü çapa yeniden koşuldu (`_anchor_cube`) ve iki satırı yan
    yana raporlamak düzeltilmiş bir kusuru hâlâ varmış gibi gösteriyordu.

    Testin ASIL İDDİASI değişmedi: küpün y⁺'ı bandı üreten yola ULAŞMALI ve
    NEREDEN geldiği yazılı olmalı. Hangi mekanizmayla ulaştığı (arşiv eşleşmesi
    ya da doğrudan çapa koşusu) ikincildir.
    """
    rec = calistir()
    kup = [x for x in rec["capalar"]
           if "küp" in x["capa"] and not x.get("_gecersiz")]
    assert kup, "hiçbir ölçülen küp satırı yok"
    for k in kup:
        assert k["yplus_ort"] is not None, f"{k['capa']}: y⁺ ulaşmıyor"
        assert k.get("yplus_kaynak"), (
            f"{k['capa']}: y⁺'ın nereden geldiği yazılmamış")


def test_yplus_bagi_TAHMINLE_kurulmaz():
    """Hücre sayısı eşleşmeyen koşunun y⁺'ı çapaya iliştirilemez — y⁺ kademeye
    göre değişir, yanlış kademeninki ölçümü uydurmak olurdu."""
    assert _kosudan_yplus(None) is None
    assert _kosudan_yplus(123_456_789) is None


def test_bant_disi_yplus_hucreye_atanmaz():
    from validity_envelope import YPLUS_BANDI
    assert _duvar_islemi(YPLUS_BANDI[1] + 500) is None
    assert _duvar_islemi(None) is None
    assert _duvar_islemi(1.0) == "wall_resolved"
    assert _duvar_islemi(100.0) == "wall_function"


# ── dış kaynaklı hücreler ──────────────────────────────────────────────────

def test_bu_betigin_uretmedigi_hucreler_ISARETLENIR():
    """Band dosyasında başka kampanyadan gelen hücreler var; farklı kurallarla
    üretilmiş sayıları aynı tabloda eşitlemek sessiz bir hata olurdu."""
    rec = calistir()
    dis = rec["dis_kaynakli_hucreler"]
    assert isinstance(dis, list)
    for x in dis:
        assert "ÜRETMEDİ" in x["_not"]
        if x["oncul_pct"] is not None and x["u_pct"] < x["oncul_pct"]:
            assert "gözden geçirilmeli" in x["_not"]


def test_kanit_dosyasi_guncel():
    d = json.loads((KOK / "model_form_bandi.json").read_text(encoding="utf-8"))
    assert "dis_kaynakli_hucreler" in d
    assert d["olculen_hucreler"], "en az bir ölçülen hücre olmalı"


# ── çapa kabul ölçütleri ───────────────────────────────────────────────────

def test_sayisal_bandi_buyuk_capa_REDDEDILIR():
    """Çapanın ayrıklaştırma gürültüsü, ölçmek istediği model hatasından büyükse
    o çapa model-form hakkında hiçbir şey söylemez. Ölçüldü: Ahmed 25° LSR
    bandı %274,7 — tek başına hücreyi ele geçirip bandı %290'a çıkarıyordu."""
    from model_form_bandi import U_SAYISAL_TAVANI
    rec = calistir()
    for x in rec["atanamayan_capalar"]:
        if x.get("u_sayisal_pct") and x["u_sayisal_pct"] > U_SAYISAL_TAVANI:
            assert "SAYISAL BAND ÇOK BÜYÜK" in x["neden"]
    for h in rec["olculen_hucreler"].values():
        for v in h.values():
            for c in v["capalar"]:
                assert c.get("sapma_pct") is not None


def test_tepe_yplus_bant_disi_capa_ATANMAZ():
    """Ortalama tek başına yetmez: Ahmed'in ortalaması 46 (bantta) ama tepesi
    1237. Duvarın bir bölümü hiçbir zaman log-bölgesinde değil."""
    from model_form_bandi import _duvar_islemi

    from validity_envelope import YPLUS_BANDI
    assert _duvar_islemi(100.0, 200.0) == "wall_function"
    assert _duvar_islemi(100.0, YPLUS_BANDI[1] + 1) is None
    assert _duvar_islemi(46.0, 1236.6) is None


def test_desteklenmeyen_eski_hucre_DUSURULUR_ve_gerekcesi_yazilir():
    """Eski sürüm 'bu betiğin kapsamadığı hücre silinmez' diyordu ve iki BOZUK
    hücreyi hayatta tutuyordu: bluff.wall_resolved (yanlış etiket) ve
    lifting.wall_function (reddedilmiş çapadan)."""
    rec = calistir()
    for x in rec["dusurulen_hucreler"]:
        assert x["onceki_pct"] is not None
        assert "ÖNCÜLE döndü" in x["neden"]
    band = json.loads((KOK / "validation_band.json").read_text(encoding="utf-8"))
    olculen = rec["olculen_hucreler"]
    for r, h in band.items():
        for i in h:
            assert (olculen.get(r) or {}).get(i), f"{r}.{i} bandda ama ölçülmemiş"


def test_disk_ve_kup_capalari_DUVAR_FONKSIYONU_hucresinde():
    """Kök hata buydu: ikisi de wall_resolved yazılmıştı, oysa y⁺ 31,3 ve 37,3."""
    rec = calistir()
    hf = (rec["olculen_hucreler"].get("bluff") or {}).get("wall_function")
    if not hf:
        return
    adlar = [c["ad"] for c in hf["capalar"]]
    assert any("disk" in a for a in adlar)
    assert hf["n_capa"] >= 2, "ikinci çapa geldi, hücre artık n=2"
    assert (rec["olculen_hucreler"].get("bluff") or {}).get("wall_resolved") is None


def test_validate_pipeline_ARTIK_band_yazmiyor():
    """Hücre ataması tek yerde olmalı; iki yazıcı iki farklı kuralla yazıyordu."""
    src = (KOK / "validate_pipeline.py").read_text(encoding="utf-8")
    assert "_BAND_FILE.write_text" not in src
    assert "model_form_bandi.py" in src
