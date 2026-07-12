"""
CalculiX (ccx) çalıştırıcı.

Windows native ccx.exe kararsız olduğu için WSL içindeki `ccx` (Ubuntu paketi)
kullanılır. Windows path'ini WSL path'ine çevirir, çalıştırır, çıktıyı Windows
tarafına geri verir.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .backend import WSL_DISTRO, linux_argv  # arka uç seçici (wsl|docker)

__all__ = ["WSL_DISTRO", "CCXResult", "windows_to_wsl_path", "run_ccx"]


@dataclass
class CCXResult:
    job_dir: Path
    job_name: str
    return_code: int
    frd_path: Path        # .frd sonuç dosyası
    dat_path: Path        # .dat printed output
    sta_path: Path        # .sta status
    cvg_path: Path        # .cvg convergence
    stdout: str
    stderr: str
    success: bool


def windows_to_wsl_path(p: Path | str) -> str:
    """C:\\Users\\... -> /mnt/c/Users/..."""
    p = Path(p).resolve()
    drive = p.drive  # 'C:'
    if not drive:
        return str(p).replace("\\", "/")
    letter = drive[0].lower()
    rest = str(p)[len(drive):].replace("\\", "/")
    return f"/mnt/{letter}{rest}"


def run_ccx(inp_path: Path, timeout: int = 1800,
            progress_callback=None) -> CCXResult:
    """CalculiX'i WSL üzerinden çalıştır.

    Args:
        inp_path: Windows .inp dosyasının yolu
        timeout: saniye
        progress_callback: callable(percent: int, message: str)

    Returns:
        CCXResult
    """
    inp_path = Path(inp_path).resolve()
    if not inp_path.exists():
        raise FileNotFoundError(f"Input dosyası yok: {inp_path}")

    job_dir = inp_path.parent
    job_name = inp_path.stem  # uzantısız

    wsl_dir = windows_to_wsl_path(job_dir)

    if progress_callback:
        progress_callback(5, "ccx çalıştırılıyor (WSL)...")

    # ccx -i jobname  (uzantısız!)
    cmd = linux_argv(f"cd '{wsl_dir}' && ccx -i {job_name} 2>&1")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return CCXResult(
            job_dir=job_dir, job_name=job_name, return_code=-1,
            frd_path=job_dir / f"{job_name}.frd",
            dat_path=job_dir / f"{job_name}.dat",
            sta_path=job_dir / f"{job_name}.sta",
            cvg_path=job_dir / f"{job_name}.cvg",
            stdout=str(e.stdout or ""), stderr="TIMEOUT",
            success=False,
        )

    frd = job_dir / f"{job_name}.frd"

    if progress_callback:
        progress_callback(100, "ccx tamamlandı")

    # ccx return code 0 olsa bile çözüm başarısız olmuş olabilir
    success = (result.returncode == 0
               and frd.exists()
               and frd.stat().st_size > 0
               and _frd_has_results(frd))

    return CCXResult(
        job_dir=job_dir, job_name=job_name,
        return_code=result.returncode,
        frd_path=frd,
        dat_path=job_dir / f"{job_name}.dat",
        sta_path=job_dir / f"{job_name}.sta",
        cvg_path=job_dir / f"{job_name}.cvg",
        stdout=result.stdout,
        stderr=result.stderr,
        success=success,
    )


_FRD_DATASET_PATTERN = re.compile(rb"^\s*-4")


def _frd_has_results(frd_path: Path) -> bool:
    """.frd içinde en az bir nodal sonuç bloğu var mı?"""
    try:
        with frd_path.open("rb") as f:
            for line in f:
                if _FRD_DATASET_PATTERN.match(line):
                    return True
    except OSError:
        return False
    return False
