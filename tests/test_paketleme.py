"""`pip install -e .` gerçekten bir şey kurmalı.

Önceden `py-modules = []` + paket bildirimi yoktu: kurulum bağımlılıkları getiriyor ama
tek bir modül yayımlamıyordu; `from analysis... import` yalnız repo kökünden çalışıyordu.
Bu test o regresyonu ve bilinçli kararı (flat modüller KURULMAZ) çapalar.
"""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _cfg():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_kanonik_katman_kurulur():
    st = _cfg()["tool"]["setuptools"]
    assert "analysis" in st.get("packages", []), \
        "analysis paketi kurulmuyor — dışarıdan import edilemez"


def test_flat_moduller_bilerek_kurulmaz():
    """Genel adlar (constants, kuyruk, mentor) site-packages'ı kirletmemeli."""
    assert _cfg()["tool"]["setuptools"].get("py-modules") == []


def test_analysis_paketi_kendi_icinde_kapali():
    """Kurulabilir olması için analysis/ kök modüllere bağımlı OLMAMALI."""
    kok_modul = {p.stem for p in ROOT.glob("*.py")}
    for p in (ROOT / "analysis").glob("*.py"):
        for satir in p.read_text(encoding="utf-8").splitlines():
            s = satir.strip()
            if s.startswith("from ") and not s.startswith(("from .", "from __future__")):
                ad = s.split()[1].split(".")[0]
                assert ad not in kok_modul, f"{p.name}: kök modül '{ad}' import ediyor"
            elif s.startswith("import "):
                ad = s.split()[1].split(".")[0].rstrip(",")
                assert ad not in kok_modul, f"{p.name}: kök modül '{ad}' import ediyor"
