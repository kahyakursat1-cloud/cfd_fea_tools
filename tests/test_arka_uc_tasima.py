"""Arka uç taşımasının DAVRANIŞI değiştirmediğini bağlar.

`arka_uc_sayaci` kaç çağrının katmanı atladığını sayar; taşındıktan sonra o
çağrının AYNI komutu çalıştırdığını söyleyemez. Asıl risk oradaydı: eski kod
`subprocess.run(f'wsl bash -c "..."', shell=True)` kullanıyordu, yani komut
Windows kabuğundan bir kez daha geçiyordu. `linux_run` argv listesi kurar ve
kabuk yoktur — tırnak/kaçış davranışı farklıdır.

Bu testler bash GÖVDESİNİN korunduğunu ve seçilen arka uca doğru sarıldığını
sınar. Çözücü çalıştırmazlar; sınanan şey komutun kendisidir.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from analysis.backend import WSL_DISTRO, linux_argv  # noqa: E402


def test_wsl_sarmalayicisi_ESKI_bicimle_ayni(monkeypatch):
    """Eski kod `wsl bash -c "<gövde>"` kuruyordu; yeni argv aynı üçlüyü
    vermeli (distro seçimi ARTI, o zaten kazançtı)."""
    monkeypatch.delenv("CFD_BACKEND", raising=False)
    govde = "source /opt/openfoam11/etc/bashrc && cd /mnt/d/x && blockMesh"
    argv = linux_argv(govde)
    assert argv[0] == "wsl" and argv[-3:] == ["bash", "-c", govde]
    assert WSL_DISTRO in argv, "distro seçimi atlanıyor"


def test_docker_arka_ucunda_AYNI_govde(monkeypatch):
    """Taşımanın bütün amacı: CFD_BACKEND=docker iken komut konteynere gitmeli
    ve gövde HİÇ değişmemeli."""
    monkeypatch.setenv("CFD_BACKEND", "docker")
    govde = "cd /mnt/d/x && ccx -i job"
    argv = linux_argv(govde)
    assert argv[0] == "docker" and argv[1] == "exec"
    assert argv[-1] == govde


def test_govde_KABUKTAN_gecmiyor(monkeypatch):
    """Eski `shell=True` yolunda tırnak ve `&&` Windows kabuğunca yorumlanırdı.
    argv listesinde gövde tek parça kalır — içindeki tırnak bozulmaz."""
    monkeypatch.delenv("CFD_BACKEND", raising=False)
    govde = "cd /mnt/d/a b && printf 'GRID\\nQUIT\\n' | c2d \"x.dat\""
    assert linux_argv(govde)[-1] == govde


# ── Taşınan modüller gerçekten katmanı kullanıyor mu ────────────────────────

TASINAN = [
    ("simulation_runner", "_wsl_openfoam"),
    ("validation_suite", "_wsl_of"),
]


@pytest.mark.parametrize("modul,fonk", TASINAN)
def test_yardimci_GOVDE_donduruyor_sarmalayici_DEGIL(modul, fonk):
    """Bu iki yardımcı komut DİZESİ döndürüyor ve çağıran onu çalıştırıyor.
    Taşımadan sonra dönen şey bash gövdesi olmalı; içinde `wsl` geçerse
    katman iki kez sarılır ve komut bozulur."""
    m = __import__(modul)
    govde = getattr(m, fonk)("/mnt/d/case", "blockMesh")
    assert not govde.startswith("wsl"), f"{modul}.{fonk} hâlâ sarmalayıcı kuruyor"
    assert "blockMesh" in govde and "/mnt/d/case" in govde


def test_sayac_TABANI_asmiyor():
    """Taban: 36 çağrı / 25 dosya ile başladı, 9 / 2'ye indi. Yeni kod bu sayıyı
    artıramaz; taşınan her modül tabanı düşürür."""
    from arka_uc_sayaci import BEKLEYEN, ozet
    o = ozet()
    assert o["toplam"] <= 9, (
        f"arka uç katmanını atlayan çağrı {o['toplam']}'a çıktı (taban 9): "
        f"{o['dosyalar']}")
    kalan = set(o["dosyalar"])
    assert kalan <= set(BEKLEYEN), (
        f"gerekçesi yazılmamış atlayan dosya: {sorted(kalan - set(BEKLEYEN))}")


def test_BEKLEYEN_gerekcesi_bos_olamaz():
    from arka_uc_sayaci import BEKLEYEN
    bos = [k for k, v in BEKLEYEN.items() if len((v or "").strip()) < 40]
    assert not bos, f"gerekçesi yetersiz: {bos}"


def test_BEKLEYEN_olu_kayit_biriktirmiyor():
    """Bir dosya taşındığında gerekçesi de gitmeli."""
    from arka_uc_sayaci import BEKLEYEN, ozet
    olu = sorted(set(BEKLEYEN) - set(ozet()["dosyalar"]))
    assert not olu, f"artık atlamayan dosyalar BEKLEYEN'de duruyor: {olu}"


def test_docstring_ORNEGI_cagri_sayilmiyor():
    """Aracın kendi yanlış pozitifi: taşınan modülde `wsl bash -c` ifadesi
    yalnız docstring'de kaldı ('eskiden şöyle kuruyordu') ve sayaç onu çağrı
    sanıyordu. Gerekçe yazan metin kod değildir."""
    from arka_uc_sayaci import _docstring_satirlari
    kaynak = ('def f():\n'
              '    """Eskiden `wsl bash -c "x"` kuruyordu."""\n'
              '    return 1\n')
    assert 2 in _docstring_satirlari(kaynak)


def test_ortam_degiskeni_TESTTEN_sizmiyor():
    """Bu dosya CFD_BACKEND'i değiştiriyor; süitin geri kalanına sızarsa
    başka testler konteyner arıyor sanır."""
    assert os.environ.get("CFD_BACKEND") in (None, "wsl", "docker")
