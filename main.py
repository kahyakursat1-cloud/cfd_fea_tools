"""
CFD/FEA ANALYSIS TOOLS — OpenFOAM & CalculiX Arayüzü
TEKNOFEST 2026 — Çelik Kubbe, Model Roket, İHA Aerodinamik Simülasyonları
Futuristic Teal & Navy UI Theme
"""

import sys
import os
import json
import subprocess
import yaml
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QFrame, QTabWidget, QListWidget, QListWidgetItem,
    QProgressBar, QGroupBox, QFormLayout, QTextEdit, QFileDialog, QMessageBox,
    QGridLayout, QHeaderView
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize, QRect
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QLinearGradient,
    QIcon, QPalette
)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG & LOGGING
# ─────────────────────────────────────────────────────────────────────────────

try:
    with open("config.yaml", "r", encoding="utf-8") as f:
        CONFIG = yaml.safe_load(f)
except Exception:
    CONFIG = {
        "openfoam": {"enabled": True, "version": "11"},
        "calculix": {"enabled": True, "version": "2.21"}
    }

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger("CFD/FEA Tools")

# ─────────────────────────────────────────────────────────────────────────────
# COLOR PALETTE
# ─────────────────────────────────────────────────────────────────────────────

BG_MAIN    = "#0a1628"
BG_PANEL   = "rgba(10, 22, 40, 0.8)"
BG_WIDGET  = "rgba(15, 35, 60, 0.9)"
TEAL       = "#06d6d0"
TEAL_DIM   = "#0a8a84"
TEAL_GLOW  = "#7ff7f1"
NAVY       = "#118ab2"
NAVY_DIM   = "#0a5a7a"
GREEN      = "#00d084"
RED        = "#ff4757"
YELLOW     = "#ffa502"
TEXT_MAIN  = "#e0f7fa"
TEXT_DIM   = "#80deea"
BORDER     = "rgba(6, 214, 208, 0.3)"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG_MAIN};
    color: {TEXT_MAIN};
    font-family: 'Consolas', 'Courier New', monospace;
}}
QFrame#panel {{
    background-color: {BG_PANEL};
    border: 2px solid {BORDER};
    border-radius: 8px;
}}
QLabel#title {{
    color: {TEAL_GLOW};
    font-size: 18px;
    font-weight: bold;
    letter-spacing: 2px;
}}
QLabel#subtitle {{
    color: {TEXT_DIM};
    font-size: 12px;
}}
QPushButton {{
    background-color: {NAVY};
    color: {TEXT_MAIN};
    border: 1px solid {TEAL};
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {TEAL_DIM};
    border: 2px solid {TEAL_GLOW};
}}
QPushButton:pressed {{
    background-color: {NAVY_DIM};
}}
QPushButton#run {{
    background-color: {GREEN};
    color: #000;
}}
QPushButton#run:hover {{
    background-color: #00b86a;
}}
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {BG_WIDGET};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
}}
QTabBar::tab {{
    background-color: {BG_WIDGET};
    color: {TEXT_DIM};
    padding: 6px 12px;
    border: 1px solid {BORDER};
}}
QTabBar::tab:selected {{
    background-color: {NAVY};
    color: {TEAL_GLOW};
    border-bottom: 2px solid {TEAL};
}}
QTableWidget {{
    background-color: {BG_WIDGET};
    gridline-color: {BORDER};
}}
QTableWidget::item {{
    padding: 4px;
}}
QHeaderView::section {{
    background-color: {NAVY_DIM};
    color: {TEAL_GLOW};
    padding: 4px;
    border: none;
}}
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    background-color: {BG_WIDGET};
}}
QProgressBar::chunk {{
    background-color: {TEAL};
}}
QTextEdit {{
    background-color: {BG_WIDGET};
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
}}
"""

# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION WORKER (THREADING)
# ─────────────────────────────────────────────────────────────────────────────

class SimulationWorker(QThread):
    """Uzun süren simülasyonları ayrı thread'te çalıştır"""
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, tool, scenario, config_dict):
        super().__init__()
        self.tool = tool
        self.scenario = scenario
        self.config_dict = config_dict
        self.is_running = True
        self.result_forces = {}
        self._proc = None

    def run(self):
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from solvers.openfoam_wrapper import OpenFOAMRunner

        try:
            self.status.emit(f"[INFO] {self.tool.upper()} simülasyonu başladı: {self.scenario}")

            case_name = self.scenario.replace(" ", "_").lower()
            case_dir = Path("cases") / case_name
            max_iter = int(self.config_dict.get("max_iter", 200))
            wind_speed = float(self.config_dict.get("wind_speed", 15.0))

            runner = OpenFOAMRunner(case_dir, solver="simpleFoam")

            self.status.emit(f"[INFO] Case yapısı oluşturuluyor: {case_dir}")
            ok = runner.create_case_structure(
                mesh_file=None,
                params={"wind_speed": wind_speed, "n_iterations": max_iter},
            )
            if not ok:
                self.finished.emit(False, "❌ Case yapısı oluşturulamadı")
                return
            self.progress.emit(10)

            if runner.check_openfoam_installation():
                ok = self._run_with_progress(runner, max_iter)
            else:
                self.status.emit("[WARNING] OpenFOAM bulunamadı — mock simülasyon")
                ok = runner._run_mock_simulation()
                self.progress.emit(100)

            if not self.is_running:
                return

            if ok:
                self.result_forces = runner.extract_forces()
                self.finished.emit(True, "✅ Simülasyon tamamlandı")
            else:
                self.finished.emit(False, "❌ Simülasyon başarısız")

        except Exception as e:
            self.finished.emit(False, f"❌ Hata: {str(e)}")

    def _run_with_progress(self, runner, max_iter: int) -> bool:
        """Solver'ı Popen ile başlat, stdout'tan Time= satırlarını okuyarak progress yayınla."""
        wrapper_bat = runner.case_dir / "_run_foam_ui.bat"
        case_drive = str(runner.case_dir)[:2]
        wrapper_bat.write_text(
            "@echo off\r\n"
            f'set "FOAM_CASE_DIR={runner.case_dir}"\r\n'
            f'call "{runner.SETVARS_BAT}"\r\n'
            f"{case_drive}\r\n"
            'cd /d "%FOAM_CASE_DIR%"\r\n'
            "foamRun -solver incompressibleFluid\r\n"
            "exit /b %ERRORLEVEL%\r\n",
            encoding="ascii",
        )

        self._proc = subprocess.Popen(
            [str(wrapper_bat)],
            cwd=str(runner.case_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )

        lines = []
        for line in self._proc.stdout:
            if not self.is_running:
                self._proc.terminate()
                wrapper_bat.unlink(missing_ok=True)
                self.finished.emit(False, "Kullanıcı durdurdu")
                return False
            lines.append(line)
            stripped = line.rstrip()
            if stripped:
                self.status.emit(stripped)
            if line.startswith("Time = "):
                try:
                    t = float(line.split("=")[1].strip())
                    self.progress.emit(min(99, 10 + int(89 * t / max_iter)))
                except ValueError:
                    pass

        self._proc.wait()
        wrapper_bat.unlink(missing_ok=True)

        with open(runner.log_file, "w", encoding="utf-8") as f:
            f.writelines(lines)

        if self._proc.returncode == 0:
            self.progress.emit(100)
            return True
        return False

    def stop(self):
        self.is_running = False
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

# ─────────────────────────────────────────────────────────────────────────────
# MAIN APPLICATION
# ─────────────────────────────────────────────────────────────────────────────

class CFDFEAToolsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CFD/FEA Analysis Tools — TEKNOFEST 2026")
        self.setGeometry(100, 100, 1400, 900)
        self.setStyleSheet(STYLESHEET)

        self.worker = None
        self.scenario_configs = CONFIG.get("scenarios", {})

        # Main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        layout = QHBoxLayout()

        # Left panel — Scenario Selection
        left_panel = self._create_left_panel()

        # Right panel — Simulation Control & Monitoring
        right_panel = self._create_right_panel()

        layout.addWidget(left_panel, 1)
        layout.addWidget(right_panel, 2)

        main_widget.setLayout(layout)

    def _create_left_panel(self):
        """Sol panel: Senaryo seçimi ve parametre ayarları"""
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout()

        # Title
        title = QLabel("📊 Simülasyon Seçimi")
        title.setObjectName("title")
        layout.addWidget(title)

        # Scenario selection
        layout.addWidget(QLabel("Senaryo:"))
        self.scenario_combo = QComboBox()
        self.scenario_combo.addItems(self.scenario_configs.keys())
        self.scenario_combo.currentTextChanged.connect(self._on_scenario_changed)
        layout.addWidget(self.scenario_combo)

        # Tool selection
        layout.addWidget(QLabel("Araç:"))
        self.tool_combo = QComboBox()
        self.tool_combo.addItems(["OpenFOAM", "CalculiX", "Her İkisi"])
        layout.addWidget(self.tool_combo)

        # Scenario info
        layout.addWidget(QLabel("Açıklama:"))
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(120)
        layout.addWidget(self.info_text)

        # Parameters
        layout.addWidget(QLabel("Parametreler:"))

        self.params = {}

        # Grid layout for parameters
        param_grid = QGridLayout()
        param_grid.addWidget(QLabel("Mesh Boyutu (mm):"), 0, 0)
        self.params["mesh_size"] = QDoubleSpinBox()
        self.params["mesh_size"].setValue(10.0)
        self.params["mesh_size"].setMinimum(0.5)
        self.params["mesh_size"].setMaximum(100.0)
        param_grid.addWidget(self.params["mesh_size"], 0, 1)

        param_grid.addWidget(QLabel("Zaman Adımı (ms):"), 1, 0)
        self.params["timestep"] = QDoubleSpinBox()
        self.params["timestep"].setValue(1.0)
        param_grid.addWidget(self.params["timestep"], 1, 1)

        param_grid.addWidget(QLabel("Max Iterasyon:"), 2, 0)
        self.params["max_iter"] = QSpinBox()
        self.params["max_iter"].setValue(1000)
        self.params["max_iter"].setMaximum(100000)
        param_grid.addWidget(self.params["max_iter"], 2, 1)

        layout.addLayout(param_grid)

        layout.addStretch()

        frame.setLayout(layout)
        return frame

    def _create_right_panel(self):
        """Sağ panel: Simülasyon kontrolü ve izleme"""
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout()

        # Title
        title = QLabel("⚙️ Simülasyon Kontrolü")
        title.setObjectName("title")
        layout.addWidget(title)

        # Tab widget for different views
        tabs = QTabWidget()

        # Tab 1: Control
        control_tab = QWidget()
        control_layout = QVBoxLayout()

        button_group = QHBoxLayout()

        self.run_btn = QPushButton("▶️ BAŞLAT")
        self.run_btn.setObjectName("run")
        self.run_btn.clicked.connect(self._start_simulation)
        button_group.addWidget(self.run_btn)

        self.stop_btn = QPushButton("⏹️ DURDUR")
        self.stop_btn.clicked.connect(self._stop_simulation)
        self.stop_btn.setEnabled(False)
        button_group.addWidget(self.stop_btn)

        self.reset_btn = QPushButton("🔄 SIFIRLA")
        self.reset_btn.clicked.connect(self._reset_simulation)
        button_group.addWidget(self.reset_btn)

        control_layout.addLayout(button_group)

        # Progress bar
        control_layout.addWidget(QLabel("İlerleme:"))
        self.progress_bar = QProgressBar()
        control_layout.addWidget(self.progress_bar)

        # Status
        control_layout.addWidget(QLabel("Durum:"))
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(150)
        control_layout.addWidget(self.status_text)

        # Result table
        control_layout.addWidget(QLabel("Çıktılar:"))
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(2)
        self.result_table.setHorizontalHeaderLabels(["Parametre", "Değer"])
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        control_layout.addWidget(self.result_table)

        control_tab.setLayout(control_layout)
        tabs.addTab(control_tab, "Kontrol")

        # Tab 2: Logger
        logger_tab = QWidget()
        logger_layout = QVBoxLayout()
        self.logger_text = QTextEdit()
        self.logger_text.setReadOnly(True)
        logger_layout.addWidget(self.logger_text)
        logger_tab.setLayout(logger_layout)
        tabs.addTab(logger_tab, "Log")

        # Tab 3: Settings
        settings_tab = QWidget()
        settings_layout = QVBoxLayout()

        settings_form = QFormLayout()

        self.openfoam_path = QLineEdit()
        self.openfoam_path.setText("/opt/openfoam11")
        settings_form.addRow("OpenFOAM Path:", self.openfoam_path)

        self.calculix_path = QLineEdit()
        self.calculix_path.setText("/opt/calculix")
        settings_form.addRow("CalculiX Path:", self.calculix_path)

        self.output_dir = QLineEdit()
        self.output_dir.setText("./results")
        settings_form.addRow("Çıktı Klasörü:", self.output_dir)

        settings_layout.addLayout(settings_form)
        settings_layout.addStretch()
        settings_tab.setLayout(settings_layout)
        tabs.addTab(settings_tab, "Ayarlar")

        layout.addWidget(tabs)

        frame.setLayout(layout)
        return frame

    def _on_scenario_changed(self):
        """Senaryo değiştiğinde info güncelle"""
        scenario = self.scenario_combo.currentText()
        if scenario in self.scenario_configs:
            config = self.scenario_configs[scenario]
            info = f"**{scenario}**\n\n"
            info += f"Araç: {config.get('tool', '?').upper()}\n"
            info += f"Açıklama: {config.get('description', '?')}\n"
            info += f"\nParametreler:\n"
            for key, value in config.items():
                if key not in ['tool', 'description']:
                    info += f"  • {key}: {value}\n"
            self.info_text.setText(info)

    def _start_simulation(self):
        """Simülasyon başlat"""
        scenario = self.scenario_combo.currentText()
        tool = self.tool_combo.currentText()

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_text.clear()

        # Worker thread
        self.worker = SimulationWorker(
            tool=tool.lower(),
            scenario=scenario,
            config_dict={
                "mesh_size": self.params["mesh_size"].value(),
                "timestep": self.params["timestep"].value(),
                "max_iter": self.params["max_iter"].value(),
            }
        )

        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self._update_status)
        self.worker.finished.connect(self._on_simulation_finished)

        self.worker.start()
        self.logger_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] ▶️ Simülasyon başlatıldı: {scenario}")

    def _stop_simulation(self):
        """Simülasyon durdur"""
        if self.worker:
            self.worker.stop()
            self.logger_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] ⏹️ Simülasyon durduruldu")

    def _reset_simulation(self):
        """Sıfırla"""
        self.progress_bar.setValue(0)
        self.status_text.clear()
        self.result_table.setRowCount(0)
        self.logger_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Sıfırlandı")

    def _update_status(self, message):
        """Status güncelle"""
        self.status_text.append(message)

    def _on_simulation_finished(self, success, message):
        """Simülasyon bittiğinde"""
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        self.logger_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

        if success:
            forces = getattr(self.worker, "result_forces", {})
            results = [
                ("Cd (Drag Katsayısı)", f"{forces.get('Cd', '—'):.4f}" if "Cd" in forces else "—"),
                ("Cl (Lift Katsayısı)", f"{forces.get('Cl', '—'):.4f}" if "Cl" in forces else "—"),
                ("Cm (Moment Katsayısı)", f"{forces.get('Cm', '—'):.4f}" if "Cm" in forces else "—"),
                ("Cd (Basınç)", f"{forces.get('Cd_pressure', '—'):.4f}" if "Cd_pressure" in forces else "—"),
                ("Cd (Viskoz)", f"{forces.get('Cd_viscous', '—'):.4f}" if "Cd_viscous" in forces else "—"),
            ]
            self.result_table.setRowCount(len(results))
            for i, (param, value) in enumerate(results):
                self.result_table.setItem(i, 0, QTableWidgetItem(param))
                self.result_table.setItem(i, 1, QTableWidgetItem(value))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CFDFEAToolsApp()
    window.show()
    sys.exit(app.exec())
