"""u_D boşluğu triyajı: "ölçülemez" ile "kaydedilmemiş" aynı şey değildir.

On bir çapanın altısı u_D beyan etmiyordu ve bu tek bir sayı olarak duruyordu.
Ayrıldığında tablo değişti: ikisinde eksik olan ÖLÇÜM değil, çapa tanımının
zaten ADINI TAŞIDIĞI ikinci kaynağın sayısıdır. Deponun düz levhada kullandığı
yöntem (iki korelasyonun farkı = u_D alt kestirimi) oralarda da uygulanabilir.

Bu testler triyajın kendisini bağlar --- özellikle doğrulanmamış bir sayının
banda sızmamasını.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from referans_belirsizligi import _kaynak_sayisi, _re_bandi, cd_kure  # noqa: E402


def test_hoerner_basligi_TEK_kaynak_sayilir():
    """'Hoerner, Fluid-Dynamic Drag (1965)' virgül taşır ama TEK kaynaktır.

    Virgülden ayırmak bu çapayı 'iki kaynaklı' gösterir ve triyajı bozardı.
    """
    assert _kaynak_sayisi("Hoerner, Fluid-Dynamic Drag (1965)") == 1
    assert _kaynak_sayisi("Ahmed et al. 1984; Meile et al. 2011") == 2


def test_re_bandi_yalniz_ARALIKTAN_okunur():
    """'>1e4' bir aralık değildir; aralık sanılırsa uydurma bir yayılım çıkar."""
    assert _re_bandi("1e3–2e5 (subkritik)") == (1e3, 2e5)
    assert _re_bandi(">1e4 (keskin-kenar, Re-duyarsız)") is None
    assert _re_bandi("6e6") is None


def test_korelasyon_bilinen_PLATOYA_oturuyor():
    """Küre sürüklemesi 1e3–2e5 arasında ≈0,47 platosundadır.

    Bu, sabitlerin birincil kaynak doğrulaması DEĞİL; ama yanlış bir formülün
    bandın iki ucunda birden platoya oturması beklenmez.
    """
    assert 0.44 < cd_kure(1e3) < 0.50
    assert 0.44 < cd_kure(2e5) < 0.52


def test_korelasyon_dusuk_Re_de_STOKES_egilimi_veriyor():
    """Re→küçük'te Cd ~ 24/Re baskın olmalı; değilse ilk terim yanlış girilmiş."""
    assert cd_kure(1.0) > 20, cd_kure(1.0)
    assert cd_kure(0.1) > 200, cd_kure(0.1)


def test_dogrulanmamis_sayi_banda_SIZMIYOR():
    """Re-BANDI kestirimi damgalı çıkmalı ve otomatik kullanılmamalı."""
    p = KOK / "referans_belirsizligi.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    d = json.loads(p.read_text(encoding="utf-8"))
    for s in d["satirlar"]:
        if s.get("u_D_alt_kestirim_pct") is not None:
            assert s.get("_dogrulama_bekliyor") is True, s
            assert s.get("_neden_beklemede"), s
    # Ve gercekten girmemis olmali: capa tanimi hala u_ref_pct=None tasiyor.
    from validation_anchors import ANCHORS
    assert ANCHORS["sphere"]["u_ref_pct"] is None, (
        "doğrulanmamış kestirim çapa tanımına yazılmış")


def test_triyaj_ENGELI_adiyla_yaziyor():
    """'u_D yok' yetmez; her satır neden yok olduğunu söylemeli."""
    p = KOK / "referans_belirsizligi.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    d = json.loads(p.read_text(encoding="utf-8"))
    eksik = [s for s in d["satirlar"] if s["durum"] != "u_D BEYAN EDİLMİŞ"]
    assert eksik, "triyaj boş çıktı"
    for s in eksik:
        assert s.get("engel"), f"{s['capa']}: engel yazılmamış"
        assert s["durum"] in ("KAYNAK-EKSİK", "TEK-KAYNAK", "Re-BANDI"), s


# ── kaynağa bakıldı: bulunan sayı nereye yazıldı, nereye yazılmadı ─────────

def test_tmr_u_D_kaynak_ve_kosulla_birlikte_KAYITLI():
    """Sayı tek başına yetmez: hangi koşulda, hangi ağda, kaç koddan?"""
    p = KOK / "tmr_kod_yayilimi.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["kaynak"].startswith("http"), d["kaynak"]
    assert d["kosul"]["ag"] and d["kosul"]["model"] and d["kosul"]["Re"]
    assert len(d["cd_kodlar"]) >= 5, "kod-arası yayılım birkaç koddan hesaplanmaz"
    assert d["yayilim"]["n"] == len(d["cd_kodlar"])


def test_tmr_u_D_capaya_AYNI_sayiyla_gecmis():
    """Kanıt dosyası ile çapa tanımı ayrışırsa 'metin sabit, veri değişti'."""
    p = KOK / "tmr_kod_yayilimi.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    from validation_anchors import ANCHORS
    d = json.loads(p.read_text(encoding="utf-8"))
    assert ANCHORS["naca0012_a0"]["u_ref_pct"] == d["u_D_pct"], (
        f'çapa {ANCHORS["naca0012_a0"]["u_ref_pct"]} ≠ kanıt {d["u_D_pct"]}')


def test_kod_arasi_yayilim_ALT_SINIR_diye_etiketli():
    """Kod-arası yayılım deneysel belirsizliği KAPSAMAZ; öyle sunulamaz."""
    p = KOK / "tmr_kod_yayilimi.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["_sinif"] == "ALT SINIR"
    assert "DENEYSEL" in d["_ne_kapsamaz"]
    from validation_anchors import ANCHORS
    assert "ALT SINIR" in ANCHORS["naca0012_a0"].get("u_ref_sinif", "")


def test_aykiri_kod_ATILMAMIS():
    """Aykırıyı atmak bandı yapay daraltır; atılmadığı kayıtlı olmalı."""
    p = KOK / "tmr_kod_yayilimi.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    d = json.loads(p.read_text(encoding="utf-8"))
    y = d["yayilim"]
    assert y["en_uzak_haric_u_D_pct"] < y["u_D_pct"], (
        "aykırı çıkarılınca band daralmalı — daralmıyorsa 'en uzak' yanlış")
    assert d["u_D_pct"] == y["u_D_pct"], "yayımlanan u_D aykırı DAHİL olmalı"


def test_ikincil_kaynakli_sayi_capaya_YAZILMAMIS():
    """Ahmed için değer bulundu ama iki gerekçeyle beyan edilmedi.

    Bulmak ile beyan edebilmek aynı şey değildir: kaynak ikincildi ve iki
    değer aynı Reynolds sayısında değil.
    """
    p = KOK / "referans_belirsizligi.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    from validation_anchors import ANCHORS
    d = json.loads(p.read_text(encoding="utf-8"))
    s = next((x for x in d["satirlar"] if x["capa"] == "ahmed_25"), None)
    if not s or "arama" not in s:
        pytest.skip('kanıt/girdi yok: not s or "arama" not in s')
    a = s["arama"]
    assert a["sonuc"] == "BULUNDU AMA BEYAN EDİLMEDİ"
    assert len(a["neden_beyan_edilmedi"]) >= 2, a
    assert ANCHORS["ahmed_25"]["u_ref_pct"] is None, (
        "ikincil kaynaklı sayı çapa tanımına sızmış")


def test_disk_TEK_KAYNAK_engeli_KALKTI_ve_sayi_kanittan_geliyor():
    """Disk'in u_D'si artık beyanlı; sayı kanıt dosyasıyla BİREBİR eşleşmeli.

    Bulunan (2026-08-19): NACA TN-253 (Knight, Langley, 1926) — 4/8/12 inçlik
    üç disk, DOĞRUDAN KUVVET ölçümü, Re 33.000–670.000. Çapa Re = 2,0e5'te
    koşuyor ve tablo o Re'yi üç diskte birden taşıyor, yani Ahmed'i engelleyen
    "iki değer aynı Re'de değil" sorunu BURADA YOK.

    Kaynağın kendi uyarısı kritik: blokaj düzeltmesi uygulanmamış ve sonuçlar
    açıkça "sınırsız hava uzayı için değil" deniyor. Çapa sınırsız akışta
    koştuğu için taşıma zorunlu; iki bağımsız yöntem (S/C→0 ekstrapolasyonu ve
    Maskell) %0,63 içinde uyuşuyor.
    """
    from validation_anchors import ANCHORS
    p = KOK / "capa_birincil_kaynak.json"
    if not p.exists():
        pytest.skip("kanıt üretilmemiş: python experiments/capa_birincil_kaynak.py")
    d = json.loads(p.read_text(encoding="utf-8"))["disk"]

    assert ANCHORS["disk"]["u_ref_pct"] == d["u_D_alt_kestirim_pct"], (
        f'çapa {ANCHORS["disk"]["u_ref_pct"]} ≠ kanıt {d["u_D_alt_kestirim_pct"]}')
    assert "TÜRETİLMİŞ" in ANCHORS["disk"]["u_ref_sinif"], (
        "blokaj düzeltmesi bu depoda uygulandı; sınıf bunu söylemeli")
    assert "TN-253" in ANCHORS["disk"]["ref"]
    # Cd DEĞİŞMEDİ: türetilmiş bir sayı referans yuvasına konmamalı.
    assert ANCHORS["disk"]["Cd"] == 1.17

    t = d["serbest_havaya_tasima"]
    assert t["iki_yontem_farki_pct"] < 2.0, (
        "iki bağımsız blokaj düzeltmesi uyuşmuyor — tek yöntem kendini "
        "doğrulayamaz, taşıma güvenilir değil")
    m = t["yontem_2_maskell_1963"]
    assert m["duzeltme_sonrasi_yayilim_pct"] < d["ham_yayilim_pct"] / 3.0, (
        "Maskell yayılımı yemiyor — ham saçılmanın kaynağı blokaj olmayabilir")


def test_kup_kaynagi_ARANDI_bulundu_ve_GEREKCELI_reddedildi():
    """"Aranmadı" ile "arandı, bulundu, koşula uymuyor" aynı şey değil.

    Küp için birincil kaynak VAR (Khan vd. 2018). Referans olamamasının nedeni
    kaynağın yokluğu değil: üst Re'si 5,5e4 iken çapa 2,0e5'te koşuyor, ve PIV
    iz-momentumundan türetilen sürükleme kuvvet-terazisi sürüklemesiyle özdeş
    değil. Hoerner'la farkı ~%40 — bu saçılma değil, yöntem farkının imzası.
    """
    from validation_anchors import ANCHORS
    p = KOK / "capa_birincil_kaynak.json"
    if not p.exists():
        pytest.skip("kanıt üretilmemiş")
    k = json.loads(p.read_text(encoding="utf-8"))["kup"]
    assert k["verdikt"].startswith("BULUNDU AMA")
    assert len(k["gerekce"]) >= 3, "ret gerekçesi tek cümleye indirgenmiş"
    # Reddedilen sayı çapa tanımına SIZMAMALI.
    assert ANCHORS["cube"]["u_ref_pct"] is None
    assert ANCHORS["cube"]["Cd"] == 1.05

    # Defter de "arandı" demeli — TEK-KAYNAK satırı arama kaydını taşımalı.
    dp = KOK / "referans_belirsizligi.json"
    if dp.exists():
        d = json.loads(dp.read_text(encoding="utf-8"))
        s = next(x for x in d["satirlar"] if x["capa"] == "cube")
        assert "arama" in s, (
            "TEK-KAYNAK satırı arama kaydı taşımıyor — 'arandı ve reddedildi' "
            "ile 'hiç aranmadı' ayırt edilemiyor")


def test_AR6_referansi_OLCULMUS_terime_dayaniyor():
    """AR6 referansının baskın terimi artık analitik değil ÖLÇÜLMÜŞ olmalı.

    ESKİ: Cd=0,020, tümüyle analitik (düz-plaka Cf + form + lifting-line),
    u_D=%15. O kadar büyük bir u_D ile ağ ne kadar inceltilirse inceltilsin
    u_val %15'in ALTINA İNEMEZ — çapa ilkece kapanamazdı.

    YENİ: profil sürüklemesi Ladson TM-4074'ten (Langley LTPT, Re=6e6),
    indüklenen sürükleme lifting-line'dan. Ladson noktaları depoda ZATEN
    kayıtlıydı (naca0012_re_eslesme.json) — eksik olan onları kullanmaktı.
    """
    from validation_anchors import ANCHORS
    a = ANCHORS["naca0012_wing_ar6"]
    assert "Ladson" in a["ref"], "referans hâlâ yarı-analitik"
    assert "ÖLÇÜLMÜŞ" in a["ref"] and "MODELLENMİŞ" in a["ref"], (
        "iki terimin hangisinin ölçüm hangisinin model olduğu yazılmıyor")
    assert a["u_ref_pct"] < 5.0, (
        f"u_D hâlâ %{a['u_ref_pct']} — ağ inceltmesi anlamsız kalır")
    assert "ALT SINIR" in a.get("u_ref_sinif", ""), (
        "u_D yalnız e bandını kapsıyor; sınıf bunu söylemeli")


def test_AR6_capasi_REFERANSIN_Re_sinde_kosuyor():
    """Referans Re=6e6'da ölçüldü; çapa da orada koşmalı.

    Ahmed'de öğrenilen ders: koştuğun koşulda ölçülmüş değer, başka bir
    koşulda ölçülmüş değerden daha iyi bir referanstır. Burada ek bir fizik
    gerekçesi de var — Re=3e5 NACA0012 için GEÇİŞ rejimidir ve tam-türbülanslı
    RANS orada yanlıştır (deponun naca2412'de ölçtüğü ders).
    """
    import validate_pipeline as vpl
    from validation_anchors import ANCHORS
    gen, _, kw = vpl._GEOM["naca0012_wing_ar6"]
    m = gen()
    kiris = float(m.bounds[1][0] - m.bounds[0][0])
    re = 30.0 * kiris / 1.5e-5
    assert abs(re - 6e6) / 6e6 < 0.02, f"çapa Re={re:.3g}, referans 6e6"
    assert "6e6" in ANCHORS["naca0012_wing_ar6"]["Re"]
    # Ma sikisamaz zarf icinde kalmali.
    assert 30.0 / 340.0 < 0.3
    # Duvar-cozunur kurulum: onceki kosu katmansizdi ve y+ 134'te takildi.
    from vehicle_pipeline import MESH_QUALITY
    assert MESH_QUALITY[kw["quality"]]["n_layers"] > 0, (
        "çapa hâlâ katmansız koşuyor — 2B kanatta ölçülen teşhis "
        "'çözüm duvar-çözünür kurulum' diyordu")
