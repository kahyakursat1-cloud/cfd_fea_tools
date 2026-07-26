"""GERÇEK çözücü regresyonu — OpenFOAM ve ccx'i uçtan uca koşturur (`external`).

Neden var: 270+ birim testin tamamı mock/saf-Python. Case yazımını, WSL/docker arka ucunu
veya frd okumayı bozan bir değişiklik hepsini yeşil bırakır; hata ancak saatlik bir koşuda
görülür. Bu iki test o zinciri KÜÇÜK ve HIZLI bir vaka üzerinde, ANALİTİK referansa karşı
çalıştırır — sayı tutmuyorsa hat bozulmuştur.

    python -m pytest -m external -v          # gerektirir: OpenFOAM 11 + ccx (doctor'a bak)
    python regresyon.py                      # aynı şey + JSON verdikt (gecelik cron için)

Toleranslar GEVŞEK bilerek: amaç fiziği doğrulamak değil (onu validation suite yapar),
hattın çalıştığını ve sonucun mertebe olarak doğru kaldığını çapalamaktır.
"""
from pathlib import Path

import numpy as np
import pytest
import trimesh

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.external


def _backend_hazir() -> bool:
    from analysis.backend import linux_run
    try:
        return linux_run("echo ok", 60).returncode == 0
    except Exception:
        return False


@pytest.fixture(scope="module")
def calisma(tmp_path_factory):
    if not _backend_hazir():
        pytest.skip("linux arka uç yok — `python pipeline.py doctor`")
    return tmp_path_factory.mktemp("regresyon")


def test_fea_ankastre_kiris_analitige_yakin(calisma):
    """STL -> tet mesh -> .inp -> ccx -> .frd zinciri, Euler-Bernoulli'ye karşı.

    δ = PL³/(3EI). Tet mesh kaba olduğu için %25 tolerans; amaç mertebe ve zincir
    bütünlüğü (kaymış düğüm sırası veya bozuk frd okuma buradan geçemez).
    """
    from analysis.calculix_writer import FEACase, FEAMaterial, FixedBC, ForceLoad, write_inp
    from analysis.ccx_runner import run_ccx
    from analysis.frd_parser import parse_frd
    from analysis.tet_mesher import generate_tet_mesh

    L, b, h = 1.0, 0.05, 0.05
    E, nu, P = 70e9, 0.33, 1000.0
    kiris = trimesh.creation.box(extents=[L, b, h])
    kiris.apply_translation([L / 2, 0, 0])

    mesh = generate_tet_mesh(kiris, target_size=0.025, output_dir=calisma, second_order=True)
    assert mesh.num_nodes > 100, "tet mesh üretilemedi"

    x = mesh.points[:, 0]
    kok = np.where(x <= x.min() + 1e-6)[0] + 1          # CalculiX 1-indexed
    uc = np.where(x >= x.max() - 1e-6)[0] + 1
    assert len(kok) >= 3 and len(uc) >= 3

    case = FEACase(
        name="regresyon_kiris", mesh=mesh,
        material=FEAMaterial.from_gpa("Al6061", E / 1e9, nu, 2700.0, yield_mpa=275.0),
        fixed_bcs=[FixedBC(node_ids=kok)],
        force_loads=[ForceLoad(node_ids=uc, direction=(0, 0, -1), total_force_n=P)],
    )
    inp = write_inp(case, calisma)
    r = run_ccx(inp, timeout=900)
    assert r.success, f"ccx başarısız (rc={r.return_code}): {(r.stdout or r.stderr)[-400:]}"

    res = parse_frd(Path(r.frd_path))
    uz = res.fields["DISP"][:, 2]
    delta_fem = abs(uz.min())
    I = b * h ** 3 / 12
    delta_analitik = P * L ** 3 / (3 * E * I)
    hata = abs(delta_fem - delta_analitik) / delta_analitik * 100
    assert hata < 25, (f"uç sehimi analitikten %{hata:.1f} sapıyor "
                       f"(fem={delta_fem * 1000:.3f} mm, analitik={delta_analitik * 1000:.3f} mm)")

    vm = res.von_mises()
    assert vm is not None and np.isfinite(vm).all() and vm.max() > 0


def test_cfd_kup_surukleme_fizik_kapisindan_gecer(calisma):
    """STL -> snappyHexMesh -> foamRun -> kuvvet çıkarımı zinciri, LİTERATÜR çapasıyla.

    Yüzeyi akışa dik küp: Cd ≈ 1.05 (Hoerner 1965, *Fluid-Dynamic Drag*; Re>1e4'te
    Re-bağımsız — burada Re = 10·0.1/1.5e-5 ≈ 6.7e4). Bant ±%30: `check_vehicle_validation`
    çapası ±%15 kullanır ama o daha ince mesh koşar; buradaki mesh regresyon hızı için
    bilerek kaba (≤250k hücre, refinement=1), o yüzden bant gevşetildi. Amaç sayısal
    doğruluk değil, hattın bozulmadığını literatüre karşı çapalamak.
    """
    from analysis.openfoam_runner import CFDCase, mesh_quality_gate, run_cfd
    from validity_envelope import force_admissibility

    kup = trimesh.creation.box(extents=[0.1, 0.1, 0.1])
    stl = calisma / "regresyon_kup.stl"
    kup.export(stl)

    case = CFDCase(name="regresyon_kup", stl_path=stl, velocity=10.0,
                   refinement_min=0, refinement_max=1, n_layers=0,
                   end_time=150, write_interval=150, max_global_cells=250_000)
    r = run_cfd(case, calisma, timeout=2400)
    assert r.success, f"CFD başarısız (rc={r.return_code}): {(r.stderr or r.stdout)[-400:]}"
    assert r.cd is not None and np.isfinite(r.cd), "Cd çıkarılamadı (forceCoeffs okuma yolu)"

    fizik = force_admissibility(r.cd, getattr(r, "cl", None))
    assert fizik["verdict"] != "inadmissible", f"Cd={r.cd}: {fizik['reasons']}"

    CD_HOERNER, BANT_PCT = 1.05, 30.0
    hata = abs(r.cd - CD_HOERNER) / CD_HOERNER * 100
    assert hata <= BANT_PCT, (f"küp Cd={r.cd:.4f}, Hoerner 1.05'ten %{hata:.1f} sapıyor "
                              f"(bant %{BANT_PCT}) — hat veya çözücü ayarı bozulmuş olabilir")

    cm = Path(r.case_dir) / "log.checkMesh"
    if cm.exists():
        assert mesh_quality_gate(cm.read_text(errors="ignore"))["verdict"] != "reject"
