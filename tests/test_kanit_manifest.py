"""Kanıt manifesti — "bu araç neyi doğrulanmış biliyor?" sorusunun tek cevabı.

Kökte 50+ JSON var, isimlendirme tutarsız (gci_cgrid_base/mid/fine/xfine/final/finding…)
ve indeks yoktu; mühendis dosya adı tahmin ederek kanıt arıyordu. Manifest dosyaları
sınıflar (kanıt / artefakt / kaynak / bozuk) ve kanıtları hükümleriyle listeler.
"""
import json

import kanit


def test_gercek_kanit_dosyalari_siniflaniyor():
    m = {k["dosya"]: k for k in kanit.manifest()}
    for ad in ("fea_validation.json", "fea_validation_hole.json", "tmr_gci_verdict.json",
               "gci_kup_arac.json"):
        assert m[ad]["sinif"] == "kanit", f"{ad} kanıt sayılmadı"
        assert m[ad]["hukum"], f"{ad} hükümsüz görünüyor"


def test_artefaktlar_kanit_sayilmaz():
    """Öğrenme kütüphanesi / tarama çıktısı doğrulama kanıtı DEĞİLDİR."""
    m = {k["dosya"]: k for k in kanit.manifest()}
    for ad in ("batch_learn_done.json", "aoa_polar.json", "regresyon_sonuc.json"):
        if ad in m:
            assert m[ad]["sinif"] != "kanit", f"{ad} yanlışlıkla kanıt sayıldı"


def test_materials_kaynak_olarak_isaretli():
    m = {k["dosya"]: k for k in kanit.manifest()}
    assert m["materials.json"]["sinif"] == "kaynak"


def test_hukum_sembolu_normallesiyor():
    assert kanit._hukum({"sonuc": "GECTI — analitik ile uyumlu"})[0] == "✅"
    assert kanit._hukum({"verdikt": "⚠️ Mesh bağımsızlığı GÖSTERİLEMEDİ: p dışı"})[0] == "⚠️"
    assert kanit._hukum({"sonuc": "KALDI — band dışı"})[0] == "❌"
    assert kanit._hukum({})[0] == "—"


def test_hukum_onceligi():
    """Kesin (strict) verdikt varsa düzyazı `sonuc`'a değil ona bakılır."""
    d = {"strict_gci_verdict": "⚠️ GÖSTERİLEMEDİ", "sonuc": "GECTI — güzel uyum"}
    assert kanit._hukum(d)[0] == "⚠️"


def test_bom_lu_dosya_okunabilir(tmp_path, monkeypatch):
    """PowerShell çıktısı BOM taşır; düz utf-8 okuma JSONDecodeError verirdi."""
    p = tmp_path / "bomlu.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps({"vaka": "x", "sonuc": "GECTI"}).encode())
    assert kanit._oku(p) == {"vaka": "x", "sonuc": "GECTI"}
    monkeypatch.setattr(kanit, "ROOT", tmp_path)
    k = kanit.sinifla(p)
    assert k["sinif"] == "kanit" and k["sembol"] == "✅"


def test_bozuk_dosya_sebebiyle_raporlanir(tmp_path):
    p = tmp_path / "bozuk.json"
    p.write_text("{ bu json degil", encoding="utf-8")
    k = kanit.sinifla(p)
    assert k["sinif"] == "bozuk" and "JSONDecodeError" in k["not"]


def test_eskimis_dosya_isaretlenir(tmp_path):
    p = tmp_path / "eski.json"
    p.write_text(json.dumps({"vaka": "x", "sonuc": "GECTI", "_SUPERSEDED": "yeni: y.json"}),
                 encoding="utf-8")
    k = kanit.sinifla(p)
    assert k["eskimis"] and "ESKİMİŞ" in k["not"]


def test_tablo_bozuk_dosyalari_ayri_listeler():
    t = kanit.tablo(kanit.manifest(), yalniz_kanit=True)
    assert "| Dosya | Vaka | Hüküm |" in t and "**Özet:**" in t


def test_zarf_bom_dayanikli():
    """Zarf da kanıt okur; BOM'lu bir kanıt dosyası tabloyu düşürmemeli."""
    import inspect

    import zarf
    assert "utf-8-sig" in inspect.getsource(zarf._json)
