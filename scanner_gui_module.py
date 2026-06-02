"""
3D Scanner GUI Module
CFD/FEA arayüzüne entegre edilen tab
Photogrammetry scanning interface
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QDoubleSpinBox, QProgressBar, QTextEdit, QGroupBox, QFormLayout,
    QFileDialog, QMessageBox, QLineEdit
)
from PySide6.QtCore import QThread, Signal
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
import cv2
import numpy as np

from photogrammetry_scanner import (
    PhotogrammetryScanner, ScanConfig, ScannerMode, MeshQuality
)
from mesh_to_cfd import convert_mesh_to_aircraft, MeshAnalyzer

# ─────────────────────────────────────────────────────────────────────────────
# COLOR THEME (CFD arayüzü ile uyumlu)
# ─────────────────────────────────────────────────────────────────────────────

TEAL = "#06d6d0"
NAVY = "#118ab2"
GREEN = "#00d084"
BG_PANEL = "rgba(10, 22, 40, 0.85)"
BG_WIDGET = "rgba(15, 35, 60, 0.9)"

# ─────────────────────────────────────────────────────────────────────────────
# SCANNER WORKER THREAD
# ─────────────────────────────────────────────────────────────────────────────

class CameraPreviewThread(QThread):
    """Kamera görüntüsünü canlı olarak GUI'ye gönderir."""
    frame_ready = Signal(np.ndarray)

    def __init__(self, source=0):
        super().__init__()
        self.source = int(source) if str(source).lstrip("-").isdigit() else source
        self._running = False

    def run(self):
        import time
        self._running = True
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            self._running = False
            return
        while self._running:
            ret, frame = cap.read()
            if ret:
                self.frame_ready.emit(frame)
            time.sleep(0.033)  # ~30fps
        cap.release()

    def stop(self):
        self._running = False
        self.wait(3000)  # max 3s wait


class ScannerWorker(QThread):
    """Tarama işlemini ayrı thread'te çalıştır"""
    progress = Signal(int, str)
    finished = Signal(bool, str)
    preview_frame = Signal(np.ndarray)

    def __init__(self, config: ScanConfig, image_folder=None, video_path=None,
                 use_colmap: bool = False):
        super().__init__()
        self.config = config
        self.image_folder = image_folder
        self.video_path = video_path
        self.use_colmap = use_colmap
        self.scanner = PhotogrammetryScanner(config)
        self.is_running = True

    def run(self):
        """Pipeline çalıştır — tüm stdout'u log dosyasına da yönlendir"""
        import io, sys, tempfile
        from pathlib import Path as _P
        log_path = _P(tempfile.gettempdir()) / "bilsem_scanner.log"
        log_buf = io.StringIO()

        class _Tee:
            def __init__(self, *streams):
                self.streams = streams
            def write(self, s):
                for st in self.streams:
                    try:
                        st.write(s)
                    except Exception:
                        pass
            def flush(self):
                for st in self.streams:
                    try:
                        st.flush()
                    except Exception:
                        pass

        orig_stdout = sys.stdout
        orig_stderr = sys.stderr
        sys.stdout = _Tee(orig_stdout, log_buf)
        sys.stderr = _Tee(orig_stderr, log_buf)

        try:
            print(f"[WORKER] use_colmap={self.use_colmap}")
            print(f"[WORKER] mode={self.config.mode}")
            success = self.scanner.run_full_pipeline(
                progress_callback=self._progress_callback,
                image_folder=self.image_folder,
                video_path=self.video_path,
                use_colmap=self.use_colmap,
                frame_callback=self._frame_callback,
            )

            # Log'u dosyaya yaz
            try:
                log_path.write_text(log_buf.getvalue(), encoding="utf-8", errors="replace")
            except Exception:
                pass

            if success:
                self.finished.emit(True, f"✅ Tarama tamamlandı! Log: {log_path}")
            else:
                self.finished.emit(False, f"❌ Tarama başarısız. Log: {log_path}")

        except Exception as e:
            import traceback
            try:
                log_buf.write(traceback.format_exc())
                log_path.write_text(log_buf.getvalue(), encoding="utf-8", errors="replace")
            except Exception:
                pass
            self.finished.emit(False, f"❌ Hata: {str(e)}\nLog: {log_path}")
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr

    def _progress_callback(self, value: int, message: str):
        """Progress emit et"""
        self.progress.emit(value, message)

    def _frame_callback(self, frame: np.ndarray):
        """Canlı kayıt sırasında her frame'i GUI'ye yolla"""
        try:
            self.preview_frame.emit(frame)
        except Exception:
            pass

    def stop(self):
        """İptal et"""
        self.is_running = False
        self.wait()

    def get_scanner(self) -> PhotogrammetryScanner:
        """Scanner nesnesini al (mesh'e erişim için)"""
        return self.scanner


# ─────────────────────────────────────────────────────────────────────────────
# SCANNER GUI TAB
# ─────────────────────────────────────────────────────────────────────────────

class ScannerTab(QWidget):
    """3D Scanner tab'ı"""

    # Signal: Mesh oluşturuldu
    mesh_ready = Signal(str)  # STL dosya yolu

    def __init__(self):
        super().__init__()
        self.worker = None
        self.last_mesh_path = None
        self._preview_thread = None

        layout = QVBoxLayout()

        # ─── Title ───
        title = QLabel("📸 3D Photogrammetry Scanner")
        title.setStyleSheet("color: #7ff7f1; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # ─── Input Configuration ───
        layout.addWidget(self._create_config_group())

        # ─── Camera Preview ───
        layout.addWidget(self._create_preview_group())

        # ─── Control Buttons ───
        layout.addWidget(self._create_control_group())

        # ─── Progress ───
        layout.addWidget(self._create_progress_group())

        # ─── Output ───
        layout.addWidget(self._create_output_group())

        layout.addStretch()
        self.setLayout(layout)

    def _create_config_group(self) -> QGroupBox:
        """Konfigürasyon grubu"""
        group = QGroupBox("⚙️ Tarama Ayarları")
        group.setStyleSheet(f"QGroupBox {{ color: #e0f7fa; border: 1px solid {TEAL}; }}")

        form = QFormLayout()

        # Mode seçimi
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Canlı Video Kaydı - Dahili (index 0)",
            "Canlı Video Kaydı - USB Telefon (index 1)",
            "IP Kamera (WiFi)",
            "Video Dosyası",
            "Resim Klasörü",
        ])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("Tarama Modu:", self.mode_combo)

        # IP Kamera URL satırı (sadece IP mod seçilince görünür)
        self._ip_row_label = QLabel("Kamera URL:")
        ip_layout = QHBoxLayout()
        self.ip_url_input = QLineEdit()
        self.ip_url_input.setPlaceholderText("http://192.168.x.x:8080/video")
        self.ip_url_input.setText("http://192.168.1.1:8080/video")
        self.ip_test_btn = QPushButton("Test")
        self.ip_test_btn.setFixedWidth(55)
        self.ip_test_btn.setStyleSheet(f"background-color: {NAVY}; color: white; border-radius:4px;")
        self.ip_test_btn.clicked.connect(self._test_ip_camera)
        ip_layout.addWidget(self.ip_url_input)
        ip_layout.addWidget(self.ip_test_btn)
        self._ip_row_widget = QWidget()
        self._ip_row_widget.setLayout(ip_layout)
        form.addRow(self._ip_row_label, self._ip_row_widget)
        # Başta gizle
        self._ip_row_label.hide()
        self._ip_row_widget.hide()

        # Görüntü sayısı
        self.num_images = QSpinBox()
        self.num_images.setValue(30)
        self.num_images.setRange(2, 200)
        self.num_images.setSuffix(" görüntü")
        form.addRow("Görüntü Sayısı:", self.num_images)

        # Kayıt süresi (canlı video modu için)
        self.record_duration = QSpinBox()
        self.record_duration.setValue(10)
        self.record_duration.setRange(3, 120)
        self.record_duration.setSuffix(" saniye")
        form.addRow("Kayıt Süresi:", self.record_duration)

        # Mesh kalitesi
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Draft (Hızlı)", "Normal (Dengeli)", "High (Detaylı)", "Production (CFD)"])
        form.addRow("Mesh Kalitesi:", self.quality_combo)

        # Voxel boyutu
        self.voxel_size = QDoubleSpinBox()
        self.voxel_size.setValue(0.01)
        self.voxel_size.setRange(0.001, 0.1)
        self.voxel_size.setSingleStep(0.001)
        self.voxel_size.setSuffix(" m")
        form.addRow("Point Cloud Voxel Boyutu:", self.voxel_size)

        # Outlier threshold
        self.outlier_threshold = QDoubleSpinBox()
        self.outlier_threshold.setValue(2.0)
        self.outlier_threshold.setRange(0.5, 5.0)
        self.outlier_threshold.setSingleStep(0.1)
        form.addRow("Gürültü Eşiği (σ):", self.outlier_threshold)

        group.setLayout(form)
        return group

    def _create_preview_group(self) -> QGroupBox:
        """Kamera preview grubu"""
        group = QGroupBox("👁️ Kamera İzlemesi")
        group.setStyleSheet(f"QGroupBox {{ color: #e0f7fa; border: 1px solid {TEAL}; }}")

        layout = QVBoxLayout()

        # Video label
        self.preview_label = QLabel("Kamera başlatılmadı")
        self.preview_label.setMinimumHeight(300)
        self.preview_label.setStyleSheet(f"background-color: #0a1628; color: #80deea;")
        layout.addWidget(self.preview_label)

        # Preview toggle
        self.test_preview_btn = QPushButton("▶ Kamera Önizleme")
        self.test_preview_btn.setStyleSheet(
            f"background-color: #0f2340; color: #06d6d0; border: 1px solid #06d6d0; border-radius:4px; padding:6px;")
        self.test_preview_btn.setCheckable(True)
        self.test_preview_btn.clicked.connect(self._toggle_preview)
        layout.addWidget(self.test_preview_btn)

        group.setLayout(layout)
        return group

    def _create_control_group(self) -> QGroupBox:
        """Kontrol butonları"""
        group = QGroupBox("🎮 Kontrol")
        group.setStyleSheet(f"QGroupBox {{ color: #e0f7fa; border: 1px solid {TEAL}; }}")

        layout = QHBoxLayout()

        self.start_btn = QPushButton("▶️ BAŞLAT")
        self.start_btn.setStyleSheet(f"background-color: {GREEN}; color: #000; font-weight: bold;")
        self.start_btn.clicked.connect(self._start_scan)
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹️ DURDUR")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_scan)
        layout.addWidget(self.stop_btn)

        self.reset_btn = QPushButton("🔄 SIFIRLA")
        self.reset_btn.clicked.connect(self._reset_scan)
        layout.addWidget(self.reset_btn)

        group.setLayout(layout)
        return group

    def _create_progress_group(self) -> QGroupBox:
        """İlerleme grubu"""
        group = QGroupBox("📊 İlerleme")
        group.setStyleSheet(f"QGroupBox {{ color: #e0f7fa; border: 1px solid {TEAL}; }}")

        layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {TEAL};
                border-radius: 4px;
                text-align: center;
                color: white;
            }}
            QProgressBar::chunk {{
                background-color: {TEAL};
            }}
        """)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Hazır")
        self.status_label.setStyleSheet("color: #80deea;")
        layout.addWidget(self.status_label)

        group.setLayout(layout)
        return group

    def _create_output_group(self) -> QGroupBox:
        """Çıktı grubu"""
        group = QGroupBox("💾 Çıktı")
        group.setStyleSheet(f"QGroupBox {{ color: #e0f7fa; border: 1px solid {TEAL}; }}")

        layout = QVBoxLayout()

        # Format seçimi
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Format:"))

        self.format_combo = QComboBox()
        self.format_combo.addItems(["STL", "OBJ", "PLY", "STEP"])
        format_layout.addWidget(self.format_combo)

        layout.addLayout(format_layout)

        # Kaydet
        self.export_btn = QPushButton("💾 Mesh'i Kaydet")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_mesh)
        layout.addWidget(self.export_btn)

        # CFD'ye yükle
        self.load_to_cfd_btn = QPushButton("🚀 CFD Arayüzüne Yükle")
        self.load_to_cfd_btn.setEnabled(False)
        self.load_to_cfd_btn.clicked.connect(self._load_to_cfd)
        layout.addWidget(self.load_to_cfd_btn)

        # Bilgi
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(150)
        layout.addWidget(self.info_text)

        group.setLayout(layout)
        return group

    # ─── Slot Methods ───

    def _toggle_preview(self, checked: bool):
        """Kamera önizlemeyi başlat / durdur."""
        if checked:
            self._start_preview()
            self.test_preview_btn.setText("⏹ Önizlemeyi Durdur")
        else:
            self._stop_preview()
            self.test_preview_btn.setText("▶ Kamera Önizleme")

    def _start_preview(self):
        """Seçili kaynaktan canlı preview başlat."""
        mode_idx = self.mode_combo.currentIndex()
        if mode_idx == 2:  # IP Kamera
            source = self.ip_url_input.text().strip()
        elif mode_idx == 1:
            source = 1
        else:
            source = 0

        self._stop_preview()  # öncekini durdur
        self._preview_thread = CameraPreviewThread(source)
        self._preview_thread.frame_ready.connect(self._update_preview)
        self._preview_thread.start()

    def _stop_preview(self):
        if self._preview_thread is not None:
            self._preview_thread.stop()
            self._preview_thread = None

    def _update_preview(self, frame: np.ndarray):
        """Frame'i QLabel'e yaz."""
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_img)
            scaled = pixmap.scaled(
                self.preview_label.width(),
                self.preview_label.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.preview_label.setPixmap(scaled)
        except Exception:
            pass

    def _on_mode_changed(self, index: int):
        """Mod değişince IP kamera URL satırını göster/gizle."""
        is_ip = (index == 2)  # "IP Kamera (WiFi)"
        self._ip_row_label.setVisible(is_ip)
        self._ip_row_widget.setVisible(is_ip)

    def _test_ip_camera(self):
        """IP kamera bağlantısını test et."""
        from photogrammetry_scanner import CameraCapture
        url = self.ip_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Uyarı", "URL boş olamaz.")
            return
        self.ip_test_btn.setEnabled(False)
        self.ip_test_btn.setText("...")
        ok = CameraCapture.test_ip_camera(url)
        self.ip_test_btn.setEnabled(True)
        self.ip_test_btn.setText("Test")
        if ok:
            QMessageBox.information(self, "Bağlantı Başarılı",
                                    f"✅ Kamera bağlandı:\n{url}")
        else:
            QMessageBox.critical(self, "Bağlantı Hatası",
                                 f"❌ Kameraya ulaşılamadı:\n{url}\n\n"
                                 "• Telefon ve bilgisayar aynı WiFi ağında mı?\n"
                                 "• IP Webcam uygulaması çalışıyor mu?\n"
                                 "• URL doğru mu? (ör. http://192.168.x.x:8080/video)")

    def _test_camera(self):
        """Kamera test et (seçili moda göre doğru source kullan)"""
        mode_idx = self.mode_combo.currentIndex()
        if mode_idx == 2:  # IP Kamera
            self._test_ip_camera()
            return
        elif mode_idx == 1:
            source = 1  # USB telefon
        else:
            source = 0  # Dahili

        cap = cv2.VideoCapture(source)

        if not cap.isOpened():
            QMessageBox.critical(self, "Hata", f"Kamera açılamadı! (index {source})")
            return

        ret, frame = cap.read()
        cap.release()

        if ret:
            # Frame'i Qt image'a dönüştür
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = 3 * w
            qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image).scaledToWidth(400)

            self.preview_label.setPixmap(pixmap)
            QMessageBox.information(self, "Başarı", "✅ Kamera çalışıyor!")
        else:
            QMessageBox.warning(self, "Hata", "Görüntü yakalanamadı")

    def _start_scan(self):
        """Taramayı başlat"""
        # Konfigürasyon
        quality_map = {
            0: MeshQuality.DRAFT,
            1: MeshQuality.NORMAL,
            2: MeshQuality.HIGH,
            3: MeshQuality.PRODUCTION
        }
        mode_idx = self.mode_combo.currentIndex()
        mode_map = {
            0: ScannerMode.LIVE_VIDEO,      # Dahili kamera canlı kayıt
            1: ScannerMode.LIVE_VIDEO,      # USB telefon canlı kayıt
            2: ScannerMode.IP_CAMERA,
            3: ScannerMode.VIDEO_SEQUENCE,
            4: ScannerMode.IMAGE_FOLDER,
        }
        scan_mode = mode_map.get(mode_idx, ScannerMode.LIVE_VIDEO)

        # Mod-spesifik kaynak seçimi
        image_folder = None
        video_path = None
        camera_source = "1" if mode_idx == 1 else "0"

        if scan_mode == ScannerMode.IP_CAMERA:
            camera_source = self.ip_url_input.text().strip()
            if not camera_source:
                QMessageBox.warning(self, "Uyarı", "IP Kamera URL'si boş.")
                return
        elif scan_mode == ScannerMode.IMAGE_FOLDER:
            folder = QFileDialog.getExistingDirectory(self, "Resim klasörü seç")
            if not folder:
                return
            image_folder = Path(folder)
        elif scan_mode == ScannerMode.VIDEO_SEQUENCE:
            vp, _ = QFileDialog.getOpenFileName(
                self, "Video dosyası seç", "",
                "Video (*.mp4 *.avi *.mov *.mkv)")
            if not vp:
                return
            video_path = Path(vp)

        config = ScanConfig(
            mode=scan_mode,
            num_images=self.num_images.value(),
            quality=quality_map[self.quality_combo.currentIndex()],
            voxel_size=self.voxel_size.value(),
            camera_source=camera_source,
            record_duration=self.record_duration.value(),
        )

        # COLMAP opsiyonel: photogrammetry kütüphanesi + colmap binary varsa
        # her modda kullan (live_video, video, image_folder).
        import shutil as _shutil
        photog_dir = Path(r"C:\Users\Victus\Desktop\photogrammetry")
        colmap_bin = _shutil.which("colmap")
        diag = []
        diag.append(f"photog_dir.exists: {photog_dir.exists()}")
        diag.append(f"shutil.which(colmap): {colmap_bin}")
        if colmap_bin is None and photog_dir.exists():
            # config.ini'den dene
            cfg = photog_dir / "config.ini"
            diag.append(f"config.ini.exists: {cfg.exists()}")
            if cfg.exists():
                import configparser
                cp = configparser.ConfigParser()
                try:
                    cp.read(cfg)
                    cand = cp.get("PATHS", "colmap_path", fallback="")
                    diag.append(f"config colmap_path: {cand!r}")
                    diag.append(f"config path exists: {Path(cand).exists() if cand else False}")
                    if cand and Path(cand).exists():
                        colmap_bin = cand
                except Exception as e:
                    diag.append(f"config read error: {e}")
        use_colmap = photog_dir.exists() and colmap_bin is not None
        diag.append(f"=> use_colmap = {use_colmap}")
        diag.append(f"=> colmap_bin = {colmap_bin}")
        diag_text = "\n".join(diag)
        print("[GUI COLMAP DETECTION]\n" + diag_text)

        # Kullanıcıya popup ile göster
        msg = QMessageBox(self)
        msg.setWindowTitle("COLMAP Durumu")
        if use_colmap:
            msg.setIcon(QMessageBox.Information)
            msg.setText(f"✅ COLMAP aktif\n\n{colmap_bin}\n\nTaramaya başlanacak.")
        else:
            msg.setIcon(QMessageBox.Warning)
            msg.setText("⚠ COLMAP DEVRE DIŞI\n\nDahili SfM kullanılacak (düz heightmap çıkar).\n\n"
                       + diag_text)
        msg.exec()

        # Worker
        self.worker = ScannerWorker(config, image_folder=image_folder,
                                    video_path=video_path, use_colmap=use_colmap)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        # Canlı video modunda worker frame yayınlar — ayrı thread açma!
        self.worker.preview_frame.connect(self._update_preview)

        # Eski preview thread varsa kapat (kamera çakışmasını önle)
        self._stop_preview()
        self.test_preview_btn.setChecked(False)
        self.test_preview_btn.setText("▶ Kamera Önizleme")

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.preview_label.setText("Kamera açılıyor…")

        self.worker.start()

    def _stop_scan(self):
        """Taramayı durdur"""
        if self.worker:
            self.worker.stop()
            self.status_label.setText("⏸️ Tarama durduruldu")

    def _reset_scan(self):
        """Sıfırla"""
        self.progress_bar.setValue(0)
        self.status_label.setText("Hazır")
        self.info_text.clear()
        self.export_btn.setEnabled(False)
        self.load_to_cfd_btn.setEnabled(False)

    def _on_progress(self, value: int, message: str):
        """İlerleme güncellemesi"""
        self.progress_bar.setValue(value)
        self.status_label.setText(f"[{value}%] {message}")

    def _on_finished(self, success: bool, message: str):
        """Tarama bitti"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText(message)
        # Tarama bitince önizlemeyi durdur
        self._stop_preview()
        self.test_preview_btn.setChecked(False)
        self.test_preview_btn.setText("▶ Kamera Önizleme")

        if success:
            scanner = self.worker.get_scanner()
            mesh = scanner.mesh

            # Support both open3d TriangleMesh and trimesh.Trimesh APIs
            try:
                n_vertices = len(mesh.vertices)
                # trimesh uses .faces, open3d uses .triangles
                if hasattr(mesh, 'faces'):
                    n_triangles = len(mesh.faces)
                else:
                    n_triangles = len(mesh.triangles)
                # watertight check
                if hasattr(mesh, 'is_watertight'):
                    watertight = mesh.is_watertight
                    if callable(watertight):
                        watertight = watertight()
                else:
                    watertight = False
                # edge manifold check
                if hasattr(mesh, 'is_winding_consistent'):
                    edge_ok = mesh.is_winding_consistent
                elif hasattr(mesh, 'is_edge_manifold'):
                    edge_ok = mesh.is_edge_manifold()
                else:
                    edge_ok = False
            except Exception:
                n_vertices = n_triangles = 0
                watertight = edge_ok = False

            info = f"""
✅ TARAMA BAŞARILI

Mesh İstatistikleri:
  • Köşe (Vertex): {n_vertices:,}
  • Üçgen (Triangle): {n_triangles:,}
  • Watertight: {'Evet' if watertight else 'Hayır'}
  • Winding Consistent: {'Evet' if edge_ok else 'Hayır'}

Sonraki Adım:
  1. Format seçin (STL/OBJ/STEP)
  2. "Mesh'i Kaydet" butonuna tıklayın
  3. Dosya CFD arayüzüne yüklenebilir
"""
            self.info_text.setText(info)
            self.export_btn.setEnabled(True)
            self.load_to_cfd_btn.setEnabled(True)

    def _export_mesh(self):
        """Mesh'i dosyaya kaydet"""
        if not self.worker:
            QMessageBox.warning(self, "Hata", "Tarama yapılmadı")
            return

        scanner = self.worker.get_scanner()
        mesh = scanner.mesh

        if mesh is None:
            QMessageBox.warning(self, "Hata", "Mesh mevcut değil")
            return

        format_ext = {
            0: ".stl",
            1: ".obj",
            2: ".ply",
            3: ".step"
        }

        ext = format_ext[self.format_combo.currentIndex()]

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Mesh'i Kaydet", f"scanned_object{ext}", f"*{ext}"
        )

        if file_path:
            scanner.export_mesh(file_path)
            self.last_mesh_path = file_path
            QMessageBox.information(self, "Başarı", f"✅ Kaydedildi:\n{file_path}")

    def _load_to_cfd(self):
        """CFD arayüzüne yükle ve otomatik dönüştür"""
        if not self.last_mesh_path:
            QMessageBox.warning(self, "Hata", "Önce mesh kaydedin")
            return

        try:
            # Mesh analizi yap
            analyzer = MeshAnalyzer(self.last_mesh_path)
            stats = analyzer.get_mesh_statistics()

            # Mesh'i Aircraft'e dönüştür
            aircraft, conversion_stats = convert_mesh_to_aircraft(
                self.last_mesh_path,
                aircraft_name=Path(self.last_mesh_path).stem
            )

            # Analiz bilgisini göster
            analysis_info = f"""
✅ MESH ANALİZİ TAMAMLANDI

BOYUTLAR:
  • Uzunluk: {stats['dimensions']['length']:.2f} mm
  • Genişlik: {stats['dimensions']['width']:.2f} mm
  • Yükseklik: {stats['dimensions']['height']:.2f} mm

TOPOLOJI:
  • Vertices: {stats['num_vertices']}
  • Üçgenler: {stats['num_triangles']}
  • Aspect Ratio: {stats['aspect_ratio']:.2f}

TAHMINLER:
  • Aircraft Tipi: {stats['estimated_type']}
  • Tahmini Kütle: {stats['estimated_mass_kg']:.2f} kg

CFD HAZIRLIĞI:
  ✅ Aircraft geometrisi oluşturuldu
  ✅ Parametreler otomatik tahmin edildi
  ✅ Simülasyona hazır
"""

            QMessageBox.information(self, "✅ Mesh Analizi Başarılı", analysis_info)

            # Signal gönder (mesh path → CFD tab'ında mesh yüklemesi için)
            self.mesh_ready.emit(self.last_mesh_path)

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"❌ Mesh dönüştürme hatası:\n{str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# PREVIEW WIDGET
# ─────────────────────────────────────────────────────────────────────────────

class MeshPreviewWidget(QWidget):
    """3D Mesh preview (basit)"""

    def __init__(self, mesh_path: str = None):
        super().__init__()
        self.mesh_path = mesh_path

    def display_mesh_info(self, mesh_path: str):
        """Mesh bilgisini göster (trimesh kullanır)"""
        try:
            import trimesh
            mesh = trimesh.load(mesh_path)
            n_v = len(mesh.vertices)
            n_f = len(mesh.faces)
            watertight = bool(getattr(mesh, "is_watertight", False))
            info = (
                f"Mesh Bilgisi\n\n"
                f"Dosya: {mesh_path}\n"
                f"Kose: {n_v:,}\n"
                f"Ucgen: {n_f:,}\n"
                f"Watertight: {'Evet' if watertight else 'Hayir'}\n\n"
                f"CFD Hazir Mi?\n"
                f"  Vertices < 1M: {'Evet' if n_v < 1_000_000 else 'Hayir'}\n"
                f"  Watertight: {'Evet' if watertight else 'Hayir'}\n"
            )
            return info
        except Exception as e:
            return f"Hata: {str(e)}"


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("Scanner Tab Test")
    window.setCentralWidget(ScannerTab())
    window.resize(1000, 800)

    window.show()
    sys.exit(app.exec())
