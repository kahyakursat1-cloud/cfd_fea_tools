"""
bilsem_beyin Launcher
=====================
Tüm CFD/FEA/Scanner araçlarına tek noktadan erişim sağlayan
PySide6 tabanlı uygulama başlatıcı.

Kullanım:
    python launcher.py
    veya
    launcher.bat (çift tıkla)
"""

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# ────────────────────────────────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent
PY = sys.executable  # current Python interpreter

# Renkler (CFD arayüzüyle uyumlu)
BG = "#0a1628"
PANEL = "#0f2340"
TEAL = "#06d6d0"
NAVY = "#118ab2"
GREEN = "#00d084"
TEXT = "#e0f7fa"
SUBTEXT = "#80deea"


# ────────────────────────────────────────────────────────────────────────────
# LAUNCH ACTIONS
# ────────────────────────────────────────────────────────────────────────────

def _run_python(script: str, *args: str) -> None:
    """Belirtilen Python script'ini ayrı bir process olarak başlat."""
    script_path = ROOT / script
    if not script_path.exists():
        QMessageBox.critical(None, "Hata", f"Dosya bulunamadı:\n{script_path}")
        return
    try:
        subprocess.Popen([PY, str(script_path), *args], cwd=str(ROOT))
    except Exception as e:
        QMessageBox.critical(None, "Başlatılamadı", str(e))


def launch_full_app():
    _run_python("app_parametric.py")


def launch_scanner_only():
    _run_python("scanner_gui_module.py")


def launch_material_editor():
    _run_python("material_editor_gui.py")


def launch_integration_test():
    _run_python("test_integration.py")


def launch_material_test():
    _run_python("test_material_system.py")


def launch_verify_system():
    _run_python("verify_system.py")


def open_docs_folder():
    """README/INDEX dosyalarının olduğu klasörü dosya yöneticisinde aç."""
    try:
        import os
        os.startfile(str(ROOT))  # Windows
    except Exception as e:
        QMessageBox.critical(None, "Açılamadı", str(e))


# ────────────────────────────────────────────────────────────────────────────
# UI
# ────────────────────────────────────────────────────────────────────────────

class LauncherButton(QPushButton):
    """Büyük, ikon + başlık + açıklama içeren launcher butonu."""

    def __init__(self, icon: str, title: str, description: str, color: str = TEAL):
        super().__init__()
        self.setMinimumHeight(85)
        self.setCursor(Qt.PointingHandCursor)
        self.setText(f"{icon}   {title}\n{description}")
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {PANEL};
                color: {TEXT};
                border: 2px solid {color};
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                text-align: left;
                padding: 12px 18px;
            }}
            QPushButton:hover {{
                background-color: {color};
                color: #000000;
            }}
            QPushButton:pressed {{
                background-color: {NAVY};
            }}
        """)


class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("bilsem_beyin — Launcher")
        self.setMinimumSize(QSize(680, 620))
        self.setStyleSheet(f"background-color: {BG};")

        root = QVBoxLayout()
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        # ─── Header ───
        title = QLabel("🛩️  bilsem_beyin CFD / FEA / Scanner")
        title.setStyleSheet(f"color: {TEAL}; font-size: 22px; font-weight: bold;")
        root.addWidget(title)

        subtitle = QLabel("TEKNOFEST araçları — Tek tıkla başlat")
        subtitle.setStyleSheet(f"color: {SUBTEXT}; font-size: 12px;")
        root.addWidget(subtitle)

        # Sistem durumu
        root.addWidget(self._build_status_bar())

        # ─── Ana uygulamalar ───
        root.addWidget(self._section_label("📊 Ana Uygulamalar"))
        grid_main = QGridLayout()
        grid_main.setSpacing(10)

        b_full = LauncherButton(
            "🚀", "Tam Parametrik Analiz Arayüzü",
            "CFD + FEA + Scanner + Material Editor (tüm sekmeler)", GREEN)
        b_full.clicked.connect(launch_full_app)
        grid_main.addWidget(b_full, 0, 0, 1, 2)

        b_scanner = LauncherButton(
            "📸", "3D Photogrammetry Scanner",
            "Webcam / Video / Klasör + COLMAP entegrasyonu", TEAL)
        b_scanner.clicked.connect(launch_scanner_only)
        grid_main.addWidget(b_scanner, 1, 0)

        b_mat = LauncherButton(
            "🧪", "Malzeme Editörü",
            "10+ malzeme veritabanı yönetimi", TEAL)
        b_mat.clicked.connect(launch_material_editor)
        grid_main.addWidget(b_mat, 1, 1)

        root.addLayout(grid_main)

        # ─── Test ve doğrulama ───
        root.addWidget(self._section_label("🔬 Test ve Doğrulama"))
        grid_test = QGridLayout()
        grid_test.setSpacing(10)

        b_int = LauncherButton(
            "✅", "End-to-End Entegrasyon Testi",
            "GMSH → OpenFOAM → CalculiX tam pipeline", NAVY)
        b_int.clicked.connect(launch_integration_test)
        grid_test.addWidget(b_int, 0, 0)

        b_mtest = LauncherButton(
            "📋", "Malzeme Sistemi Testi",
            "MaterialDatabase doğrulama", NAVY)
        b_mtest.clicked.connect(launch_material_test)
        grid_test.addWidget(b_mtest, 0, 1)

        b_ver = LauncherButton(
            "🩺", "Sistem Sağlık Kontrolü",
            "Bağımlılıklar ve harici tool'lar", NAVY)
        b_ver.clicked.connect(launch_verify_system)
        grid_test.addWidget(b_ver, 1, 0)

        b_docs = LauncherButton(
            "📁", "Proje Klasörü",
            "Dosya yöneticisinde aç (rehberler, log'lar)", NAVY)
        b_docs.clicked.connect(open_docs_folder)
        grid_test.addWidget(b_docs, 1, 1)

        root.addLayout(grid_test)

        root.addStretch()

        # ─── Footer ───
        footer = QLabel(
            f"Python: {sys.version.split()[0]}  •  Klasör: {ROOT.name}"
        )
        footer.setStyleSheet(f"color: {SUBTEXT}; font-size: 10px;")
        footer.setAlignment(Qt.AlignCenter)
        root.addWidget(footer)

        self.setLayout(root)

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {TEAL}; font-size: 14px; font-weight: bold; "
            f"padding-top: 8px; padding-bottom: 4px;"
        )
        return lbl

    def _build_status_bar(self) -> QFrame:
        """Bağımlılık durumlarını gösteren küçük çubuk."""
        frame = QFrame()
        frame.setStyleSheet(
            f"background-color: {PANEL}; border: 1px solid {NAVY}; "
            f"border-radius: 6px; padding: 8px;"
        )
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 6, 10, 6)

        has_open3d = self._has("open3d")
        has_pymeshlab = self._has("pymeshlab")
        has_trimesh = self._has("trimesh")
        # Mesh backend gösterimi: en iyi mevcut backend
        if has_open3d:
            mesh_label, mesh_ok = "open3d", True
        elif has_pymeshlab:
            mesh_label, mesh_ok = "pymeshlab", True
        elif has_trimesh:
            mesh_label, mesh_ok = "trimesh", True
        else:
            mesh_label, mesh_ok = "mesh-backend", False

        checks = [
            ("PySide6", self._has("PySide6")),
            ("OpenCV", self._has("cv2")),
            ("numpy", self._has("numpy")),
            (mesh_label, mesh_ok),
            ("GMSH", self._has_exe("gmsh")),
            ("OpenFOAM", Path(r"C:\Program Files\blueCFD-Core-2024\setvars_OF12.bat").exists()),
            ("CalculiX", Path(r"C:\AnalysisTools\CalculiX\CL32-win32\bin\ccx\ccx213.exe").exists()),
            ("COLMAP", Path(r"C:\Users\Victus\Desktop\photogrammetry").exists()),
        ]
        for name, ok in checks:
            color = GREEN if ok else "#ff6b6b"
            mark = "✓" if ok else "✗"
            lbl = QLabel(f"{mark} {name}")
            lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            layout.addWidget(lbl)
        layout.addStretch()
        frame.setLayout(layout)
        return frame

    @staticmethod
    def _has(module: str) -> bool:
        import importlib.util
        return importlib.util.find_spec(module) is not None

    @staticmethod
    def _has_exe(name: str) -> bool:
        import shutil
        return shutil.which(name) is not None


# ────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Koyu palet
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(PANEL))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(PANEL))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    app.setPalette(palette)

    window = LauncherWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
