"""
CFD/FEA V&V Pipeline — Tek Giris Noktasi
=========================================
Endustri on-tasarim is akisini tek komutta yonetir:
  validate -> mesh-study -> polar -> loads -> fea -> report

Kullanim:
  python pipeline.py loads             # V-n yuk zarfi (hizli)
  python pipeline.py fea               # kritik yuk -> kanat FEA
  python pipeline.py report            # mevcut json'lardan V&V raporu
  python pipeline.py all               # loads + fea + report (compute-hafif)
  python pipeline.py validate-fea      # ankastre kiris dogrulama
  python pipeline.py coupling VTK STL  # CFD->FEA basinc coupling

Her asama sonucu JSON'a yazar; report bu JSON'lari toplar.
Agir CFD asamalari (mesh-study, polar) ayri runner'larla calistirilir:
  python run_aoa_polar.py 0 4 8 12 16
"""
import sys
import os
import json
from pathlib import Path

BASE = Path(__file__).parent


# ── Ucak konfigurasyonu (tek kaynak) ────────────────────────────────────────
AIRCRAFT_CFG = {
    "name": "MiniHawk İHA",
    "mass_kg": 1.8,
    "wing_area_m2": 0.45,
    "wing_span_m": 1.5,
    "mac_m": 0.30,
    "cl_max": 1.3,
    "cl_alpha": 5.0,
    "v_cruise_ms": 18.0,
    "category": "normal",
    # kanat yapisal
    "root_chord_m": 0.28,
    "tip_chord_m": 0.14,
    "wing_struct_span_m": 1.4,
    "material": "balsa_wood",
    "shell_thickness_m": 0.003,
    "naca": "2412",
}


def stage_loads():
    """V-n yuk zarfi + kritik durumlar."""
    from structural_loads import FlightEnvelope
    c = AIRCRAFT_CFG
    env = FlightEnvelope(
        mass_kg=c["mass_kg"], wing_area_m2=c["wing_area_m2"],
        wing_span_m=c["wing_span_m"], mac_m=c["mac_m"],
        cl_max=c["cl_max"], cl_min=-0.8 * c["cl_max"],
        cl_alpha=c["cl_alpha"], v_cruise_ms=c["v_cruise_ms"],
        category=c["category"],
    )
    summary = env.summary()
    (BASE / "envelope.json").write_text(json.dumps(summary, indent=2, default=str))
    crit = max(summary["critical_cases"], key=lambda x: abs(x["n"]))
    print(f"[loads] V-n zarfi: Va={summary['speeds_ms']['Va']} Vd={summary['speeds_ms']['Vd']} m/s")
    print(f"[loads] Tasarim-kritik: {crit['name']} n={crit['n']} -> envelope.json")
    return summary, crit


def stage_fea(crit=None):
    """Kritik yuk faktorunde kanat yapisal degerlendirme."""
    from fea_runner import FEASimulationRunner
    c = AIRCRAFT_CFG
    if crit is None:
        _, crit = stage_loads()
    n_crit = abs(crit["n"])
    runner = FEASimulationRunner(str(BASE / "fea_cases"))
    r = runner.run_wing_structural_assessment(
        span=c["wing_struct_span_m"], root_chord=c["root_chord_m"],
        tip_chord=c["tip_chord_m"], material_key=c["material"],
        aircraft_mass_kg=c["mass_kg"], cfd_cl=c["cl_max"],
        wind_speed=crit["V"], maneuver_g=n_crit,
        shell_thickness=c["shell_thickness_m"], naca_digits=c["naca"],
    )
    r["critical_case"] = crit
    (BASE / "fea_critical.json").write_text(json.dumps(r, indent=2, default=str))
    for lt in ("limit", "ultimate"):
        if lt in r and "safety_factor" in r[lt]:
            d = r[lt]
            print(f"[fea] {lt}: g={d['g_factor']} SF={d['safety_factor']} "
                  f"vonMises={d['max_von_mises_MPa']}MPa safe={d['is_safe']}")
    return r


def stage_coupling(vtk, stl):
    """CFD basinc -> FEA dugum kuvvetleri (1-way FSI)."""
    from coupling_fsi import cfd_pressure_to_fea_loads
    r = cfd_pressure_to_fea_loads(vtk, stl)
    out = {k: v for k, v in r.items() if k != "node_forces"}
    (BASE / "coupling_result.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"[coupling] Lift={out.get('lift_Fz_N')}N Drag={out.get('drag_Fx_N')}N "
          f"korunum={out.get('conservation_error'):.1e}")
    return out


def stage_validate_fea():
    """Ankastre kiris analitik dogrulama (hizli)."""
    from validation_suite import ValidationSuite
    suite = ValidationSuite(str(BASE / "validation"))
    r = suite.run_fea()
    print(f"[validate-fea] defleksiyon hata={r.get('deflection_err_pct')}% -> {r.get('status')}")
    return r


def stage_vspaero(alphas=(0, 4, 8, 12, 16)):
    """OpenVSP VSPAERO VLM hizli polar (saniyeler) — OpenFOAM capraz-kontrol.
    openvsp conda env'inde ayri Python ile calisir (subprocess).
    Induced drag + Cl-alpha egrisi; viskoz drag ve stall YOK (inviscid VLM).
    """
    import subprocess
    vsp_py = r"C:\Users\Victus\miniconda3\envs\openvsp\python.exe"
    if not Path(vsp_py).exists():
        print("[vspaero] openvsp conda env bulunamadi — atlandi")
        return None
    bridge = BASE / "openvsp_bridge.py"
    args = [vsp_py, str(bridge), "polar"] + [str(a) for a in alphas]
    r = subprocess.run(args, cwd=str(BASE), capture_output=True, text=True, timeout=600)
    pj = BASE / "vspaero_polar.json"
    if pj.exists():
        data = json.loads(pj.read_text())
        ok = [d for d in data if d.get("Cl") is not None]
        if len(ok) >= 2:
            sl = (ok[-1]["Cl"] - ok[0]["Cl"]) / (ok[-1]["alpha"] - ok[0]["alpha"] + 1e-9)
            print(f"[vspaero] {len(ok)} aci, Cl egimi={sl:.4f}/deg (VLM, ~saniyeler)")
        return data
    print(f"[vspaero] basarisiz: {r.stderr[-200:] if r.stderr else ''}")
    return None


def stage_rocket(ork_path="rockets/simple.ork"):
    """OpenRocket ucus simulasyonu — roketin VSPAERO'su (Barrowman + flight sim).
    Stabilite marji, apogee, hiz-irtifa, Cd(Mach). orenv conda env'inde calisir.
    """
    import subprocess
    or_py = r"C:\Users\Victus\miniconda3\envs\orenv\python.exe"
    java_home = r"C:\Users\Victus\miniconda3\envs\orenv\Library\lib\jvm"
    if not Path(or_py).exists():
        print("[rocket] orenv bulunamadi — atlandi")
        return None
    env = dict(os.environ, JAVA_HOME=java_home, PYTHONIOENCODING="utf-8")
    bridge = BASE / "openrocket_bridge.py"
    r = subprocess.run([or_py, str(bridge), ork_path], cwd=str(BASE),
                       capture_output=True, text=True, timeout=300, env=env)
    rj = BASE / "openrocket_result.json"
    if rj.exists():
        d = json.loads(rj.read_text())
        print(f"[rocket] apogee={d.get('apogee_m')}m  "
              f"stabilite={d.get('stability_min_cal')}-{d.get('stability_max_cal')}cal  "
              f"Vmax={d.get('max_velocity_ms')}m/s  Cd~{d.get('cd_at_burnout')}")
        return d
    print(f"[rocket] basarisiz: {r.stderr[-200:] if r.stderr else r.stdout[-200:]}")
    return None


def stage_rocket_fin(material="balsa", v_flight=29.3):
    """Roket fin yapisal: flutter (NACA TN 4197) + statik FEA."""
    from rocket_fin import assess
    r = assess(material, v_flight)
    (BASE / "rocket_fin_result.json").write_text(json.dumps(r, indent=2))
    fl = r["flutter"]
    print(f"[rocket-fin] flutter={fl['flutter_velocity_ms']}m/s margin={r['flutter_margin']}x "
          f"finSF={r['static_fea'].get('safety_factor')}")
    return r


def stage_rocket_cfd():
    """Roket CFD Cd — OpenRocket Barrowman ile capraz-dogrulama (yavas, ~15dk)."""
    import subprocess
    r = subprocess.run([sys.executable, str(BASE / "rocket_cfd.py")],
                       cwd=str(BASE), capture_output=True, text=True, timeout=5400)
    rf = BASE / "rocket_cfd_result.json"
    if rf.exists():
        d = json.loads(rf.read_text())
        print(f"[rocket-cfd] Cd_CFD={d.get('Cd_cfd')} vs Cd_OR={d.get('Cd_openrocket')} "
              f"(%{d.get('cross_val_err_pct')} fark)")
        return d
    print(f"[rocket-cfd] basarisiz")
    return None


def stage_report():
    """Mevcut tum JSON sonuclarindan V&V raporu uret."""
    import subprocess
    subprocess.run([sys.executable, str(BASE / "report_generator.py")], cwd=str(BASE))
    print(f"[report] -> {BASE / 'report' / 'VV_report.md'}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "loads":
        stage_loads()
    elif cmd == "fea":
        stage_fea()
    elif cmd == "validate-fea":
        stage_validate_fea()
    elif cmd == "coupling":
        if len(sys.argv) < 4:
            print("Kullanim: python pipeline.py coupling <VTK> <STL>")
            sys.exit(1)
        stage_coupling(sys.argv[2], sys.argv[3])
    elif cmd == "vspaero":
        alphas = [float(x) for x in sys.argv[2:]] or [0, 4, 8, 12, 16]
        stage_vspaero(alphas)
    elif cmd == "rocket":
        ork = sys.argv[2] if len(sys.argv) > 2 else "rockets/simple.ork"
        stage_rocket(ork)
    elif cmd == "rocket-fin":
        mat = sys.argv[2] if len(sys.argv) > 2 else "balsa"
        stage_rocket_fin(mat)
    elif cmd == "rocket-cfd":
        stage_rocket_cfd()
    elif cmd == "report":
        stage_report()
    elif cmd == "all":
        _, crit = stage_loads()
        stage_fea(crit)
        stage_report()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
