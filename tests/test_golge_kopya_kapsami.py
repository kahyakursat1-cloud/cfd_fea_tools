"""Kaynak tarayan kapılar GÖLGE KOPYALARI saymaz.

2026-09-05'te iki bayat ajan worktree'si (`.claude/worktrees/`) 12 testi
düşürdü. Kusur depoda değildi: `sessiz_yutma` sayacı 101 olan tabana karşı
252 sessiz yutma buluyordu ve listenin ilk kaydı
`.claude/worktrees/upbeat-bardeen-d87959/run_aoa_polar.py` idi --- kapı kendi
kodunun kopyalarını sayıyordu.

Bu, deponun imza kusurunun bir örneği: **kapının ölçütü iddiasından geniş.**
İddia "bu deponun kaynağında sessiz yutma", sayılan "kaynakta + gölge
kopyalarda". Worktree'yi silmek 12 testi düzeltti ama düzeltme değildi ---
bir sonraki ajan koşusu yenisini açar açmaz aynı 4 test yine düşerdi.

Ölçüldü, varsayılmadı: HEAD'in aynısını taşıyan bir worktree ile
`sessiz_yutma` ve `case_iskele` kapıları düşüyordu; öteki yedi kaynak
tarayıcısı (`iki_hiz`, `oksuz_savunma`, `kanit`, `arka_uc_sayaci`,
`bagimlilik_beyani`, `konsol_kodlamasi`, `sessiz_dususler`) kirli bir gölge
kopyaya --- içine `except: pass` ve bir controlDict yazıcısı enjekte
edilmişine --- karşı bile dayandı. Bu yüzden yalnız ikisi düzeltildi.

Kapıların KÖR OLMADIĞI ayrıca sınandı: aynı kusurlar gerçek depoya
enjekte edilince ikisi de düşüyor.
"""

import ast
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))


def _atla_kumesi(yol: Path) -> set[str]:
    """Dosyanın ATLA sabitini KAYNAKTAN okur; import etmez."""
    agac = ast.parse(yol.read_text(encoding="utf-8", errors="replace"))
    for d in ast.walk(agac):
        if isinstance(d, ast.Assign):
            for h in d.targets:
                if isinstance(h, ast.Name) and h.id == "ATLA":
                    return set(ast.literal_eval(d.value))
    raise AssertionError(f"{yol.name} içinde ATLA bulunamadı")


TARAYICILAR = [
    KOK / "sessiz_yutma.py",
    KOK / "tests" / "test_case_iskele_tutarlilik.py",
]


@pytest.mark.parametrize("yol", TARAYICILAR, ids=lambda p: p.name)
def test_kaynak_tarayicisi_CLAUDE_dizinini_atlar(yol: Path) -> None:
    assert ".claude" in _atla_kumesi(yol), (
        f"{yol.name} `.claude` altını tarıyor. Orada ajan iskelesi ve geçici "
        "worktree gölge kopyaları var; onları saymak kapının ölçütünü "
        "iddiasından geniş yapar ve bir sonraki ajan koşusunda kapı düşer.")


def test_OLCUT_gercekten_ATLA_uzerinden_isliyor() -> None:
    """Sabit doğru ama kullanılmıyorsa kapı yine sayar.

    `ATLA` tanımlı olup dosya gezintisinde SÜZGEÇ olarak kullanılmadığı bir
    sürüm bu testi geçer ama kusuru geri getirirdi; süzgecin varlığı ayrıca
    aranıyor.
    """
    for yol in TARAYICILAR:
        govde = yol.read_text(encoding="utf-8", errors="replace")
        assert "& ATLA" in govde, (
            f"{yol.name}: ATLA tanımlı ama dosya gezintisinde süzgeç değil")


def test_GOLGE_KOPYA_deposu_bugun_YOK() -> None:
    """Depoda bekleyen bir worktree kalmamalı.

    Kapılar artık `.claude`'u atladığı için bu bir başarısızlık sebebi değil;
    bekleyen kopya yine de GB'larca yer tutar ve hangi sürümün doğru olduğunu
    belirsizleştirir. Uyarı niteliğinde, bu yüzden atlanarak bildiriliyor.
    """
    kalanlar = sorted(p.name for p in (KOK / ".claude" / "worktrees").glob("*") if p.is_dir())
    if kalanlar:
        pytest.skip(f"bekleyen worktree: {kalanlar} (git worktree remove ile temizlenir)")
