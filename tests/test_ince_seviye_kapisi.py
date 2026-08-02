"""İNCE seviye de kaba seviyelerle AYNI kapılardan geçmeli.

Ana koşunun sonucu GCI seviye listesine KOŞULSUZ ekleniyordu; oysa kaba seviyeler
fizik / yakınsama / yüzey kapılarından geçmek zorundaydı. Kapı eşitsiz uygulanıyordu.

ÖLÇÜLDÜ (Ahmed çapası, 2026-08-02): `orta` seviye "rezidüeller hedefin üzerinde
(Uy=1.08e-03, p=1.21e-03)" diye REDDEDİLDİ; aynı koşunun `ince` seviyesi
Uy=1.54e-03, p=1.46e-03 ile DAHA KÖTÜ yakınsamışken sorgusuz kabul edildi ve
GCI (=%275) tam onun üzerine kuruldu.

Kalan üç çapada (küp, disk, kanat) ince seviye kapıyı zaten geçiyor — düzeltme
mevcut sonuçları bozmuyor, dar hedefli.
"""
import inspect

import vehicle_pipeline as vp

_SRC = inspect.getsource(vp.run_vehicle_analysis)
_i = _SRC.index("cells_fine = ")
_BLOK = _SRC[_i:_i + 2000]


def test_ince_seviye_UC_kapiya_da_tabi():
    for parca in ("seviye_yakinsadi_mi(conv)", "base.fizik_kabul", "_yc"):
        assert parca in _BLOK, parca


def test_ince_seviye_kosulsuz_EKLENMIYOR():
    assert 'levels = [{"ad": "ince", "cells": cells_fine, "Cd": cd}] if cells_fine else []' \
        not in _SRC, "koşulsuz ekleme geri gelmiş"
    assert "not _ince_red" in _BLOK


def test_ince_dusunce_KABA_seviyeler_de_kosulmuyor():
    """Referans seviye düşmüşse aile anlamsız; koşmak saatleri boşa harcar
    (Ahmed'de üç kaba koşu böyle harcandı)."""
    i = _SRC.index("kademeler = [")
    assert "if _ince_red:" in _SRC[i:i + 700]
    assert "kademeler = []" in _SRC[i:i + 700]


def test_durum_metni_SEBEBI_soyluyor():
    i = _SRC.index('"durum":')
    blok = _SRC[i:i + 600]
    assert "_ince_red" in blok and "ÇALIŞMASI YAPILMADI" in blok


def test_OLCULEN_capalarda_dogru_ayrim():
    """Ahmed düşmeli, diğer üçü geçmeli — düzeltme dar hedefli olmalı."""
    vakalar = {
        "ahmed": {"iterasyon": 647, "rezidual_ok": False, "drift_ok": True,
                  "son_rezidualler": {"Uy": "1.54e-03", "p": "1.46e-03"},
                  "salinim": {"osilasyon": True, "genlik_pct": 3.23, "gecis": 4}},
        "kup": {"iterasyon": 796, "rezidual_ok": True, "drift_ok": True,
                "son_rezidualler": {"Ux": "1e-06"}, "salinim": {"osilasyon": False}},
    }
    assert vp.seviye_yakinsadi_mi(vakalar["ahmed"])[0] is False
    assert vp.seviye_yakinsadi_mi(vakalar["kup"])[0] is True
