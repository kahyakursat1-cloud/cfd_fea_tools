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
        return
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
        return
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
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["kaynak"].startswith("http"), d["kaynak"]
    assert d["kosul"]["ag"] and d["kosul"]["model"] and d["kosul"]["Re"]
    assert len(d["cd_kodlar"]) >= 5, "kod-arası yayılım birkaç koddan hesaplanmaz"
    assert d["yayilim"]["n"] == len(d["cd_kodlar"])


def test_tmr_u_D_capaya_AYNI_sayiyla_gecmis():
    """Kanıt dosyası ile çapa tanımı ayrışırsa 'metin sabit, veri değişti'."""
    p = KOK / "tmr_kod_yayilimi.json"
    if not p.exists():
        return
    from validation_anchors import ANCHORS
    d = json.loads(p.read_text(encoding="utf-8"))
    assert ANCHORS["naca0012_a0"]["u_ref_pct"] == d["u_D_pct"], (
        f'çapa {ANCHORS["naca0012_a0"]["u_ref_pct"]} ≠ kanıt {d["u_D_pct"]}')


def test_kod_arasi_yayilim_ALT_SINIR_diye_etiketli():
    """Kod-arası yayılım deneysel belirsizliği KAPSAMAZ; öyle sunulamaz."""
    p = KOK / "tmr_kod_yayilimi.json"
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["_sinif"] == "ALT SINIR"
    assert "DENEYSEL" in d["_ne_kapsamaz"]
    from validation_anchors import ANCHORS
    assert "ALT SINIR" in ANCHORS["naca0012_a0"].get("u_ref_sinif", "")


def test_aykiri_kod_ATILMAMIS():
    """Aykırıyı atmak bandı yapay daraltır; atılmadığı kayıtlı olmalı."""
    p = KOK / "tmr_kod_yayilimi.json"
    if not p.exists():
        return
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
        return
    from validation_anchors import ANCHORS
    d = json.loads(p.read_text(encoding="utf-8"))
    s = next((x for x in d["satirlar"] if x["capa"] == "ahmed_25"), None)
    if not s or "arama" not in s:
        return
    a = s["arama"]
    assert a["sonuc"] == "BULUNDU AMA BEYAN EDİLMEDİ"
    assert len(a["neden_beyan_edilmedi"]) >= 2, a
    assert ANCHORS["ahmed_25"]["u_ref_pct"] is None, (
        "ikincil kaynaklı sayı çapa tanımına sızmış")
