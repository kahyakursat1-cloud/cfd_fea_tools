"""Ortam kapısının DİŞLERİ var mı: bayat/eksik ölçümü geçirmemeli.

Kapı "konteyner masaüstüyle aynı sonucu verir" iddiasını sürüm öncesi bağlar.
Bu iddia başsız dağıtımın TEK gerekçesidir, ve tek seferlik bir ölçüm bir
sonraki imaj inşasında sessizce geçersizleşir.

Testler kapıyı BİLEREK KIRARAK sınar: her engeli ayrı ayrı tetikleyip kapının
gerçekten durduğunu görür. Yalnız yeşil halini sınayan bir test, kapının hiçbir
şey kontrol etmemesi durumunda da geçerdi --- bu deponun tekrar tekrar ölçtüğü
kusur sınıfı tam olarak budur.
"""
import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import ortam_kapisi as ok  # noqa: E402

GECERLI = {
    "damga": {"olcum_zamani": "2026-08-15 16:00", "kaynak_islemesi": "abc1234",
              "kaynak_kirli": False, "konteyner_imaji": "sha256:aaa"},
    "ayar": {"tip": "roket", "hiz": 20.0, "kalite": "standart"},
    "esik_yuzde": 1.0, "fark_yuzde": 0.099,
    "ortamlar_ortusuyor": True, "sinif_ayni": True,
    "hucre_sayilari": {"host": 316514, "konteyner": 316514},
    "kosular": [{"ortam": "host-wsl", "cd": 0.14124}, {"ortam": "konteyner", "cd": 0.14138}],
}


@pytest.fixture
def kur(tmp_path, monkeypatch):
    """Ölçüm dosyasını ve dış komutları taklit et."""
    def _kur(veri: dict | None, imaj: str | None = "sha256:aaa", islem: str | None = "abc1234"):
        yol = tmp_path / "ortam_capraz_olcumu.json"
        if veri is not None:
            yol.write_text(json.dumps(veri), encoding="utf-8")
        monkeypatch.setattr(ok, "OLCUM", yol)
        monkeypatch.setattr(ok, "_guncel_imaj", lambda: imaj)
        monkeypatch.setattr(ok, "_kabuk", lambda argv: islem if "rev-parse" in argv else None)
        return {k["ad"]: k for k in ok.denetle()}
    return _kur


def test_gecerli_olcum_GECER(kur):
    ks = kur(GECERLI)
    dusen = [a for a, k in ks.items() if not k["gecti"]]
    assert not dusen, f"geçerli ölçüm reddedildi: {dusen}"


def test_olcum_YOKSA_durur(kur):
    ks = kur(None)
    assert not all(k["gecti"] for k in ks.values())


def test_DAMGASIZ_olcum_durur(kur):
    """Damgasız dosya, hangi imaj/kaynak üzerinde üretildiğini söyleyemez."""
    v = {k: x for k, x in GECERLI.items() if k != "damga"}
    assert not kur(v)["ölçüm damgası"]["gecti"]


def test_IMAJ_degistiyse_durur(kur):
    """Sayılar geçse bile: ölçüm başka bir imaj üzerinde yapılmışsa geçersiz."""
    ks = kur(GECERLI, imaj="sha256:BASKA")
    assert not ks["imaj tazeliği"]["gecti"]


def test_KAYNAK_ilerlediyse_durur(kur):
    ks = kur(GECERLI, islem="ffff999")
    assert not ks["kaynak tazeliği"]["gecti"]


def test_KIRLI_agacta_olculduyse_durur(kur):
    """Kirli ağaçtaki işleme damgası kaynağı tanımlamaz: aynı hash, başka kod."""
    v = json.loads(json.dumps(GECERLI))
    v["damga"]["kaynak_kirli"] = True
    assert not kur(v)["ölçüm temiz ağaçta"]["gecti"]


def test_konteyner_AYAKTA_DEGILSE_gecmez(kur):
    """Doğrulanamayan tazelik 'geçti' sayılmaz --- eksik kanıt olumlu kanıt değildir."""
    ks = kur(GECERLI, imaj=None)
    assert not ks["konteyner erişimi"]["gecti"]


def test_SINIF_ayrisirsa_durur(kur):
    """Sayı örtüşüp hüküm ayrışırsa iki ortam aynı sonucu vermiyordur."""
    v = json.loads(json.dumps(GECERLI))
    v["sinif_ayni"] = False
    assert not kur(v)["geçerlilik sınıfı aynı"]["gecti"]


def test_AG_ayrisirsa_durur(kur):
    v = json.loads(json.dumps(GECERLI))
    v["hucre_sayilari"] = {"host": 316514, "konteyner": 316000}
    assert not kur(v)["ağ bit-aynı"]["gecti"]


def test_ESIK_asilirsa_durur(kur):
    v = json.loads(json.dumps(GECERLI))
    v["ortamlar_ortusuyor"], v["fark_yuzde"] = False, 4.2
    assert not kur(v)[f"Cd farkı ≤ %{v['esik_yuzde']}"]["gecti"]
