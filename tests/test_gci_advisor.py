"""gci_advisor — GCI sonuç-hasadı + koşu-öncesi öğrenilen-öncül (kNN)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gci_advisor as ga  # noqa: E402

_GEO = {"dosya": "r.stl", "boyutlar_m": [0.8, 0.08, 0.08], "lmax_m": 0.8,
        "ucgen_sayisi": 2000, "su_gecirmez": True, "on_alan_m2": 0.005,
        "planform_alan_m2": 0.06, "yuzey_alani_m2": 0.2,
        "ince_yassilik": 0.9, "radyal_doluluk": 1.0}

_COZULDU = {"yuzey_cozunurlugu": {"cozuldu": True, "gerekce": []}}


def _sonuc(gci_fine=8.0, verdikt="⚠️ Mesh bağımsızlığı GÖSTERİLEMEDİ: p dışı",
           u_num=None, p=0.3, cds=(0.50, 0.55, 0.56), sinir=_COZULDU):
    cells = (200000, 600000, 1600000)
    return {"status": "ok", "vehicle_type": "roket", "geometry": _GEO,
            "mesh": {"cells": 1600000}, "sinir_tabaka": dict(sinir),
            "mesh_duyarlilik": {
                "seviyeler": [{"ad": a, "cells": c, "Cd": f}
                              for a, c, f in zip(("kaba", "orta", "ince"), cells, cds)],
                "gci": {"p": p, "gci_fine_pct": gci_fine, "monotonic": True},
                "verdikt": verdikt},
            "belirsizlik": {"u_sayisal_pct": u_num}}


def test_harvest_collects_and_rewrites(tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "HERE", tmp_path)
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "gci_memory.jsonl")
    for i, (g, v) in enumerate([(4.0, "✅ Yakınsadı"), (60.0, "⚠️ GÖSTERİLEMEDİ"),
                                (12.0, "⚠️ GÖSTERİLEMEDİ")]):
        d = tmp_path / "vehicle_runs" / f"m{i}"
        d.mkdir(parents=True)
        (d / "sonuc.json").write_text(json.dumps(_sonuc(g, v)), encoding="utf-8")
    (tmp_path / "vehicle_runs" / "bos").mkdir()
    (tmp_path / "vehicle_runs" / "bos" / "sonuc.json").write_text(
        json.dumps({"status": "failed"}), encoding="utf-8")   # GCI'sız → alınmaz
    r = ga.harvest()
    assert r["n_kayit"] == 3 and r["asimptotik"] == 1
    recs = ga._load()
    assert all(rc["tip"] == "roket" and rc["metrik"] for rc in recs)
    r2 = ga.harvest()                              # idempotent: yeniden yazar, şişmez
    assert r2["n_kayit"] == 3


def test_band_KAYITLI_sayidan_degil_SEVIYELERDEN_turetilir(tmp_path, monkeypatch):
    """ASIL KUSUR: belirsizlik kuralı beş kez değişti, jsonl kayıtları değişmedi.
    ÖLÇÜLDÜ (doe_6.90_0.37): kayıtlı %1.40 — asimptotik OLMAYAN Richardson sayısı,
    bugün reddedilir. Aynı seviyelerden bugünün kuralı %84.0 verir: 60 kat.
    Kayıt bir SAYI değil, o sayının TÜRETİLDİĞİ SEVİYELER üzerinden okunmalı."""
    monkeypatch.setattr(ga, "HERE", tmp_path)
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "mem.jsonl")
    d = tmp_path / "vehicle_runs" / "eski"
    d.mkdir(parents=True)
    # Gerçek doe_6.90_0.37 dizisi ve o koşunun kaydettiği sayı.
    (d / "sonuc.json").write_text(
        json.dumps(_sonuc(u_num=1.40, cds=(0.54849, 0.77796, 0.81943))),
        encoding="utf-8")
    ga.harvest()
    r = json.loads((tmp_path / "mem.jsonl").read_text(encoding="utf-8").strip())
    assert r["u_kayitli_pct"] == 1.40
    assert 80.0 < r["u_num_pct"] < 90.0, "3·Δ_M kuralı uygulanmadı"
    assert r["sapma_kat"] > 20, "kayıtla bugünün kuralı arasındaki sapma GÖRÜNMELİ"
    assert r["yontem"] == "salinim"


def test_yuzeyi_COZULMEMIS_kosu_ogrenmeye_girmez(tmp_path, monkeypatch):
    """mesh_memory ile AYNI ölçüt: çözülmemiş gövdenin GCI'si o gövdenin değil,
    74-yüzlü gölgesinindir (MiniHawk'ta %379 böyle çıkmıştı)."""
    monkeypatch.setattr(ga, "HERE", tmp_path)
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "mem.jsonl")
    for ad, sinir in (("cozuldu", _COZULDU), ("olculmedi", {}),
                      ("cozulmedi", {"yuzey_cozunurlugu":
                                     {"cozuldu": False, "gerekce": ["74 yüz"]}})):
        d = tmp_path / "vehicle_runs" / ad
        d.mkdir(parents=True)
        (d / "sonuc.json").write_text(json.dumps(_sonuc(sinir=sinir)), encoding="utf-8")
    r = ga.harvest()
    assert r["n_kayit"] == 3 and r["n_ogrenilebilir"] == 1 and r["n_dislanan"] == 2
    assert len(ga._load()) == 1                      # havuza yalnız çözülmüş giren
    assert len(ga._load(sadece_gecerli=False)) == 3  # ama kayıt SİLİNMEZ, görünür


def test_advise_predicts_band_and_asymptotic_probability(tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "mem.jsonl")
    import auto_pilot as ap
    metrik = ap.classify_vehicle(_GEO)["metrik"]
    recs = [{"tip": "roket", "metrik": metrik, "u_num_pct": u, "p": 0.4,
             "ogrenilebilir": True, "asimptotik_ok": ok} for u, ok in
            [(40.0, False), (60.0, False), (55.0, False), (35.0, False), (8.0, True)]]
    (tmp_path / "mem.jsonl").write_text(
        "".join(json.dumps(r) for r in recs).replace("}{", "}\n{") + "\n", encoding="utf-8")
    out = ga.advise(metrik, "roket")
    assert out is not None and out["n_destek"] == 5 and out["ayni_tip"]
    assert out["ayirt_edici"]                     # havuzda iki farklı sonuç var
    assert out["asimptotik_olasilik"] < 0.5        # çoğunluk kapıyı geçememiş
    assert "LSR" in out["oneri"]                   # → 4+ seviye + LSR önerisi
    assert 8.0 <= out["u_num_beklenen_pct"] <= 60.0
    assert "ÖNCÜL" in out["etiket"]                # dürüstlük etiketi zorunlu


def test_tek_YONLU_havuzdan_OLASILIK_uretilmiyor(tmp_path, monkeypatch):
    """Komşuların hepsi aynı sonucu verdiyse "olasılık" bir öğrenme değil SABİTTİR:
    geometri ne olursa olsun aynı cevap çıkar. Mentor'da aynı kusur ölçülmüştü —
    iki kalite de %100 görünüyor, sıralama beraberlik-bozucuya kalıyordu."""
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "mem.jsonl")
    import auto_pilot as ap
    metrik = ap.classify_vehicle(_GEO)["metrik"]
    recs = [{"tip": "roket", "metrik": metrik, "u_num_pct": u, "p": 0.4,
             "ogrenilebilir": True, "asimptotik_ok": False}
            for u in (40.0, 60.0, 55.0, 35.0)]
    (tmp_path / "mem.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    out = ga.advise(metrik, "roket")
    assert out["ayirt_edici"] is False
    assert out["asimptotik_olasilik"] is None      # sahte olasılık YAYINLANMAZ
    assert out["guven"] == 0.0
    assert "AYIRT EDİCİ DEĞİL" in out["oneri"]


def test_saçilan_komsu_bandi_ORTALAMA_diye_sunulmuyor(tmp_path, monkeypatch):
    """Kayıtlı havuzda ölçüldü: bandlar %1.4 ile %93.7 arasında. Bunların ağırlıklı
    ortalaması bir beklenti değildir; aralık gösterilmezse öncül olduğundan
    kesin görünür."""
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "mem.jsonl")
    import auto_pilot as ap
    metrik = ap.classify_vehicle(_GEO)["metrik"]
    recs = [{"tip": "roket", "metrik": metrik, "u_num_pct": u, "p": 0.4,
             "ogrenilebilir": True, "asimptotik_ok": bool(i % 2)}
            for i, u in enumerate((2.3, 93.7, 1.4, 62.9))]
    (tmp_path / "mem.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    out = ga.advise(metrik, "roket")
    assert out["u_komsu_araligi_pct"] == [1.4, 93.7]
    assert "saçılıyor" in out["oneri"]


def test_advise_refuses_thin_data(tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "mem.jsonl")
    import auto_pilot as ap
    metrik = ap.classify_vehicle(_GEO)["metrik"]
    (tmp_path / "mem.jsonl").write_text(
        json.dumps({"tip": "roket", "metrik": metrik, "u_num_pct": 10.0,
                    "ogrenilebilir": True, "asimptotik_ok": True}) + "\n",
        encoding="utf-8")
    assert ga.advise(metrik, "roket") is None      # n<4 → şeffaf ret, sahte güven yok


def test_FARKLI_yontemli_bandlar_tek_sayi_gibi_sunulmuyor(tmp_path, monkeypatch):
    """`u_num_pct` üç ayrı tanımdan gelir ve aynı büyüklük DEĞİLDİR:
      lsr      → U = 1.25|δ_RE| + σ, bir EKSTRAPOLASYON hatası
      salinim  → U = 3·Δ_M, ekstrapolasyon YOK, yalnız veri aralığı
      2-mesh   → ikisi de değil, vekil bant
    ÖLÇÜLDÜ (11 kayıt): havuz 4 lsr + 5 salınım + 1 iki-mesh — ağırlıklı ortalama
    tanımı olmayan bir sayı üretiyordu."""
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "mem.jsonl")
    import auto_pilot as ap
    metrik = ap.classify_vehicle(_GEO)["metrik"]
    recs = [{"tip": "roket", "metrik": metrik, "u_num_pct": u, "p": 1.0,
             "ogrenilebilir": True, "asimptotik_ok": ok, "yontem": y}
            for u, ok, y in [(2.3, True, "lsr"), (60.0, False, "salinim"),
                             (3.1, True, "lsr"), (55.0, False, "salinim")]]
    (tmp_path / "mem.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    out = ga.advise(metrik, "roket")
    assert out["karisik_yontem"] is True
    assert out["yontem_karisimi"] == ["lsr", "salinim"]
    assert "FARKLI YÖNTEMLERDEN" in out["oneri"]


def test_TEK_yontemli_havuzda_uyari_YOK(tmp_path, monkeypatch):
    """Kapı yalnız karışımı işaretlemeli; tek tanımlı havuzda gürültü yapmasın."""
    monkeypatch.setattr(ga, "GCI_MEMORY", tmp_path / "mem.jsonl")
    import auto_pilot as ap
    metrik = ap.classify_vehicle(_GEO)["metrik"]
    recs = [{"tip": "roket", "metrik": metrik, "u_num_pct": u, "p": 1.0,
             "ogrenilebilir": True, "asimptotik_ok": bool(i % 2), "yontem": "lsr"}
            for i, u in enumerate((2.3, 3.1, 2.8, 3.4))]
    (tmp_path / "mem.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    out = ga.advise(metrik, "roket")
    assert out["karisik_yontem"] is False
    assert "FARKLI YÖNTEMLERDEN" not in out["oneri"]
