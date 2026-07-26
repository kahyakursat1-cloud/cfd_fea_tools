"""Çalışma zarfı tablosu README ile kanıt arasında sürüklenmesin.

Bu testin varlık sebebi somut: README "Mesh yakınsama ✅ GCI %0.09" derken aynı
vaka için VV_report "p asimptotik dışı — GÖSTERİLEMEDİ" diyordu. Tablo artık
kanıttan üretiliyor; test, üretilenin README'ye yazılmış olduğunu doğrular.
"""
import zarf


def test_readme_zarf_tablosu_guncel():
    metin = (zarf.ROOT / "README.md").read_text(encoding="utf-8")
    assert zarf.BASLANGIC in metin and zarf.BITIS in metin, "README'de zarf işaretçileri yok"
    blok = metin[metin.index(zarf.BASLANGIC) + len(zarf.BASLANGIC):metin.index(zarf.BITIS)]
    assert blok.strip() == zarf.zarf_tablosu().strip(), (
        "README zarf tablosu kanıtla uyuşmuyor — `python zarf.py --yaz` çalıştır")


def test_kanit_yoksa_satir_dusmez(monkeypatch):
    """Kanıt dosyası silinirse satır sessizce kaybolmaz; 'kanıt yok' der."""
    def _yok(ad):
        raise FileNotFoundError(2, "yok", ad)
    monkeypatch.setattr(zarf, "_json", _yok)
    t = zarf.zarf_tablosu()
    assert t.count("\n") == len(zarf.SATIRLAR) + 1          # başlık + ayraç + satırlar
    assert "❓ Kanıt yok" in t
    assert "tmr_gci_verdict.json` bulunamadı" in t


def test_verdikt_kanonik_fonksiyondan():
    """Zarf, GCI hükmünü kendi eşiğiyle değil report_generator ile vermeli."""
    import json

    from report_generator import compute_gci, gci_verdict

    lv = json.loads((zarf.ROOT / "mesh_independence.json").read_text(encoding="utf-8"))["levels"]
    g = compute_gci(*[x["h"] for x in lv], *[x["Cd"] for x in lv])
    beklenen_ok = gci_verdict(g).startswith("✅")
    guv, _ = zarf._arac_mesh()
    assert guv.startswith("✅") == beklenen_ok
