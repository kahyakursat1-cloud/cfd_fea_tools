"""Linux-yürütme arka ucu seçici — WSL kırılganlığının ve tek-makine tavanının kapısı.

Tüm çözücü çağrıları (OpenFOAM, ccx) tek noktadan geçer; CFD_BACKEND ortam değişkeni
arka ucu seçer:
  wsl    (varsayılan) — mevcut davranış birebir (Ubuntu-22.04)
  yerel  — zaten Linux'ta koşuyoruz; komut doğrudan `bash -c` ile çalışır.
           Konteyner/CI/küme dağıtımı bunu kullanır (`native`/`linux` da kabul).
  docker — aynı bash komutu konteynerde koşar. Önkoşul: konteyner, host sürücüsünü
           AYNI /mnt/<x> yoluna bağlamalı (windows_to_wsl_path değişmeden çalışsın):
           docker run -d --name aerosim -v D:\\:/mnt/d aerosim-hub sleep infinity
CFD_EXT4=1 (yalnız wsl): case, çözüm süresince WSL'in ext4 diskinde koşar, sonunda
geri kopyalanır — drvfs (9p) paralel-yazım çökmesini (küre vakası) kökten çözer.
"""
from __future__ import annotations

import os
import subprocess

WSL_DISTRO = "Ubuntu-22.04"


def backend() -> str:
    return os.environ.get("CFD_BACKEND", "wsl")


def container() -> str:
    return os.environ.get("CFD_DOCKER_CONTAINER", "aerosim")


def linux_argv(bash_cmd: str, login: bool = False) -> list[str]:
    """Verilen bash komutunu seçili arka uçta koşacak argv.

    `login=True` → `bash -lc`: kabuk kullanıcının profil dosyalarını okur, yani
    PATH oradan gelir. Bu seçenek YOKTU ve eksikliği ölçülebilir bir sonuç
    doğuruyordu: `xfoil_kesit` XFOIL'i profilden gelen PATH ile buluyordu,
    dolayısıyla ortak katmana taşınamıyor ve kendi `wsl bash -lc` çağrısını
    kuruyordu (arka-uç sayacında 5 satır). Seçenek eklenince taşıma engeli
    kalktı. Varsayılan DEĞİŞMEDİ --- login olmayan çağrılar birebir eskisi gibi.
    """
    bayrak = "-lc" if login else "-c"
    ad = backend()
    if ad == "docker":
        return ["docker", "exec", container(), "bash", bayrak, bash_cmd]
    # YEREL: zaten Linux'tayız, sarmalayıcı YOK. Bu arka uç KONTEYNER İÇİNDE
    # zorunlu ve eksikti: katman yalnız "Windows'tan WSL'e" ve "Windows'tan
    # docker'a" biliyordu, "zaten Linux'tayım" seçeneği hiç yoktu. Ölçüldü
    # (2026-08-15): konteynerde worker `[Errno 2] No such file or directory:
    # 'wsl'` ile düştü — `CFD_BACKEND=yerel` tanınmadığı için varsayılan wsl
    # dalına SESSİZCE düşüyordu.
    if ad in ("yerel", "native", "linux"):
        return ["bash", bayrak, bash_cmd]
    return ["wsl", "-d", WSL_DISTRO, "--", "bash", bayrak, bash_cmd]


def linux_run(bash_cmd: str, timeout: int, login: bool = False,
              girdi: str | None = None) -> subprocess.CompletedProcess:
    """`girdi` verilirse komutun STDIN'ine yazılır.

    Etkileşimli çözücüler (XFOIL, Construct2D) komut dizisini stdin'den okur ve
    bu yetenek katmanda YOKTU --- eksikliği onları ortak katmandan uzak tutan
    gerekçelerden biriydi. Eklenmesi mevcut çağrıları etkilemez: `girdi=None`
    iken `subprocess.run` stdin'i eskisi gibi devralır.
    """
    return subprocess.run(linux_argv(bash_cmd, login=login), input=girdi,
                          capture_output=True, text=True, timeout=timeout)


def linux_popen(bash_cmd: str) -> subprocess.Popen:
    return subprocess.Popen(linux_argv(bash_cmd),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_home: str | None = None


def linux_home() -> str:
    """Arka uçtaki $HOME (ext4 çalışma dizini için; bir kez çözülür, önbellek)."""
    global _home
    if _home is None:
        try:
            _home = linux_run("echo $HOME", 30).stdout.strip() or "/root"
        except Exception:
            _home = "/root"
    return _home


def ext4_enabled() -> bool:
    return backend() == "wsl" and os.environ.get("CFD_EXT4") == "1"
