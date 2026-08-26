"""2-yönlü FSI çapası: engelin YERİ ölçülür.

DIŞ HAKEM P3 (2026-08-26) engeli donanıma bağladı: ``uygun vaka ~94,1 M
hücre, ~73 GB.'' O sayı gerçek ama BİR TEK GEOMETRİ AİLESİNE ait --- deponun
kendi araç gövdesi. `fsi_tahrik_fizibilite.json`ın kendi kısıtı zaten
``bu bir DONANIM sorunundan çok bir GEOMETRİ-AİLESİ sorunudur'' diyordu ve
başka aile hiç değerlendirilmemişti.

ÖLÇÜLDÜ: kanonik Turek--Hron benchmark'ında üç varyantın da bütçesi
164.000 hücre / 0,425 GB --- yani DONANIM ENGEL DEĞİL. FSI2/FSI3'ü kapatan
şey YAPISAL YETENEKTİR ve bu farklı bir engel, farklı bir çare: ölçüm
yapıldığında iki yetenek eksikti (büyük yer-değiştirme ve zaman-çözünür
yapısal analiz). NLGEOM 2026-08-27'de eklendi ve doğrulandı
(`nlgeom_dogrulama.json`); geriye zaman-çözünür yapısal analiz kaldı.
Testler tek bir günün durumunu değil KAYNAĞIN kendisini okur.

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


def test_FSI2_ve_FSI3_engeli_ASLA_BUTCE_degil():
    """Bulgunun çekirdeği: bu vakalar bütçe yüzünden kapalı DEĞİL.

    OLCUT BIR ANI DEGIL BIR KURALI BAGLAR. Ilk surum "engeller BOS OLMAMALI
    ve YETENEK demeli" diyordu --- o gunku durumu pinliyordu. NLGEOM ve
    *DYNAMIC eklenince engel KALKTI ve test dustu; oysa kalkması ISTENEN
    seydi. Degismeyen kural su: engel ne olursa olsun BUTCE olmamali,
    cunku uc varyantin da hucre kestirimi ayni.
    """
    r = F.olc()
    for ad in ("FSI2", "FSI3"):
        engeller = r["capalar"][ad]["engeller"]
        assert not any("BÜTÇE" in e for e in engeller),             f"{ad} bütçeden düşüyor — 'donanım engel değil' bulgusu geçersiz"


def test_ENGEL_LISTESI_YETENEK_DENETIMIYLE_tutarli():
    """Engel listesi yetenek denetiminden TÜRETİLMELİ; ikisi ayrışırsa
    kayıt kendi içinde çelişir ve hangisinin doğru olduğu bilinemez."""
    r = F.olc()
    y = r["yapisal_yetenek"]
    for ad, v in r["capalar"].items():
        nl_engel = any("NLGEOM" in e for e in v["engeller"])
        dn_engel = any("zaman-çözünür" in e for e in v["engeller"])
        assert nl_engel == (v["nlgeom_gerekir"] and not y["nlgeom"]), ad
        assert dn_engel == (v["rejim"] == "zamana bağlı"
                            and not y["zaman_cozunur_yapisal"]), ad


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
    # ULASILABILIR LISTESI bir ANI degil, YETENEGIN sonucudur.
    # Ilk surum == ["FSI1"] diyordu ve iki yetenek eklenince dustu ---
    # oysa listenin buyumesi ISTENEN seydi.
    src = (KOK / "analysis" / "calculix_writer.py").read_text(encoding="utf-8")
    assert d["yapisal_yetenek"]["nlgeom"] == ("NLGEOM" in src.upper())
    assert "FSI1" in d["ulasilabilir_capalar"],         "en ucuz varyant bile ulaşılamaz görünüyor"


def test_ULASILABILIR_KOSULDU_DEMEK_DEGIL():
    """En tehlikeli okuma. Uc varyantin da engeli kalkinca kayit
    "dogrulandi" gibi okunabilir; oyle DEGIL --- hicbiri kosulmadi."""
    r = F.olc()
    if len(r["ulasilabilir_capalar"]) == len(r["capalar"]):
        assert "doğrulanmış da DEĞİLLER" in r["verdikt"],             "engel kalktı ama 'koşulmadı' uyarısı yok"
    assert "KOSULDU demek DEGILDIR" in r["_kisit"]
