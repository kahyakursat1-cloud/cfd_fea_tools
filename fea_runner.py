"""
CalculiX FEA Simulation Runner
Yapısal analiz (structural, thermal, frequency analysis)
"""

import concurrent.futures
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def _is_float(s: str) -> bool:
    try: float(s); return True
    except ValueError: return False


def _to_wsl_path(win_path: Path) -> str:
    """Windows yolunu WSL mount yoluna çevir: D:\\foo\\bar → /mnt/d/foo/bar"""
    p = str(win_path.resolve())
    drive = p[0].lower()
    rest = p[2:].replace("\\", "/")
    return f"/mnt/{drive}{rest}"


# ─────────────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MaterialProperties:
    """Malzeme özellikleri"""
    name: str
    youngs_modulus: float      # E (MPa)
    poisson_ratio: float       # ν (0.0-0.5)
    density: float             # ρ (kg/m³)
    yield_strength: float      # σ_y (MPa)
    thermal_conductivity: float = 50.0  # W/(m⋅K)
    specific_heat: float = 900.0        # J/(kg⋅K)


@dataclass
class BoundaryCondition:
    """Sınır koşulu"""
    name: str
    node_set: str
    dof: tuple[int, int]       # DOF range (e.g., (1, 6) for all)
    value: float


@dataclass
class Load:
    """Yük koşulu"""
    name: str
    node_set: str
    load_type: str             # "FORCE", "PRESSURE", "MOMENT", "TEMPERATURE"
    magnitude: float


@dataclass
class FEAJob:
    """FEA simülasyon işi"""
    case_name: str
    mesh_file: str             # STL or MSH dosyası
    material: MaterialProperties
    boundary_conditions: list[BoundaryCondition]
    loads: list[Load]
    analysis_type: str         # "STATIC", "FREQUENCY", "BUCKLING", "THERMAL"
    num_modes: int = 10        # Frequency analizi için
    output_format: str = "FRD"  # FRD (CalculiX native), VTK


# ─────────────────────────────────────────────────────────────────────────────
# MATERIAL LIBRARY
# ─────────────────────────────────────────────────────────────────────────────

MATERIAL_LIBRARY = {
    "aluminum_6061": MaterialProperties(
        name="Aluminum 6061",
        youngs_modulus=69000,
        poisson_ratio=0.33,
        density=2700,
        yield_strength=290,
        thermal_conductivity=167,
        specific_heat=896
    ),
    "steel_s355": MaterialProperties(
        name="Steel S355",
        youngs_modulus=210000,
        poisson_ratio=0.30,
        density=7850,
        yield_strength=355,
        thermal_conductivity=50,
        specific_heat=486
    ),
    "carbon_fiber": MaterialProperties(
        name="Carbon Fiber (Unidirectional)",
        youngs_modulus=140000,
        poisson_ratio=0.30,
        density=1600,
        yield_strength=800,
        thermal_conductivity=10,
        specific_heat=1200
    ),
    "titanium": MaterialProperties(
        name="Titanium Grade 2",
        youngs_modulus=103000,
        poisson_ratio=0.32,
        density=4510,
        yield_strength=345,
        thermal_conductivity=21.8,
        specific_heat=523
    ),
    "balsa_wood": MaterialProperties(
        name="Balsa Wood",
        youngs_modulus=12000,
        poisson_ratio=0.4,
        density=150,
        yield_strength=50,
        thermal_conductivity=0.05,
        specific_heat=1500
    ),
}


def make_distributed_load_from_cfd(cfd_results: dict, stl_path: str) -> dict:
    """CFD Cl/Cd sonuçlarından FEA için düzgün yayılı basınç yükü üretir.

    Nokta kuvveti yerine gerçeğe yakın yük dağılımı:
    - Lift → +z yönünde düzgün basınç (kanat alt yüzeyi)
    - Drag → +x yönünde düzgün basınç (fuselage ön yüzeyi)

    Döndürür: FEAJob.loads listesine eklenebilir Load nesneleri + özet dict.
    """
    import numpy as np
    import trimesh

    lift_N = cfd_results.get("lift_force_N") or cfd_results.get("Cl", 0) * (
        0.5 * 1.225 * cfd_results.get("wind_speed", 15.0) ** 2 * cfd_results.get("wing_area", 0.45)
    )
    drag_N = cfd_results.get("drag_force_N") or cfd_results.get("Cd", 0) * (
        0.5 * 1.225 * cfd_results.get("wind_speed", 15.0) ** 2 * cfd_results.get("wing_area", 0.45)
    )

    mesh = trimesh.load(stl_path, force='mesh')
    verts = mesh.vertices
    faces = mesh.faces
    face_normals = mesh.face_normals
    face_areas   = mesh.area_faces

    # Kanat yüzeyleri: yaklaşık olarak geniş y-aralığı ve ince z-aralığı
    # Lift yükleri alt yüzeyden gelir (normal -z bileşeni pozitif)
    wing_faces = np.where(face_normals[:, 2] < -0.3)[0]  # aşağı bakan yüzeyler
    total_wing_area = face_areas[wing_faces].sum() if len(wing_faces) else mesh.area / 2

    # p_lift: düzgün basınç (Pascal), F = p × A
    p_lift = lift_N / total_wing_area if total_wing_area > 0 else 0

    # Drag yükleri ön yüzeyden: normal -x bileşeni pozitif
    front_faces = np.where(face_normals[:, 0] < -0.3)[0]
    total_front_area = face_areas[front_faces].sum() if len(front_faces) else mesh.area / 6
    p_drag = drag_N / total_front_area if total_front_area > 0 else 0

    return {
        "lift_N":          round(lift_N, 4),
        "drag_N":          round(drag_N, 4),
        "p_lift_Pa":       round(p_lift, 3),
        "p_drag_Pa":       round(p_drag, 3),
        "wing_area_m2":    round(total_wing_area, 5),
        "front_area_m2":   round(total_front_area, 5),
        "load_type":       "distributed_pressure_from_cfd",
        # CalculiX *DLOAD için: EALL, P, p_value (normal yönde basınç)
        "ccx_lift_dload":  f"*DLOAD\nEALL, P, {p_lift:.4f}\n",
        "ccx_drag_dload":  f"*DLOAD\nEALL, P, {p_drag:.4f}\n",
    }


def extract_cfd_pressure_loads(cfd_case_dir: str, stl_path: str,
                                rho: float = 1.225) -> dict:
    """CFD sonucundan basınç alanını okur ve FEA yüzey düğümlerine interpolasyon yapar.

    Workflow:
      1. OpenFOAM postProcessing/wallPressure'dan p alanını oku
      2. STL yüzey düğümleri için en yakın CFD yüzey noktasına interpolasyon
      3. Her düğüm için kgf cinsinden yük vektörü döndür

    Döndürür: {node_id: (Fx, Fy, Fz)} sözlüğü — doğrudan *CLOAD olarak kullanılabilir
    """
    try:
        from pathlib import Path

        import numpy as np
        import trimesh

        case = Path(cfd_case_dir)

        # OpenFOAM son zaman adımını bul
        time_dirs = sorted(
            [d for d in case.iterdir() if d.is_dir() and d.name.replace('.','').isdigit()],
            key=lambda d: float(d.name)
        )
        if not time_dirs:
            return {"error": "No time directories found"}
        last_time = time_dirs[-1]

        # p dosyasını oku (binary veya ascii)
        p_file = last_time / "p"
        if not p_file.exists():
            return {"error": f"p field not found at {p_file}"}

        content = p_file.read_text(errors="replace")

        # InternalField değerlerini çıkar
        import re
        # Boundary field'dan airfoil patch basıncını al
        # Önce mesh yüzey koordinatlarını bul
        points_file = case / "constant" / "polyMesh" / "points"
        faces_file  = case / "constant" / "polyMesh" / "faces"
        boundary_file = case / "constant" / "polyMesh" / "boundary"

        if not points_file.exists():
            return {"error": "polyMesh/points not found — run CFD first"}

        # Points dosyasını oku (OpenFOAM binary format gerektiriyor, ascii dene)
        pts_content = points_file.read_text(errors="replace")
        coords = re.findall(r'\((-?[\d.eE+\-]+)\s+(-?[\d.eE+\-]+)\s+(-?[\d.eE+\-]+)\)', pts_content)
        if not coords:
            return {"error": "Could not parse points file"}
        mesh_points = np.array([[float(x), float(y), float(z)] for x,y,z in coords])

        # p field değerlerini oku
        p_vals_match = re.search(r'internalField\s+nonuniform\s+List<scalar>\s+\d+\s*\(([^)]+)\)', content, re.DOTALL)
        if not p_vals_match:
            # Uniform field
            p_uni = re.search(r'internalField\s+uniform\s+([\d.eE+\-]+)', content)
            if p_uni:
                p_values = np.full(len(mesh_points), float(p_uni.group(1)))
            else:
                return {"error": "Could not parse pressure field"}
        else:
            p_values = np.array([float(v) for v in p_vals_match.group(1).split()])

        # STL yüzey düğümlerini yükle
        mesh_stl = trimesh.load(stl_path, force='mesh')
        surface_nodes = mesh_stl.vertices  # (N, 3)

        # Her STL düğümü için en yakın CFD mesh noktasına interpolasyon
        from scipy.spatial import KDTree
        tree = KDTree(mesh_points)
        distances, indices = tree.query(surface_nodes, k=4)  # 4 en yakın

        # IDW (Inverse Distance Weighting) interpolasyon
        weights = 1.0 / (distances + 1e-12)
        weights /= weights.sum(axis=1, keepdims=True)
        p_interp = (weights * p_values[indices]).sum(axis=1)  # (N,) Pascal

        # Basınç yüklerini düğüm kuvvetlerine dönüştür
        # Her düğüme bağlı yüzey alanını hesapla (vertex area)
        areas = np.zeros(len(surface_nodes))
        face_areas = mesh_stl.area_faces  # (M,) array
        for fi, face in enumerate(mesh_stl.faces):
            face_area = face_areas[fi] / 3.0 if face_areas is not None else 0.0
            for nid in face:
                areas[nid] += face_area

        # Yüzey normalleri
        normals = np.zeros_like(surface_nodes)
        for i, face in enumerate(mesh_stl.faces):
            fn = mesh_stl.face_normals[i]
            for nid in face:
                normals[nid] += fn
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        normals /= np.maximum(norms, 1e-10)

        # F = -p * n * A (basınç kuvveti = -p * normal * alan)
        forces = {}
        for i in range(len(surface_nodes)):
            F = -p_interp[i] * normals[i] * areas[i]  # Newton
            forces[i + 1] = (float(F[0]), float(F[1]), float(F[2]))

        return {
            "status": "SUCCESS",
            "n_nodes": len(surface_nodes),
            "p_min_Pa": float(p_interp.min()),
            "p_max_Pa": float(p_interp.max()),
            "total_Fx_N": float(sum(f[0] for f in forces.values())),
            "total_Fz_N": float(sum(f[2] for f in forces.values())),
            "node_forces": forces,
        }

    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# FEA RUNNER
# ─────────────────────────────────────────────────────────────────────────────

class FEASimulationRunner:
    """CalculiX FEA simülasyonu yönetimi"""

    def __init__(self, base_path: str = "./fea_cases"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)

    def setup_case(self, job: FEAJob) -> bool:
        """FEA case klasörü hazırla"""
        case_dir = self.base_path / job.case_name
        case_dir.mkdir(exist_ok=True)
        mesh_src = Path(job.mesh_file)
        if mesh_src.exists():
            (case_dir / mesh_src.name).write_bytes(mesh_src.read_bytes())
        return True

    def _stl_to_fem_mesh(self, stl_path: Path, out_inp: Path,
                          shell_thickness: float = 0.002) -> bool:
        """STL yüzey → CalculiX S3 shell element INP.
        İnce cidarlı uçak yapıları için shell formülasyonu solid tet'ten çok daha doğrudur.
        Her STL üçgeni → bir S3 element; kalınlık *SHELL SECTION ile tanımlanır.
        shell_thickness: kabuk et kalınlığı (m), default 2 mm (tipik UAV alüminyum)
        """
        try:
            import numpy as np
            import trimesh

            mesh_tr = trimesh.load(str(stl_path), force='mesh')
            if len(mesh_tr.faces) < 200:
                mesh_tr = mesh_tr.subdivide()

            verts = mesh_tr.vertices
            faces = mesh_tr.faces

            x = verts[:, 0]
            x_min, x_max = x.min(), x.max()
            tol = (x_max - x_min) * 0.05
            fixed_ids = (np.where(x <= x_min + tol)[0] + 1).tolist()
            load_ids  = (np.where(x >= x_max - tol)[0] + 1).tolist()

            lines = []
            lines.append("*NODE, NSET=NALL\n")
            for i, (vx, vy, vz) in enumerate(verts):
                lines.append(f"{i+1}, {vx:.8e}, {vy:.8e}, {vz:.8e}\n")

            lines.append("*ELEMENT, TYPE=S3, ELSET=EALL\n")
            for i, (n0, n1, n2) in enumerate(faces):
                lines.append(f"{i+1}, {n0+1}, {n1+1}, {n2+1}\n")

            if fixed_ids:
                lines.append("*NSET, NSET=NSET_FIXED\n")
                for j in range(0, len(fixed_ids), 8):
                    lines.append(", ".join(str(n) for n in fixed_ids[j:j+8]) + "\n")
            if load_ids:
                lines.append("*NSET, NSET=NSET_LOAD\n")
                for j in range(0, len(load_ids), 8):
                    lines.append(", ".join(str(n) for n in load_ids[j:j+8]) + "\n")

            lines.append(f"** SHELL_THICKNESS={shell_thickness:.6f}\n")
            out_inp.write_text("".join(lines))
            return True

        except Exception as e:
            print(f"Shell mesh generation failed: {e}")
            return False

    def generate_inp_file(self, job: FEAJob, shell_thickness: float = 0.002) -> str:
        """CalculiX input dosyası oluştur.
        STL → S3 shell mesh; birim sistemi N/m/Pa (tutarlı).
        shell_thickness: yapı et kalınlığı (m)
        """
        case_dir = self.base_path / job.case_name
        mesh_stl = case_dir / Path(job.mesh_file).name
        mesh_inp = case_dir / "mesh.inp"
        inp_path = case_dir / f"{job.case_name}.inp"

        mesh_ok = False
        if mesh_stl.exists():
            mesh_ok = self._stl_to_fem_mesh(mesh_stl, mesh_inp, shell_thickness)

        mat_name = job.material.name.replace(" ", "_")
        mesh_include = "*INCLUDE, INPUT=mesh.inp\n" if mesh_ok else \
                       f"** WARNING: mesh not found at {job.mesh_file}\n"

        # Boundary conditions
        bc_section = ""
        for bc in job.boundary_conditions:
            nset = "NSET_FIXED" if "fixed" in bc.node_set.lower() else bc.node_set
            bc_section += f"*BOUNDARY\n{nset}, {bc.dof[0]}, {bc.dof[1]}, {bc.value}\n"
        if not bc_section:
            bc_section = "*BOUNDARY\nNSET_FIXED, 1, 6, 0\n"

        # Loads
        load_section = ""
        for load in job.loads:
            nset = "NSET_LOAD" if ("load" in load.node_set.lower()
                                    or "top" in load.node_set.lower()) else load.node_set
            if load.load_type == "PRESSURE":
                load_section += f"*DLOAD\nEALL, P, {load.magnitude}\n"
            elif load.load_type == "FORCE":
                load_section += f"*CLOAD\n{nset}, 3, {load.magnitude}\n"

        # Birim: MPa → Pa (geometri metre cinsinden)
        E_pa = job.material.youngs_modulus * 1e6

        # Analiz adımı — S3 için NODE FILE + EL FILE
        if job.analysis_type == "STATIC":
            step = f"*STEP\n*STATIC\n1.0, 1.0\n{load_section}*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n"
        elif job.analysis_type == "FREQUENCY":
            step = f"*STEP\n*FREQUENCY\n{job.num_modes}\n*NODE FILE\nU\n*END STEP\n"
        elif job.analysis_type == "BUCKLING":
            step = f"*STEP, PERTURBATION\n*BUCKLE\n{job.num_modes}\n{load_section}*NODE FILE\nU\n*END STEP\n"
        else:
            step = f"*STEP\n*STATIC\n1.0, 1.0\n{load_section}*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n"

        inp_content = f"""*HEADING
{job.case_name} - {job.analysis_type} Analysis
{mesh_include}
*MATERIAL, NAME={mat_name}
*ELASTIC
{E_pa:.6e}, {job.material.poisson_ratio}
*DENSITY
{job.material.density}
*SHELL SECTION, ELSET=EALL, MATERIAL={mat_name}
{shell_thickness:.6f},
{bc_section}
{step}"""

        inp_path.write_text(inp_content)
        return str(inp_path)

    def run_simulation(self, job: FEAJob) -> dict:
        """FEA simülasyonu çalıştır"""
        case_dir = self.base_path / job.case_name

        try:
            # Case hazırlama
            if not self.setup_case(job):
                return {"status": "FAILED", "error": "Case setup failed"}

            # Input dosyası oluştur
            inp_file = self.generate_inp_file(job)
            print(f"🔄 [{job.case_name}] Input file generated: {inp_file}")

            # CalculiX solver çalıştır
            print(f"🔄 [{job.case_name}] Running FEA analysis...")

            try:
                wsl_dir = _to_wsl_path(case_dir)
                cmd = f'wsl bash -c "cd {wsl_dir} && ccx -i {job.case_name}"'
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    timeout=1800,
                    text=True
                )

                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout or "CalculiX solver failed"
                    return {"status": "FAILED", "error": f"CalculiX failed: {error_msg}"}

            except subprocess.TimeoutExpired:
                return {"status": "TIMEOUT", "error": "FEA analysis exceeded 30 minute timeout"}

            print(f"✅ [{job.case_name}] FEA analysis completed")

            # Sonuçları oku
            return self._extract_results(case_dir, job)

        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    @staticmethod
    def _parse_frd(frd_path: Path) -> dict:
        """CalculiX .frd dosyasını parse et.
        Döndürür: displacement (max, mean), von Mises stress (max), frequencies (list)
        FRD format: -4 block header, -5 component, -1 node_id val1 val2 ...
        """
        results = {}
        try:
            lines = frd_path.read_text(errors="replace").splitlines()
            block = None
            disps, vm_stresses, freqs = [], [], []
            # FRD fixed-width: negatif sayilar bitisik yazilir (0.0E+00-2.8E-11).
            # split() bunlari tek token yapip atlar -> sci-notation regex gerekli.
            # Us OPSIYONEL: ccx'in kendisi hep %12.5E yazar, ama donusturulmus/uretilmis
            # .frd'lerde ussuz bilesen gorulebilir. Eksik okunan bilesen 6-bilesen
            # kosulunu dusurur ve STRESS satiri SESSIZCE atlanir -> tepe gerilme kacar,
            # SF olduğundan YUKSEK cikar (tehlikeli yon). Superset kabul, savunmaci.
            _SCI = re.compile(r'[-+]?\d*\.\d+(?:[eE][-+]?\d+)?')

            for line in lines:
                # Blok başlıkları
                if " -4  DISP" in line:
                    block = "DISP"; continue
                if " -4  STRESS" in line:
                    block = "STRESS"; continue
                if " -4  FREQ" in line or " -4  MODEFREQ" in line:
                    block = "FREQ"; continue
                if line.startswith(" -4") or line.startswith(" -3") or line.startswith("    1"):
                    block = None

                if block and line.startswith(" -1"):
                    vals = [float(x) for x in _SCI.findall(line[3:])]

                    if block == "DISP" and len(vals) >= 3:
                        u1, u2, u3 = vals[0], vals[1], vals[2]
                        disps.append((u1**2 + u2**2 + u3**2) ** 0.5)

                    elif block == "STRESS" and len(vals) >= 6:
                        # S11,S22,S33,S12,S23,S13 → von Mises
                        s11, s22, s33, s12, s23, s13 = vals[:6]
                        vm = ((s11-s22)**2 + (s22-s33)**2 + (s33-s11)**2
                              + 6*(s12**2 + s23**2 + s13**2)) ** 0.5 / (2**0.5)
                        vm_stresses.append(vm)

                    elif block == "FREQ" and len(vals) >= 1:
                        freqs.append(vals[0])

            if disps:
                results["max_displacement_m"] = max(disps)
                results["mean_displacement_m"] = sum(disps) / len(disps)
            if vm_stresses:
                results["max_von_mises_pa"] = max(vm_stresses)
                results["max_von_mises_mpa"] = max(vm_stresses) / 1e6
            if freqs:
                results["natural_frequencies_hz"] = freqs[:10]

        except Exception as e:
            results["frd_parse_error"] = str(e)
        return results

    def _extract_results(self, case_dir: Path, job: FEAJob) -> dict:
        """FEA sonuçlarını çıkar — FRD parser + güvenlik faktörü"""
        frd_file = case_dir / f"{job.case_name}.frd"

        results = {
            "status": "SUCCESS",
            "case_name": job.case_name,
            "analysis_type": job.analysis_type,
            "material": job.material.name,
            "timestamp": datetime.now().isoformat(),
        }

        if frd_file.exists():
            frd_data = self._parse_frd(frd_file)
            results.update(frd_data)

            # Güvenlik faktörü (statik analiz)
            if job.analysis_type == "STATIC" and "max_von_mises_pa" in results:
                sigma_y_pa = job.material.yield_strength * 1e6   # MPa → Pa
                sf = sigma_y_pa / results["max_von_mises_pa"]
                results["safety_factor"] = round(sf, 3)
                results["is_safe"] = sf > 1.5
                results["yield_strength_mpa"] = job.material.yield_strength

        return results

    def _extract_frequencies(self, frd_file: Path) -> list[float]:
        """Modal frekanslar — DOĞRULANMIŞ ayrıştırıcıya devreder.

        Bu metot iki ayrı biçimde yanlıştı ve hiçbir yerden çağrılmadığı için sessiz
        kalmıştı: (1) frekansları `.frd`'de arıyordu, oysa ccx onları `.dat`'a yazar;
        (2) "eigenvalue" satırının SON alanını okuyordu, oysa CYCLES/TIME sütunu 4.
        sıradadır. `vehicle_fea._parse_eigenfrequencies` gerçek ccx çıktısında
        doğrulandı (iki başlık biçimi + doğru sütun) — çoğaltmak yerine ona devredilir.
        """
        from vehicle_fea import _parse_eigenfrequencies
        dat = Path(frd_file).with_suffix(".dat")
        return _parse_eigenfrequencies(dat)

    def run_parametric_study(self, base_job: FEAJob, parameter_variations: dict,
                            num_workers: int = 4) -> list[dict]:
        """Parametrik FEA çalışması"""
        jobs = []

        # Varyasyonları oluştur
        param_names = list(parameter_variations.keys())
        param_values = [parameter_variations[p] for p in param_names]

        import itertools
        for combo in itertools.product(*param_values):
            modified_job = FEAJob(
                case_name=f"{base_job.case_name}_{'_'.join(str(v) for v in combo)}",
                mesh_file=base_job.mesh_file,
                material=base_job.material,
                boundary_conditions=base_job.boundary_conditions,
                loads=base_job.loads,
                analysis_type=base_job.analysis_type,
                num_modes=base_job.num_modes,
                output_format=base_job.output_format
            )
            jobs.append(modified_job)

        # Paralel çalıştırma
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(self.run_simulation, job) for job in jobs]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        return results

    def run_structural_assessment(self, stl_path: str, material_key: str,
                                   aircraft_mass_kg: float,
                                   maneuver_g: float = 2.5,
                                   base_path: str = "./fea_cases",
                                   shell_thickness: float = 0.0015,
                                   cfd_results: dict = None) -> dict:
        """Gerçek uçak yükleriyle yapısal değerlendirme.
        Limit yük (n×m×g) ve Ultimate yük (×1.5) için iki ayrı analiz çalıştırır.

        cfd_results: varsa CFD'den Cl/Cd ile distributed pressure load hesaplanır.
                     yoksa nokta kuvveti kullanılır (daha az gerçekçi).

        FAR/CS-23: limit → SF > 1.0, ultimate → SF > 1.0 (yield'e göre)
        """
        g = 9.81
        limit_force    = maneuver_g * aircraft_mass_kg * g
        ultimate_force = limit_force * 1.5

        mat = MATERIAL_LIBRARY.get(material_key)
        if mat is None:
            return {"status": "FAILED", "error": f"Material '{material_key}' not found"}

        load_description = "point_force"

        # CFD sonucu varsa distributed pressure load hesapla
        dist_load = None
        if cfd_results and cfd_results.get("status") == "SUCCESS":
            try:
                dist_load = make_distributed_load_from_cfd(cfd_results, stl_path)
                load_description = "distributed_pressure_from_cfd"
                print(f"  CFD distributed load: lift={dist_load['lift_N']:.2f}N "
                      f"p_lift={dist_load['p_lift_Pa']:.2f}Pa")
            except Exception as e:
                print(f"  Distributed load failed ({e}), falling back to point force")

        results = {
            "aircraft_mass_kg":  aircraft_mass_kg,
            "maneuver_g":        maneuver_g,
            "limit_force_N":     round(limit_force, 2),
            "ultimate_force_N":  round(ultimate_force, 2),
            "material":          mat.name,
            "shell_thickness_mm": shell_thickness * 1000,
            "load_description":  load_description,
        }

        for load_type, force in [("limit", limit_force), ("ultimate", ultimate_force)]:
            bc   = BoundaryCondition("fixed", "NSET_FIXED", (1, 6), 0.0)

            # Distributed pressure: *DLOAD EALL P p_value (manöver faktörü ile ölçekle)
            if dist_load:
                scale = force / max(dist_load["lift_N"], 1e-6)
                p_scaled = dist_load["p_lift_Pa"] * scale
                load = Load("aero_pressure", "EALL", "PRESSURE", p_scaled)
            else:
                load = Load("maneuver", "NSET_LOAD", "FORCE", force)

            job  = FEAJob(
                case_name=f"structural_{load_type}",
                mesh_file=stl_path,
                material=mat,
                boundary_conditions=[bc],
                loads=[load],
                analysis_type="STATIC",
            )
            r = self.run_simulation(job)
            results[load_type] = r

            if r.get("status") == "SUCCESS":
                sf  = r.get("safety_factor")
                vm  = r.get("max_von_mises_mpa")
                u   = r.get("max_displacement_m")
                safe = r.get("is_safe")
                print(f"  [{load_type.upper()} {force:.1f} N] "
                      f"SF={sf}  vonMises={vm} MPa  u_max={u} m  safe={safe}")

        # Genel karar
        lim_safe = results.get("limit", {}).get("is_safe", False)
        ult_sf   = results.get("ultimate", {}).get("safety_factor", 0)
        results["design_acceptable"] = lim_safe and (ult_sf is not None and ult_sf > 1.0)
        return results

    def run_wing_structural_assessment(
        self,
        span: float,
        root_chord: float,
        tip_chord: float,
        material_key: str,
        aircraft_mass_kg: float,
        cfd_cl: float,
        wind_speed: float,
        maneuver_g: float = 2.5,
        shell_thickness: float = 0.0015,
        naca_digits: str = "2412",
    ) -> dict:
        """Yarım kanat (semi-span) kantilever yapısal değerlendirmesi.

        Gerçekçi beklentiler:
        - Kanat kökü rijit ankastre (wing-box fuselage bağlantısı)
        - Distributed lift pressure: p = Cl * q (kanat alt yüzeyi)
        - FAR/CS-23: limit=2.5g ultimate=3.75g

        Döndürür: tip deflection, max von Mises, safety factor
        """
        import numpy as np
        import trimesh

        case_dir = self.base_path / "wing_structural"
        case_dir.mkdir(exist_ok=True)

        q_pa   = 0.5 * 1.225 * wind_speed ** 2     # dynamic pressure
        Lift_N = cfd_cl * q_pa * span * root_chord  # half-wing, approx rectangular
        p_lift = Lift_N / (span * (root_chord + tip_chord) / 2)  # Pa, trapezoidal area

        mat = MATERIAL_LIBRARY.get(material_key)
        if mat is None:
            return {"status": "FAILED", "error": f"Material '{material_key}' not found"}

        # NACA 4-digit profil
        t_ratio = int(naca_digits[2:]) / 100.0
        def yt(x_nd):
            return (t_ratio / 0.2) * (0.2969 * np.sqrt(np.maximum(x_nd, 1e-10))
                    - 0.1260 * x_nd - 0.3516 * x_nd**2
                    + 0.2843 * x_nd**3 - 0.1015 * x_nd**4)

        # Semi-span mesh: n_span sections boyunca NACA profil extrude
        n_prof  = 32    # profil nokta sayısı (her yarı = 16 nokta)
        n_span  = 20    # span istasyon sayısı

        beta = np.linspace(0, 2 * np.pi, n_prof, endpoint=False)
        x_nd = 0.5 * (1 - np.cos(beta))
        z_nd = yt(x_nd) * np.sign(np.sin(beta) + 1e-10)

        # Taper: kord, root'tan tip'e lineer azalır
        span_stations = np.linspace(0, span, n_span + 1)
        taper_ratio   = tip_chord / root_chord
        chords = root_chord * (1 - (1 - taper_ratio) * span_stations / span)

        verts_list = []
        for i, (y_val, c) in enumerate(zip(span_stations, chords)):
            xv = x_nd * c      # metre cinsinden x (kord boyunca)
            zv = z_nd * c      # metre cinsinden z (kalınlık)
            yv = np.full(n_prof, y_val)
            verts_list.append(np.column_stack([xv, yv, zv]))

        verts = np.vstack(verts_list)  # (n_span+1)*n_prof nodes

        # Faces: her iki komşu istasyon arasında quad → 2 üçgen
        faces = []
        for s in range(n_span):
            base = s * n_prof
            for j in range(n_prof):
                a  = base + j
                b  = base + (j + 1) % n_prof
                c_ = base + n_prof + j
                d  = base + n_prof + (j + 1) % n_prof
                faces.extend([[a, b, c_], [b, d, c_]])

        mesh_w = trimesh.Trimesh(vertices=verts,
                                  faces=np.array(faces, dtype=np.int64),
                                  process=True)
        stl_path = case_dir / "wing.stl"
        mesh_w.export(str(stl_path))

        # INP dosyası yaz
        inp_lines = [f"*HEADING\nWing structural assessment — {naca_digits} span={span}m\n"]

        inp_lines.append("*NODE, NSET=NALL\n")
        for i, (vx, vy, vz) in enumerate(verts):
            inp_lines.append(f"{i+1}, {vx:.8e}, {vy:.8e}, {vz:.8e}\n")

        inp_lines.append("*ELEMENT, TYPE=S3, ELSET=EALL\n")
        for i, (n0, n1, n2) in enumerate(np.array(faces)):
            inp_lines.append(f"{i+1}, {n0+1}, {n1+1}, {n2+1}\n")

        # Root nodes: y ≈ 0 (wing root, ankastre)
        root_ids = [i + 1 for i, (_, yv, _) in enumerate(verts) if yv < span * 0.02]
        inp_lines.append("*NSET, NSET=NROOT\n")
        for j in range(0, len(root_ids), 8):
            inp_lines.append(", ".join(str(n) for n in root_ids[j:j+8]) + "\n")

        E_pa = mat.youngs_modulus * 1e6
        mat_name = material_key.upper()
        inp_lines.extend([
            f"*MATERIAL, NAME={mat_name}\n",
            f"*ELASTIC\n{E_pa:.6e}, {mat.poisson_ratio}\n",
            f"*DENSITY\n{mat.density}\n",
            f"*SHELL SECTION, ELSET=EALL, MATERIAL={mat_name}\n",
            f"{shell_thickness:.6f},\n",
        ])

        # Lift kuvvetini span boyunca düğümlere dağıt (eliptik dağılım)
        # Her span istasyonunda tüm profil düğümlerine eşit pay
        # Bu *DLOAD'un üst/alt yüzey sıfırlama problemini ortadan kaldırır.
        span_y = np.array([verts[s * n_prof, 1] for s in range(n_span + 1)])
        # Eliptik dağılım: q(y) = q0 * sqrt(1 - (y/(b/2))^2)
        elliptic = np.sqrt(np.maximum(1 - (span_y / span) ** 2, 0))
        elliptic_sum = elliptic.sum() if elliptic.sum() > 0 else 1.0

        results = {
            "span_m": span, "root_chord_m": root_chord, "tip_chord_m": tip_chord,
            "material": mat.name, "shell_thickness_mm": shell_thickness * 1000,
            "cfd_cl": cfd_cl, "wind_speed_ms": wind_speed,
            "q_pa": round(q_pa, 2), "lift_N": round(Lift_N, 2),
            "p_lift_Pa": round(p_lift, 2),
        }

        for load_label, g_factor in [("limit", maneuver_g), ("ultimate", maneuver_g * 1.5)]:
            total_force = Lift_N * g_factor  # Newton, +z yonu (lift)

            # Her span istasyonuna eliptik agirlikla kuvvet dagit
            cload_lines = ["*CLOAD\n"]
            for s in range(n_span + 1):
                f_station = total_force * elliptic[s] / elliptic_sum
                f_per_node = f_station / n_prof  # istasyondaki her dugume esit pay
                for j in range(n_prof):
                    nid = s * n_prof + j + 1
                    cload_lines.append(f"{nid}, 3, {f_per_node:.8f}\n")

            step_lines = inp_lines + [
                "*BOUNDARY\nNROOT, 1, 6, 0\n",
                "*STEP\n*STATIC\n1.0, 1.0\n",
            ] + cload_lines + [
                "*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n",
            ]
            inp_path = case_dir / f"wing_{load_label}.inp"
            inp_path.write_text("".join(step_lines))

            wsl_dir = _to_wsl_path(case_dir)
            rc = subprocess.run(
                f'wsl bash -c "cd {wsl_dir} && ccx -i wing_{load_label}"',
                shell=True, capture_output=True, timeout=600, text=True
            ).returncode

            frd_path = case_dir / f"wing_{load_label}.frd"
            if rc == 0 and frd_path.exists():
                frd_data = self._parse_frd(frd_path)
                sf = None
                if "max_von_mises_pa" in frd_data:
                    sf = round(mat.yield_strength * 1e6 / frd_data["max_von_mises_pa"], 2)
                results[load_label] = {
                    "g_factor": g_factor,
                    "total_force_N": round(total_force, 2),
                    "tip_deflection_mm": round(frd_data.get("max_displacement_m", 0) * 1000, 2),
                    "max_von_mises_MPa": round(frd_data.get("max_von_mises_pa", 0) / 1e6, 2),
                    "safety_factor": sf,
                    "is_safe": sf > 1.5 if sf else False,
                }
                print(f"  [{load_label.upper()} {g_factor}g] "
                      f"u_tip={results[load_label]['tip_deflection_mm']}mm  "
                      f"vonMises={results[load_label]['max_von_mises_MPa']}MPa  SF={sf}")
            else:
                results[load_label] = {"status": "FAILED"}

        return results

    def generate_report(self, results: list[dict]) -> str:
        """FEA analiz raporu oluştur"""
        report = f"""
# FEA Analiz Raporu
Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Özet
- Toplam Analiz: {len(results)}
- Başarılı: {sum(1 for r in results if r.get('status') == 'SUCCESS')}
- Başarısız: {sum(1 for r in results if r.get('status') == 'FAILED')}

## Detaylı Sonuçlar

"""
        for i, result in enumerate(results, 1):
            report += f"\n### Analiz {i}: {result.get('case_name', 'Unknown')}\n"
            report += f"- Durum: {result.get('status', 'Unknown')}\n"

            if result.get('status') == 'SUCCESS':
                report += f"- Analiz Tipi: {result.get('analysis_type')}\n"
                report += f"- Malzeme: {result.get('material')}\n"

                if "max_displacement" in result:
                    report += f"- Maks. Yer Değiştirme: {result.get('max_displacement', 'N/A'):.6f} m\n"

                if "max_stress" in result:
                    report += f"- Maks. Gerilme: {result.get('max_stress', 'N/A'):.2f} MPa\n"

                if "safety_factor" in result:
                    report += f"- Emniyet Faktörü: {result.get('safety_factor', 'N/A'):.2f}\n"
                    report += f"- Güvenli: {'✅ Evet' if result.get('is_safe') else '❌ Hayır'}\n"

                if "frequencies" in result:
                    report += f"- Doğal Frekanslar (Hz): {[f'{f:.2f}' for f in result['frequencies'][:5]]}\n"

        return report
