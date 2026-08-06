"""Kuyruk kurtarma: bayat kilit, yarım iş, iptal.

ÖLÇÜLEN ARIZA (bu oturumda yaşandı): makine koşu ortasında kapandı.
`kuyruk.lock` diskte kaldı ve kimse kilit sahibi PID'in yaşayıp yaşamadığına
bakmadığı için kuyruk KALICI olarak bloke olurdu; ayrıca 'kosuyor' kalan iş
hiçbir zaman yeniden ele alınmazdı çünkü worker yalnız 'bekliyor' işlere bakar.

Kurtarmanın iki dürüstlük kuralı var:
  1. Süreç durumu SORULAMIYORSA kilit devralınmaz — 'bilmiyorum' ile 'ölü'yü
     karıştırmak, koşan bir worker'ın üstüne ikinci worker salmak demektir.
  2. Yarım iş SESSİZCE yeniden koşulmaz. Saatler sürmüş ve yarım bir case
     dizini bırakmış olabilir; `devam()` açık bir karardır.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import kuyruk  # noqa: E402


@pytest.fixture
def kuy(tmp_path, monkeypatch):
    monkeypatch.setattr(kuyruk, "KUYRUK", tmp_path / "kuyruk.jsonl")
    monkeypatch.setattr(kuyruk, "KILIT", tmp_path / "kuyruk.lock")
    return kuyruk


def _is(kuy, ad="a.stl"):
    return kuy.ekle({"stl_path": ad, "vehicle_type": "ucak", "velocity": 15.0})


# ── kilit ───────────────────────────────────────────────────────────────────

def test_bayat_kilit_devralinir(kuy):
    kuy.KILIT.write_text("999999", encoding="utf-8")     # var olmayan PID
    d = kuy.kilit_durumu()
    assert d["kilitli"] and d["bayat"] is True
    assert kuy._kilit_al() is True
    assert kuy.KILIT.read_text(encoding="utf-8") == str(os.getpid())


def test_canli_kilit_DEVRALINMAZ(kuy):
    kuy.KILIT.write_text(str(os.getpid()), encoding="utf-8")   # bu süreç yaşıyor
    d = kuy.kilit_durumu()
    assert d["yasiyor"] is True and d["bayat"] is False
    assert kuy._kilit_al() is False


def test_surec_sorulamazsa_kilit_birakilir(kuy, monkeypatch):
    """'Bilmiyorum' ile 'ölü' aynı şey değil: bilinmiyorsa güvenli taraf."""
    kuy.KILIT.write_text("4242", encoding="utf-8")
    monkeypatch.setattr(kuy, "_surec_yasiyor", lambda pid: None)
    d = kuy.kilit_durumu()
    assert d["yasiyor"] is None and d["bayat"] is False
    assert kuy._kilit_al() is False
    assert "SORULAMADI" in d["_not"]


def test_bozuk_kilit_dosyasi_cokmeye_yol_acmaz(kuy):
    kuy.KILIT.write_text("pid degil", encoding="utf-8")
    d = kuy.kilit_durumu()
    assert d["pid"] == -1 and d["bayat"] is True


def test_calis_kilitliyken_kilit_durumunu_da_donduruyor(kuy):
    kuy.KILIT.write_text(str(os.getpid()), encoding="utf-8")
    out = kuy.calis(runner=lambda p: {"status": "ok"})
    assert out["durum"] == "kilitli"
    assert out["kilit"]["yasiyor"] is True


# ── yarım iş ────────────────────────────────────────────────────────────────

def test_kosarken_olen_worker_isi_YARIM_kalir_kaybolmaz(kuy):
    i = _is(kuy)
    kuy._guncelle(i["id"], durum="kosuyor")
    kuy.KILIT.write_text("999999", encoding="utf-8")      # ölü worker
    assert kuy.yarim_isaretle() == [i["id"]]
    kayit = kuy.listele()[0]
    assert kayit["durum"] == "yarim"
    assert "tamamlanmadı" in kayit["yarim_neden"]


def test_yarim_is_SESSIZCE_yeniden_kosulmaz(kuy):
    i = _is(kuy)
    kuy._guncelle(i["id"], durum="kosuyor")
    kuy.KILIT.write_text("999999", encoding="utf-8")
    kosulan = []
    out = kuy.calis(runner=lambda p: kosulan.append(p) or {"status": "ok"})
    assert kosulan == [], "yarım iş kullanıcı istemeden yeniden koşmamalı"
    assert out["yarim_bulundu"] == 1
    assert kuy.listele()[0]["durum"] == "yarim"


def test_devam_yarim_isi_geri_kuyruga_alir(kuy):
    i = _is(kuy)
    kuy._guncelle(i["id"], durum="kosuyor")
    kuy.KILIT.write_text("999999", encoding="utf-8")
    kuy.yarim_isaretle()
    assert kuy.devam() == 1
    assert kuy.listele()[0]["durum"] == "bekliyor"
    kosulan = []
    kuy.calis(runner=lambda p: kosulan.append(p) or {"status": "ok"})
    assert len(kosulan) == 1


def test_canli_worker_varken_yarim_isaretlenmez(kuy):
    i = _is(kuy)
    kuy._guncelle(i["id"], durum="kosuyor")
    kuy.KILIT.write_text(str(os.getpid()), encoding="utf-8")
    assert kuy.yarim_isaretle() == []
    assert kuy.listele()[0]["durum"] == "kosuyor"


# ── iptal ───────────────────────────────────────────────────────────────────

def test_bekleyen_is_iptal_edilir(kuy):
    i = _is(kuy)
    assert kuy.iptal(i["id"])["ok"] is True
    assert kuy.listele()[0]["durum"] == "iptal"
    kosulan = []
    kuy.calis(runner=lambda p: kosulan.append(p) or {"status": "ok"})
    assert kosulan == [], "iptal edilen iş koşulmamalı"


def test_kosan_is_iptal_EDILMEZ(kuy):
    i = _is(kuy)
    kuy._guncelle(i["id"], durum="kosuyor")
    r = kuy.iptal(i["id"])
    assert r["ok"] is False and r["durum"] == "kosuyor"


def test_olmayan_is_iptali_sessizce_basarili_demez(kuy):
    assert kuy.iptal("yokboyle")["ok"] is False


def test_temizle_yarim_isi_atmaz(kuy):
    a, b = _is(kuy, "a.stl"), _is(kuy, "b.stl")
    kuy._guncelle(a["id"], durum="yarim")
    kuy._guncelle(b["id"], durum="bitti")
    assert kuy.temizle() == 1
    assert kuy.listele()[0]["durum"] == "yarim"
