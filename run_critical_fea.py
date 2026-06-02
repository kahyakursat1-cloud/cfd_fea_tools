"""Sertifikasyon zinciri: V-n kritik yuk -> kanat FEA boyutlandirma."""
import json
from structural_loads import FlightEnvelope
from fea_runner import FEASimulationRunner

env = FlightEnvelope(mass_kg=1.8, wing_area_m2=0.45, wing_span_m=1.5, mac_m=0.30,
                     cl_max=1.3, cl_min=-1.04, cl_alpha=5.0, v_cruise_ms=18.0)
cases = env.critical_load_cases()
crit = max(cases, key=lambda c: abs(c["n"]))
print(f"Tasarim-kritik durum: {crit['name']}  n={crit['n']}  V={crit['V']} m/s")
n_crit = abs(crit["n"])

runner = FEASimulationRunner("./fea_cases")
r = runner.run_wing_structural_assessment(
    span=1.4, root_chord=0.28, tip_chord=0.14,
    material_key="balsa_wood", aircraft_mass_kg=1.8,
    cfd_cl=1.3, wind_speed=crit["V"], maneuver_g=n_crit,
    shell_thickness=0.003, naca_digits="2412")
r["critical_case"] = crit
json.dump(r, open("fea_critical.json", "w"), indent=2, default=str)
print(json.dumps({k: v for k, v in r.items() if k in ("limit", "ultimate", "lift_N")},
                 indent=2, default=str))
