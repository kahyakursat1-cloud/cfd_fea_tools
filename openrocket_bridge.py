"""
OpenRocket Bridge
=================
orhelper (JPype) ile OpenRocket.jar'i suren kopru. Roket ucus simulasyonu
calistirir; stabilite marji, apogee, hiz-irtifa profili, Cd(Mach) cikarir.

Sabit-kanat pipeline'indaki VSPAERO'nun roket karsiligi:
  OpenRocket (Barrowman, hizli) <-> OpenFOAM CFD (Cd-Mach, yuksek fidelite)

Gereksinim (orenv conda):
  Python 3.11 + orhelper + jpype1 + openjdk=17
  JAVA_HOME = <orenv>/Library/lib/jvm
Calistirma:
  <orenv>/python.exe openrocket_bridge.py <rocket.ork>
"""

import os
import sys
import json
import math

JAR = r"C:\Program Files\OpenRocket\OpenRocket.jar"


def simulate(ork_path: str, sim_index: int = 0) -> dict:
    """Bir .ork roketini simule eder, ucus + aerodinamik metrikleri dondurur."""
    import orhelper
    from orhelper import FlightDataType
    import numpy as np

    with orhelper.OpenRocketInstance(JAR) as inst:
        orh = orhelper.Helper(inst)
        doc = orh.load_doc(ork_path)
        n_sim = doc.getSimulationCount()
        if n_sim == 0:
            return {"status": "FAILED", "error": "Roket dosyasinda simulasyon yok"}
        sim = doc.getSimulation(min(sim_index, n_sim - 1))
        orh.run_simulation(sim)

        ts = orh.get_timeseries(sim, [
            FlightDataType.TYPE_TIME,
            FlightDataType.TYPE_ALTITUDE,
            FlightDataType.TYPE_VELOCITY_TOTAL,
            FlightDataType.TYPE_ACCELERATION_TOTAL,
            FlightDataType.TYPE_MACH_NUMBER,
            FlightDataType.TYPE_DRAG_COEFF,
            FlightDataType.TYPE_STABILITY,
            FlightDataType.TYPE_CG_LOCATION,
            FlightDataType.TYPE_CP_LOCATION,
            FlightDataType.TYPE_THRUST_FORCE,
            FlightDataType.TYPE_MASS,
        ])

        t   = np.array(ts[FlightDataType.TYPE_TIME])
        alt = np.array(ts[FlightDataType.TYPE_ALTITUDE])
        vel = np.array(ts[FlightDataType.TYPE_VELOCITY_TOTAL])
        acc = np.array(ts[FlightDataType.TYPE_ACCELERATION_TOTAL])
        mach = np.array(ts[FlightDataType.TYPE_MACH_NUMBER])
        cd   = np.array(ts[FlightDataType.TYPE_DRAG_COEFF])
        stab = np.array(ts[FlightDataType.TYPE_STABILITY])
        cg   = np.array(ts[FlightDataType.TYPE_CG_LOCATION])
        cp   = np.array(ts[FlightDataType.TYPE_CP_LOCATION])
        thr  = np.array(ts[FlightDataType.TYPE_THRUST_FORCE])
        mass = np.array(ts[FlightDataType.TYPE_MASS])

        def fclean(a):
            a = np.asarray(a, dtype=float)
            return a[np.isfinite(a)]

        apogee = float(np.nanmax(alt))
        i_apogee = int(np.nanargmax(alt))
        v_max = float(np.nanmax(vel))
        a_max = float(np.nanmax(acc))
        # Burnout: thrust sifirlanma ani
        burn_idx = int(np.nonzero(thr > 0.1)[0][-1]) if np.any(thr > 0.1) else 0

        # Stabilite (kalip yukselis fazinda, v>5 m/s)
        flying = vel > 5.0
        stab_fly = stab[flying] if np.any(flying) else stab
        stab_min = float(np.nanmin(fclean(stab_fly))) if len(fclean(stab_fly)) else None
        stab_max = float(np.nanmax(fclean(stab_fly))) if len(fclean(stab_fly)) else None

        # Cd(Mach) tablosu — yukselis fazindan ornekle
        cd_mach = []
        if burn_idx > 1:
            for frac in [0.2, 0.4, 0.6, 0.8, 1.0]:
                k = int(frac * burn_idx)
                if 0 <= k < len(mach) and math.isfinite(mach[k]) and math.isfinite(cd[k]):
                    cd_mach.append({"Mach": round(float(mach[k]), 4),
                                    "Cd": round(float(cd[k]), 4)})

        return {
            "status": "SUCCESS",
            "apogee_m": round(apogee, 1),
            "time_to_apogee_s": round(float(t[i_apogee]), 2),
            "max_velocity_ms": round(v_max, 1),
            "max_mach": round(float(np.nanmax(fclean(mach))), 3),
            "max_acceleration_ms2": round(a_max, 1),
            "max_accel_g": round(a_max / 9.81, 1),
            "burnout_time_s": round(float(t[burn_idx]), 2),
            "burnout_altitude_m": round(float(alt[burn_idx]), 1),
            "liftoff_mass_kg": round(float(mass[0]), 4),
            "stability_min_cal": round(stab_min, 2) if stab_min is not None else None,
            "stability_max_cal": round(stab_max, 2) if stab_max is not None else None,
            "cd_vs_mach": cd_mach,
            "cd_at_burnout": round(float(cd[burn_idx]), 4) if math.isfinite(cd[burn_idx]) else None,
        }


if __name__ == "__main__":
    ork = sys.argv[1] if len(sys.argv) > 1 else "rockets/simple.ork"
    print(f"[OpenRocket] simule ediliyor: {ork}", flush=True)
    r = simulate(ork)
    print(json.dumps(r, indent=2), flush=True)
    if r.get("status") == "SUCCESS":
        json.dump(r, open("openrocket_result.json", "w"), indent=2)
        print("Kaydedildi: openrocket_result.json", flush=True)
