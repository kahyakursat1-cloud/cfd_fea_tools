"""Case iskelesi tekrarı — refactor edilemiyorsa en azından SAPMA görünür olsun.

26 dosya kendi `controlDict`/`fvSolution`'ını yazıyor (ADR: "iki-hızlı", mass-refactor
İPTAL — regresyon riski). Bu testler o kararı bozmadan asıl tehlikeyi bağlar: kanonik
eşik değişince ad-hoc yazıcıların sessizce gerisinde kalması.

Ölçülen durum (2026-07-27): ad-hoc yazıcıların tamamı 1e-4 veya DAHA SIKI kullanıyor
(1e-5, 1e-6, 1e-7, 1e-9). İhlal yok — ama koruma da yoktu.
"""
import re
from pathlib import Path

from analysis.thresholds import RESIDUAL_TARGET

ROOT = Path(__file__).resolve().parent.parent
ATLA = {"Construct2D", "sources", "__pycache__", ".venv"}

_BLOK = re.compile(r"residualControl\s*\{(.*?)\}", re.S)
_ALAN = re.compile(r'"?\(?([pU])[^"]*"?\)?\s+([0-9.]+e?-?[0-9]*)\s*;', re.I)


def _kaynaklar():
    for f in ROOT.rglob("*.py"):
        if not (set(f.parts) & ATLA):
            yield f


def _hedefler() -> dict[str, float]:
    """{dosya: en gevşek residual hedefi} — literal yazılmış tüm bloklardan."""
    out: dict[str, float] = {}
    for f in _kaynaklar():
        t = f.read_text(encoding="utf-8", errors="replace")
        for m in _BLOK.finditer(t):
            for _ad, v in _ALAN.findall(m.group(1)):
                try:
                    d = float(v)
                except ValueError:
                    continue
                ad = f.relative_to(ROOT).as_posix()
                out[ad] = max(out.get(ad, 0.0), d)
    return out


def test_hicbir_case_kanonikten_gevsek_yakinsama_kullanmaz():
    """Daha SIKI hedef meşrudur (V&V kampanyaları 1e-6..1e-9 kullanır).
    GEVŞEK hedef ise yakınsamamış bir koşuyu 'yakınsadı' diye raporlar."""
    gevsek = {a: v for a, v in _hedefler().items() if v > RESIDUAL_TARGET}
    assert not gevsek, (
        f"kanonik hedeften ({RESIDUAL_TARGET:g}) GEVŞEK residualControl: {gevsek} — "
        "yakınsamamış koşu 'yakınsadı' görünür")


def test_ad_hoc_yazici_envanteri_bilinir():
    """Yazıcı sayısı sessizce büyümesin: yeni bir ad-hoc case iskelesi eklendiğinde
    bu test hatırlatır (kanonik `analysis/openfoam_runner` kullanılmalı)."""
    yazicilar = {a for a in _hedefler() if not a.startswith(("analysis/", "tests/"))}
    # 14 (2026-07-27): experiments/duz_levha_cf.py — 2D yapısal blockMesh düz levha.
    # analysis/openfoam_runner snappyHexMesh+STL üzerine kurulu; sıfır-basınç-gradyanlı
    # levha için gerekli graded blockMesh'i ifade edemiyor. Tabanı yükseltmek bilinçli;
    # bu satır artışın SESSİZ olmasını engelliyor.
    # 15 (2026-07-28): experiments/basamak_ayrilma.py — 2D geriye-basamaklı akış.
    # duz_levha_cf ile aynı gerekçe: analysis/openfoam_runner snappyHexMesh+STL üzerine
    # kurulu, çok bloklu yapısal blockMesh'i ifade edemiyor. V&V çapaları bu yüzden
    # kendi iskelesini kurar; artış bilinçli ve bu satır sessiz kalmasını engelliyor.
    assert len(yazicilar) <= 15, (
        f"{len(yazicilar)} ad-hoc residualControl yazıcısı var (ölçülen taban 15): "
        f"{sorted(yazicilar)}. "
        "Yeni CFD kodu analysis/openfoam_runner kullanmalı (CLAUDE.md kuralı)")


def test_kanonik_yazici_esikten_okur():
    """analysis/openfoam_runner literal yazmamalı — eşik tek kaynaktan gelmeli."""
    src = (ROOT / "analysis" / "openfoam_runner.py").read_text(encoding="utf-8")
    i = src.index("residualControl")
    pencere = src[i:i + 400]
    assert "RESIDUAL_TARGET" in pencere, "kanonik yazıcı eşiği sabit koda gömmüş"


def test_controldict_yazan_dosya_sayisi_bilinir():
    """ADR kararı: mass-refactor iptal. Ama sayı sessizce artmasın."""
    n = sum(1 for f in _kaynaklar()
            if "controlDict" in f.read_text(encoding="utf-8", errors="replace")
            and not f.relative_to(ROOT).as_posix().startswith(("analysis/", "tests/")))
    assert n <= 25, (f"{n} dosya kendi controlDict'ini yazıyor (ölçülen taban 25). "
                     "Yeni case iskelesi yazmadan analysis/openfoam_runner'a bak")
