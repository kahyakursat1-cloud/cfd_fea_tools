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

import pytest

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
    """Alan var ve hat onu dolduruyor mu.

    ÇAĞRININ BİÇİMİNE PİNLENMİYOR: eski sürüm `base.ortam =
    _ortam_mod.parmak_izi()` metnini birebir arıyordu ve çağrı
    `parmak_izi(cozucu=True)` olunca --- yani DÜZELİNCE --- kırıldı. Metne
    pinlenen test, iyileştirmeyi gerileme sanır. Çağrının ARGÜMANINI denetleyen
    yapısal test ayrı durur: tests/test_capa_ortam.py.
    """
    import ast

    from vehicle_pipeline import VehicleAnalysisResult
    assert "ortam" in VehicleAnalysisResult.__dataclass_fields__
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    atamalar = [d for d in ast.walk(ast.parse(src)) if isinstance(d, ast.Assign)
                and any(isinstance(t, ast.Attribute) and t.attr == "ortam"
                        for t in d.targets)
                and isinstance(d.value, ast.Call)]
    assert atamalar, "hat `…ortam = <çağrı>` ataması yapmıyor"
    cagrilan = {(d.value.func.attr if isinstance(d.value.func, ast.Attribute)
                 else getattr(d.value.func, "id", None)) for d in atamalar}
    assert cagrilan == {"parmak_izi"}, cagrilan


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


# ── Üretim-anı damgası ve çözücü sürümü ─────────────────────────────────────

def test_damgala_ORTAM_alanini_basiyor():
    """Damga şimdiye kadar yalnız `kanit.py --dogrula` yolundan ekleniyordu,
    yani bir kanıt ancak SONRADAN doğrulanırsa ortamını taşıyordu. Ölçüldü:
    kökteki 95 JSON'un hiçbiri damga taşımıyordu."""
    import ortam
    d = ortam.damgala({"vaka": "x"}, cozucu=False)
    assert "_ortam" in d and d["_ortam"]["python"]
    assert d["vaka"] == "x", "damga özgün alanları bozmamalı"


def test_cozucu_surumu_EKSIKSE_ayni_sayilmiyor():
    """`if a and b` koşulu, biri None olduğunda ne fark ne karşılaştırılamaz
    sayıyordu — 'çözücü sürümü bilinmiyor' hâli 'aynı' gibi okunuyordu. Paket
    alanlarında bu ayrım vardı; çözücüde yoktu ve çözücü daha kritik."""
    import ortam
    eski = {"python": "3.13.12", "os": "Windows 11", "cekirdek": 28,
            "paketler": dict.fromkeys(ortam.IZLENEN_PAKETLER, "1.0"),
            "cozucu": {"openfoam": None, "calculix": "2.17"}}
    yeni = dict(eski, cozucu={"openfoam": "Build: 11-abc", "calculix": "2.17"})
    f = ortam.fark(eski, yeni)
    assert any("cozucu:openfoam" in x for x in f["karsilastirilamaz"])


def test_cozucu_surumu_DEGISIRSE_fark_yaziliyor():
    import ortam
    eski = {"python": "3.13.12", "os": "Windows 11", "cekirdek": 28,
            "paketler": dict.fromkeys(ortam.IZLENEN_PAKETLER, "1.0"),
            "cozucu": {"openfoam": "Build: 11-aaa", "calculix": "2.17"}}
    yeni = dict(eski, cozucu={"openfoam": "Build: 11-bbb", "calculix": "2.17"})
    f = ortam.fark(eski, yeni)
    assert f["ayni"] is False
    assert any("openfoam" in x for x in f["farklar"])


def test_yeni_capalar_URETIM_aninda_damgali():
    """Taban sayaç: üretim anında damgalayan kanıt sayısı azalmasın."""
    import json
    damgali = []
    for ad in ("silindir_vorteks.json", "basamak_duvar_fonksiyonu.json"):
        p = KOK / ad
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d.get("_ortam"), dict):
            damgali.append(ad)
    if not damgali:
        pytest.skip("yeni çapa kanıtları henüz üretilmemiş")
    assert len(damgali) >= 1
    for ad in damgali:
        d = json.loads((KOK / ad).read_text(encoding="utf-8"))
        assert d["_ortam"].get("cozucu"), f"{ad}: çözücü sürümü damgada yok"


def test_capa_betikleri_DAMGALIYOR():
    """Kural kod düzeyinde: kanıt yazan yeni çapa betiği damgayı çağırmalı."""
    for ad in ("silindir_vorteks.py", "basamak_duvar_fonksiyonu.py",
               "basamak_yplus_ailesi.py"):
        src = (KOK / "experiments" / ad).read_text(encoding="utf-8")
        assert "ortam.damgala" in src, f"{ad} ortam damgası basmıyor"


# ── Damgalama kapsamı: taban sayaç ──────────────────────────────────────────

# Zarf tablosunu besleyen kanıtları üreten betikler — bunlar YAYIMLANAN
# sayılardır ve ortamlarını üretim anında damgalamalıdır. Taban: bu sayı
# AZALMAMALI. Yeni bir çapa betiği eklendiğinde listeye girer.
DAMGALAYAN_TABAN = 6


def _damgalayan_betikler() -> list[str]:
    out = []
    for p in sorted((KOK / "experiments").glob("*.py")):
        if "ortam.damgala" in p.read_text(encoding="utf-8", errors="ignore"):
            out.append(p.name)
    return out


def test_damgalayan_betik_sayisi_AZALMADI():
    d = _damgalayan_betikler()
    assert len(d) >= DAMGALAYAN_TABAN, (
        f"üretim anında damgalayan betik {len(d)} (taban {DAMGALAYAN_TABAN}): {d}")


def test_ESKI_kanitlar_toplu_damgalanmadi():
    """Eski kanıtı BUGÜNKÜ ortamla damgalamak YALAN olur: o sayı bu yığında
    üretilmedi. Damgasız kalmaları doğrudur ve `kanit.py --ortam` bunu
    'damga eklenmeden önce üretilmiş' diye ayrı sayar. Bu test, ileride
    'sayacı düzeltmek için' toplu damgalama yapılmasını engeller.
    """
    import json as _j
    damgali_eski = []
    for p in sorted(KOK.glob("*.json")):
        try:
            d = _j.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(d, dict) or not isinstance(d.get("_ortam"), dict):
            continue
        # Damgali olanlar, damgayi URETIM aninda basan betiklerden gelmeli
        if not d.get("_uretim") and "verdikt" not in d:
            damgali_eski.append(p.name)
    assert not damgali_eski, (
        f"üretim komutu olmayan dosyalara damga basılmış: {damgali_eski}")


def test_docker_taban_imaji_DIGESTE_sabit():
    """`:latest` DEĞİŞTİRİLEBİLİR bir etikettir: aynı Dockerfile yarın başka
    bir OpenFOAM derlemesi çekebilir ve yayımlanmış bir GCI bandı sessizce
    geçersizleşir. Digest içerik-adreslidir."""
    df = KOK / "docker" / "Dockerfile"
    if not df.exists():
        pytest.skip("Dockerfile yok")
    satir = [x for x in df.read_text(encoding="utf-8").splitlines()
             if x.startswith("FROM ")]
    assert satir, "FROM satırı yok"
    for x in satir:
        assert "@sha256:" in x, f"taban imaj digest'e sabit değil: {x}"
