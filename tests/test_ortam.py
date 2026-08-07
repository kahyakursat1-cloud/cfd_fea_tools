"""Ortam parmak izi: bir sayının hangi sürümlerle üretildiği kanıtın parçasıdır.

Kanıt dosyaları üretim KOMUTUNU taşıyordu ama komut yetmez — aynı komut başka
bir OpenFOAM ya da numpy ile başka bir sayı verebilir ve yayımlanmış bir band
sessizce geçersizleşir.

Tasarım kuralı: eksik alan "farksızlık" SAYILMAZ. Eski bir kanıtta parmak izi
yoksa cevap "aynı" değil, "karşılaştırılamaz"dır.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import ortam  # noqa: E402


def test_parmak_izi_sonucu_etkileyenleri_tasiyor():
    d = ortam.parmak_izi()
    assert d["python"] and d["os"]
    for ad in ("numpy", "scipy", "trimesh"):
        assert ad in d["paketler"]


def test_parmak_izi_KISISEL_veri_tasimaz():
    """Kanıt dosyaları paylaşılıyor: makine/kullanıcı adı ve yol girmemeli."""
    metin = json.dumps(ortam.parmak_izi(), ensure_ascii=False).lower()
    import getpass
    import socket
    for gizli in (getpass.getuser().lower(), socket.gethostname().lower()):
        if len(gizli) > 3:
            assert gizli not in metin
    assert "c:\\" not in metin and "/users/" not in metin


def test_ayni_ortam_fark_uretmez():
    d = ortam.parmak_izi()
    f = ortam.fark(d, d)
    assert f["ayni"] is True and f["farklar"] == []


def test_surum_degisimi_yakalanir():
    a = ortam.parmak_izi()
    b = json.loads(json.dumps(a))
    b["paketler"]["numpy"] = "0.0.1"
    f = ortam.fark(a, b)
    assert f["ayni"] is False
    assert any("numpy" in x for x in f["farklar"])


def test_python_ve_cekirdek_degisimi_de_yakalanir():
    a = ortam.parmak_izi()
    b = json.loads(json.dumps(a))
    b["python"] = "3.9.0"
    b["cekirdek"] = (a["cekirdek"] or 1) + 4
    f = ortam.fark(a, b)
    assert sum(1 for x in f["farklar"] if x.startswith(("python", "cekirdek"))) == 2


def test_damgasiz_kanit_AYNI_sayilmaz():
    """En tehlikeli hâl: parmak izi yokken 'fark yok' demek."""
    f = ortam.fark(None)
    assert f["ayni"] is None
    assert f["karsilastirilamaz"]
    assert "YOK" in f["karsilastirilamaz"][0]


def test_eksik_alan_farksizlik_sayilmaz():
    a = ortam.parmak_izi()
    b = json.loads(json.dumps(a))
    b["paketler"].pop("scipy")
    f = ortam.fark(a, b)
    assert "paket:scipy" in f["karsilastirilamaz"]
    assert not any("scipy" in x for x in f["farklar"])


def test_cozucu_surumu_istege_bagli():
    """WSL'e gitmek yavaş; varsayılan parmak izi çözücüye DOKUNMAZ."""
    assert "cozucu" not in ortam.parmak_izi()


# ── tüketiciler ────────────────────────────────────────────────────────────

def test_damgalama_ortami_yaziyor():
    src = (KOK / "kanit.py").read_text(encoding="utf-8")
    i = src.index("def damgala(")
    assert "ortam.parmak_izi()" in src[i:i + 1200]


def test_arac_hatti_sonuca_ortam_koyuyor():
    from vehicle_pipeline import VehicleAnalysisResult
    assert "ortam" in VehicleAnalysisResult.__dataclass_fields__
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    assert "base.ortam = _ortam_mod.parmak_izi()" in src


# ── kilit dosyası ──────────────────────────────────────────────────────────

def test_kilit_dosyasi_kurulu_surumlerle_TUTARLI():
    """Kilit elle yazılırsa bir süre sonra yalan söyler. Bu test onu ölçülene
    bağlar: kilitteki sürüm kurulu sürümden farklıysa kilit tazelenmeli."""
    import importlib.metadata as md
    satirlar = (KOK / "ortam_kilidi.txt").read_text(encoding="utf-8").splitlines()
    sapma = []
    for s in satirlar:
        s = s.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)==(.+)$", s)
        assert m, f"kilit satırı çözümlenemedi: {s}"
        ad, sur = m.group(1), m.group(2)
        kurulu = md.version(ad)
        if kurulu != sur:
            sapma.append(f"{ad}: kilit {sur} ≠ kurulu {kurulu}")
    assert not sapma, ("ortam_kilidi.txt tazelenmeli: " + "; ".join(sapma))


def test_kilit_pyprojectteki_zorunlulari_kapsiyor():
    kilit = (KOK / "ortam_kilidi.txt").read_text(encoding="utf-8")
    tomlmetin = (KOK / "pyproject.toml").read_text(encoding="utf-8")
    blok = tomlmetin[tomlmetin.index("dependencies = ["):]
    blok = blok[:blok.index("]")]
    for ad in re.findall(r'"([A-Za-z0-9_.\-]+)\s*[><=]', blok):
        assert re.search(rf"^{re.escape(ad)}==", kilit, re.M), f"kilitte yok: {ad}"


def test_kilit_kapsamadigi_seyi_ACIKCA_soyluyor():
    """OpenFOAM/CalculiX kilitte yok ve Docker etiketi digest'e sabit değil —
    bu bilinen boşluk saklanmamalı."""
    kilit = (KOK / "ortam_kilidi.txt").read_text(encoding="utf-8")
    assert "OpenFOAM" in kilit and "CalculiX" in kilit
    assert "digest" in kilit.lower()
