"""2-yönlü FSI çapası: engelin YERİ ölçülür.

DIŞ HAKEM P3 (2026-08-26) engeli donanıma bağladı: ``uygun vaka ~94,1 M
hücre, ~73 GB.'' O sayı gerçek ama BİR TEK GEOMETRİ AİLESİNE ait --- deponun
kendi araç gövdesi. `fsi_tahrik_fizibilite.json`ın kendi kısıtı zaten
``bu bir DONANIM sorunundan çok bir GEOMETRİ-AİLESİ sorunudur'' diyordu ve
başka aile hiç değerlendirilmemişti.

ÖLÇÜLDÜ: kanonik Turek--Hron benchmark'ında üç varyantın da bütçesi
164.000 hücre / 0,425 GB --- yani DONANIM ENGEL DEĞİL. FSI2/FSI3'ü kapatan
şey YAPISAL YETENEKTİR: büyük yer-değiştirme (NLGEOM) ve zaman-çözünür
yapısal analiz yok. Bu farklı bir engel ve farklı bir çare.

Bu testler bulguyu ve dayanaklarını bağlar --- özellikle YETENEK denetiminin
kaynaktan okunduğunu: bir belgeye ya da hatıraya dayanan yetenek iddiası,
kod değiştiğinde sessizce yanlış olur.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

import fsi_capa_ulasilabilirlik as F  # noqa: E402

KANIT = KOK / "fsi_capa_ulasilabilirlik.json"


def test_YETENEK_KAYNAKTAN_okunuyor_varsayilmiyor():
    """Yetenek iddiası koddan gelmeli; belgeye dayanan iddia sessizce eskir."""
    y = F._yapisal_yetenek()
    assert y["okunabildi"], y
    assert "STATIC" in y["analiz_tipleri"], "yazıcı STATIC'i bile taşımıyor mu?"
    # NLGEOM YOKSA bu bir GERCEK: yazicida gecmemeli.
    src = (KOK / "analysis" / "calculix_writer.py").read_text(encoding="utf-8")
    assert y["nlgeom"] == ("NLGEOM" in src.upper())


def test_UC_VARYANT_da_AYNI_BUTCEDE_kaliyor():
    """Bulgunun çekirdeği: FSI2/FSI3 bütçe yüzünden kapalı DEĞİL.

    Ucunun de hucre kestirimi ayni cikmali (bayrak kalinligi ayni); farkli
    ciksaydi "engel butce" savunmasi ayakta kalirdi.
    """
    r = F.olc()
    butceler = {v["butce"]["hucre_tekduze_ust_sinir"]
                for v in r["capalar"].values()}
    assert len(butceler) == 1, f"varyantlar farklı bütçede: {butceler}"


def test_FSI2_ve_FSI3_engeli_YETENEK_diyor():
    r = F.olc()
    for ad in ("FSI2", "FSI3"):
        engeller = r["capalar"][ad]["engeller"]
        assert engeller, f"{ad} engelsiz görünüyor"
        assert any("YETENEK" in e for e in engeller), \
            f"{ad} engeli yetenek olarak adlandırılmıyor: {engeller}"
        # BUTCE ENGELI OLMAMALI --- bulgunun tersi olurdu
        assert not any("BÜTÇE" in e for e in engeller), \
            f"{ad} bütçeden düşüyor — bulgu geçersiz"


def test_FSI1_ULASILABILIR_ama_HAKEMIN_SORDUGUNU_kapatmiyor():
    """Ulaşılabilir olmak, sorulan soruyu kapatmak demek değildir.

    FSI1 kucuk-sehim rejimindedir: akis kayda deger olcude degismez, yani
    'fizik tahrik ediyor' iddiasini SINAMAZ. Bunu yazmamak, bir capa kosup
    'iki yonlu FSI dogrulandi' demeye kapi acardi.
    """
    r = F.olc()
    f1 = r["capalar"]["FSI1"]
    assert f1["ulasilabilir"] is True and not f1["engeller"]
    assert f1["nlgeom_gerekir"] is False
    assert "SINAMAZ" in f1["ne_kapatmaz"] or "SINAMAZ" in r["verdikt"]
    assert "KAPATMAZ" in r["verdikt"]


def test_VERDIKT_engeli_DONANIMA_yuklemiyor():
    """Hakemin çerçevesi (donanım) ölçümle çürüdü; verdikt bunu söylemeli."""
    r = F.olc()
    assert "DONANIM DEĞİL" in r["verdikt"]
    assert "94,1" in r["verdikt"], "94,1 M'lik tahminin kapsamı yazılmıyor"


def test_KISIT_ULASILABILIR_ile_KOSULDU_yu_ayiriyor():
    """En tehlikeli okuma: 'ulaşılabilir' = 'yapıldı'."""
    r = F.olc()
    assert "KOSULDU demek DEGILDIR" in r["_kisit"]
    assert "UST SINIRDIR" in r["_kisit"], "tekdüze-ağ varsayımı yazılmıyor"


def test_KAYIT_dosyasi_olcumle_TUTARLI():
    if not KANIT.exists():
        pytest.skip("fsi_capa_ulasilabilirlik.json üretilmemiş")
    d = json.loads(KANIT.read_text(encoding="utf-8"))
    assert d["ulasilabilir_capalar"] == ["FSI1"]
    assert d["yapisal_yetenek"]["nlgeom"] is False
