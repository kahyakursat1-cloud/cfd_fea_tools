"""Mesh-bağımsızlık kampanyası kendi geçersizliğini SÖYLEMELİ.

Gerçek vaka (küp, 2026-07-26): `--duyarlilik` 3 seviye koştu, ~10 dk compute yaktı,
"orta" ve "kaba" seviyeler AYNI mesh'i üretti (ikisi de 70022 hücre) ve sonuç yalnızca
"hesaplanamadı" dedi. Kullanıcı neyi düzelteceğini bilemez.

Kök sebep: taban hücre `lmax / max(3, bg_div - ddiv)` ile kırpılıyordu; bg_div=5 (hizli)
presetinde her iki kaba seviye de 3'e düşüyordu. Sabit orana (r=1.5) geçildi.
"""
import inspect
import re

import vehicle_pipeline

SRC = inspect.getsource(vehicle_pipeline.run_vehicle_analysis)


def test_seviyeler_sabit_oranla_ayrisir():
    """Kırpılan çıkarma yerine çarpımsal oran — seviye çakışması matematiksel olarak
    imkânsız hale gelir."""
    assert "bg_ince * oran" in SRC
    assert 'max(3, q["bg_div"]' not in SRC, "kırpan eski formül geri gelmiş"
    m = re.search(r"GCI_ORANI\s*=\s*([\d.]+)", SRC)
    assert m and float(m.group(1)) >= 1.3, "Celik 2008: refinement oranı r ≥ 1.3 olmalı"


def test_kademeler_farkli_oranlar_kullanir():
    # Kademe demeti artık (ad, oran, end_time): iyileştirme-seviyesi düşürme
    # (`dref`) KALDIRILDI, çünkü arka planla birlikte düşünce aile TEKDÜZE
    # ölçeklenmiyordu (bkz. test_seviye_tekduze_olcekleme).
    oranlar = re.findall(r'\("(?:orta|kaba|cokkaba)",\s*(GCI_ORANI[^,]*)', SRC)
    assert len(set(oranlar)) == len(oranlar) >= 2, f"kademeler aynı oranı paylaşıyor: {oranlar}"


def test_dejenere_seviye_sebebiyle_birlikte_raporlanir():
    assert "dejenere" in SRC and "seviyeler ayrışmadı" in SRC
    assert "--kalite" in SRC, "kullanıcıya düzeltme yolu gösterilmeli"


def test_dejenere_esigi_yuzde_bes():
    """%5 altı hücre farkı pratikte aynı mesh demektir (küp vakası: %0.0)."""
    m = re.search(r"abs\(a\[.cells.\] - b\[.cells.\]\) / max\(a\[.cells.\], 1\) < ([\d.]+)", SRC)
    assert m and 0.0 < float(m.group(1)) <= 0.1


def test_gerçek_kup_vakasi_dejenere_sayilir():
    """Kampanyanın ürettiği gerçek sayılar eşikten geçmemeli."""
    seviyeler = [{"ad": "kaba", "cells": 70022}, {"ad": "orta", "cells": 70022},
                 {"ad": "ince", "cells": 320552}]
    dejenere = [(a["ad"], b["ad"]) for a, b in zip(seviyeler, seviyeler[1:])
                if abs(a["cells"] - b["cells"]) / max(a["cells"], 1) < 0.05]
    assert dejenere == [("kaba", "orta")]


def test_saglikli_seviyeler_dejenere_sayilmaz():
    seviyeler = [{"ad": "kaba", "cells": 70000}, {"ad": "orta", "cells": 150000},
                 {"ad": "ince", "cells": 320000}]
    dejenere = [a for a, b in zip(seviyeler, seviyeler[1:])
                if abs(a["cells"] - b["cells"]) / max(a["cells"], 1) < 0.05]
    assert dejenere == []
