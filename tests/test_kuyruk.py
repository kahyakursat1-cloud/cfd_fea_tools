"""kuyruk — iş ekleme, sıralı worker, kilit ve hata yolları (CFD'siz, runner mock)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kuyruk  # noqa: E402


@pytest.fixture
def izole(tmp_path, monkeypatch):
    monkeypatch.setattr(kuyruk, "KUYRUK", tmp_path / "kuyruk.jsonl")
    monkeypatch.setattr(kuyruk, "KILIT", tmp_path / "kuyruk.lock")
    # BELLEK OKUMASI SABITLENIR. Kuyruk artik bos bellek esigin altindaysa
    # isi baslatmiyor (dogru davranis). Ama o okuma CANLI sistemden geliyor:
    # suit kosarken bos RAM 2 GB'in altina inince bu dosyadaki is-sirasi
    # testleri kiriliyordu — tek baslarina gecip suitte kirilmalari bundandi.
    # Kaynak kotasi ayri testlerde (test_bellek_kapisi) sinaniyor; buradaki
    # testler SIRALAMA ve DURUM makinesini sinar, ortam bellegini degil.
    monkeypatch.setattr(kuyruk.bellek_kapisi, "bos_bellek_gb", lambda: 999.0)
    return tmp_path


def test_ekle_listele_temizle(izole):
    a = kuyruk.ekle({"stl_path": "a.stl", "vehicle_type": "roket"})
    kuyruk.ekle({"stl_path": "b.stl"})
    assert len(kuyruk.listele()) == 2 and a["durum"] == "bekliyor"
    with pytest.raises(ValueError):
        kuyruk.ekle({})                          # stl_path zorunlu
    assert kuyruk.temizle(hepsi=True) == 0


def test_worker_runs_jobs_in_order(izole):
    kuyruk.ekle({"stl_path": "a.stl"})
    kuyruk.ekle({"stl_path": "b.stl"})
    sira = []

    def runner(p):
        sira.append(Path(p["stl_path"]).name)
        return {"status": "ok", "cd": 0.3, "u_pct": 5.0, "rapor": "", "hata": ""}
    ozet = kuyruk.calis(runner=runner)
    assert sira == ["a.stl", "b.stl"]            # FIFO
    assert ozet["bitti"] == 2 and ozet["hata"] == 0
    assert all(i["durum"] == "bitti" and i["sonuc"]["cd"] == 0.3 for i in kuyruk.listele())
    assert not kuyruk.KILIT.exists()             # kilit bırakıldı


def test_worker_marks_failure_and_continues(izole):
    kuyruk.ekle({"stl_path": "patlar.stl"})
    kuyruk.ekle({"stl_path": "saglam.stl"})

    def runner(p):
        if "patlar" in p["stl_path"]:
            raise RuntimeError("mesh çöktü")
        return {"status": "ok", "cd": 0.2}
    ozet = kuyruk.calis(runner=runner)
    isler = {Path(i["params"]["stl_path"]).name: i for i in kuyruk.listele()}
    assert isler["patlar.stl"]["durum"] == "hata"
    assert "mesh çöktü" in isler["patlar.stl"]["sonuc"]["hata"]
    assert isler["saglam.stl"]["durum"] == "bitti"   # biri çöktü, kuyruk devam etti
    assert {k: ozet[k] for k in ("bitti", "hata", "atlandi_disk")} ==         {"bitti": 1, "hata": 1, "atlandi_disk": 0}
    assert ozet["yarim_bulundu"] == 0


def test_second_worker_blocked_by_lock(izole):
    # KILIT SAHIBI YASIYOR OLMALI: rastgele bir PID artik yeterli degil, cunku
    # bayat kilit (olu sahip) bilerek DEVRALINIYOR — makine kapanmasindan sonra
    # kuyrugun kalici bloke kalmasi bu depoda yasandi. Bkz.
    # tests/test_kuyruk_kurtarma.py.
    import os
    kuyruk.KILIT.write_text(str(os.getpid()))
    r = kuyruk.calis(runner=lambda p: {"status": "ok"})
    assert r["durum"] == "kilitli"
    kuyruk.KILIT.unlink()


def test_disk_guard_skips(izole, monkeypatch):
    kuyruk.ekle({"stl_path": "a.stl"})
    monkeypatch.setattr(kuyruk, "_disk_gb", lambda: 2.0)
    ozet = kuyruk.calis(runner=lambda p: {"status": "ok"})
    assert ozet["atlandi_disk"] == 1
    assert kuyruk.listele()[0]["durum"] == "hata"


def test_json_roundtrip_utf8(izole):
    kuyruk.ekle({"stl_path": "roket_gövde.stl", "vehicle_type": "kanatli_roket"})
    raw = kuyruk.KUYRUK.read_text(encoding="utf-8")
    assert "roket_gövde" in raw and json.loads(raw.splitlines()[0])
