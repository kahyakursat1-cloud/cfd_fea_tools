"""Başsız hizmet katmanı — CLI ile REST'in AYNI çekirdeği kullandığını bağlar.

Çözücü çağrılmaz; `vehicle_pipeline` sahte bir modülle değiştirilir. Sınanan
şey sözleşmedir: çıktı JSON-serileştirilebilir mi, sınıf sayıyla birlikte
gidiyor mu, düzeltici bilgisi düz veriye çevriliyor mu.
"""
import json
import sys
import types

import pytest

import hizmet


class _Sonuc:
    status = "ok"
    vehicle_type = "ucak"
    velocity = 30.0
    alpha_deg = 4.0
    cd, cl, ld = 0.31, 0.42, 1.35
    aref_m2, drag_N = 0.12, 21.0
    belirsizlik = {"u_toplam_pct": 6.0}
    mesh = {"cells": 120000}
    convergence = {"ok": True}
    mesh_duyarlilik = {}
    fizik_kabul = {"verdict": "ok", "reasons": []}
    uyarilar = []
    case_dir = "_case"
    report = "rapor.md"
    error = ""


def _sahte_hat(monkeypatch, sonuc=None):
    mod = types.ModuleType("vehicle_pipeline")
    mod.run_vehicle_analysis = lambda stl, **kw: sonuc or _Sonuc()
    monkeypatch.setitem(sys.modules, "vehicle_pipeline", mod)


def test_cikti_JSON_serilestirilebilir(monkeypatch):
    """Tarayıcı ya da başka bir dil karar-katmanı nesnelerini göremez."""
    _sahte_hat(monkeypatch)
    o = hizmet.analiz_et("x.stl")
    json.dumps(o, ensure_ascii=False)          # patlarsa sözleşme bozuk


def test_SINIF_sayiyla_BIRLIKTE_gider(monkeypatch):
    """Çıplak Cd döndürmek bu aracın varlık nedenine aykırı."""
    _sahte_hat(monkeypatch)
    o = hizmet.analiz_et("x.stl")
    assert o["sonuc"]["cd"] == 0.31
    assert o["gecerlilik"]["genel"] in ("VALIDATED", "TREND", "OUT")
    assert o["gecerlilik"]["nicelikler"], "nicelik başına hüküm yok"
    for n in o["gecerlilik"]["nicelikler"]:
        assert {"nicelik", "sinif", "tasarimda_kullanilir", "gerekce"} <= set(n)


def test_duzeltici_KAPALIYKEN_None(monkeypatch):
    _sahte_hat(monkeypatch)
    assert hizmet.analiz_et("x.stl")["duzeltici"] is None


def test_ENGELLENEN_kusur_ciktida_KALIR(monkeypatch):
    """İstemci 'kusur yok' ile 'kusur var ama elimden gelmedi'yi ayırmalı."""
    import duzeltici as D
    s = D.DuzelticiSonuc(sinif=D.TREND, verdikt="v")
    s.engellenenler = [("rampali_baslangic", "kaba çözüm BULUNMALI")]
    monkeypatch.setattr(hizmet, "_duzeltici_dict", hizmet._duzeltici_dict)
    mod = types.ModuleType("duzeltici_adaptor")
    mod.duzelterek_analiz = lambda stl, **kw: (_Sonuc(), s)
    monkeypatch.setitem(sys.modules, "duzeltici_adaptor", mod)
    o = hizmet.analiz_et("x.stl", duzeltici=True)
    assert o["duzeltici"]["engellenenler"] == [
        {"duzeltme": "rampali_baslangic", "neden": "kaba çözüm BULUNMALI"}]


def test_cozucu_hatasi_ISTEMCIYE_ayristirlabilir_gider(monkeypatch):
    kotu = _Sonuc()
    kotu.status, kotu.error = "hata", "snappyHexMesh düştü"
    _sahte_hat(monkeypatch, kotu)
    o = hizmet.analiz_et("x.stl")
    assert o["durum"] == "hata" and "snappy" in o["hata"]


# ── CLI ile REST AYNI çekirdeği kullanmalı ───────────────────────────────────
def test_cli_ve_api_AYNI_islevi_cagirir():
    """İki arayüz ayrı mantık taşırsa biri düzeltilirken diğeri unutulur;
    bu depoda o kusur üç kez ölçüldü."""
    import api
    import cli
    assert cli.analiz_et is hizmet.analiz_et
    assert api.analiz_et is hizmet.analiz_et


def test_cli_JSON_basar_ve_cikis_kodu_dogru(monkeypatch, capsys):
    _sahte_hat(monkeypatch)
    import cli
    kod = cli.main(["--stl", "x.stl", "--tip", "ucak", "--hiz", "30"])
    cikti = capsys.readouterr().out
    assert kod == 0
    o = json.loads(cikti)
    assert o["durum"] == "ok" and o["gecerlilik"]["genel"]


def test_cli_hatayi_da_JSON_yazar(monkeypatch, capsys):
    """Yalnız stderr'e yazmak, borulayan istemciyi kör bırakır."""
    def patla(*a, **k):
        raise RuntimeError("çözücü yok")
    monkeypatch.setattr("hizmet.analiz_et", patla)
    import cli
    monkeypatch.setattr(cli, "analiz_et", patla)
    kod = cli.main(["--stl", "x.stl"])
    assert kod == 1
    o = json.loads(capsys.readouterr().out)
    assert o["durum"] == "hata" and "çözücü yok" in o["hata"]


def test_api_saglik_ucu():
    api = pytest.importorskip("api")
    assert api.saglik()["durum"] == "ayakta"


# ── Konteyner sözleşmesi ─────────────────────────────────────────────────────
def test_bassiz_giris_noktalari_GUI_ITHAL_ETMEZ():
    """Başsız imajda PySide6 yoktur; `cli`/`api`/`hizmet` onu import ederse
    konteyner çöker. Bu testin yakaladığı şey çalışma zamanında değil, İNŞA
    zamanında görünmez: imaj kurulur, ilk istekte patlar."""
    import ast
    from pathlib import Path
    yasak = {"PySide6", "PyQt5", "PyQt6"}
    for ad in ("cli.py", "api.py", "hizmet.py"):
        agac = ast.parse(Path(ad).read_text(encoding="utf-8"))
        for d in ast.walk(agac):
            if isinstance(d, ast.Import):
                adlar = {a.name.split(".")[0] for a in d.names}
            elif isinstance(d, ast.ImportFrom):
                adlar = {(d.module or "").split(".")[0]}
            else:
                continue
            assert not (adlar & yasak), f"{ad} GUI kütüphanesi ithal ediyor: {adlar & yasak}"


def test_dockerfile_hizmet_GIRIS_NOKTALARINI_kopyalar():
    """İmaj cli.py/api.py'yi taşımıyorsa başsız dağıtım yalan olur."""
    from pathlib import Path
    d = Path("docker/Dockerfile.hizmet").read_text(encoding="utf-8")
    assert "COPY . /uygulama" in d
    assert "fastapi" in d and "uvicorn" in d
    # Taban imaj digest'e sabit olmali: `:latest` yarin baska bir cozucu ceker
    # ve yayimlanmis bir bant sessizce gecersizlesir.
    assert "@sha256:" in d, "taban imaj digest'e sabit degil"


# ── Kuyruk ile eşzamanlı yol AYNI sözleşmeyi döndürmeli ──────────────────────
def test_kuyruk_ve_senkron_AYNI_sozlesmeyi_uretir(monkeypatch, tmp_path):
    """İstemci, işin hangi yoldan geldiğine göre farklı ayrıştırıcı yazmamalı."""
    import api
    import kuyruk
    _sahte_hat(monkeypatch)
    monkeypatch.setattr(kuyruk, "KUYRUK", tmp_path / "k.jsonl")
    monkeypatch.setattr(kuyruk, "KILIT", tmp_path / "k.lock")

    istek = api.AnalizIstegi(stl="x.stl", tip="ucak", hiz=30.0)
    senkron = api.analiz(istek)

    kuyruk.ekle({"stl_path": "x.stl", "vehicle_type": "ucak", "velocity": 30.0})
    kuyruk.calis(once=True)
    kuyruklu = api.is_durumu(kuyruk.listele()[0]["id"])["sonuc"]

    assert set(senkron) == set(kuyruklu), "iki yolun sözleşmesi ayrıştı"
    assert kuyruklu["gecerlilik"]["genel"] == senkron["gecerlilik"]["genel"]


def test_kuyruk_GUI_alanlarini_KORUR(monkeypatch, tmp_path):
    """Kuyruk tablosu `cd`/`u_pct`/`hata` okur; sözleşme değişimi onu bozmamalı."""
    import kuyruk
    _sahte_hat(monkeypatch)
    monkeypatch.setattr(kuyruk, "KUYRUK", tmp_path / "k.jsonl")
    monkeypatch.setattr(kuyruk, "KILIT", tmp_path / "k.lock")
    kuyruk.ekle({"stl_path": "x.stl", "velocity": 30.0})
    kuyruk.calis(once=True)
    son = kuyruk.listele()[0]["sonuc"]
    assert son["cd"] == 0.31 and son["u_pct"] == 6.0
    assert "tam" in son


def test_bilinmeyen_is_kimligi_ACIKCA_soylenir():
    import api
    o = api.is_durumu("yokboyle")
    assert o["durum"] == "yok" and o["hata"]
