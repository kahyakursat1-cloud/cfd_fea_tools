"""Arka uç katmanını atlayan çağrılar ARTMASIN.

`analysis/backend.py` çözücünün nerede koşacağını tek yerden seçer (WSL ya da
Docker konteyneri, `CFD_BACKEND`). Kök dizindeki birçok betik `wsl bash -c`
çağrısını elle kurup o katmanı atlıyor. Sonuç sessizdir: `CFD_BACKEND=docker`
ayarlandığında araç hattı konteynere giderken bu betikler WSL'de kalır — aynı
kampanyanın iki yarısı FARKLI çözücülerde koşabilir.

24 dosyayı tek commit'te yeniden yazmak ölçülmemiş bir riski bir araya
sıkıştırmak olurdu (bazıları yarış-durumu ve zaman-aşımı inceliklerine sahip).
Bu yüzden taban ölçülür ve kilitlenir; taşınan her modül tabanı DÜŞÜRÜR.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from arka_uc_sayaci import ozet, tara  # noqa: E402

# 2026-08-07 ölçümü. Taşındı: transition_polar, cgrid_elliptic, cgrid_generator,
# rocket_cfd, run_aoa_polar. Bu sayı ARTAMAZ; düşürmek serbesttir (ve amaçtır).
TABAN_TOPLAM = 36
TABAN_DOSYA = 25


def test_arka_uc_atlama_artmadi():
    o = ozet()
    assert o["toplam"] <= TABAN_TOPLAM, (
        f"{o['toplam']} çağrı arka uç katmanını atlıyor (taban {TABAN_TOPLAM}). "
        "Yeni kod `analysis.backend.linux_run` kullanmalı: bash gövdesi aynen "
        "kalır, değişen yalnız taşımadır. Dosyalar: "
        + ", ".join(o["dosyalar"]))


def test_dosya_sayisi_artmadi():
    assert ozet()["dosya_sayisi"] <= TABAN_DOSYA


def test_tasinan_moduller_geri_donmedi():
    """Bu turda taşınan beş modül yeniden elle `wsl bash -c` kurmamalı."""
    tasinan = {"transition_polar.py", "cgrid_elliptic.py", "cgrid_generator.py",
               "rocket_cfd.py", "run_aoa_polar.py"}
    kirli = {x["dosya"] for x in tara()} & tasinan
    assert not kirli, f"taşınmış modül geri döndü: {kirli}"


def test_tasinan_moduller_backend_kullaniyor():
    for ad in ("transition_polar.py", "cgrid_elliptic.py", "cgrid_generator.py",
               "rocket_cfd.py", "run_aoa_polar.py"):
        src = (KOK / ad).read_text(encoding="utf-8")
        assert "from analysis.backend import linux_run" in src, ad
        assert "linux_run(" in src, f"{ad}: import var ama kullanılmıyor"


def test_backend_kendisi_MUAF():
    """Taşıma katmanını kuran tek meşru yer sayılmamalı, yoksa sayaç kendi
    çözümünü ihlal sayardı."""
    assert not any(x["dosya"] == "analysis/backend.py" for x in tara())


def test_yorum_satiri_ihlal_sayilmaz():
    """Gerekçe yazan yorumlar (`# ARKA UC KATMANI: wsl bash -c ...`) sayılmaz;
    aksi hâlde kusuru AÇIKLAMAK kusur sayılırdı."""
    for x in tara():
        assert not x["kod"].startswith("#")


def test_docker_arka_ucu_gercekten_farkli_komut_uretiyor(monkeypatch):
    """Sayacın varlık nedeni: backend seçimi gerçekten komutu değiştiriyor."""
    from analysis import backend
    monkeypatch.setenv("CFD_BACKEND", "wsl")
    a = backend.linux_argv("echo x")
    monkeypatch.setenv("CFD_BACKEND", "docker")
    b = backend.linux_argv("echo x")
    assert a != b
    assert a[0] == "wsl" and b[0] == "docker"
