"""Linux-yürütme arka ucu seçici — WSL kırılganlığının ve tek-makine tavanının kapısı.

Tüm çözücü çağrıları (OpenFOAM, ccx) tek noktadan geçer; CFD_BACKEND ortam değişkeni
arka ucu seçer:
  wsl    (varsayılan) — mevcut davranış birebir (Ubuntu-22.04)
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


def linux_argv(bash_cmd: str) -> list[str]:
    """Verilen bash komutunu seçili arka uçta koşacak argv."""
    if backend() == "docker":
        return ["docker", "exec", container(), "bash", "-c", bash_cmd]
    return ["wsl", "-d", WSL_DISTRO, "--", "bash", "-c", bash_cmd]


def linux_run(bash_cmd: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(linux_argv(bash_cmd), capture_output=True, text=True,
                          timeout=timeout)


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
