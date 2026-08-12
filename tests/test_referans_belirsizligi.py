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
