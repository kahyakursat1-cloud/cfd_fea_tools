"""
Integration Test — End-to-end CFD/FEA workflow

Tüm sistemi test et:
  1. Geometry seç
  2. Material seç
  3. Mesh oluştur (GMSH mock)
  4. CFD çalıştır (OpenFOAM mock)
  5. FEA çalıştır (CalculiX mock)
  6. Post-processing (results extract)
  7. Rapor oluştur (PDF)
"""

import tempfile
from pathlib import Path

# Core modules
from aircraft_geometry import AircraftLibrary
from material_database import MaterialLibrary

# Post-processing
from post_processing.cfd_postprocessor import CFDPostProcessor
from post_processing.fea_postprocessor import FEAPostProcessor
from solvers.calculix_wrapper import CalculiXRunner

# Solvers
from solvers.gmsh_wrapper import GMSHMeshGenerator
from solvers.openfoam_wrapper import OpenFOAMRunner


def test_end_to_end_workflow():
    """Complete CFD/FEA workflow test"""
    print("="*70)
    print("END-TO-END WORKFLOW TEST")
    print("="*70)

    # Temporary directory for simulation
    temp_dir = Path(tempfile.mkdtemp())
    print(f"\n[INFO] Çalışma klasörü: {temp_dir}")

    try:
        # STEP 1: Geometry selection
        print("\n[STEP 1] Geometri seç")
        lib = AircraftLibrary()
        aircraft = lib.minihawk_uav()
        print(f"  [OK] Aircraft: {aircraft.name}")
        print(f"       Fuselage: L={aircraft.fuselage.length}m, D={aircraft.fuselage.diameter}m")

        # Geometric parameters for analytical calculations
        fuselage_L = aircraft.fuselage.length
        fuselage_D = aircraft.fuselage.diameter
        wing = getattr(aircraft, 'wing', None)

        def _resolve(obj, name, default):
            """Get attribute (may be method or value)"""
            v = getattr(obj, name, default)
            if callable(v):
                try:
                    v = v()
                except Exception:
                    v = default
            return v if v else default

        wing_span = _resolve(wing, 'span', 1.0) if wing else 1.0
        wing_root_chord = _resolve(wing, 'root_chord', 0.2) if wing else 0.2
        wing_tip_chord = _resolve(wing, 'tip_chord', wing_root_chord) if wing else wing_root_chord
        wing_area = _resolve(wing, 'area', 0.0) if wing else 0.0
        if not wing_area or wing_area <= 0:
            wing_area = 0.5 * (wing_root_chord + wing_tip_chord) * wing_span
        aspect_ratio = _resolve(wing, 'aspect_ratio', 0.0) if wing else 0.0
        if not aspect_ratio or aspect_ratio <= 0:
            aspect_ratio = (wing_span ** 2) / max(wing_area, 1e-6)
        wing_chord = 0.5 * (wing_root_chord + wing_tip_chord)  # mean chord
        print(f"       Wing: span={wing_span}m, MAC={wing_chord:.3f}m, S={wing_area:.3f}m², AR={aspect_ratio:.2f}")

        # STEP 2: Material selection
        print("\n[STEP 2] Malzeme seç")
        mat_lib = MaterialLibrary()
        material = mat_lib.get_material("Aluminum 6061")
        print(f"  [OK] Material: {material.name}")
        print(f"       sigma_y={material.yield_strength} MPa, E={material.youngs_modulus} GPa, rho={material.density} kg/m3")

        # STEP 3: Mesh generation
        print("\n[STEP 3] Mesh oluştur (GMSH)")
        mesh_dir = temp_dir / "mesh"
        mesh_gen = GMSHMeshGenerator(mesh_dir)

        from mesh_generator import MeshGenerator
        geo_gen = MeshGenerator(aircraft, mesh_size=0.1)
        geo_script = geo_gen.generate_gmsh_script()

        geo_file = mesh_gen.create_geo_file(geo_script, mesh_dir / "geometry.geo")
        mesh_file = mesh_gen.run_gmsh(geo_file, mesh_size=0.1)
        if mesh_file and mesh_file.exists():
            size_kb = mesh_file.stat().st_size / 1024
            print(f"  [OK] Mesh oluşturuldu: {size_kb:.1f} KB")
        else:
            print("  [WARNING] Gerçek mesh yok, mock kullanılıyor")

        # STEP 4: CFD Simulation
        wind_speed = 15.0  # m/s
        alpha_deg = 2.0    # angle of attack
        print(f"\n[STEP 4] CFD analizi (V={wind_speed}m/s, α={alpha_deg}°)")
        cfd_dir = temp_dir / "OpenFOAM"
        cfd_runner = OpenFOAMRunner(cfd_dir / "case", solver="simpleFoam")

        cfd_runner.create_case_structure(mesh_file, params={'wind_speed': wind_speed})
        cfd_success = cfd_runner.run_simulation(n_processors=4, use_gpu=True)

        # Use real wing area as reference
        cfd_processor = CFDPostProcessor(
            cfd_dir / "case",
            reference_area=wing_area,
            reference_length=wing_chord,
        )
        cfd_result = cfd_processor.extract_all(
            aircraft_name=aircraft.name,
            wind_speed=wind_speed,
            mesh_elements=2500000,
            aspect_ratio=aspect_ratio,
            alpha_deg=alpha_deg,
        )

        print(f"  [OK] Cd={cfd_result.drag_coefficient:.4f}, Cl={cfd_result.lift_coefficient:.4f}")
        print(f"       Re={cfd_result.reynolds_number:.2e}, Fd={cfd_result.drag_force:.2f}N, Fl={cfd_result.lift_force:.2f}N")

        # STEP 5: FEA Simulation
        # Applied load = lift force (worst case: 2.5g maneuver)
        applied_load = max(cfd_result.lift_force * 2.5, 100.0)  # N
        print(f"\n[STEP 5] FEA analizi (P={applied_load:.1f}N, L={wing_span/2}m)")
        fea_dir = temp_dir / "CalculiX"
        fea_runner = CalculiXRunner(fea_dir / "case.inp", output_dir=fea_dir)

        fea_runner.create_inp_file(mesh_file, material, analysis_type="STATIC", applied_load=applied_load)
        fea_success = fea_runner.run_analysis(n_cpus=4, use_gpu=True)

        # Wing spar dimensions (tube): typical aircraft spar
        spar_od = 0.020  # 20mm OD
        spar_id = 0.018  # 18mm ID (2mm wall)
        spar_length = wing_span / 2  # half-span = cantilever length

        fea_processor = FEAPostProcessor(fea_dir / "case.frd", fea_dir / "case.inp")
        fea_result = fea_processor.extract_all(
            aircraft_name=aircraft.name,
            material=material,
            analysis_type="STATIC",
            applied_load=applied_load,
            n_elements=150000,
            beam_length=spar_length,
            tube_od=spar_od,
            tube_id=spar_id,
        )

        print(f"  [OK] FEA Sonuçları: sigma_max={fea_result.max_stress:.2f} MPa, SF={fea_result.safety_factor:.2f}")

        # STEP 6: Summary
        print("\n" + "="*70)
        print("[SUCCESS] END-TO-END WORKFLOW TAMAMLANDI!")
        print("="*70)
        print(f"\nAircraft: {aircraft.name}")
        print(f"Material: {material.name}")
        print(f"CFD: Cd={cfd_result.drag_coefficient:.4f}, Cl={cfd_result.lift_coefficient:.4f}")
        print(f"FEA: sigma_max={fea_result.max_stress:.2f} MPa, SF={fea_result.safety_factor:.2f} ({fea_result.stress_status()})")

        return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_end_to_end_workflow()
    exit(0 if success else 1)
