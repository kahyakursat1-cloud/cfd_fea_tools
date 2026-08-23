"""Kayıtlı hükümler bayatlıyor mu — ve bayatlık HANGİ YÖNDE.

ÖLÇÜLDÜ 2026-08-23 (uçtan uca gerileme testi bunu yüzeye çıkardı): 23 kayıtlı
koşunun 15'inde kalem-düzeyi hüküm bayat ve on beşi de AYNI yönde --- kayıt
`C_L: VALIDATED, tasarım-güvenli EVET` diyor, bugünkü kod `TREND, HAYIR`.
Yani bayat hüküm DAHA GEVŞEK: kayıt, bugünkü aracın vermeyeceği bir güvence
vaat ediyor.

NEDEN MEVCUT KAPILAR GÖRMEDİ: genel sınıf (`validity.sinif`) ikisinde de aynı
kalıyor. Genel sınıfa bakan bir tarama 23/23 "aynı" der --- ilk taramam tam
bunu yaptı ve bayatlığı hiç görmedi. Fark yalnız `kalemler` içinde.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from hukum_tazeligi import _yon, ozet, tara  # noqa: E402


def test_YON_gevseklik_sirasina_gore():
    """Gevşeyen bayatlık TEHLİKELİ, sıkılaşan yalnız muhafazakâr.

    İkisi tek sayıda toplanırsa hüküm verilemez.
    """
    assert _yon("VALIDATED", "TREND") == "gevşek"
    assert _yon("TREND", "OUT") == "gevşek"
    assert _yon("OUT", "TREND") == "sıkı"
    assert _yon("TREND", "TREND") == "aynı"


def test_GENEL_SINIF_bayatligi_GIZLIYOR():
    """Bu testin varlık sebebi: neden daha önce yakalanmadı.

    Kayıtlı ve bugünkü genel sınıf aynıyken kalemler farklı olabilir. Genel
    sınıfa bakan bir denetim bunu göremez.
    """
    p = KOK / "hukum_tazeligi.json"
    if not p.exists():
        pytest.skip("hukum_tazeligi.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    if not d["bayat_kosular"]:
        pytest.skip("bayat koşu yok — bu ortamda gösterilemez")
    # Bayat kosularin HEPSINDE fark KALEM duzeyinde
    for b in d["bayat_kosular"]:
        assert b["farklar"], f"{b['kosu']}: bayat ama fark listesi boş"
        for f in b["farklar"]:
            assert f["kayitli"] != f["bugun"]


def test_KANIT_yonu_ADIYLA_yaziyor():
    p = KOK / "hukum_tazeligi.json"
    if not p.exists():
        pytest.skip("hukum_tazeligi.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "gevseyen_kosu" in d
    if d["gevseyen_kosu"]:
        assert "GEVŞEK" in d["verdikt"]
        # Tehlikeli yon SAYIYLA gorunmeli
        assert str(d["gevseyen_kosu"]) in d["verdikt"]


def test_ESKI_kayitlar_YENIDEN_YAZILMIYOR():
    """Hüküm, koşunun üretildiği andaki kodun ifadesidir.

    Üstüne bugünkü hükmü yazmak tarihi siler ve koşunun girdileri tam geri
    kurulamıyorsa YANLIŞ da olabilir. Ölçer yalnız FARKI raporlar.
    """
    import ast
    src = (KOK / "hukum_tazeligi.py").read_text(encoding="utf-8")
    assert "YENIDEN YAZILMIYOR" in src

    # OLCUT IDDIASINA UYMALI. Ilk surum "hic write_text olmasin" diyordu ve
    # olcer KENDI KANIT dosyasini yazmaya baslayinca dustu — yazmanin kendisi
    # degil, NEREYE yazildigi yasak. AST ile yazma hedefleri toplanir.
    hedefler = []
    for d in ast.walk(ast.parse(src)):
        if (isinstance(d, ast.Call)
                and getattr(d.func, "attr", None) == "write_text"):
            hedefler.append(ast.unparse(d.func.value))
    assert hedefler, "ölçer hiç dosya yazmıyor — kanıt üretimi düşmüş olabilir"
    for h in hedefler:
        assert "sonuc" not in h, (
            f"ölçer koşu kaydına yazıyor ({h}) — eski hükmün üstüne bugünküyü "
            f"yazmak tarihi siler")
        assert "hukum_tazeligi" in h, f"beklenmeyen yazma hedefi: {h}"


def test_OLCUT_rapor_ureticisinin_KENDI_yolundan_geciyor():
    """Ayrı bir sınıflandırma kurmak İKİNCİ KAYNAK yaratırdı.

    O zaman ölçer, kodla kayıt arasındaki farkı değil kendi yorumuyla kod
    arasındaki farkı ölçerdi.
    """
    src = (KOK / "hukum_tazeligi.py").read_text(encoding="utf-8")
    assert "build_vehicle_report" in src
    assert "classify_cfd" not in src, "ölçer kendi sınıflandırmasını kuruyor"


def test_CANLI_yol_tek_kosuda_kosuyor(tmp_path):
    """`tara()` gerçekten koşuyor mu — ama TEK koşuyla.

    Tüm arşivi taramak 23 rapor üretiyor ve süiti ~2 dakika uzatıyordu. Sınanan
    şey muhasebe ve okuma yolu; onun için bir koşu yeter. Kapsamın tamamı
    ölçerin kendi çalıştırmasında (`python hukum_tazeligi.py`) ölçülür.
    """
    kaynak = next((p for p in sorted((KOK / "vehicle_runs").glob("*/sonuc.json"))
                   if json.loads(p.read_text(encoding="utf-8")).get("status") == "ok"
                   and (json.loads(p.read_text(encoding="utf-8")).get("validity")
                        or {}).get("kalemler")), None)
    if kaynak is None:
        pytest.skip("hüküm taşıyan kayıtlı koşu yok")
    hedef = tmp_path / kaynak.parent.name
    hedef.mkdir()
    (hedef / "sonuc.json").write_text(kaynak.read_text(encoding="utf-8"),
                                      encoding="utf-8")
    o = ozet(tara(tmp_path))
    assert o["toplam_kosu"] == 1
    assert o["taze"] + o["bayat"] == o["toplam_kosu"], "muhasebe tutmuyor"


def test_OLCULEMEYEN_kosu_TAZE_sayilmiyor():
    """Yokluğun hükmü yok: rapor üretilemeyen koşu 'aynı' sayılamaz."""
    p = KOK / "hukum_tazeligi.json"
    if not p.exists():
        pytest.skip("hukum_tazeligi.json üretilmemiş")
    o = json.loads(p.read_text(encoding="utf-8"))
    assert o["taze"] + o["bayat"] == o["toplam_kosu"]
    for x in o["olculemeyen"]:
        assert x["neden"], "gerekçesiz ölçülemeyen"
