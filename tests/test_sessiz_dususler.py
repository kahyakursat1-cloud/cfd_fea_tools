"""Sessiz düşüşlerin GERÇEKTEN konuştuğunu bağlar.

`sessiz_yutma` sayacı bir `except` bloğunun gerekçesi olup olmadığını sorar;
gerekçenin DOĞRU olup olmadığını soramaz. Bu dosya, incelemede düzeltilen
düşüşlerin sebebi bir yere yazdığını sınar — gerekçe metni değil, davranış.

Her biri gerçek bir kayıp senaryosuydu:
  - kuyruk dosyasında bozuk satır → bir iş sessizce yok oluyordu
  - bozuk sonuc.json → koşu geçmiş tablosundan düşüyordu
  - bozuk öğrenci profili → tüm ilerleme sıfırlanıp üzerine yazılıyordu
  - yatay kuyruk üretilemedi → uçak KUYRUKSUZ analiz ediliyordu
  - manifold3d yok → katı birleşim hiç denenmiyordu (en yaygın hâl, en sessizi)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))


def test_kuyrukta_bozuk_satir_SAYILIYOR(tmp_path, monkeypatch):
    import kuyruk
    f = tmp_path / "kuyruk.jsonl"
    f.write_text(json.dumps({"id": "a", "durum": "bekliyor", "params": {}}) + "\n"
                 + "{bozuk json\n"
                 + json.dumps({"id": "b", "durum": "bekliyor", "params": {}}) + "\n",
                 encoding="utf-8")
    monkeypatch.setattr(kuyruk, "KUYRUK", f)
    isler = kuyruk._yukle()
    assert len(isler) == 2, "sağlam kayıtlar yine okunmalı"
    bozuk = kuyruk.bozuk_kayitlar()
    assert bozuk and "satır 2" in bozuk[0], f"bozuk satır bildirilmedi: {bozuk}"


def test_saglam_kuyrukta_bozuk_kayit_YOK(tmp_path, monkeypatch):
    import kuyruk
    f = tmp_path / "kuyruk.jsonl"
    f.write_text(json.dumps({"id": "a", "durum": "bekliyor", "params": {}}) + "\n",
                 encoding="utf-8")
    monkeypatch.setattr(kuyruk, "KUYRUK", f)
    kuyruk._yukle()
    assert kuyruk.bozuk_kayitlar() == []


def test_bozuk_sonuc_json_gecmiste_ADIYLA_gorunuyor(tmp_path, monkeypatch):
    """Atlamak koşuyu kaybetmektir: kullanıcı 'koşum listede yok' der ve
    nedenini öğrenemez."""
    import kosu_gecmisi
    kok = tmp_path / "vehicle_runs" / "bozuk_kosu"
    kok.mkdir(parents=True)
    (kok / "sonuc.json").write_text("{ bu json degil", encoding="utf-8")
    monkeypatch.setattr(kosu_gecmisi, "HERE", tmp_path)
    kayitlar = kosu_gecmisi.tara(roots=["vehicle_runs"])
    hedef = [k for k in kayitlar if k["ad"] == "bozuk_kosu"]
    assert hedef, "okunamayan koşu tablodan tümüyle düştü"
    assert hedef[0]["durum"] == "okunamadi"
    assert "hata" in hedef[0]


def test_bozuk_profil_UZERINE_YAZILMIYOR(tmp_path, monkeypatch):
    """Öğrenci ilerlemesi geri dönüşü olmayan biçimde gidiyordu: bozuk profil
    boş sayılıyor, sonraki kayıt üzerine yazıyordu."""
    import yolculuk
    prof = tmp_path / "profil.json"
    prof.write_text("{ bozuk", encoding="utf-8")
    monkeypatch.setattr(yolculuk, "PROFIL", prof)
    p = yolculuk._profil_yukle()
    assert p["analiz_sayisi"] == 0                      # taze profille devam
    assert "profil_hatasi" in p, "sessizce sıfırlandı"
    assert (tmp_path / "profil.bozuk.json").exists(), "bozuk dosya yedeklenmedi"


def test_kuyruksuz_govde_GERILEME_kaydediyor(monkeypatch):
    """Yatay kuyruk üretilemezse uçak KUYRUKSUZ analiz edilir: boyuna
    kararlılık ve Cm o geometriden çıkarılamaz."""
    pytest.importorskip("trimesh")
    from aircraft_geometry import AircraftLibrary
    from mesh_generator import MeshGenerator
    g = MeshGenerator(AircraftLibrary().minihawk_uav())

    ozgun = MeshGenerator._extrude_profile_to_mesh

    def _kuyrukta_patla(self, profile_2d, y_root, y_tip, cr, ct, lr, lt):
        # Kuyruk cagrisi kok kirisinden KUCUK kiris tasir; kanat cagrisi gecer.
        if cr < 0.2:
            raise RuntimeError("kuyruk ekstruzyonu duştu (test)")
        return ozgun(self, profile_2d, y_root, y_tip, cr, ct, lr, lt)

    monkeypatch.setattr(MeshGenerator, "_extrude_profile_to_mesh", _kuyrukta_patla)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        g.generate_stl(str(Path(d) / "u.stl"))
    assert any("KUYRUK" in x.upper() for x in g.gerilemeler), g.gerilemeler


def test_manifold_yoksa_BIRLESIM_ATLANDI_deniyor(monkeypatch):
    """En yaygın hâl en sessiz olandı: manifold3d kurulu değilse birleşim
    bloğuna hiç girilmiyordu, dolayısıyla içerideki gerileme de yazılmıyordu."""
    pytest.importorskip("trimesh")
    import builtins

    from aircraft_geometry import AircraftLibrary
    from mesh_generator import MeshGenerator
    gercek_import = builtins.__import__

    def _manifoldsuz(ad, *a, **k):
        if ad == "manifold3d":
            raise ImportError("No module named 'manifold3d' (test)")
        return gercek_import(ad, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _manifoldsuz)
    g = MeshGenerator(AircraftLibrary().minihawk_uav())
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        g.generate_stl(str(Path(d) / "u.stl"))
    assert any("BİRLEŞİM ATLANDI" in x for x in g.gerilemeler), g.gerilemeler


def test_sayac_incelenmemis_SIFIR():
    """Taban çizgisi: gerekçesiz yeni bir `except` eklenirse burada kırılır."""
    import sessiz_yutma
    inc = sessiz_yutma.incelenmemis()
    assert not inc, ("gerekçesiz sessiz yutma:\n  "
                     + "\n  ".join(f"{x['dosya']}:{x['satir']} {x['fonksiyon']}"
                                   for x in inc))
