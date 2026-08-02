"""Elenen GCI seviyesinin GEREKÇESİ her dalda kayda girmeli.

ÖLÇÜLDÜ (çapa kampanyası 2026-08-02, küp): kaba seviyeler yüzey kapısında
reddedildi — gövde 176 ve 436 yüz, eşik 500. Kapı DOĞRU çalıştı. Ama gerekçe
yalnız "3+ seviye hayatta kaldı" dalında kaydediliyordu; 2'ye düşünce
`fizik_disi_seviyeler` ve `yuzeyi_cozulmemis_seviyeler` sessizce kayboluyor,
kullanıcı gerekçesiz bir "yalnız 2 seviye tamamlandı" görüyordu.

Aynı desen: hüküm hesaplanıyor, tüketicisine ulaşmıyor — bu kez kapıları
ekleyen kodun kendisinde.
"""
import inspect
import re

import vehicle_pipeline as vp

_SRC = inspect.getsource(vp.run_vehicle_analysis)


def _dal(baslangic: str, uzunluk: int = 1400) -> str:
    i = _SRC.index(baslangic)
    return _SRC[i:i + uzunluk]


def test_red_kayitlari_TEK_yerde_uretiliyor():
    """Üç dal aynı bloğu kopyalarsa biri güncellenmeden kalır — nitekim kaldı."""
    assert _SRC.count("def _red_kayitlari") == 1
    assert _SRC.count("_red_kayitlari(") >= 4          # tanım + üç dal


def test_IKI_seviye_dali_YUZEY_gerekcesini_tasiyor():
    d = _dal("elif len(levels) == 2:")
    assert "_red_kayitlari(" in d
    assert "yuzey çözülmedi" in d or "yüzey çözülmedi" in d


def test_YETERSIZ_seviye_dali_YUZEYI_sayiyor():
    # Metin artık koşullu: ince seviye kapıdan geçmediyse "ÇALIŞMASI YAPILMADI",
    # aksi halde "yetersiz seviye". Sayım listesi ikisinin de üstünde kuruluyor.
    i = _SRC.index("yetersiz seviye — bant hesaplanamadı")
    ust = _SRC[max(0, i - 1200):i]
    assert "yuzeysiz" in ust and "ÇÖZÜLMEDİ" in ust
    assert "_red_kayitlari(" in _SRC[i:i + 700]


def test_UC_dal_da_ayni_dort_listeyi_kapsiyor():
    """Elenme sebepleri: koşamadı / fizik-dışı / yakınsamadı / yüzey çözülmedi."""
    fn = inspect.getsource(vp.run_vehicle_analysis)
    i = fn.index("def _red_kayitlari")
    govde = fn[i:i + 1600]
    for alan in ("basarisiz_seviyeler", "fizik_disi_seviyeler",
                 "yakinsamayan_seviyeler", "yuzeyi_cozulmemis_seviyeler"):
        assert alan in govde, alan


def test_gerekce_alanlari_dogru_yerden_okunuyor():
    """fizik gerekçesi `reasons` listesinde, digerleri `gerekce` alanindadir;
    karistirilirsa gerekce BOS string olur ve yine bilgi tasimaz."""
    i = _SRC.index("def _red_kayitlari")
    govde = _SRC[i:i + 1600]
    assert 'get("reasons"' in govde and 'get("gerekce"' in govde
    assert re.search(r'alan == "fizik"', govde)
