"""Kanal ayrışması sayacı — taban çizgisi ve tarayıcının kendi doğruluğu.

`kanal_ayrismasi` bu turda ELLE bulunan kusur sınıfını mekanikleştirir: bir
alan raporda okunur, arayüzde okunmaz (ya da tersi) ve kullanıcı öbür kanaldan
bakıyorsa o bilgiyi hiç görmez.

İzlenen sayı `incelenmemis`tir, `toplam` değil: ayrışmaların çoğu meşrudur
(rapor VTK yolunu yazar, arayüz yazmaz). Meşru olanın gerekçesi KABUL
sözlüğünde durur ve gerekçe yazmadan oraya alan eklenmez.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from kanal_ayrismasi import KABUL, KANALLAR, ozet, tara  # noqa: E402


def test_incelenmemis_ayrisma_YOK():
    o = ozet()
    if o["incelenmemis"]:
        satir = [f"{x['alan']}: {','.join(x['okuyan'])} okuyor, "
                 f"{','.join(x['susan'])} susuyor"
                 for x in o["bulgular"] if not x["kabul"]]
        raise AssertionError(
            "İncelenmemiş kanal ayrışması var. Ya eksik kanal düzeltilmeli ya "
            "da neden tek kanalda olmasının doğru olduğu KABUL'e yazılmalı:\n  "
            + "\n  ".join(satir))


def test_KABUL_gerekcesi_bos_olamaz():
    """Sayacı susturmanın tek yolu gerekçe yazmaktır; boş dize ile susturmak
    tam olarak kaçınılmak istenen şeydir."""
    bos = [a for a, g in KABUL.items() if not (g or "").strip()]
    assert not bos, f"gerekçesiz kabul: {bos}"


def test_KABUL_olu_kayit_biriktirmiyor():
    """Bir alan silindiğinde ya da ayrışması kapandığında gerekçesi de
    gitmeli; yoksa sözlük zamanla anlamını yitirir."""
    ayrisan = {x["alan"] for x in tara()}
    olu = sorted(set(KABUL) - ayrisan)
    assert not olu, f"KABUL'de artık ayrışmayan alanlar var: {olu}"


def test_tarayici_BILINEN_kusuru_yakaliyor():
    """Aracın kendi doğrulaması: `kurulum` gerekçesi olmasaydı bugün
    incelenmemiş sayılır mıydı? (Kusur düzeltildiği için alan artık iki
    kanalda da okunuyor; burada tarayıcının MANTIĞI sınanıyor.)"""
    import kanal_ayrismasi as ka
    kaynak = {ad: (KOK / yol).read_text(encoding="utf-8", errors="replace")
              for ad, yol in KANALLAR.items()}
    d = ka._desen("kurulum")
    okuyan = [ad for ad, s in kaynak.items() if d.search(s)]
    assert set(okuyan) == set(KANALLAR), \
        "kurulum uyarıları yine tek kanalda — ekranda görünmeyen geçersizleştirici"


def test_kosum_kosulu_SONUCTAN_yaziliyor():
    """Ekrandaki metrikler bir koşuya aittir; form o sırada değişmiş olabilir
    (kuyrukta tek pencere, çok koşu). Koşum koşulu formdan değil sonuçtan
    okunmalı."""
    gui = (KOK / "app_analyzer.py").read_text(encoding="utf-8")
    i = gui.find("def _on_done")
    govde = gui[i:gui.find("def _on_fail", i)]
    assert "r.velocity" in govde and "r.alpha_deg" in govde
    assert "spn_hiz.value()" not in govde, "koşum koşulu formdan okunuyor"
