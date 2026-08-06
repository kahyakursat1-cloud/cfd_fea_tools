"""Raporu YAZAN kod — bu depoda en çok avlanan kusur sınıfının yaşadığı yer.

Belirsizlik matematiği zaten kapsanmış (`band_from_levels` %100,
`least_squares_gci` %100, `compute_gci` %92). Kapsanmayan `VVReport.build`:
618 satırlık modülün 433 satırı, %62'si test edilmemişti. Doğru matematikle
YANLIŞ rapor mümkündür ve bu oturumda üç kez oldu:

  - VLM band metni ölçülen seriyi GÖMMÜŞTÜ; kümeleme eklenip seri monotonlaşınca
    metin "MONOTON DEGIL" demeye DEVAM ETTİ
  - kanıt yazıcının y⁺ cümlesi sabitti; y⁺ 5399→129'a inince veriyle çelişti
  - band iki yönlü aileye geçince metin hâlâ TEK yönlü dosyayı gösteriyordu

Bu testler sabit çıktı değil, RAPORUN KENDİ VERİSİYLE TUTARLILIĞINI bağlar.
"""
import json
import re

import pytest

from report_generator import VVReport, _fea_val_error_pct


@pytest.fixture
def rapor(tmp_path):
    return VVReport(out_dir=str(tmp_path))


def _oku(r) -> str:
    """VVReport çıktıyı `self.out / VV_report.md` içine yazar."""
    p = r.out / "VV_report.md"
    assert p.exists(), "rapor markdown üretmedi"
    return p.read_text(encoding="utf-8")


class TestFeaHataCikarimi:
    """`_fea_val_error_pct` fea_validation*.json şemalarından EN KÖTÜ hatayı
    çıkarır. Şema dosyadan dosyaya değişiyor (sehim/gerilme/analitik/fem) ve
    yanlış çıkarım, doğrulama tablosunda İYİMSER bir sayı gösterir."""

    def test_EN_KOTU_hata_seciliyor(self):
        d = {"sehim": {"hata_pct": 1.0}, "gerilme": {"hata_pct": 4.8}}
        assert _fea_val_error_pct(d) == 4.8

    def test_ic_ice_semada_da_buluyor(self):
        d = {"fem": {"analitik": {"tepe": {"hata_pct": 2.5}}}, "x": [{"hata_pct": 7.1}]}
        assert _fea_val_error_pct(d) == 7.1

    def test_hata_yoksa_None(self):
        """Bulunamayan hata SIFIR sayılmamalı — 'ölçülmedi' ile 'hatasız'
        aynı şey değildir (bu ayrım Δ_entegrasyon'da bir kez kaybolmuştu)."""
        assert _fea_val_error_pct({"vaka": "x", "sonuc": "GECTI"}) is None

    def test_sayi_olmayan_deger_YUTULMUYOR(self):
        assert _fea_val_error_pct({"a": {"hata_pct": "yok"}}) is None


class TestRaporTutarliligi:
    """Rapor, üzerinde çalıştığı veriyle ÇELİŞMEMELİ."""

    # GERCEK SEMA: seviye LISTESI (h, cells, Cd); GCI raporun ICINDE hesaplanir.
    # Kup capasinin olculen degerleri (gci_kup_arac.json).
    _MESH = [
        {"name": "cokkaba", "h": 23968 ** (-1 / 3), "cells": 23968, "Cd": 0.90397},
        {"name": "kaba", "h": 82201 ** (-1 / 3), "cells": 82201, "Cd": 0.95523},
        {"name": "orta", "h": 267305 ** (-1 / 3), "cells": 267305, "Cd": 1.06849},
        {"name": "ince", "h": 888377 ** (-1 / 3), "cells": 888377, "Cd": 1.11332},
    ]

    def test_ZARF_TABLOSU_raporun_basinda(self, rapor):
        """Zarf tablosu kanıtlardan üretilir; rapor kendi bölümlerini eski JSON
        kümesinden kurduğu için tablo YOKSA rapor eski kanıtı yansıtır."""
        rapor.build(mesh_indep=self._MESH)
        md = _oku(rapor)
        assert "Çalışma Zarfı" in md
        i_zarf, i_ilk = md.index("Çalışma Zarfı"), md.index("## 1")
        assert i_zarf < i_ilk, "zarf tablosu bölümlerden SONRA geliyor"

    def test_GCI_KANONIK_hesapla_AYNI(self, rapor):
        """Rapordaki GCI, kanonik `compute_gci` ile AYNI olmalı. Rapor kendi
        hesabını yaparsa iki sayı sessizce ayrışır — bu depoda tam bu sınıf
        hata (band/metin ayrışması) üç kez yaşandı."""
        from report_generator import compute_gci
        # compute_gci EN INCE UC kademeyi alir (h_coarse, h_med, h_fine, ...)
        uc = sorted(self._MESH, key=lambda m: -m["h"])[-3:]
        beklenen = compute_gci(uc[0]["h"], uc[1]["h"], uc[2]["h"],
                               uc[0]["Cd"], uc[1]["Cd"], uc[2]["Cd"])
        rapor.build(mesh_indep=self._MESH)
        md = _oku(rapor)
        assert f"{beklenen['gci_fine_pct']}" in md, "rapordaki GCI kanonikle ayni degil"
        assert f"{beklenen['p']}" in md, "gozlenen mertebe p raporda yok/farkli"

    def test_SEVIYE_TABLOSU_girdiyle_ayni(self, rapor):
        """Tablodaki her Cd, verilen kademeden gelmeli."""
        rapor.build(mesh_indep=self._MESH)
        md = _oku(rapor)
        for m in self._MESH:
            assert f"{m['Cd']:.4f}" in md, f"{m['name']} kademesi tabloda yok"

    def test_MONOTONLUK_hukmu_seriyle_TUTARLI(self, rapor):
        """Seri monoton DEĞİLKEN rapor 'monoton' dememeli."""
        bozuk = [{**m, "Cd": cd} for m, cd in
                 zip(self._MESH, (0.90, 1.20, 1.05, 1.11))]
        rapor.build(mesh_indep=bozuk)
        md = _oku(rapor)
        blok = md[:md.index("## 2")] if "## 2" in md else md
        if "monoton" in blok.lower():
            assert re.search(r"monoton\s+(değil|DEĞİL|degil)", blok, re.I), \
                "seri monoton değilken rapor 'monoton' diyor"

    def test_VERI_YOKSA_bolum_UYDURULMUYOR(self, rapor):
        """Girdi verilmeyen bölüm için rapor sayı üretmemeli."""
        rapor.build()
        md = _oku(rapor)
        assert "0.0000" not in md.replace("0.00000", ""), \
            "veri yokken sıfır değerler basılmış olabilir"

    def test_RAPOR_uretim_bilgisi_tasiyor(self, rapor):
        rapor.build(mesh_indep=self._MESH, project="TestArac")
        md = _oku(rapor)
        assert "TestArac" in md
        assert "ASME V&V 20" in md, "hangi standarda göre raporlandığı yazılı değil"


class TestZarfEntegrasyonu:
    """Rapor zarf tablosunu KANITTAN alır; kopyalamaz."""

    def test_zarf_tablosu_kanittan_URETILIYOR(self, rapor):
        import zarf
        rapor.build()
        md = _oku(rapor)
        tablo = zarf.zarf_tablosu()
        ilk_satir = next(s for s in tablo.splitlines()
                         if s.startswith("|") and "Koşul" not in s and "---" not in s)
        anahtar = ilk_satir.split("|")[1].strip()[:28]
        assert anahtar in md, "rapordaki zarf tablosu zarf.py ile aynı değil"


def test_KANIT_dosyalari_semasi_BOZULMAMIS():
    """_fea_val_error_pct gerçek kanıt dosyalarında da çalışmalı; şema
    değişirse doğrulama tablosu SESSİZCE boşalır."""
    from pathlib import Path
    kok = Path(__file__).resolve().parent.parent
    bulunan = 0
    for p in sorted(kok.glob("fea_validation*.json")):
        h = _fea_val_error_pct(json.loads(p.read_text(encoding="utf-8")))
        if h is not None:
            bulunan += 1
            assert 0 <= h < 100, f"{p.name}: makul olmayan hata {h}"
    assert bulunan >= 3, f"yalnız {bulunan} kanıttan hata çıkarılabildi — şema kaymış olabilir"


class TestKanonikBand:
    """Band TEK KAYNAKTAN gelmeli: `band_from_levels` hiyerarşisi.

    ÖLÇÜLDÜ (küp, 4 kademe): rapor 3-kademe Richardson'ı tek başına basıyordu
    (%3.15) ama kanonik kural LSR ile %58.33 (asimptotik-altı, p<0.5) diyor —
    18.5 kat, ve rapor İYİMSER olanı gösteriyordu. Hiyerarşi tam da "iyi
    görünen üç kademeyi seçmeyi" engellemek için var.
    """

    _MESH = TestRaporTutarliligi._MESH

    def test_KANONIK_band_raporda(self, rapor):
        from report_generator import band_from_levels
        beklenen = band_from_levels([m["cells"] for m in self._MESH],
                                    [m["Cd"] for m in self._MESH], boyut=3)
        rapor.build(mesh_indep=self._MESH)
        md = _oku(rapor)
        assert f"{beklenen['u_pct']}" in md, "kanonik band raporda yok"
        assert beklenen["yontem"] in md or beklenen["kaynak"][:12] in md

    def test_IYIMSER_3_kademe_UYARIYLA_veriliyor(self, rapor):
        """3-kademe GCI kanonikten belirgin küçükse rapor bunu SÖYLEMELİ;
        iki sayıyı yan yana gerekçesiz koymak okuyucuyu yanıltır."""
        rapor.build(mesh_indep=self._MESH)
        md = _oku(rapor)
        assert "yalnız BİLGİ" in md or "yalnız BILGI" in md
        assert "Geçerli olan kanonik banddır" in md

    def test_HUCRE_yoksa_kanonik_band_IDDIA_EDILMIYOR(self, rapor):
        """cells verilmezse h^-3 tabanı kurulamaz; band uydurulmamalı."""
        hucresiz = [{k: v for k, v in m.items() if k != "cells"}
                    for m in self._MESH]
        rapor.build(mesh_indep=hucresiz)
        md = _oku(rapor)
        assert "KANONİK" not in md
