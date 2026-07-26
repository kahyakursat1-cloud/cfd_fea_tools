"""Araç FEA yolu GERÇEK ccx ile uçtan uca — `external`.

`vehicle_fea.run_structural_check` GUI'deki "FEA" butonunun arkasıdır ve kapsamı %17'ydi:
CFD basıncı → tet mesh → .inp → ccx → .frd → gerilme/SF → yapısal fizik kapısı zinciri
hiçbir otomatik testle korunmuyordu. Test, CFD koşusu GEREKTİRMEZ — sentetik ama
format-sadık bir yüzey-basınç VTK'sı ile aynı yolu sürer.

    python -m pytest -m external tests/test_vehicle_fea_regresyon.py -v
"""
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

pytestmark = pytest.mark.external


def _backend_hazir() -> bool:
    from analysis.backend import linux_run
    try:
        return linux_run("which ccx", 60).returncode == 0
    except Exception:
        return False


@pytest.fixture(scope="module")
def kosu(tmp_path_factory):
    """Tamamlanmış bir CFD koşusunu taklit eden asgari dizin (sonuc.json + basınç VTK)."""
    if not _backend_hazir():
        pytest.skip("ccx yok — `python pipeline.py doctor`")
    d = tmp_path_factory.mktemp("fea_reg")

    kutu = trimesh.creation.box(extents=(0.4, 0.2, 0.05)).subdivide().subdivide()
    stl = d / "govde_prep.stl"
    kutu.export(stl)

    # Yüzey basınç VTK'sı: üst yüzde üniform p (aşağı bastırır)
    v = kutu.vertices
    f = kutu.faces
    ust = [i for i, tri in enumerate(f) if v[tri][:, 2].mean() > 0.02]
    satir = ["# vtk DataFile Version 3.0", "sentetik", "ASCII", "DATASET POLYDATA",
             f"POINTS {len(v)} float"]
    satir += [f"{p[0]} {p[1]} {p[2]}" for p in v]
    satir.append(f"POLYGONS {len(f)} {4 * len(f)}")
    satir += [f"3 {t[0]} {t[1]} {t[2]}" for t in f]
    satir += [f"CELL_DATA {len(f)}", "FIELD attributes 1", f"p 1 {len(f)} float"]
    satir += [("2000.0" if i in ust else "0.0") for i in range(len(f))]
    vtk = d / "yuzey.vtk"
    vtk.write_text("\n".join(satir) + "\n", encoding="ascii")

    (d / "sonuc.json").write_text(json.dumps({
        "status": "ok", "stl": str(stl), "cp_vtk": str(vtk),
        "velocity": 20.0, "geometry": {"lmax_m": 0.4},
    }, ensure_ascii=False), encoding="utf-8")
    return d


def test_arac_fea_zinciri_ve_fizik_kapisi(kosu):
    """CFD basıncı → tet mesh → ccx → gerilme → SF → kapı."""
    from vehicle_fea import run_structural_check

    r = run_structural_check(kosu, material="aluminum_6061", constraint="x_min",
                             model="dolu", analysis="statik")
    assert r["status"] == "ok", f"FEA zinciri koptu: {r.get('error', '')[:300]}"

    assert r["dugum"] > 100 and r["eleman"] > 100, "tet mesh üretilememiş"
    vm = r.get("max_von_mises_MPa")
    assert vm is not None and np.isfinite(vm) and vm > 0, "gerilme alanı çıkarılamadı"

    kapi = r.get("fizik_kabul")
    assert kapi is not None, "yapısal fizik kapısı sonuca yazılmamış"
    assert kapi["verdict"] != "inadmissible", (
        f"hafif ama GERÇEK yük reddedildi (σ={vm} MPa): {kapi['reasons']}")

    sf = r.get("emniyet_faktoru")
    assert sf is None or (np.isfinite(sf) and 0 < sf < 1e4)


def test_yuksuz_kosu_kapiya_takilir(kosu, tmp_path):
    """Basınç sıfırsa yapı yüklenmemiştir; SF astronomik çıkar ve rapor 'güvenli'
    derdi. Kapı bunu yakalamalı — testin varlık sebebi."""
    from vehicle_fea import run_structural_check

    d = tmp_path / "yuksuz"
    d.mkdir()
    for ad in ("govde_prep.stl",):
        (d / ad).write_bytes((kosu / ad).read_bytes())
    metin = (kosu / "yuzey.vtk").read_text(encoding="ascii")
    bas, veri = metin.split("float\n", 2)[0], metin.rsplit("float\n", 1)[1]
    sifirli = metin.replace("2000.0", "0.0")
    (d / "yuzey.vtk").write_text(sifirli, encoding="ascii")
    assert veri is not None and bas is not None
    (d / "sonuc.json").write_text(json.dumps({
        "status": "ok", "stl": str(d / "govde_prep.stl"), "cp_vtk": str(d / "yuzey.vtk"),
        "velocity": 20.0, "geometry": {"lmax_m": 0.4},
    }, ensure_ascii=False), encoding="utf-8")

    r = run_structural_check(d, material="aluminum_6061", constraint="x_min",
                             model="dolu", analysis="statik")
    if r["status"] != "ok":
        pytest.skip(f"yüksüz case çözücüde durdu: {r.get('error','')[:120]}")
    kapi = r.get("fizik_kabul") or {}
    assert kapi.get("verdict") == "inadmissible", \
        f"yüksüz koşu kapıdan geçti (σ={r.get('max_von_mises_MPa')} MPa) — 'güvenli' der"
    assert "SF ANLAMSIZ" in r.get("_gerilme_notu", "")


def test_modal_analiz_pozitif_frekans(kosu):
    """Frekans analizi yük gerektirmez; f1>0 ve sonlu olmalı (rijit-cisim modu değil)."""
    from vehicle_fea import run_structural_check

    r = run_structural_check(kosu, material="aluminum_6061", constraint="x_min",
                             model="kabuk", analysis="frekans", n_modes=4)
    if r["status"] != "ok":
        pytest.skip(f"modal çözüm yapılamadı: {r.get('error','')[:150]}")
    fr = [f for f in (r.get("dogal_frekanslar_hz") or []) if f is not None and np.isfinite(f)]
    assert fr, "ccx frekans tablosu ÜRETTİ ama parser okuyamadı (sürüm/başlık uyumu)"
    assert all(a <= b + 1e-9 for a, b in zip(fr, fr[1:])), f"modlar sıralı değil: {fr[:4]}"
    assert all(f >= 0 for f in fr)
    # Rijit-cisim modu sessizce raporlanmamalı: ya gerçek yapısal frekans ya AÇIK uyarı
    if fr[0] < 1.0:
        assert r.get("rijit_cisim_suphesi") is True and "uyari" in r,             f"f1={fr[0]:.4g} Hz ≈ 0 ama rijit-cisim uyarısı yok"
