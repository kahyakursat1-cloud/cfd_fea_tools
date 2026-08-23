"""İş istasyonu kuyruğu — bütçeler KANITTAN okunuyor mu, elle mi yazılmış.

Bu oturumda kapanamayan her madde için bir fizibilite bütçesi ölçüldü ve ayrı
kanıt dosyalarına yazıldı. Liste elle derlenirse koşular yenilendiğinde
sessizce eskir --- bu deponun her yerde avladığı kusur. Bu testler listenin
üretilmiş olduğunu ve kısıtlarını taşıdığını bağlar.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))


@pytest.fixture(scope="module")
def kuyruk():
    p = KOK / "is_istasyonu_kuyrugu.json"
    if not p.exists():
        pytest.skip("is_istasyonu_kuyrugu.json üretilmemiş")
    return json.loads(p.read_text(encoding="utf-8"))


def test_HER_KALEM_bir_KANIT_dosyasina_dayaniyor(kuyruk):
    """Bütçesi olan her kalem, o bütçeyi ölçen dosyayı adıyla göstermeli."""
    for k in kuyruk["kalemler"]:
        assert k["kanit"], f"{k['is']}: kanıt dosyası yazılmamış"
        assert (KOK / k["kanit"]).exists(), f"{k['is']}: {k['kanit']} yok"


def test_BELLEK_sayilari_kanittaki_ile_AYNI(kuyruk):
    """Sayı elle kopyalanmışsa kanıt yenilendiğinde ayrışır."""
    ahmed = next((k for k in kuyruk["kalemler"] if "Ahmed" in k["is"]), None)
    if ahmed:
        b = json.loads((KOK / ahmed["kanit"]).read_text(encoding="utf-8"))
        assert ahmed["bellek_GB"] == pytest.approx(
            b["ahmed_butcesi"]["bellek_gb"], abs=1e-9)
    les = next((k for k in kuyruk["kalemler"] if "LES" in k["is"]), None)
    if les:
        b = json.loads((KOK / les["kanit"]).read_text(encoding="utf-8"))
        assert les["bellek_GB"] == pytest.approx(b["butce"]["bellek_GB"], abs=1e-9)
        assert les["hucre"] == b["butce"]["hucre"]


def test_BELLEK_GEREKTIRMEYEN_kalemler_ayri_isaretli(kuyruk):
    """"Donanım açar" ile "koşu zamanı açar" farklı şeyler; karışırsa iş
    istasyonu alındığında yanlış beklenti doğar."""
    bellek = [k for k in kuyruk["kalemler"] if k["bellek_GB"]]
    zaman = [k for k in kuyruk["kalemler"] if not k["bellek_GB"]]
    assert bellek and zaman, "iki sınıf da temsil edilmeli"
    for k in zaman:
        assert k["tahmini_sure"], f"{k['is']}: süre/çapa kestirimi yok"
        assert k["is_istasyonunda"] is False, (
            f"{k['is']}: belleksiz kalem 'iş istasyonunda sığıyor' "
            f"işaretlenmiş — donanım onu açmaz")


def test_FSI_butcesi_BAND_oldugunu_soyluyor(kuyruk):
    """İyimser ucu tek sayı gibi sunmak, ölçülmemiş bir kesinlik yayımlamaktır."""
    f = next((k for k in kuyruk["kalemler"] if "FSI" in k["is"]), None)
    if f is None:
        pytest.skip("FSI kalemi yok")
    assert "BAND" in (f["_not"] or ""), "bütçenin band olduğu yazılmamış"
    assert "SIĞMAZ" in (f["_not"] or ""), "kötümser ucun sonucu yazılmamış"


def test_HER_KALEM_NEYI_ACTIGINI_soyluyor(kuyruk):
    """Maliyet tek başına karar verdirmez; ne kazanıldığı yazılı olmalı."""
    for k in kuyruk["kalemler"]:
        assert k["neyi_acar"], f"{k['is']}: neyi açtığı yazılmamış"
        assert len(k["neyi_acar"]) > 25


def test_SIRA_VERILMIYOR(kuyruk):
    """Öncelik mühendislik kararıdır; liste onu üstlenmemeli."""
    assert "SIRA VERILMEZ" in kuyruk["_kisit"]
    for k in kuyruk["kalemler"]:
        assert "oncelik" not in k and "sira" not in k


def test_URETICI_sayilari_GOMMUYOR():
    """Bütçe sayıları koda gömülürse liste kanıttan kopar.

    AST: modülde bellek/hücre mertebesinde sabit sayı olmamalı (eşik ve
    donanım kapasitesi dışında).
    """
    src = (KOK / "experiments" / "is_istasyonu_kuyrugu.py").read_text(encoding="utf-8")
    izinli = {192.0, 4.62, 10.0, 1.0, 0.0, 1e6, 1e-9, 2.0, 25.0}
    gomulu = []
    for d in ast.walk(ast.parse(src)):
        if isinstance(d, ast.Constant) and isinstance(d.value, (int, float)):
            v = float(d.value)
            if v > 100 and v not in izinli:
                gomulu.append(v)
    assert not gomulu, f"bütçe sayısı koda gömülmüş: {gomulu}"


def test_KANIT_EKSIK_olan_kalem_SESSIZCE_dusmuyor(kuyruk):
    """Bir kanıt dosyası yoksa kalem listeden çıkar; bu GÖRÜNMELİ."""
    assert "kanit_eksik" in kuyruk
    for ad in kuyruk["kanit_eksik"]:
        assert not (KOK / ad).exists(), f"{ad} var ama eksik sayılmış"
