"""analysis.backend — arka uç seçici (wsl|docker|yerel) + ext4 bayrağı (saf mantık)."""
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


def test_YEREL_arka_uc_sarmalayici_KULLANMAZ():
    """Konteyner/CI/küme: zaten Linux'tayız, `wsl` ya da `docker exec` YOK.

    ÖLÇÜLEN KUSUR (2026-08-15): katman yalnız `docker` ve (varsayılan) `wsl`
    tanıyordu. `CFD_BACKEND=yerel` tanınmadığı için SESSİZCE wsl dalına düşüyor
    ve konteynerde worker `[Errno 2] ... 'wsl'` ile patlıyordu. Sessiz düşüş
    tehlikeliydi: yanlış ayar bir hata vermiyor, yalnızca yanlış komut kuruyordu.
    """
    import os

    from analysis.backend import linux_argv
    onceki = os.environ.get("CFD_BACKEND")
    try:
        for ad in ("yerel", "native", "linux"):
            os.environ["CFD_BACKEND"] = ad
            argv = linux_argv("echo x")
            assert argv[0] == "bash", f"{ad}: sarmalayıcı var -> {argv[:2]}"
            assert "wsl" not in argv and "docker" not in argv
        os.environ["CFD_BACKEND"] = "yerel"
        assert linux_argv("echo x", login=True)[:2] == ["bash", "-lc"]
    finally:
        if onceki is None:
            os.environ.pop("CFD_BACKEND", None)
        else:
            os.environ["CFD_BACKEND"] = onceki


def test_VARSAYILAN_arka_uc_DEGISMEDI():
    """Yeni seçenek mevcut Windows davranışını bozmamalı."""
    import os

    from analysis.backend import linux_argv
    onceki = os.environ.pop("CFD_BACKEND", None)
    try:
        assert linux_argv("echo x")[0] == "wsl"
    finally:
        if onceki is not None:
            os.environ["CFD_BACKEND"] = onceki
