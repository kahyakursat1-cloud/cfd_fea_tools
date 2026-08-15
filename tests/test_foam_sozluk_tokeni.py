"""Sözlüğe yazılan her ad geçerli bir OpenFOAM `word` olmalı; hata metni LOG İÇERMELİ.

İKİSİ DE KONTEYNERDE ÖLÇÜLDÜ (2026-08-15), ikisi de masaüstünde görünmezdi:

1. REST ucu yüklenen dosyayı rastgele onaltılık adla saklıyor. `3b8737f31c36.stl`
   snappyHexMeshDict'e anahtar olarak yazılınca OpenFOAM `3` sayısı + kelime diye
   ayrıştırıp `readBeginList` ile düştü. Onaltılık adların ~%62'si rakamla başlar
   -> ucun çoğu çağrısı düşerdi. Masaüstünde adlar hep harfle başlıyordu
   (`minihawk`, `test_sphere`), bu yüzden yıllarca görünmedi.

2. Hata metni yalnız log YOLUNU taşıyordu; içerik yoktu. Başsız dağıtımda yol
   konteynerin içini gösterir ve JSON'u alan kullanıcı o dosyaya erişemez —
   gerçek hata ancak konteynere elle girilerek görülebildi.
"""
from pathlib import Path

from analysis.openfoam_runner import foam_word


def test_RAKAMLA_baslayan_ad_gecerli_token_olur():
    for ham in ("3b8737f31c36.stl", "0deadbeef.stl", "9.stl"):
        t = foam_word(ham)
        assert t[0].isalpha() or t[0] == "_", f"{ham} -> {t} hâlâ rakamla başlıyor"


def test_HARFLE_baslayan_ad_DEGISMEZ():
    """Mevcut vakalar birebir korunmalı: eski case adları bozulmamalı."""
    for ham in ("minihawk_prep.stl", "test_sphere_prep.stl", "clean_rocket_prep"):
        assert foam_word(ham) == ham


def test_bosluk_ve_gecersiz_karakterler_temizlenir():
    assert " " not in foam_word("my model.stl")
    assert foam_word("a(b)c.stl") == "a_b_c.stl"


def test_hata_metni_LOG_ICERIGINI_tasir(tmp_path: Path):
    from vehicle_pipeline import _log_kuyrugu

    log = tmp_path / "log.snappyHexMesh"
    log.write_text("satir1\nFOAM FATAL IO ERROR: bozuk\nFOAM exiting\n", encoding="utf-8")
    ozet = _log_kuyrugu(str(log))
    assert "FOAM FATAL IO ERROR" in ozet, "hata metni logun İÇERİĞİNİ taşımıyor"

    assert _log_kuyrugu(None) == ""
    assert "okunamadı" in _log_kuyrugu(str(tmp_path / "yok.log"))
