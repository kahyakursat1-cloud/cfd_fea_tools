"""analysis.backend — arka uç seçici (wsl|docker) + ext4 bayrağı (saf mantık)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis import backend  # noqa: E402


def test_default_is_wsl_verbatim(monkeypatch):
    monkeypatch.delenv("CFD_BACKEND", raising=False)
    argv = backend.linux_argv("echo x")
    assert argv == ["wsl", "-d", "Ubuntu-22.04", "--", "bash", "-c", "echo x"]


def test_docker_backend_argv(monkeypatch):
    monkeypatch.setenv("CFD_BACKEND", "docker")
    monkeypatch.setenv("CFD_DOCKER_CONTAINER", "aerosim-test")
    argv = backend.linux_argv("foamRun > log 2>&1")
    assert argv[:3] == ["docker", "exec", "aerosim-test"]
    assert argv[-1] == "foamRun > log 2>&1"


def test_ext4_only_meaningful_on_wsl(monkeypatch):
    monkeypatch.setenv("CFD_EXT4", "1")
    monkeypatch.delenv("CFD_BACKEND", raising=False)
    assert backend.ext4_enabled()
    monkeypatch.setenv("CFD_BACKEND", "docker")   # docker zaten Linux-yerli disk
    assert not backend.ext4_enabled()
    monkeypatch.delenv("CFD_EXT4", raising=False)
    monkeypatch.delenv("CFD_BACKEND", raising=False)
    assert not backend.ext4_enabled()


def test_ccx_runner_routes_through_backend(monkeypatch):
    monkeypatch.setenv("CFD_BACKEND", "docker")
    monkeypatch.setenv("CFD_DOCKER_CONTAINER", "kutu")
    from analysis.ccx_runner import linux_argv as ccx_argv
    assert ccx_argv("ccx -i is")[:2] == ["docker", "exec"]
