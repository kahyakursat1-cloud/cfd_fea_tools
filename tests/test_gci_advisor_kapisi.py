"""GCI öncül havuzunun giriş kapısı — bandı türetilemeyen koşu ÖĞRENİLMEZ.

NEDEN: `gci_advisor` geçmiş koşulardan bir öncül üretir. Bir koşunun bandı
seviye Cd/hücre kayıtlarından yeniden türetilemiyorsa o koşu havuza girmemeli;
girerse öncül, kaynağı doğrulanamayan bir sayıyla kirlenir. Aynı ölçüt
`mentor._load`'da da var (gövdesi çözülmemiş koşu öğrenilmez) --- MiniHawk'ta
çözülmemiş gövdenin GCI'si %379 çıkmıştı ve o sayı gövdenin değil, 74-yüzlü
gölgesinindi.

Bu kapı kapsam ölçümünde SINANMAMIŞ çıktı (`gci_advisor.py:83`). Karar üreten
katmanda sınanmamış tek gerçek daldı ve onu bulan şey kapsam \\emph{yüzdesi}
değil, "hangi karar yolu sınanmamış" sorusu oldu.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))


def _yaz_sonuc(dizin: Path, seviyeler, yplus_ort: float = 1.0,
               yuzey_yuz: int = 5000) -> Path:
    """Geçici bir koşu dizini + sonuc.json yaz, yolunu döndür."""
    dizin.mkdir(parents=True, exist_ok=True)
    p = dizin / "sonuc.json"
    # SEMA GERCEK: _record_from_sonuc, status="ok" VE geometry.boyutlar_m
    # olmadan hic kayit uretmez (erken None). Testi yazarken modulun gercek
    # sozlesmesi ortaya cikti.
    p.write_text(json.dumps({
        "status": "ok",
        "cd": 0.30,
        "vehicle_type": "genel",
        "mesh": {"cells": 500_000},
        "sinir_tabaka": {"yplus": {"ort": yplus_ort}},
        "geometry": {"yuzey_yuz": yuzey_yuz, "lmax_m": 1.0,
                     "boyutlar_m": [1.0, 0.3, 0.25], "ucgen_sayisi": 20000,
                     "su_gecirmez": True},
        "mesh_duyarlilik": {"verdikt": "✅ mesh bağımsız",
                            "gci": {"gci_fine_pct": 2.0},
                            "seviyeler": seviyeler},
        "belirsizlik": {"u_sayisal_pct": 2.0},
    }, ensure_ascii=False), encoding="utf-8")
    return p


def test_band_turetilemeyen_kosu_OGRENILEMEZ(tmp_path):
    """Seviye kaydı yoksa band yeniden türetilemez → öğrenilebilir DEĞİL."""
    import gci_advisor
    p = _yaz_sonuc(tmp_path / "kosu", seviyeler=None)
    rec = gci_advisor._record_from_sonuc(p)
    assert rec is not None, "kayıt hiç üretilmedi"
    assert rec.get("ogrenilebilir") is False, rec
    assert rec.get("gecersizlik"), "ret GEREKÇESİZ"
    assert len(rec["gecersizlik"]) > 15, rec["gecersizlik"]


def test_ret_gerekcesi_NEDENI_soyluyor(tmp_path):
    """'öğrenilemez' tek başına yetmez; hangi eksikten geldiği yazılmalı."""
    import gci_advisor
    rec = gci_advisor._record_from_sonuc(_yaz_sonuc(tmp_path / "k2",
                                                    seviyeler=None))
    g = rec["gecersizlik"].lower()
    assert ("band" in g or "seviye" in g), rec["gecersizlik"]


def test_bos_havuzda_oneri_URETILMEZ(tmp_path, monkeypatch):
    """Havuz dosyası yoksa boş liste döner — uydurma öncül üretilmez."""
    import gci_advisor
    monkeypatch.setattr(gci_advisor, "GCI_MEMORY", tmp_path / "yok.jsonl")
    assert gci_advisor._load() == []


def test_bozuk_satir_havuzu_DUSURMEZ(tmp_path, monkeypatch):
    """Tek bozuk JSONL satırı tüm öğrenme havuzunu düşürmemeli.

    Havuz satır-satır büyür; bir koşu yarım yazılmış olabilir. O satırın
    tamamı okunamaz kılması, geçmiş tüm öğrenmeyi silmek demektir.
    """
    import gci_advisor
    p = tmp_path / "gci.jsonl"
    # `metrik` ZORUNLU: _load onsuz kaydi havuza almaz (kNN ozellik vektoru).
    saglam = {"ad": "iyi", "ogrenilebilir": True, "u_num_pct": 2.0,
              "hucre": 500_000, "metrik": {"narinlik": 3.0}}
    p.write_text(json.dumps(saglam, ensure_ascii=False) + "\n{bozuk json\n",
                 encoding="utf-8")
    monkeypatch.setattr(gci_advisor, "GCI_MEMORY", p)
    out = gci_advisor._load(sadece_gecerli=False)
    assert len(out) == 1 and out[0]["ad"] == "iyi"


def test_ogrenilemeyen_kayit_havuzdan_DISLANIR(tmp_path, monkeypatch):
    """`sadece_gecerli=True` iken öğrenilemez kayıt havuza girmemeli."""
    import gci_advisor
    p = tmp_path / "gci.jsonl"
    satirlar = [
        {"ad": "gecerli", "ogrenilebilir": True, "u_num_pct": 2.0,
         "hucre": 5e5, "metrik": {"narinlik": 3.0}},
        {"ad": "gecersiz", "ogrenilebilir": False, "u_num_pct": 379.0,
         "hucre": 5e5, "metrik": {"narinlik": 3.0},
         "gecersizlik": "gövde çözülmedi"},
    ]
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in satirlar),
                 encoding="utf-8")
    monkeypatch.setattr(gci_advisor, "GCI_MEMORY", p)
    adlar = [r["ad"] for r in gci_advisor._load(sadece_gecerli=True)]
    assert "gecersiz" not in adlar, "öğrenilemez kayıt havuza sızdı"
