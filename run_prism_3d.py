"""
A3 dogrulama: prism-layer'li 3D mesh ile CFD + y+ kontrolu.
Tek medium case calistirir, checkMesh + y+ raporlar.
"""
import sys, subprocess
from pathlib import Path
from aircraft_geometry import AircraftLibrary
from simulation_runner import SimulationRunner, SimulationJob, _to_wsl_path, _wsl_openfoam

ac = AircraftLibrary.minihawk_uav()
runner = SimulationRunner(base_path="./prism_validation")
job = SimulationJob(
    case_name="minihawk_prism",
    aircraft=ac,
    solver="foamRun",
    mesh_size=0.012,
    wind_speed=15.0,
    analysis_type="aerodinamik",
    num_processors=1,
    end_time=500,
)

print("[A3] Prism-layer 3D mesh + CFD basliyor...", flush=True)
r = runner.run_simulation(job)
print(f"[A3] Sonuc: Cd={r.get('Cd')} Cl={r.get('Cl')} status={r.get('status')}", flush=True)

# checkMesh + y+
case_dir = Path("./prism_validation/cases/minihawk_prism")
wsl = _to_wsl_path(case_dir)
print("\n[A3] checkMesh:", flush=True)
cm = subprocess.run(_wsl_openfoam(wsl, "checkMesh -latestTime 2>&1 | grep -E 'non-ortho|skewness|layers|Layer'"),
                    shell=True, capture_output=True, text=True, timeout=300)
print(cm.stdout, flush=True)

print("[A3] y+ hesabi:", flush=True)
yp = subprocess.run(_wsl_openfoam(wsl, "foamRun -solver incompressibleFluid -postProcess -func yPlus -latestTime 2>&1 | grep -E 'y\\+|min|max|average' | tail -5"),
                    shell=True, capture_output=True, text=True, timeout=300)
print(yp.stdout, flush=True)
print("[A3] TAMAMLANDI", flush=True)
