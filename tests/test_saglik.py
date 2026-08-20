"""Sağlık toplayıcısı: düşen ölçer SESSİZCE listeden düşmemeli.

Toplayıcının tek asıl iddiası budur. Beş ölçeri koşup "hepsi temiz" demek
kolaydır; zor olan, ölçerlerden biri koşamazken bunu SÖYLEMEKTİR. Aksi halde
toplayıcı, kapsamı daralmış bir "✅" üretir — bu deponun 2026-08-20'de tam da
düzelttiği kusurun (taranamayan dosya sessizce atlanıyordu) bir kademe
yukarısı.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import pytest  # noqa: E402

import saglik  # noqa: E402


@pytest.fixture(scope="module")
def rapor():
    """Gercek tarama BIR KEZ kosar. Olculdu: kanit 35,9 s (git tarih sorgulari),
    oksuz_alan 6,3 s — her testte yeniden kosmak pakete ~3 dk ekliyordu."""
    return saglik.topla()


def test_bes_olcer_de_kosuyor(rapor):
    r = rapor
    assert len(r["olcerler"]) == 5
    assert [x["olcer"] for x in r["olcerler"]] == [a for a, _, _ in saglik.OLCERLER]
    for x in r["olcerler"]:
        assert x["olculdu"] is True, f"{x['olcer']}: {x['detay']}"
        assert x["soru"], x["olcer"]


def test_DUSEN_olcer_sessizce_listeden_DUSMEZ(monkeypatch):
    def _patlat():
        raise RuntimeError("olcer coktu")

    def _saglam():
        return {"toplam": 0, "acik": 0, "detay": "sınama", "taranamayan": []}

    # GERCEK olcerler KOSULMAZ: sinanan sey toplayicinin DUSEN olceri nasil
    # raporladigi, olcerlerin kendisi degil. Gercek listeyle kosmak teste
    # 45 s ekliyordu ve hicbir sey eklemiyordu.
    monkeypatch.setattr(
        saglik, "OLCERLER",
        [("sahte_olcer", "sınama", _patlat), ("saglam_olcer", "sınama", _saglam)])
    r = saglik.topla()

    satir = next(x for x in r["olcerler"] if x["olcer"] == "sahte_olcer")
    assert satir["olculdu"] is False
    assert "ÖLÇÜLEMEDİ" in satir["detay"]
    assert "olcer coktu" in satir["detay"], "sebep kaydedilmiyor"
    assert satir["iz"], "yığın izi tutulmuyor"
    # Ve TOPLAM HUKUM eksik kapsami soylemeli — yoksa daralmis bir ✅ uretilir.
    assert "EKSİK KAPSAM" in r["verdikt"]
    assert "sahte_olcer" in r["verdikt"]
    assert r["olculemeyen"] == ["sahte_olcer"]


def test_temiz_durumda_verdikt_KAPSAMI_da_soyluyor(rapor):
    r = rapor
    if r["acik_toplam"] == 0 and not r["kapsam_disi"] and not r["olculemeyen"]:
        # "Sifir acik madde" iddiasi, TARANAMAYAN olmadigini da soylemeli;
        # aksi halde okuyucu kapsami bilmeden hukme guvenir.
        assert "taranamayan dosya yok" in r["verdikt"]


def test_kanit_dosyasi_HUKUM_ve_URETIM_tasiyor(rapor):
    # Toplayici da bir kanit uretiyor; depo kurali herkese aynen uygulanir.
    r = rapor
    assert r["verdikt"] and len(r["verdikt"]) > 20
    assert r["_uretim"].startswith("Üretim: python saglik.py")
