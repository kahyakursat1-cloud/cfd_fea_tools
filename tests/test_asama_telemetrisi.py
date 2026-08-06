"""Aşama süreleri: doğrudan telemetri, dosya zaman damgalarına TERCİH EDİLİR.

Zaman-damgası yöntemi aşamanın kendi süresini değil, iki log dosyasına dokunma
anları arasındaki farkı ölçer — arada geçen her şey (kopyalama, bekleme, kuyruk)
aşamaya yazılır. Çözücü artık kendi sürelerini kaydediyor; bu testler seçimin
telemetri lehine olduğunu ve yöntemin etikette göründüğünü bağlar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from rapor_figurleri import ASAMALAR, asama_verisi  # noqa: E402


def _mtime_kosusu(tmp_path: Path, ad: str = "k") -> Path:
    kosu = tmp_path / ad
    (kosu / ad).mkdir(parents=True)
    for i, (_, dosya) in enumerate(ASAMALAR[:5]):
        p = kosu / ad / dosya
        p.write_text("x", encoding="utf-8")
        import os
        os.utime(p, (1_700_000_000 + i * 60, 1_700_000_000 + i * 60))
    return kosu


def test_telemetri_yoksa_zaman_damgasina_duser(tmp_path):
    adlar, sureler, hucre, yontem = asama_verisi(_mtime_kosusu(tmp_path))
    assert len(adlar) == 4
    assert all(abs(s - 60.0) < 1.0 for s in sureler)
    assert hucre is None
    assert "DOLAYLI" in yontem


def test_telemetri_varsa_zaman_damgasi_KULLANILMAZ(tmp_path):
    kosu = _mtime_kosusu(tmp_path)
    (kosu / "sonuc.json").write_text(json.dumps({
        "mesh": {"cells": 123456},
        "asama_sureleri": [{"asama": "blockMesh", "sure_s": 3.5, "durum": "ok"},
                           {"asama": "snappyHexMesh", "sure_s": 91.0, "durum": "ok"},
                           {"asama": "foamRun", "sure_s": 640.0, "durum": "ok"}],
    }), encoding="utf-8")
    adlar, sureler, hucre, yontem = asama_verisi(kosu)
    assert adlar == ["blockMesh", "snappyHexMesh", "foamRun"]
    assert sureler == [3.5, 91.0, 640.0]
    assert hucre == 123456
    assert "telemetri" in yontem
    assert "DOLAYLI" not in yontem


def test_bos_telemetri_zaman_damgasini_engellemez(tmp_path):
    kosu = _mtime_kosusu(tmp_path)
    (kosu / "sonuc.json").write_text(json.dumps({"asama_sureleri": []}),
                                     encoding="utf-8")
    _, _, _, yontem = asama_verisi(kosu)
    assert "DOLAYLI" in yontem


def test_kanit_yoksa_uydurmaz(tmp_path):
    assert asama_verisi(tmp_path / "yok") is None


def test_cozucu_her_asamayi_kaydeder():
    """CFDResult alanı ve _step kaydı gerçekten var mı — figür buna dayanıyor."""
    from analysis.openfoam_runner import CFDResult
    assert "asama_sureleri" in CFDResult.__dataclass_fields__
    kaynak = (KOK / "analysis" / "openfoam_runner.py").read_text(encoding="utf-8")
    assert 'asama_sureleri.append' in kaynak
    # BASARILI yolda da tasinmali: yalnizca hata yollarinda olsaydi figur
    # sadece coken kosularda telemetri gorurdu.
    son = kaynak[kaynak.rindex("return CFDResult(\n        case_dir=case_dir, success=True"):]
    assert "asama_sureleri=asama_sureleri" in son[:400]
