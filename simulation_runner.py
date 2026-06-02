"""
Batch Simulation Runner
Otomatik CFD/FEA çalıştırma, paralel işleme, sonuç analizi
"""

import concurrent.futures
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from aircraft_geometry import Aircraft, AircraftLibrary, ParametricStudy
from mesh_generator import MeshGenerator

# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION JOB
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SimulationJob:
    """Tek bir simülasyon işi"""
    case_name: str
    aircraft: Aircraft
    solver: str              # "simpleFoam" | "pimpleFoam" | "rhoCentralFoam"
    mesh_size: float
    wind_speed: float
    analysis_type: str       # "aerodinamik" | "structural" | "thermal"
    num_processors: int = 4
    end_time: float = 500.0  # Solver iterasyon sayısı (SIMPLE yakınsaması için min 500)

    def case_directory(self) -> str:
        return f"cases/{self.case_name}"

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def _to_wsl_path(win_path: Path) -> str:
    """Windows yolunu WSL mount yoluna çevir: D:\\foo\\bar → /mnt/d/foo/bar"""
    p = str(win_path.resolve())
    drive = p[0].lower()
    rest = p[2:].replace("\\", "/")
    return f"/mnt/{drive}{rest}"


def _wsl_openfoam(wsl_case_dir: str, cmd: str) -> str:
    """OpenFOAM ortamını kaynak alarak WSL'de komut çalıştır"""
    return f'wsl bash -c "source /opt/openfoam11/etc/bashrc && cd {wsl_case_dir} && {cmd}"'


class SimulationRunner:
    """OpenFOAM simülasyonları yönet"""

    def __init__(self, base_path: str = "./simulations"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        self.results = []

    def setup_case(self, job: SimulationJob) -> bool:
        """Simülasyon case'i hazırla"""
        try:
            case_dir = self.base_path / job.case_directory()
            case_dir.mkdir(parents=True, exist_ok=True)

            # 0/ — Başlangıç koşulları
            self._create_initial_conditions(case_dir, job)

            # system/ — Solver ayarları
            self._create_system_files(case_dir, job)

            # Constant/ — Geometri ve malzeme
            self._create_constant_files(case_dir, job)

            # Case özet dosyası
            with open(case_dir / "case_info.json", "w") as f:
                json.dump(job.to_dict(), f, default=str, indent=2)

            return True
        except Exception as e:
            print(f"[FAIL] Case setup failed: {e}")
            return False

    def _create_initial_conditions(self, case_dir: Path, job: SimulationJob) -> None:
        """0/ Başlangıç koşulları — U, p, k, omega, nut (kOmegaSST)"""
        zero_dir = case_dir / "0"
        zero_dir.mkdir(exist_ok=True)

        import math as _math
        V = job.wind_speed
        alpha_rad = getattr(self, "_alpha_override", 0.0)
        Vx = V * _math.cos(alpha_rad)
        Vz = V * _math.sin(alpha_rad)

        I = 0.01
        L_turb = 0.07 * job.aircraft.fuselage.length
        k0     = 1.5 * (V * I) ** 2
        omega0 = (k0 ** 0.5) / (0.09 ** 0.25 * L_turb)
        nut0   = k0 / omega0

        with open(zero_dir / "U", "w") as f:
            f.write(f"""FoamFile
{{
    version     2.0; format ascii;
    class       volVectorField; object U;
}}
dimensions      [0 1 -1 0 0 0 0];
internalField   uniform ({Vx:.6f} 0 {Vz:.6f});
boundaryField
{{
    inlet    {{ type fixedValue; value uniform ({Vx:.6f} 0 {Vz:.6f}); }}
    outlet   {{ type inletOutlet; inletValue uniform (0 0 0); value uniform ({Vx:.6f} 0 {Vz:.6f}); }}
    aircraft {{ type noSlip; }}
    sides    {{ type symmetry; }}
}}
""")

        with open(zero_dir / "p", "w") as f:
            f.write("""FoamFile
{
    version     2.0; format ascii;
    class       volScalarField; object p;
}
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0;
boundaryField
{
    inlet    { type zeroGradient; }
    outlet   { type fixedValue; value uniform 0; }
    aircraft { type zeroGradient; }
    sides    { type symmetry; }
}
""")

        with open(zero_dir / "k", "w") as f:
            f.write(f"""FoamFile
{{
    version     2.0; format ascii;
    class       volScalarField; object k;
}}
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform {k0:.6f};
boundaryField
{{
    inlet    {{ type fixedValue; value uniform {k0:.6f}; }}
    outlet   {{ type inletOutlet; inletValue uniform {k0:.6f}; value uniform {k0:.6f}; }}
    aircraft {{ type kqRWallFunction; value uniform {k0:.6f}; }}
    sides    {{ type symmetry; }}
}}
""")

        with open(zero_dir / "omega", "w") as f:
            f.write(f"""FoamFile
{{
    version     2.0; format ascii;
    class       volScalarField; object omega;
}}
dimensions      [0 0 -1 0 0 0 0];
internalField   uniform {omega0:.4f};
boundaryField
{{
    inlet    {{ type fixedValue; value uniform {omega0:.4f}; }}
    outlet   {{ type inletOutlet; inletValue uniform {omega0:.4f}; value uniform {omega0:.4f}; }}
    aircraft {{ type omegaWallFunction; value uniform {omega0:.4f}; }}
    sides    {{ type symmetry; }}
}}
""")

        with open(zero_dir / "nut", "w") as f:
            f.write(f"""FoamFile
{{
    version     2.0; format ascii;
    class       volScalarField; object nut;
}}
dimensions      [0 2 -1 0 0 0 0];
internalField   uniform {nut0:.6e};
boundaryField
{{
    inlet    {{ type calculated; value uniform {nut0:.6e}; }}
    outlet   {{ type calculated; value uniform {nut0:.6e}; }}
    aircraft {{ type nutkWallFunction; value uniform 0; }}
    sides    {{ type symmetry; }}
}}
""")

    def _create_system_files(self, case_dir: Path, job: SimulationJob) -> None:
        """system/ Solver ayarları: controlDict, fvSchemes, fvSolution, blockMeshDict, snappyHexMeshDict"""
        sys_dir = case_dir / "system"
        sys_dir.mkdir(exist_ok=True)

        cg_x = job.aircraft.mass_properties()['cg_x']
        with open(sys_dir / "controlDict", "w") as f:
            f.write(f"""FoamFile
{{
    version     2.0; format ascii;
    class       dictionary; location "system"; object controlDict;
}}
application     {job.solver};
startFrom       startTime;
startTime       0;
endTime         {int(job.end_time)};
deltaT          1;
writeInterval   {int(job.end_time / 10)};
purgeWrite      3;
writeFormat     binary;
runTimeModifiable true;
functions
{{
    forces
    {{
        type            forces;
        libs            ("libforces.so");
        writeControl    timeStep;
        writeInterval   {int(job.end_time / 10)};
        patches         ("aircraft");
        rho             rhoInf;
        rhoInf          1.225;
        pRef            0;
        CofR            ({cg_x:.6f} 0 0);
    }}
}}
""")

        # blockMeshDict — aircraft geometry'den üretilmiş domain
        mesh_gen = MeshGenerator(job.aircraft, mesh_size=job.mesh_size)
        with open(sys_dir / "blockMeshDict", "w") as f:
            f.write(mesh_gen.generate_blockmeshdict())

        # snappyHexMeshDict — gerçek STL geometrisi
        with open(sys_dir / "snappyHexMeshDict", "w") as f:
            f.write(mesh_gen.generate_snappyhexmeshdict("aircraft.stl"))

        # surfaceFeaturesDict — OF11 formatı
        with open(sys_dir / "surfaceFeaturesDict", "w") as f:
            f.write('FoamFile\n{ version 2.0; format ascii; class dictionary; object surfaceFeaturesDict; }\n')
            f.write('surfaces ( "aircraft.stl" );\nincludedAngle 150;\nwriteObj yes;\n')

        # fvSchemes — OF11 kOmegaSST uyumlu
        schemes = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}

ddtSchemes      { default steadyState; }

gradSchemes
{
    default         Gauss linear;
    grad(U)         cellLimited Gauss linear 1;
    grad(k)         cellLimited Gauss linear 1;
    grad(omega)     cellLimited Gauss linear 1;
}

divSchemes
{
    default             none;
    div(phi,U)          bounded Gauss linearUpwindV grad(U);
    div(phi,k)          bounded Gauss linearUpwind grad(k);
    div(phi,omega)      bounded Gauss linearUpwind grad(omega);
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}

laplacianSchemes    { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes       { default corrected; }

wallDist            { method meshWave; }
"""
        with open(sys_dir / "fvSchemes", "w") as f:
            f.write(schemes)

        # fvSolution — p, U, k, omega solver tanımları
        solution = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSolution;
}

solvers
{
    p
    {
        solver          GAMG;
        tolerance       1e-7;
        relTol          0.01;
        smoother        GaussSeidel;
        nPreSweeps      0;
        nPostSweeps     2;
        cacheAgglomeration on;
        agglomerator    faceAreaPair;
        nCellsInCoarsestLevel 10;
        mergeLevels     1;
    }
    "(U|k|omega)"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 1;
    consistent               yes;
    residualControl
    {
        p       1e-4;
        U       1e-4;
        "(k|omega)" 1e-4;
    }
}

relaxationFactors
{
    equations
    {
        U       0.7;
        k       0.5;
        omega   0.5;
    }
    fields
    {
        p       0.3;
    }
}
"""
        with open(sys_dir / "fvSolution", "w") as f:
            f.write(solution)

    def _create_constant_files(self, case_dir: Path, job: SimulationJob) -> None:
        """constant/ — transportProperties, turbulenceProperties, triSurface/aircraft.stl"""
        const_dir = case_dir / "constant"
        const_dir.mkdir(exist_ok=True)

        with open(const_dir / "transportProperties", "w") as f:
            f.write("""FoamFile
{
    version     2.0; format ascii;
    class       dictionary; location "constant"; object transportProperties;
}
transportModel  Newtonian;
nu              1.5e-05;
""")

        with open(const_dir / "turbulenceProperties", "w") as f:
            f.write("""FoamFile
{
    version     2.0; format ascii;
    class       dictionary; location "constant"; object turbulenceProperties;
}
simulationType  RAS;
RAS
{
    RASModel    kOmegaSST;
    turbulence  on;
    printCoeffs on;
}
""")

        # OF11-native momentumTransport — postProcess yPlus icin gerekli
        with open(const_dir / "momentumTransport", "w") as f:
            f.write("""FoamFile
{
    version     2.0; format ascii;
    class       dictionary; location "constant"; object momentumTransport;
}
simulationType  RAS;
RAS
{
    model       kOmegaSST;
    turbulence  on;
    printCoeffs on;
}
""")

        # Gerçek aircraft STL'ini triSurface/ altına oluştur
        tri_dir = const_dir / "triSurface"
        tri_dir.mkdir(exist_ok=True)
        stl_path = tri_dir / "aircraft.stl"
        mesh_gen = MeshGenerator(job.aircraft, mesh_size=job.mesh_size)

        # Önce OpenVSP STL dene (daha kaliteli), başarısız olursa trimesh
        from mesh_generator import generate_stl_openvsp
        vsp_result = generate_stl_openvsp(job.aircraft, str(stl_path))
        if vsp_result is None:
            mesh_gen.generate_stl(str(stl_path))

    def run_simulation(self, job: SimulationJob) -> dict:
        """Simülasyon çalıştır"""
        case_dir = self.base_path / job.case_directory()

        try:
            # Case hazırlama
            if not self.setup_case(job):
                return {"status": "FAILED", "error": "Case setup failed"}

            # Mesh oluştur
            print(f"[...] [{job.case_name}] Mesh generation...")
            mesh_gen = MeshGenerator(job.aircraft, mesh_size=job.mesh_size,
                                     wind_speed=job.wind_speed, target_yplus=1.0)
            gmsh_script = mesh_gen.generate_gmsh_script()

            wsl_dir = _to_wsl_path(case_dir)

            # blockMesh — arka plan hex kafes
            try:
                result = subprocess.run(
                    _wsl_openfoam(wsl_dir, "blockMesh > log.blockMesh 2>&1"),
                    shell=True, capture_output=True, timeout=600, text=True
                )
                if result.returncode != 0:
                    log = (case_dir / "log.blockMesh").read_text(errors="replace")[-500:] if (case_dir / "log.blockMesh").exists() else ""
                    return {"status": "FAILED", "error": f"blockMesh failed:\n{log}"}
            except subprocess.TimeoutExpired:
                return {"status": "FAILED", "error": "blockMesh timeout"}

            # surfaceFeatures — STL'den kenar hatları çıkar (OF11 formatı)
            surf_cfg = case_dir / "system" / "surfaceFeaturesDict"
            if not surf_cfg.exists():
                surf_cfg.write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object surfaceFeaturesDict; }
surfaces ( "aircraft.stl" );
includedAngle 150;
writeObj yes;
""")
            r = subprocess.run(
                _wsl_openfoam(wsl_dir, "surfaceFeatures > log.surfFeat 2>&1"),
                shell=True, capture_output=True, timeout=120, text=True
            )
            # .eMesh oluştu mu kontrol et — oluşmadıysa snappy features bölümünü devre dışı bırak
            emesh = case_dir / "constant" / "triSurface" / "aircraft.eMesh"
            _emesh_ok = emesh.exists()

            # snappyHexMesh — gerçek geometriye refinement + boundary layer
            try:
                result = subprocess.run(
                    _wsl_openfoam(wsl_dir, "snappyHexMesh -overwrite > log.snappy 2>&1"),
                    shell=True, capture_output=True, timeout=1800, text=True
                )
                if result.returncode != 0:
                    log = (case_dir / "log.snappy").read_text(errors="replace")[-500:] if (case_dir / "log.snappy").exists() else ""
                    return {"status": "FAILED", "error": f"snappyHexMesh failed:\n{log}"}
            except subprocess.TimeoutExpired:
                return {"status": "FAILED", "error": "snappyHexMesh timeout"}

            print(f"[{job.case_name}] Mesh ready")

            # Solver çalıştır
            print(f"[{job.case_name}] Running {job.solver}...")

            try:
                of11_solver = "foamRun -solver incompressibleFluid"

                if job.num_processors > 1:
                    # WSL2 MPI: --mca plm_rsh_disable_qrsh 1 -H localhost:N gerekli
                    decompDict = case_dir / "system" / "decomposeParDict"
                    decompDict.write_text(
                        f'FoamFile {{ version 2.0; format ascii; class dictionary; object decomposeParDict; }}\n'
                        f'numberOfSubdomains {job.num_processors};\nmethod scotch;\n'
                    )
                    r_decomp = subprocess.run(
                        _wsl_openfoam(wsl_dir, "decomposePar > log.decompose 2>&1"),
                        shell=True, capture_output=True, timeout=300, text=True
                    )
                    if r_decomp.returncode != 0:
                        return {"status": "FAILED", "error": "decomposePar failed"}

                    mpi_flags = (f"mpirun -np {job.num_processors} "
                                 f"--mca plm_rsh_disable_qrsh 1 "
                                 f"--mca orte_keep_fqdn_hostnames 0 "
                                 f"-H localhost:{job.num_processors}")
                    solver_cmd = f"{mpi_flags} {of11_solver} -parallel > log.solver 2>&1"
                else:
                    solver_cmd = f"{of11_solver} > log.solver 2>&1"

                result = subprocess.run(
                    _wsl_openfoam(wsl_dir, solver_cmd),
                    shell=True, capture_output=True, timeout=7200, text=True
                )

                if result.returncode != 0:
                    error_msg = result.stdout or "Solver failed"
                    return {"status": "FAILED", "error": f"{job.solver} failed: {error_msg}"}

                if job.num_processors > 1:
                    subprocess.run(
                        _wsl_openfoam(wsl_dir, "reconstructPar -latestTime > log.reconstruct 2>&1"),
                        shell=True, capture_output=True, timeout=300, text=True
                    )

                print(f"[OK] [{job.case_name}] Completed")
                return self._extract_results(case_dir, job)

            except subprocess.TimeoutExpired:
                return {"status": "TIMEOUT", "error": "Simulation exceeded 1 hour"}

        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    def _extract_results(self, case_dir: Path, job: SimulationJob) -> dict:
        """Simülasyon sonuçlarını çıkar"""
        import math as _math
        try:
            forces_file = case_dir / "postProcessing" / "forces" / "0" / "forces.dat"

            results = {
                "status": "SUCCESS",
                "case_name": job.case_name,
                "aircraft": job.aircraft.name,
                "timestamp": datetime.now().isoformat(),
                "mesh_size": job.mesh_size,
                "wind_speed": job.wind_speed,
            }

            if forces_file.exists():
                # OF11 format: Time ((Fpx Fpy Fpz) (Fvx Fvy Fvz)) ((Mpx Mpy Mpz) (Mvx Mvy Mvz))
                with open(forces_file) as f:
                    data_lines = [l for l in f if not l.strip().startswith("#") and l.strip()]
                if data_lines:
                    import re as _re
                    nums = _re.findall(r'[-+]?\d+\.?\d*[eE]?[-+]?\d*', data_lines[-1])
                    try:
                        # nums[0]=time, [1..3]=Fp, [4..6]=Fv, [7..9]=Mp, [10..12]=Mv
                        Fpx, Fpz = float(nums[1]), float(nums[3])
                        Fvx, Fvz = float(nums[4]), float(nums[6])
                        Mpy       = float(nums[8])
                        Mvy       = float(nums[11])
                        Fx = Fpx + Fvx
                        Fz = Fpz + Fvz
                        alpha_rad = getattr(self, "_alpha_override", 0.0)
                        drag =  Fx * _math.cos(alpha_rad) + Fz * _math.sin(alpha_rad)
                        lift = -Fx * _math.sin(alpha_rad) + Fz * _math.cos(alpha_rad)
                        results["drag_force_N"]       = round(drag, 4)
                        results["lift_force_N"]        = round(lift, 4)
                        results["alpha_deg"]           = round(_math.degrees(alpha_rad), 1)
                        results["pitching_moment_Nm"]  = round(Mpy + Mvy, 6)
                        q = 0.5 * 1.225 * job.wind_speed ** 2
                        S = job.aircraft.wing.area
                        c = job.aircraft.wing.root_chord()
                        results["Cd"] = round(drag / (q * S), 4)
                        results["Cl"] = round(lift / (q * S), 4)
                        results["Cm"] = round((Mpy + Mvy) / (q * S * c), 6)
                        results["L_D_ratio"] = round(lift / drag, 2) if drag > 0 else None
                    except (IndexError, ValueError):
                        pass

            results["mass_properties"] = job.aircraft.mass_properties()
            return results

        except Exception as e:
            return {"status": "PARTIAL", "error": str(e)}

    def run_parametric_study(self, base_aircraft: Aircraft, variations: dict,
                            num_workers: int = 4) -> list[dict]:
        """Parametrik çalışma (paralel)"""
        # Varyasyonları oluştur
        study = ParametricStudy(base_aircraft)
        for param, values in variations.items():
            study.add_variation(param, values)

        cases = study.generate_cases()

        # Simülasyon jobları
        jobs = [
            SimulationJob(
                case_name=f"{base_aircraft.name.replace(' ', '_')}_{i:03d}",
                aircraft=case,
                solver="simpleFoam",
                mesh_size=0.01,
                wind_speed=15.0,
                analysis_type="aerodinamik",
                num_processors=4
            )
            for i, case in enumerate(cases)
        ]

        # Paralel çalıştırma
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(self.run_simulation, job) for job in jobs]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        return results

    def generate_report(self, results: list[dict]) -> str:
        """Simülasyon raporu oluştur"""
        report = f"""
# Parametrik Çalışma Raporu
Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Özet
- Toplam Simülasyon: {len(results)}
- Başarılı: {sum(1 for r in results if r.get('status') == 'SUCCESS')}
- Başarısız: {sum(1 for r in results if r.get('status') == 'FAILED')}

## Detaylı Sonuçlar

"""
        for i, result in enumerate(results, 1):
            report += f"\n### Case {i}: {result.get('case_name', 'Unknown')}\n"
            report += f"- Status: {result.get('status', 'Unknown')}\n"

            if result.get('status') == 'SUCCESS':
                report += f"- Aircraft: {result.get('aircraft')}\n"
                report += f"- Drag Force: {result.get('drag_force', 'N/A'):.2f} N\n"
                report += f"- Lift Force: {result.get('lift_force', 'N/A'):.2f} N\n"
                report += f"- Pitching Moment: {result.get('pitching_moment', 'N/A'):.2f} N⋅m\n"

        return report

    def run_mesh_independence_study(self, aircraft: Aircraft, wind_speed: float = 15.0,
                                    base_path: str = "./mesh_independence") -> dict:
        """3 kademeli mesh bağımsızlık analizi.
        Coarse / Medium / Fine mesh için Cd ve Cl hesaplar.
        Sonuçlar arasındaki fark < 5% ise yakınsadı kabul edilir.
        """
        levels = [
            {"name": "coarse", "mesh_size": 0.050, "end_time": 300},
            {"name": "medium", "mesh_size": 0.025, "end_time": 500},
            {"name": "fine",   "mesh_size": 0.012, "end_time": 500},
        ]

        results = {}
        for lvl in levels:
            case_name = f"{aircraft.name.replace(' ', '_')}_{lvl['name']}"
            job = SimulationJob(
                case_name=case_name,
                aircraft=aircraft,
                solver="foamRun",
                mesh_size=lvl["mesh_size"],
                wind_speed=wind_speed,
                analysis_type="aerodinamik",
                num_processors=1,
                end_time=lvl["end_time"],
            )
            runner = SimulationRunner(base_path=base_path)
            print(f"\n[Mesh Independence] {lvl['name'].upper()} — mesh_size={lvl['mesh_size']}")
            r = runner.run_simulation(job)
            results[lvl["name"]] = r
            print(f"  Cd={r.get('Cd','?')}  Cl={r.get('Cl','?')}  status={r.get('status')}")

        # Yakınsama kontrolü
        cds = [results[l["name"]].get("Cd") for l in levels
               if results[l["name"]].get("Cd") is not None]
        cls = [results[l["name"]].get("Cl") for l in levels
               if results[l["name"]].get("Cl") is not None]

        summary = {"levels": results}
        if len(cds) >= 2:
            cd_change = abs(cds[-1] - cds[-2]) / (abs(cds[-2]) + 1e-10) * 100
            cl_change = abs(cls[-1] - cls[-2]) / (abs(cls[-2]) + 1e-10) * 100 if len(cls) >= 2 else None
            summary["cd_change_pct"]  = round(cd_change, 2)
            summary["cl_change_pct"]  = round(cl_change, 2) if cl_change is not None else None
            summary["mesh_converged"] = cd_change < 5.0
            print(f"\n[Mesh Independence] Cd degisimi: {cd_change:.1f}%  "
                  f"({'YAKINSAMIS' if cd_change < 5 else 'YAKINSAMAMIS'})")

        return summary


    def run_aoa_sweep(self, aircraft: Aircraft, wind_speed: float = 15.0,
                      alphas: list = None, mesh_size: float = 0.012,
                      end_time: float = 500, base_path: str = "./aoa_sweep") -> dict:
        """Hücum açısı (AoA) taraması: α = 0, 2, 4, 6, 8 deg.

        Her açı için Cl, Cd, L/D hesaplar. Velocity vektörünü döndürür,
        geometri sabit kalır.

        Döndürür: {alpha: {"Cd": ..., "Cl": ..., "LD": ...}} + polar curve özeti
        """
        import math
        if alphas is None:
            alphas = [0, 2, 4, 6, 8]

        all_results = {}

        for alpha in alphas:
            print(f"\n[AoA Sweep] alpha={alpha} deg")
            case_name = f"{aircraft.name.replace(' ', '_')}_alpha{alpha:02d}"
            job = SimulationJob(
                case_name=case_name,
                aircraft=aircraft,
                solver="foamRun",
                mesh_size=mesh_size,
                wind_speed=wind_speed,
                analysis_type="aerodinamik",
                num_processors=1,
                end_time=end_time,
            )

            runner = SimulationRunner(base_path=base_path)
            # AoA: hız vektörünü döndür
            runner._alpha_override = math.radians(alpha)
            r = runner.run_simulation(job)

            if r.get("Cd") and r.get("Cl"):
                ld = r["Cl"] / r["Cd"] if r["Cd"] != 0 else None
                all_results[alpha] = {
                    "Cd": r["Cd"], "Cl": r["Cl"],
                    "LD": round(ld, 2) if ld else None,
                    "status": r.get("status"),
                }
                print(f"  Cl={r['Cl']:.4f}  Cd={r['Cd']:.5f}  L/D={ld:.1f}")
            else:
                all_results[alpha] = {"status": "FAILED"}
                print("  FAILED")

        # Polar özeti
        successful = {a: v for a, v in all_results.items() if v.get("Cl") is not None}
        if successful:
            best_ld_alpha = max(successful, key=lambda a: successful[a].get("LD") or 0)
            all_results["_summary"] = {
                "best_LD_alpha": best_ld_alpha,
                "best_LD":       successful[best_ld_alpha].get("LD"),
                "Cl_slope":      None,  # dCl/dalpha — lineer bölgede ~0.1/deg
            }
            alphas_deg = sorted(successful.keys())
            if len(alphas_deg) >= 2:
                cls = [successful[a]["Cl"] for a in alphas_deg]
                slope = (cls[-1] - cls[0]) / (alphas_deg[-1] - alphas_deg[0])
                all_results["_summary"]["Cl_slope"] = round(slope, 4)
                print(f"\n  Cl slope = {slope:.4f}/deg  (teorik 2D: 0.1097/deg)")
                print(f"  Best L/D = {all_results['_summary']['best_LD']} @ alpha={best_ld_alpha}deg")

        return all_results


# ─────────────────────────────────────────────────────────────────────────────
# EXAMPLE USAGE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    runner = SimulationRunner(base_path="./simulations")

    # Parametrik çalışma: Model roket
    roket = AircraftLibrary.model_rocket()

    variations = {
        "span": [0.12, 0.15, 0.18],      # 3 değer
        "sweep": [20, 30, 40]             # 3 değer
    }  # Toplam: 3 × 3 = 9 case

    print(f"🚀 Parametrik çalışma başlatılıyor: {len(variations)} kombinasyon")

    results = runner.run_parametric_study(roket, variations, num_workers=2)

    # Rapor
    report = runner.generate_report(results)
    print(report)

    with open("parametric_study_report.md", "w") as f:
        f.write(report)

    print("[OK] Rapor kaydedildi: parametric_study_report.md")
