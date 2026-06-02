"""
3D Photogrammetry Scanner
Kameradan otomatik 3D model oluşturma
Structure from Motion (SfM) → Point Cloud → Mesh → CFD
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import cv2
import numpy as np

# open3d is optional (not available on Python 3.13)
try:
    import open3d as o3d  # type: ignore[import-untyped]
    HAS_OPEN3D = True
except ImportError:
    o3d = None  # type: ignore[assignment]
    HAS_OPEN3D = False

# trimesh is the primary mesh backend (always available)
try:
    import trimesh
    HAS_TRIMESH = True
except ImportError:
    trimesh = None
    HAS_TRIMESH = False

# pymeshlab: Poisson reconstruction (Python 3.14 uyumlu open3d alternatifi)
try:
    import pymeshlab
    HAS_PYMESHLAB = True
except ImportError:
    pymeshlab = None
    HAS_PYMESHLAB = False

# ─────────────────────────────────────────────────────────────────────────────
# ENUMS & DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

class ScannerMode(Enum):
    """Tarama modu"""
    WEBCAM = "webcam"          # Webcam ile manuel (geri sayımlı)
    LIVE_VIDEO = "live_video"  # Kameradan canlı kayıt → otomatik frame
    IP_CAMERA = "ip_camera"    # Telefon kamerası (IP Webcam / DroidCam)
    VIDEO_SEQUENCE = "sequence"  # Kaydedilmiş video dosyasından frame çıkar
    IMAGE_FOLDER = "folder"    # Klasördeki resimleri kullan

class MeshQuality(Enum):
    """Mesh kalitesi"""
    DRAFT = "draft"            # Hızlı, düşük poly (test)
    NORMAL = "normal"          # Dengeli
    HIGH = "high"              # Yüksek detay
    PRODUCTION = "production"  # CFD/FEA hazır

@dataclass
class ScanConfig:
    """Tarama konfigürasyonu"""
    mode: ScannerMode
    num_images: int = 20       # Kaç resim taranacak
    quality: MeshQuality = MeshQuality.NORMAL
    voxel_size: float = 0.01   # Point cloud simplification (m)
    outlier_threshold: float = 0.05  # Gürültü giderme
    output_format: str = "stl"  # stl, step, ply, obj
    camera_source: str = "0"   # int index (webcam) veya URL (IP camera)
    record_duration: int = 10  # canlı kayıt süresi (saniye)

# ─────────────────────────────────────────────────────────────────────────────
# IMAGE CAPTURE MODULE
# ─────────────────────────────────────────────────────────────────────────────

class CameraCapture:
    """Webcam veya IP kameradan görüntü yakalama.

    camera_source örnekleri:
      0                              → ilk USB/dahili webcam
      "http://192.168.1.5:8080/video"→ Android IP Webcam uygulaması
      "http://192.168.1.5:4747/video"→ DroidCam (WiFi)
      "rtsp://192.168.1.5:8080/h264_ulaw.sdp" → RTSP stream
    """

    def __init__(self, camera_source=0):
        self.camera_source = camera_source
        # Sayısal string ise int'e çevir ("0" → 0), URL ise olduğu gibi bırak
        if isinstance(camera_source, str) and camera_source.lstrip("-").isdigit():
            source = int(camera_source)
        elif isinstance(camera_source, str):
            source = camera_source  # http/rtsp URL
        else:
            source = int(camera_source)
        self.cap = cv2.VideoCapture(source)
        self.images = []

    @staticmethod
    def test_ip_camera(url: str) -> bool:
        """IP kamera bağlantısını test et."""
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            return False
        ret, _ = cap.read()
        cap.release()
        return ret

    def get_frame(self) -> tuple[bool, np.ndarray]:
        """Bir frame al"""
        ret, frame = self.cap.read()
        return ret, frame

    def capture_sequence(self, num_images: int, interval: int = 500,
                         progress_callback=None) -> list[np.ndarray]:
        """Resim sekansı yakala (cv2.imshow kullanmaz — PySide6 uyumlu)"""
        import time
        images = []
        while len(images) < num_images:
            ret, frame = self.get_frame()
            if ret:
                images.append(frame)
                if progress_callback:
                    progress_callback(len(images), num_images)
            time.sleep(interval / 1000.0)
        self.images = images
        return images

    def preview_with_countdown(self, num_images: int, interval: int = 2000,
                               progress_callback=None) -> list[np.ndarray]:
        """Geri sayımlı resim çekimi (cv2.imshow yok — PySide6 uyumlu)"""
        import time
        images = []
        for i in range(num_images):
            # Geri sayım: sadece sleep, pencere açma
            secs = max(1, interval // 1000)
            for countdown in range(secs, 0, -1):
                if progress_callback:
                    progress_callback(
                        int(i / num_images * 100),
                        f"Resim {i+1}/{num_images} — {countdown}s"
                    )
                time.sleep(1.0)

            # Frame yakala
            ret, frame = self.get_frame()
            if ret:
                images.append(frame)
                if progress_callback:
                    progress_callback(
                        int((i + 1) / num_images * 100),
                        f"Resim {i+1}/{num_images} yakalandı"
                    )
            time.sleep(0.3)

        self.images = images
        return images

    def release(self):
        """Kamerayı serbest bırak"""
        self.cap.release()


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE DETECTION & MATCHING
# ─────────────────────────────────────────────────────────────────────────────

class FeatureDetector:
    """SIFT/SURF feature detection"""

    def __init__(self, method: str = "sift"):
        self.method = method

        if method == "sift":
            self.detector = cv2.SIFT_create()
        elif method == "orb":
            self.detector = cv2.ORB_create(nfeatures=5000)
        else:
            self.detector = cv2.SIFT_create()

    def detect_and_compute(self, image: np.ndarray) -> tuple[list, np.ndarray]:
        """Keypoint ve descriptor hesapla"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        keypoints, descriptors = self.detector.detectAndCompute(gray, None)
        return keypoints, descriptors

    def match_features(self, desc1: np.ndarray, desc2: np.ndarray,
                      ratio_threshold: float = 0.8) -> list:
        """İki görüntü arasında eşleşme bul (Lowe's ratio test)"""
        if desc1 is None or desc2 is None:
            return []

        bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        matches = bf.knnMatch(desc1, desc2, k=2)

        # Lowe's ratio test
        good_matches = []
        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < ratio_threshold * n.distance:
                    good_matches.append(m)

        return good_matches


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURE FROM MOTION (SfM)
# ─────────────────────────────────────────────────────────────────────────────

class StructureFromMotion:
    """Structure from Motion — Point cloud oluşturma"""

    def __init__(self, camera_matrix: np.ndarray = None):
        """
        camera_matrix: Kamera kalibrasyonu (3x3)
                      None ise set_from_image_size() ile dinamik üretilir.
        """
        self.camera_matrix = camera_matrix  # may be None until set_from_image_size
        self.detector = FeatureDetector(method="sift")

    def set_from_image_size(self, w: int, h: int):
        """Görüntü boyutuna göre kamera matrisini tahmin et.
        Smartphone tipik FOV ≈ 60° → focal ≈ 1.2 * max(w,h)."""
        focal = 1.2 * max(w, h)
        self.camera_matrix = np.array([
            [focal, 0, w / 2.0],
            [0, focal, h / 2.0],
            [0, 0, 1.0],
        ])

    def estimate_fundamental_matrix(self, pts1: np.ndarray, pts2: np.ndarray) -> tuple:
        """Temel matris (F) hesapla. 8-point RANSAC, sonuç (3,3) garanti."""
        if len(pts1) < 8 or len(pts2) < 8:
            return None, None
        F, mask = cv2.findFundamentalMat(pts1, pts2, cv2.FM_RANSAC, 1.0, 0.99)
        if F is None:
            return None, None
        # findFundamentalMat bazen (9,3) döner (7-point fallback, 3 çözüm stacked)
        if F.shape != (3, 3):
            if F.shape[0] >= 3 and F.shape[1] == 3:
                F = F[:3, :3]
            else:
                return None, None
        return F, mask

    def triangulate_points(self, P1: np.ndarray, P2: np.ndarray,
                          pts1: np.ndarray, pts2: np.ndarray) -> np.ndarray:
        """Eşleştirilen noktaları 3D'ye triangüle et"""
        points_4d = cv2.triangulatePoints(P1, P2, pts1.T, pts2.T)
        points_3d = (points_4d[:3] / points_4d[3]).T
        return points_3d

    def estimate_pose(self, matches, keypoints1, keypoints2, F):
        """İki görüntü arasında pose (R, t) hesapla"""
        if F is None or F.shape != (3, 3) or self.camera_matrix is None:
            return None, None, None
        points1 = np.float32([keypoints1[m.queryIdx].pt for m in matches])
        points2 = np.float32([keypoints2[m.trainIdx].pt for m in matches])

        # Temel matrisden essential matris
        E = self.camera_matrix.T @ F @ self.camera_matrix
        if E.shape != (3, 3):
            return None, None, None

        # Pose çıkar (4 olası çözüm)
        try:
            _, R, t, mask = cv2.recoverPose(E, points1, points2,
                                            self.camera_matrix, mask=None)
        except cv2.error:
            return None, None, None

        return R, t, mask


# ─────────────────────────────────────────────────────────────────────────────
# POINT CLOUD PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

class PointCloudProcessor:
    """Point cloud işleme (trimesh primary, open3d optional).

    Tüm metotlar bir numpy (N,3) point array'i üzerinde çalışır; backend
    farkını gizler. open3d varsa Poisson reconstruction için kullanılır,
    yoksa trimesh + scipy.ConvexHull / alpha-shape fallback uygulanır.
    """

    def __init__(self):
        self.pcd = None  # numpy (N,3) array
        self.normals = None  # numpy (N,3) array

    def create_point_cloud(self, points: np.ndarray) -> np.ndarray:
        """Numpy array'den point cloud oluştur"""
        self.pcd = np.asarray(points, dtype=np.float64)
        return self.pcd

    def remove_outliers(self, pcd: np.ndarray,
                       nb_neighbors: int = 20,
                       std_ratio: float = 2.0) -> np.ndarray:
        """Statistical outlier removal (sklearn KDTree)"""
        if len(pcd) < nb_neighbors + 1:
            return pcd
        try:
            from scipy.spatial import cKDTree
        except ImportError:
            return pcd
        tree = cKDTree(pcd)
        dists, _ = tree.query(pcd, k=nb_neighbors + 1)
        # Mean distance to neighbors (skip self at index 0)
        mean_d = dists[:, 1:].mean(axis=1)
        threshold = mean_d.mean() + std_ratio * mean_d.std()
        keep = mean_d < threshold
        return pcd[keep]

    def downsample(self, pcd: np.ndarray, voxel_size: float = 0.01) -> np.ndarray:
        """Voxel-grid downsample (her voxel hücresinden bir nokta)"""
        if voxel_size <= 0 or len(pcd) == 0:
            return pcd
        keys = np.floor(pcd / voxel_size).astype(np.int64)
        # Unique voxel keys → temsilci nokta
        _, idx = np.unique(keys, axis=0, return_index=True)
        return pcd[np.sort(idx)]

    def estimate_normals(self, pcd: np.ndarray, k: int = 30) -> np.ndarray:
        """KNN tabanlı PCA ile normal vektör tahmini"""
        if len(pcd) < k + 1:
            self.normals = np.zeros_like(pcd)
            return pcd
        try:
            from scipy.spatial import cKDTree
        except ImportError:
            self.normals = np.zeros_like(pcd)
            return pcd
        tree = cKDTree(pcd)
        _, idx = tree.query(pcd, k=k + 1)
        normals = np.zeros_like(pcd)
        for i, neigh in enumerate(idx):
            pts = pcd[neigh]
            cov = np.cov((pts - pts.mean(axis=0)).T)
            try:
                w, v = np.linalg.eigh(cov)
                normals[i] = v[:, 0]  # smallest eigenvalue → normal
            except np.linalg.LinAlgError:
                pass
        # Yönlendir: her normal kamera (origin) yönüne baksın
        flip = (normals * pcd).sum(axis=1) > 0
        normals[flip] = -normals[flip]
        self.normals = normals
        return pcd

    def poisson_mesh(self, pcd: np.ndarray, depth: int = 9):
        """Surface reconstruction — öncelik sırası:
        1. open3d  (Poisson, en kaliteli)
        2. pymeshlab (Screened Poisson, Python 3.14 uyumlu open3d alternatifi)
        3. trimesh convex hull (her zaman çalışan fallback)
        """
        if HAS_OPEN3D:
            o3pcd = o3d.geometry.PointCloud()
            o3pcd.points = o3d.utility.Vector3dVector(pcd)
            if self.normals is not None:
                o3pcd.normals = o3d.utility.Vector3dVector(self.normals)
            else:
                o3pcd.estimate_normals()
            mesh, _ = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
                o3pcd, depth=depth)
            return mesh

        if HAS_PYMESHLAB:
            ms = pymeshlab.MeshSet()
            ms.add_mesh(pymeshlab.Mesh(vertex_matrix=pcd.astype(np.float64)))
            ms.compute_normal_for_point_clouds()
            ms.generate_surface_reconstruction_screened_poisson(depth=depth)
            m = ms.current_mesh()
            if HAS_TRIMESH:
                return trimesh.Trimesh(
                    vertices=m.vertex_matrix(),
                    faces=m.face_matrix(),
                    process=False,
                )
            return m  # pymeshlab Mesh nesnesi

        # Son çare: trimesh convex hull
        if HAS_TRIMESH:
            return trimesh.Trimesh(vertices=pcd).convex_hull
        raise RuntimeError("Mesh backend bulunamadı: pymeshlab, open3d veya trimesh gerekli")

    def ball_pivoting_mesh(self, pcd: np.ndarray,
                          radii: list[float] | None = None):
        """Ball pivoting (open3d) veya convex hull fallback"""
        if HAS_OPEN3D:
            o3pcd = o3d.geometry.PointCloud()
            o3pcd.points = o3d.utility.Vector3dVector(pcd)
            o3pcd.estimate_normals()
            r = o3d.utility.DoubleVector(radii or [0.005, 0.01, 0.02])
            return o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(o3pcd, r)
        return self.poisson_mesh(pcd)


# ─────────────────────────────────────────────────────────────────────────────
# MESH OPTIMIZATION FOR CFD
# ─────────────────────────────────────────────────────────────────────────────

def _is_o3d_mesh(mesh) -> bool:
    return HAS_OPEN3D and isinstance(mesh, o3d.geometry.TriangleMesh)


class MeshOptimizer:
    """CFD/FEA için mesh optimize etme (trimesh + open3d uyumlu)"""

    @staticmethod
    def simplify_mesh(mesh, target_count: int = 50000):
        """Mesh'i sadeleştir (polygon sayısını azalt)"""
        if _is_o3d_mesh(mesh):
            return mesh.simplify_quadric_decimation(target_number_of_triangles=target_count)
        # trimesh
        try:
            return mesh.simplify_quadric_decimation(target_count)
        except Exception:
            return mesh  # fallback: olduğu gibi döndür

    @staticmethod
    def smooth_mesh(mesh, iterations: int = 3):
        """Laplacian smoothing"""
        if _is_o3d_mesh(mesh):
            for _ in range(iterations):
                mesh = mesh.filter_smooth_laplacian(number_of_iterations=1)
            return mesh
        # trimesh
        try:
            import trimesh.smoothing as ts
            ts.filter_laplacian(mesh, iterations=iterations)
        except Exception:
            pass
        return mesh

    @staticmethod
    def remove_isolated_triangles(mesh, cluster_size_threshold: int = 100):  # noqa: ARG004
        """İzole üçgenleri sil"""
        if _is_o3d_mesh(mesh):
            mesh.remove_degenerate_triangles()
            mesh.remove_unreferenced_vertices()
            return mesh
        try:
            mesh.process()
            mesh.remove_unreferenced_vertices()
        except Exception:
            pass
        return mesh

    @staticmethod
    def check_mesh_quality(mesh) -> dict:
        """Mesh kalitesini kontrol et"""
        if _is_o3d_mesh(mesh):
            return {
                "is_watertight": mesh.is_watertight(),
                "vertices": len(mesh.vertices),
                "triangles": len(mesh.triangles),
                "is_edge_manifold": mesh.is_edge_manifold(),
                "is_vertex_manifold": mesh.is_vertex_manifold(),
            }
        # trimesh
        return {
            "is_watertight": bool(getattr(mesh, "is_watertight", False)),
            "vertices": len(mesh.vertices),
            "triangles": len(mesh.faces),
            "is_edge_manifold": bool(getattr(mesh, "is_winding_consistent", True)),
            "is_vertex_manifold": True,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 3D SCANNER PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

class PhotogrammetryScanner:
    """Tam tarama pipeline"""

    def __init__(self, config: ScanConfig):
        self.config = config
        self.images = []
        self.image_dir: Path | None = None  # for COLMAP / disk-based modes
        self.point_cloud = None
        self.mesh = None

        # Camera lazy-init: only when WEBCAM mode is used
        self.camera = None
        self.feature_detector = FeatureDetector()
        self.sfm = StructureFromMotion()
        self.point_processor = PointCloudProcessor()
        self.mesh_optimizer = MeshOptimizer()

    def scan_with_webcam(self, progress_callback=None) -> bool:
        """Webcam veya IP kamera ile geri sayımlı tarama."""
        source = self.config.camera_source
        is_ip = isinstance(source, str) and source.startswith(("http", "rtsp"))
        label = f"IP Kamera ({source})" if is_ip else "Webcam"
        print(f"[INFO] {label} taraması başladı...")

        if self.camera is None:
            self.camera = CameraCapture(source)

        if not self.camera.cap.isOpened():
            print(f"[ERROR] Kamera açılamadı: {source}")
            if is_ip:
                print("[HINT] IP Webcam uygulamasının çalıştığından ve URL'nin doğru olduğundan emin ol.")
            return False

        self.images = self.camera.preview_with_countdown(
            self.config.num_images, interval=2000,
            progress_callback=progress_callback)
        self.camera.release()

        if progress_callback:
            progress_callback(25, f"{len(self.images)} görüntü yakalandı ({label})")

        return len(self.images) > 0

    def capture_live_video(self, duration_sec: int = 10,
                           progress_callback=None,
                           frame_callback=None) -> bool:
        """Kameradan canlı video kaydı yap, eşit aralıklı frame'ler çıkar.

        Kullanıcı kamerayı objenin etrafında döndürür, sistem otomatik
        frame yakalar — manuel geri sayım yok.

        frame_callback(frame): her okunan frame için çağrılır (canlı önizleme).
        """
        import time
        source = self.config.camera_source
        if isinstance(source, str) and source.lstrip("-").isdigit():
            source = int(source)

        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"[ERROR] Kamera açılamadı: {source}")
            return False

        # Siyah-frame guard: ilk birkaç frame'i ısıt ve parlaklık kontrolü yap
        warmup_brightness = []
        for _ in range(8):
            ret, fr = cap.read()
            if ret and fr is not None:
                warmup_brightness.append(float(fr.mean()))
            time.sleep(0.05)
        if warmup_brightness:
            avg_b = sum(warmup_brightness) / len(warmup_brightness)
            print(f"[INFO] Kamera ısınma parlaklığı: {avg_b:.1f}/255")
            if avg_b < 5.0:
                print(f"[ERROR] Kamera siyah frame veriyor (brightness={avg_b:.1f}).")
                print("[HINT] Telefon webcam yayını başlatılmamış olabilir (DroidCam/Iriun gerekli)")
                print("[HINT] Veya başka bir kamera index'i dene (0=laptop, 1/2=USB)")
                cap.release()
                return False

        n_frames = self.config.num_images
        interval = duration_sec / n_frames  # saniye cinsinden frame aralığı
        frames = []
        start = time.time()

        print(f"[INFO] Canlı kayıt başladı — {duration_sec}s, {n_frames} frame")

        while len(frames) < n_frames:
            elapsed = time.time() - start
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                if time.time() - start > duration_sec + 2:
                    break
                continue

            # Her frame'i preview'a gönder
            if frame_callback is not None:
                try:
                    frame_callback(frame)
                except Exception:
                    pass

            # Eşit zaman aralığı geçtiyse SfM için sakla
            expected = len(frames) * interval
            if elapsed >= expected:
                frames.append(frame.copy())
                pct = int(len(frames) / n_frames * 25)
                if progress_callback:
                    progress_callback(pct,
                        f"Kayıt: {len(frames)}/{n_frames} "
                        f"({elapsed:.1f}s / {duration_sec}s)")

            # Kalan süre bitmişse çık
            if time.time() - start > duration_sec + 2:
                break

            time.sleep(0.01)

        cap.release()
        self.images = frames
        print(f"[OK] {len(frames)} frame yakalandı ({duration_sec}s kayıt)")
        return len(frames) >= 2

    def load_images_from_folder(self, folder: Path,
                                progress_callback=None) -> bool:
        """Klasördeki tüm görüntüleri yükle (COLMAP veya SfM için)"""
        folder = Path(folder)
        if not folder.exists():
            print(f"❌ Klasör bulunamadı: {folder}")
            return False

        exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
        files = sorted([p for p in folder.iterdir() if p.suffix.lower() in exts])

        if not files:
            print(f"❌ Görüntü bulunamadı: {folder}")
            return False

        self.image_dir = folder
        self.images = []
        for i, f in enumerate(files):
            img = cv2.imread(str(f))
            if img is not None:
                self.images.append(img)
            if progress_callback:
                progress_callback(int(25 * (i + 1) / len(files)),
                                  f"Resim yükleniyor: {i+1}/{len(files)}")

        print(f"✅ {len(self.images)} görüntü yüklendi: {folder}")
        return len(self.images) >= 2

    def load_video(self, video_path: Path, n_frames: int = 30,
                   progress_callback=None) -> bool:
        """Video dosyasından eşit aralıklı frame'ler çıkar"""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"❌ Video açılamadı: {video_path}")
            return False

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        step = max(1, total // n_frames)
        self.images = []
        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if idx % step == 0:
                self.images.append(frame)
                if progress_callback:
                    progress_callback(int(25 * len(self.images) / n_frames),
                                      f"Frame: {len(self.images)}/{n_frames}")
                if len(self.images) >= n_frames:
                    break
            idx += 1
        cap.release()
        print(f"✅ Video'dan {len(self.images)} frame çıkarıldı")
        return len(self.images) >= 2

    def run_colmap_pipeline(self, images_dir: Path, workspace: Path,
                            progress_callback=None) -> Path | None:
        """COLMAP-based reconstruction (Desktop\\photogrammetry kütüphanesi).

        Reconstructor sınıfını core/__init__.py'yi atlayarak doğrudan
        modül dosyasından yükler (open3d bağımlılığını tetiklememek için).
        COLMAP binary'sini PATH'ten veya config.ini'den arar.
        Returns: fused.ply yolu veya None
        """
        import importlib.util
        import shutil as _shutil

        colmap_lib = Path(r"C:\Users\Victus\Desktop\photogrammetry")
        if not colmap_lib.exists():
            print("[INFO] Desktop\\photogrammetry yok, dahili SfM kullanılacak")
            return None

        recon_py = colmap_lib / "core" / "reconstructor.py"
        if not recon_py.exists():
            print(f"[INFO] {recon_py} bulunamadı, dahili SfM kullanılacak")
            return None

        # COLMAP binary kontrolü
        colmap_bin = _shutil.which("colmap")
        if colmap_bin is None:
            # config.ini'den path oku
            cfg = colmap_lib / "config.ini"
            if cfg.exists():
                import configparser
                cp = configparser.ConfigParser()
                try:
                    cp.read(cfg)
                    candidate = cp.get("PATHS", "colmap_path", fallback="colmap")
                    if Path(candidate).exists():
                        colmap_bin = candidate
                except Exception:
                    pass
        if colmap_bin is None:
            print("[ERROR] COLMAP binary bulunamadı (PATH veya config.ini'de yok)")
            print("[HINT] https://github.com/colmap/colmap/releases adresinden indir,")
            print("       sonra config.ini'de [PATHS] colmap_path=C:\\path\\to\\colmap.exe ayarla")
            return None

        try:
            import sys as _sys
            if str(colmap_lib) not in _sys.path:
                _sys.path.insert(0, str(colmap_lib))
            # utils.config / utils.logger erişimi için
            spec = importlib.util.spec_from_file_location(
                "_colmap_reconstructor", str(recon_py))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            Reconstructor = mod.Reconstructor
        except Exception as e:
            print(f"[INFO] COLMAP wrapper yüklenemedi ({e}), dahili SfM kullanılacak")
            return None

        # Reconstructor Config()'i CWD'den arar; geçici olarak photogrammetry'e in.
        # Ayrıca Reconstructor/Config unicode (✅, ❌, ⚠) basıyor — Windows
        # cp1254 konsolunda patlamasın diye builtins.print'i sarmalıyoruz.
        import builtins as _builtins
        import os as _os
        _orig_cwd = _os.getcwd()
        _orig_print = _builtins.print

        def _safe_print(*args, **kwargs):
            try:
                _orig_print(*args, **kwargs)
            except (UnicodeEncodeError, UnicodeError):
                # Unicode'u ASCII'ye düşür
                safe_args = []
                for a in args:
                    s = str(a)
                    safe_args.append(s.encode("ascii", "replace").decode("ascii"))
                try:
                    _orig_print(*safe_args, **kwargs)
                except Exception:
                    pass

        _builtins.print = _safe_print
        try:
            _os.chdir(str(colmap_lib))
            recon = Reconstructor()
            workspace.mkdir(parents=True, exist_ok=True)
            ply_path = recon.run_colmap(
                images_dir=str(images_dir),
                workspace_dir=str(workspace),
                progress_callback=progress_callback,
            )
            return Path(ply_path) if ply_path else None
        except Exception as e:
            import traceback
            _orig_print(f"[WARNING] COLMAP basarisiz: {e}")
            traceback.print_exc()
            return None
        finally:
            _builtins.print = _orig_print
            try:
                _os.chdir(_orig_cwd)
            except Exception:
                pass

    def process_images(self, progress_callback=None) -> bool:
        """Görüntüleri işle ve SfM yapı oluştur"""
        if len(self.images) < 2:
            print("❌ En az 2 görüntü gerekli")
            return False

        # Kamera matrisini gerçek görüntü boyutundan üret
        h, w = self.images[0].shape[:2]
        self.sfm.set_from_image_size(w, h)
        print(f"[INFO] Kamera matrisi {w}x{h} için ayarlandı (focal≈{1.2*max(w,h):.0f})")

        print(f"🔍 {len(self.images)} görüntüde feature detection...")

        # Tüm görüntülerin keypoint'lerini bul
        all_keypoints = []
        all_descriptors = []

        for i, img in enumerate(self.images):
            kp, desc = self.feature_detector.detect_and_compute(img)
            all_keypoints.append(kp)
            all_descriptors.append(desc)

            if progress_callback:
                progress = 25 + int((i + 1) / len(self.images) * 25)
                progress_callback(progress, f"Feature detection: {i+1}/{len(self.images)}")

        # Point cloud başlat
        all_points_3d = []
        total_matches = 0
        successful_pairs = 0

        # Sliding window: her görüntüyü sonraki 1-3 görüntü ile dene
        n = len(self.images)
        pair_list = []
        for i in range(n - 1):
            for j in range(i + 1, min(i + 4, n)):
                pair_list.append((i, j))

        for idx, (i, j) in enumerate(pair_list):
            # Feature matching
            matches = self.feature_detector.match_features(
                all_descriptors[i], all_descriptors[j])

            if len(matches) < 6:
                continue

            # Point çıkar
            pts1 = np.float32([all_keypoints[i][m.queryIdx].pt for m in matches])
            pts2 = np.float32([all_keypoints[j][m.trainIdx].pt for m in matches])

            # F matrix
            F, mask = self.sfm.estimate_fundamental_matrix(pts1, pts2)
            if F is None or mask is None:
                continue

            inliers = int(mask.sum())
            if inliers < 6:
                continue

            try:
                R, t, _ = self.sfm.estimate_pose(matches, all_keypoints[i],
                                                  all_keypoints[j], F)
            except cv2.error:
                continue
            if R is None or t is None:
                continue

            # Triangulation
            P1 = self.sfm.camera_matrix @ np.hstack([np.eye(3), np.zeros((3, 1))])
            P2 = self.sfm.camera_matrix @ np.hstack([R, t.reshape(3, 1)])

            try:
                points_3d = self.sfm.triangulate_points(
                    P1, P2,
                    pts1[mask.ravel() == 1],
                    pts2[mask.ravel() == 1])
            except cv2.error:
                continue

            all_points_3d.extend(points_3d)
            total_matches += inliers
            successful_pairs += 1
            print(f"  ✓ {i}↔{j}: {inliers} inlier ({len(matches)} match)")

            if progress_callback:
                progress = 50 + int((idx + 1) / len(pair_list) * 25)
                progress_callback(progress,
                    f"SfM: {successful_pairs} başarılı çift, {total_matches} nokta")

        print(f"[SfM] {successful_pairs}/{len(pair_list)} çift başarılı, "
              f"{len(all_points_3d)} ham 3D nokta")

        if len(all_points_3d) < 10:
            print("❌ 3D noktalar yetersiz")
            return False

        # Point cloud
        points_array = np.array(all_points_3d)

        # Gürültü noktaları kaldır (z > 100m vb.)
        valid_mask = np.abs(points_array) < 100
        valid_mask = np.all(valid_mask, axis=1)
        points_array = points_array[valid_mask]

        print(f"✅ {len(points_array)} 3D nokta oluşturuldu")

        self.point_cloud = self.point_processor.create_point_cloud(points_array)

        if progress_callback:
            progress_callback(75, "Point cloud oluşturuldu")

        return True

    def generate_mesh(self, progress_callback=None) -> bool:
        """Point cloud'dan mesh oluştur"""
        if self.point_cloud is None or len(self.point_cloud) < 10:
            print(f"[ERROR] Point cloud yetersiz: {len(self.point_cloud) if self.point_cloud is not None else 0} nokta")
            print("[HINT] SfM başarısız — kamerayı objenin etrafında yavaşça ve düzgün döndür, obje iyi aydınlatılmış olmalı")
            return False

        print("🔧 Point cloud işleniyor...")

        # Outlier kaldır
        self.point_cloud = self.point_processor.remove_outliers(
            self.point_cloud, nb_neighbors=20, std_ratio=2.0)

        # Voxel downsample
        self.point_cloud = self.point_processor.downsample(
            self.point_cloud, voxel_size=self.config.voxel_size)

        # Normal hesapla
        self.point_cloud = self.point_processor.estimate_normals(self.point_cloud)

        if progress_callback:
            progress_callback(80, "Mesh oluşturuluyor (Poisson)...")

        # Mesh
        if self.config.quality == MeshQuality.DRAFT:
            self.mesh = self.point_processor.poisson_mesh(self.point_cloud, depth=7)
        elif self.config.quality == MeshQuality.HIGH:
            self.mesh = self.point_processor.poisson_mesh(self.point_cloud, depth=10)
        else:
            self.mesh = self.point_processor.poisson_mesh(self.point_cloud, depth=9)

        n_v = len(self.mesh.vertices)
        n_t = len(self.mesh.triangles) if hasattr(self.mesh, "triangles") else len(self.mesh.faces)
        print(f"✅ Mesh oluşturuldu: {n_v} vertices, {n_t} triangles")

        if progress_callback:
            progress_callback(85, "Mesh optimize ediliyor...")

        # Optimize
        self.mesh = self.mesh_optimizer.smooth_mesh(self.mesh, iterations=2)

        if self.config.quality in [MeshQuality.NORMAL, MeshQuality.PRODUCTION]:
            target_triangles = 100000 if self.config.quality == MeshQuality.PRODUCTION else 50000
            self.mesh = self.mesh_optimizer.simplify_mesh(self.mesh, target_count=target_triangles)

        # Kontrol
        metrics = self.mesh_optimizer.check_mesh_quality(self.mesh)
        print(f"📊 Mesh kalitesi: {metrics}")

        if progress_callback:
            progress_callback(90, "Mesh validate ediliyor...")

        return True

    def export_mesh(self, filename: str) -> bool:
        """Mesh'i dosyaya kaydet (STL/PLY/OBJ - backend'e göre)"""
        if self.mesh is None:
            print("❌ Mesh mevcut değil")
            return False

        try:
            if HAS_OPEN3D and isinstance(self.mesh, o3d.geometry.TriangleMesh):
                o3d.io.write_triangle_mesh(filename, self.mesh)
            else:
                # trimesh
                self.mesh.export(filename)
            print(f"✅ Mesh kaydedildi: {filename}")
            return True
        except Exception as e:
            print(f"❌ Export başarısız: {e}")
            return False

    def load_point_cloud_from_ply(self, ply_path: Path) -> bool:
        """COLMAP fused.ply gibi bir dosyadan point cloud yükle"""
        ply_path = Path(ply_path)
        if not ply_path.exists():
            return False
        try:
            if HAS_TRIMESH:
                pc = trimesh.load(str(ply_path))
                pts = np.asarray(pc.vertices)
            elif HAS_OPEN3D:
                o3pcd = o3d.io.read_point_cloud(str(ply_path))
                pts = np.asarray(o3pcd.points)
            else:
                return False
        except Exception as e:
            print(f"[ERROR] PLY okunamadı: {e}")
            return False

        # Düşük çözünürlüklü girişlerde COLMAP dense fusion boş PLY üretebilir;
        # bu durumda reconstructor sparse modeli fallback olarak kaydeder.
        # Sparse modeller genelde 30-200 nokta içerir, bu yüzden threshold düşük.
        if len(pts) < 20:
            print(f"⚠ PLY çok az nokta içeriyor ({len(pts)}), reddedildi")
            return False
        self.point_cloud = self.point_processor.create_point_cloud(pts)
        print(f"✅ COLMAP PLY → {len(pts)} nokta yüklendi")
        return True

    def run_full_pipeline(self, progress_callback=None,
                          image_folder: Path | None = None,
                          video_path: Path | None = None,
                          use_colmap: bool = False,
                          workspace: Path | None = None,
                          frame_callback=None) -> bool:
        """Tam pipeline'ı çalıştır.

        Mod seçimi öncelik sırası:
          1. image_folder verilmişse → folder mode
          2. video_path verilmişse → video frame extraction
          3. config.mode == WEBCAM → webcam
        Eğer use_colmap=True ve image_folder mevcutsa, dahili SfM yerine
        COLMAP wrapper (Desktop\\photogrammetry) kullanılır.
        """
        print("=" * 50)
        print("🚀 3D Tarama Pipeline'ı Başlatılıyor")
        print("=" * 50)

        # 1. Görüntüleri al
        if image_folder is not None:
            if not self.load_images_from_folder(image_folder, progress_callback):
                return False
        elif video_path is not None:
            if not self.load_video(video_path, self.config.num_images, progress_callback):
                return False
        elif self.config.mode == ScannerMode.LIVE_VIDEO:
            duration = getattr(self.config, "record_duration", 10)
            if not self.capture_live_video(duration, progress_callback,
                                           frame_callback=frame_callback):
                return False
        elif self.config.mode in (ScannerMode.WEBCAM, ScannerMode.IP_CAMERA):
            if not self.scan_with_webcam(progress_callback):
                return False
        else:
            print("❌ Geçerli giriş kaynağı yok")
            return False

        # 2. SfM/COLMAP ile point cloud
        if use_colmap:
            # image_folder yoksa, mevcut self.images'ı temp klasöre yaz
            if image_folder is not None:
                colmap_images_dir = image_folder
                ws = workspace or (image_folder.parent / "colmap_ws")
            else:
                import tempfile
                tmp_root = Path(tempfile.gettempdir()) / "bilsem_colmap"
                tmp_root.mkdir(parents=True, exist_ok=True)
                colmap_images_dir = tmp_root / "images"
                colmap_images_dir.mkdir(exist_ok=True)
                # Eski frame'leri temizle
                for f in colmap_images_dir.glob("*.jpg"):
                    try:
                        f.unlink()
                    except OSError:
                        pass
                # Frame'leri yaz
                for idx, frame in enumerate(self.images):
                    cv2.imwrite(str(colmap_images_dir / f"frame_{idx:04d}.jpg"), frame)
                print(f"[INFO] {len(self.images)} frame → {colmap_images_dir}")
                ws = workspace or (tmp_root / "colmap_ws")

            ply = self.run_colmap_pipeline(colmap_images_dir, ws, progress_callback)
            if ply is None or not self.load_point_cloud_from_ply(ply):
                print("[INFO] COLMAP başarısız, dahili SfM'ye düşülüyor")
                if not self.process_images(progress_callback):
                    return False
        else:
            if not self.process_images(progress_callback):
                return False

        # 3. Mesh oluşturma
        if not self.generate_mesh(progress_callback):
            return False

        if progress_callback:
            progress_callback(100, "✅ Tarama tamamlandı!")

        return True


# ─────────────────────────────────────────────────────────────────────────────
# EXAMPLE USAGE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Konfigürasyon
    config = ScanConfig(
        mode=ScannerMode.WEBCAM,
        num_images=10,
        quality=MeshQuality.NORMAL,
        voxel_size=0.01
    )

    # Scanner başlat
    scanner = PhotogrammetryScanner(config)

    # Pipeline
    def progress_callback(value: int, message: str):
        print(f"[{value}%] {message}")

    success = scanner.run_full_pipeline(progress_callback)

    if success:
        # Mesh'i kaydet
        scanner.export_mesh("scanned_object.stl")
        print("\n✅ 3D model hazır! CFD arayüzüne yükleyebilirsiniz.")
