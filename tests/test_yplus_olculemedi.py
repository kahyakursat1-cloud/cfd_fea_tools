"""y⁺ ÖLÇÜLEMEDİĞİNDE analiz ÇÖKMEMELİ.

`measure_yplus` ölçemediğinde {"olculemedi": True, "neden": ...} döner — bu, sessiz
None yerine SEBEBİ tasisin diye eklenmisti. Ama tüketiciler `yp["ort"]` diye
indekslemeye devam ediyordu: ölçüm başarısız olunca TÜM analiz KeyError ile
çöküyordu. Güvenilirlik taramasında 12 geometrinin 2'si böyle düştü.

DERS: sessiz bir başarısızlığı görünür yapmak, tüketicileri güncellemeden yapılırsa
sessiz hatayı SERT hataya çevirir.
"""
import re
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
SRC = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")


def test_hicbir_yerde_dogrudan_ort_indekslemesi_kalmadi():
    kotu = [i for i, s in enumerate(SRC.splitlines(), 1)
            if re.search(r'yp\[\s*["\']ort["\']\s*\]', s) and not s.lstrip().startswith("#")]
    assert not kotu, f"dogrudan yp['ort'] indekslemesi: satir {kotu}"


def test_olculemedi_dali_SEBEBI_yaziyor():
    assert 'get("neden")' in SRC or "get('neden')" in SRC
    assert "y⁺ ÖLÇÜLEMEDİ" in SRC


def test_measure_yplus_basarisizken_sebepli_sozluk_donuyor(tmp_path, monkeypatch):
    import vehicle_pipeline as vp

    class R:
        stdout = ""
    monkeypatch.setattr(vp, "_wsl_run", lambda *a, **k: R())
    y = vp.measure_yplus(tmp_path, patch="govde")
    assert y.get("olculemedi") is True
    assert y.get("neden")
    assert "ort" not in y            # uydurma sayi YOK


def test_olculemeyen_yplus_savunulabilir_saymaz():
    """Tarama tarafındaki karşılık: 'ölçemedim' geçer not değildir."""
    from experiments.guvenilirlik_taramasi import duvar_hukmu
    ok, neden = duvar_hukmu({"yplus": {"olculemedi": True, "neden": "log yok"},
                             "katman_olcumu": {"durum": "katman_istenmedi"}})
    assert ok is False and "ölçülemedi" in neden
