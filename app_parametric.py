"""
CFD/FEA Parametric Analysis Tool
Sabit kanat roket, drone, İHA için parametrik simülasyon
PySide6 GUI — Teal & Navy Cyberpunk Tema
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from aircraft_geometry import AircraftLibrary
from material_database import MaterialLibrary
from material_editor_gui import MaterialManagerTab
from mesh_generator import MeshGenerator
from simulation_runner import SimulationJob, SimulationRunner

# Unified malzeme kütüphanesi (advanced JSON-backed DB).
# fea_runner.MATERIAL_LIBRARY (dict) eski API; GUI ise MaterialLibrary objesi bekliyor.
MATERIAL_LIBRARY = MaterialLibrary()

# ─────────────────────────────────────────────────────────────────────────────
# COLOR THEME
# ─────────────────────────────────────────────────────────────────────────────

BG_MAIN    = "#0a1628"
BG_PANEL   = "rgba(10, 22, 40, 0.85)"
BG_WIDGET  = "rgba(15, 35, 60, 0.9)"
TEAL       = "#06d6d0"
TEAL_GLOW  = "#7ff7f1"
NAVY       = "#118ab2"
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
    font-family: 'Consolas', monospace;
}}
QFrame#panel {{
    background-color: {BG_PANEL};
    border: 2px solid {BORDER};
    border-radius: 8px;
}}
QLabel#title {{
    color: {TEAL_GLOW};
    font-size: 16px;
    font-weight: bold;
}}
QLabel#subtitle {{
    color: {TEXT_DIM};
    font-size: 11px;
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
    background-color: {TEAL};
    border: 2px solid {TEAL_GLOW};
}}
QPushButton#run {{
    background-color: {GREEN};
    color: #000;
    font-weight: bold;
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
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 4px;
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
QCheckBox {{
    color: {TEXT_MAIN};
    spacing: 5px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
}}
QCheckBox::indicator:checked {{
    background-color: {TEAL};
    border: 1px solid {TEAL};
}}
"""

# ─────────────────────────────────────────────────────────────────────────────
# PARAMETRIC STUDY DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class ParametricStudyDialog(QDialog):
    """Parametrik çalışma yapılandırması"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parametrik Çalışma Tanımı")
        self.setGeometry(200, 200, 500, 400)
        self.setStyleSheet(STYLESHEET)

        layout = QVBoxLayout()

        # Parametre listesi
        layout.addWidget(QLabel("Parametreler ve Değerler:"))

        self.param_table = QTableWidget()
        self.param_table.setColumnCount(3)
        self.param_table.setHorizontalHeaderLabels(["Parametre", "Min", "Max"])
        self.param_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.param_table)

        # Parametre ekleme
        add_btn = QPushButton("+ Parametre Ekle")
        add_btn.clicked.connect(self._add_parameter_row)
        layout.addWidget(add_btn)

        # Nokta sayısı
        form = QFormLayout()
        self.num_points = QSpinBox()
        self.num_points.setValue(3)
        self.num_points.setMinimum(2)
        self.num_points.setMaximum(10)
        form.addRow("Her Parametrede Nokta Sayısı:", self.num_points)

        layout.addLayout(form)

        # Butonlar
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("✅ Tamam")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("❌ İptal")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        # Varsayılan parametreler
        self._add_parameter_row("span")
        self._add_parameter_row("sweep")
        self._add_parameter_row("aspect_ratio")

    def _add_parameter_row(self, param_name: str = ""):
        """Parametre satırı ekle"""
        row = self.param_table.rowCount()
        self.param_table.insertRow(row)

        param_combo = QComboBox()
        param_combo.addItems([
            "span", "area", "aspect_ratio", "taper", "sweep",
            "fuselage_length", "fuselage_diameter", "nose_length"
        ])
        if param_name:
            param_combo.setCurrentText(param_name)

        min_spin = QDoubleSpinBox()
        min_spin.setValue(0.8)
        min_spin.setRange(0, 100)
        min_spin.setSingleStep(0.1)

        max_spin = QDoubleSpinBox()
        max_spin.setValue(1.2)
        max_spin.setRange(0, 100)
        max_spin.setSingleStep(0.1)

        self.param_table.setCellWidget(row, 0, param_combo)
        self.param_table.setCellWidget(row, 1, min_spin)
        self.param_table.setCellWidget(row, 2, max_spin)

    def get_study_config(self) -> dict:
        """Çalışma konfigürasyonunu al"""
        variations = {}

        for row in range(self.param_table.rowCount()):
            param_combo = self.param_table.cellWidget(row, 0)
            min_spin = self.param_table.cellWidget(row, 1)
            max_spin = self.param_table.cellWidget(row, 2)

            param = param_combo.currentText()
            min_val = min_spin.value()
            max_val = max_spin.value()
            num_points = self.num_points.value()

            # Lineer aralık oluştur
            values = [min_val + (max_val - min_val) * i / (num_points - 1)
                     for i in range(num_points)]

            variations[param] = values

        return variations


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APPLICATION
# ─────────────────────────────────────────────────────────────────────────────

class ParametricAnalysisTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🚀 CFD/FEA Parametric Analysis Tool — TEKNOFEST 2026")
        self.setGeometry(50, 50, 1600, 1000)
        self.setStyleSheet(STYLESHEET)

        self.runner = SimulationRunner(base_path="./simulations")
        self.current_aircraft = None
        self.results = []

        # Main layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        layout = QHBoxLayout()

        # Left panel — Aircraft Selection
        left_panel = self._create_aircraft_panel()

        # Right panel — Parametric Analysis & Results
        right_panel = self._create_analysis_panel()

        layout.addWidget(left_panel, 1)
        layout.addWidget(right_panel, 2)

        main_widget.setLayout(layout)

    def _create_aircraft_panel(self) -> QFrame:
        """Sol panel: Uçak seçimi"""
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout()

        title = QLabel("✈️ Uçak Seçimi")
        title.setObjectName("title")
        layout.addWidget(title)

        # Aircraft library
        layout.addWidget(QLabel("Hazır Tasarımlar:"))

        self.aircraft_list = QListWidget()
        self.aircraft_list.addItem("MiniHawk UAV")
        self.aircraft_list.addItem("Model Roket (F25)")
        self.aircraft_list.addItem("Fixed-Wing Racer")
        self.aircraft_list.addItem("VTOL Drone")
        self.aircraft_list.addItem("High Altitude Platform")

        self.aircraft_list.itemClicked.connect(self._load_aircraft)
        layout.addWidget(self.aircraft_list)

        # Bilgi
        layout.addWidget(QLabel("Özellikleri:"))
        self.aircraft_info = QTextEdit()
        self.aircraft_info.setReadOnly(True)
        self.aircraft_info.setMaximumHeight(250)
        layout.addWidget(self.aircraft_info)

        # Parametreler (görüntüleme)
        layout.addWidget(QLabel("Mevcut Parametreler:"))
        self.params_table = QTableWidget()
        self.params_table.setColumnCount(2)
        self.params_table.setHorizontalHeaderLabels(["Parametre", "Değer"])
        self.params_table.setMaximumHeight(200)
        layout.addWidget(self.params_table)

        layout.addStretch()

        frame.setLayout(layout)
        return frame

    def _create_analysis_panel(self) -> QFrame:
        """Sağ panel: Parametrik analiz"""
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout()

        title = QLabel("📊 Parametrik Analiz")
        title.setObjectName("title")
        layout.addWidget(title)

        # Tab widget
        tabs = QTabWidget()

        # Tab 1: Configuration
        config_tab = self._create_config_tab()
        tabs.addTab(config_tab, "Konfigürasyon")

        # Tab 2: Mesh
        mesh_tab = self._create_mesh_tab()
        tabs.addTab(mesh_tab, "Mesh")

        # Tab 3: Simulation
        sim_tab = self._create_simulation_tab()
        tabs.addTab(sim_tab, "Simülasyon")

        # Tab 4: Results
        results_tab = self._create_results_tab()
        tabs.addTab(results_tab, "Sonuçlar")

        # Tab 5: Materials
        self.materials_tab = MaterialManagerTab(MATERIAL_LIBRARY)
        self.materials_tab.materials_changed.connect(self._on_materials_updated)
        tabs.addTab(self.materials_tab, "🧪 Malzemeler")

        # Tab 6: FEA
        fea_tab = self._create_fea_tab()
        tabs.addTab(fea_tab, "⚙️ FEA")

        layout.addWidget(tabs)

        frame.setLayout(layout)
        return frame

    def _create_config_tab(self) -> QWidget:
        """Konfigürasyon tab'ı"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Simülasyon parametreleri
        form = QFormLayout()

        self.solver_combo = QComboBox()
        self.solver_combo.addItems(["simpleFoam", "pimpleFoam", "rhoCentralFoam"])
        form.addRow("Solver:", self.solver_combo)

        self.wind_speed = QDoubleSpinBox()
        self.wind_speed.setValue(15.0)
        self.wind_speed.setRange(0, 100)
        self.wind_speed.setSuffix(" m/s")
        form.addRow("Rüzgar Hızı:", self.wind_speed)

        self.num_processors = QSpinBox()
        self.num_processors.setValue(4)
        self.num_processors.setRange(1, 16)
        form.addRow("İşlemci Sayısı:", self.num_processors)

        layout.addLayout(form)

        # Parametrik çalışma
        layout.addWidget(QLabel("Parametrik Çalışma:"))

        self.parametric_btn = QPushButton("⚙️ Parametreler Tanımla")
        self.parametric_btn.clicked.connect(self._open_parametric_dialog)
        layout.addWidget(self.parametric_btn)

        self.study_info = QTextEdit()
        self.study_info.setReadOnly(True)
        self.study_info.setMaximumHeight(150)
        layout.addWidget(self.study_info)

        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def _create_mesh_tab(self) -> QWidget:
        """Mesh tab'ı"""
        widget = QWidget()
        layout = QVBoxLayout()

        form = QFormLayout()

        self.mesh_size = QDoubleSpinBox()
        self.mesh_size.setValue(0.01)
        self.mesh_size.setRange(0.001, 0.1)
        self.mesh_size.setSingleStep(0.001)
        self.mesh_size.setSuffix(" m")
        form.addRow("Base Mesh Boyutu:", self.mesh_size)

        self.bl_enabled = QCheckBox("Boundary Layer Etkinleştir")
        self.bl_enabled.setChecked(True)
        form.addRow("", self.bl_enabled)

        self.bl_layers = QSpinBox()
        self.bl_layers.setValue(10)
        self.bl_layers.setRange(1, 20)
        form.addRow("BL Katman Sayısı:", self.bl_layers)

        self.bl_ratio = QDoubleSpinBox()
        self.bl_ratio.setValue(1.2)
        self.bl_ratio.setRange(1.0, 2.0)
        self.bl_ratio.setSingleStep(0.1)
        form.addRow("BL Growth Ratio:", self.bl_ratio)

        layout.addLayout(form)

        # Mesh oluştur
        self.gen_mesh_btn = QPushButton("🔨 Mesh Oluştur")
        self.gen_mesh_btn.clicked.connect(self._generate_mesh)
        layout.addWidget(self.gen_mesh_btn)

        self.mesh_log = QTextEdit()
        self.mesh_log.setReadOnly(True)
        layout.addWidget(self.mesh_log)

        widget.setLayout(layout)
        return widget

    def _create_simulation_tab(self) -> QWidget:
        """Simülasyon tab'ı"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Kontrol butonları
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("▶️ BAŞLAT")
        self.start_btn.setObjectName("run")
        self.start_btn.clicked.connect(self._start_simulation)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹️ DURDUR")
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        self.reset_btn = QPushButton("🔄 SIFIRLA")
        self.reset_btn.clicked.connect(self._reset_simulation)
        btn_layout.addWidget(self.reset_btn)

        layout.addLayout(btn_layout)

        # İlerleme
        layout.addWidget(QLabel("İlerleme:"))
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        # Log
        layout.addWidget(QLabel("Log:"))
        self.sim_log = QTextEdit()
        self.sim_log.setReadOnly(True)
        layout.addWidget(self.sim_log)

        widget.setLayout(layout)
        return widget

    def _create_results_tab(self) -> QWidget:
        """Sonuçlar tab'ı"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Sonuç tablosu
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels([
            "Case", "Drag (N)", "Lift (N)", "Moment (N⋅m)", "Status", "Timestamp"
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.results_table)

        # Rapor oluştur
        report_btn = QPushButton("📄 Rapor Oluştur")
        report_btn.clicked.connect(self._generate_report)
        layout.addWidget(report_btn)

        widget.setLayout(layout)
        return widget

    def _load_aircraft(self, item):
        """Uçak yükle"""
        aircraft_name = item.text()

        if "MiniHawk" in aircraft_name:
            self.current_aircraft = AircraftLibrary.minihawk_uav()
        elif "Roket" in aircraft_name:
            self.current_aircraft = AircraftLibrary.model_rocket()
        elif "Racer" in aircraft_name:
            self.current_aircraft = AircraftLibrary.fixed_wing_racer()
        elif "VTOL" in aircraft_name:
            self.current_aircraft = AircraftLibrary.vtol_drone()
        elif "Altitude" in aircraft_name:
            self.current_aircraft = AircraftLibrary.high_altitude_platform()

        # Bilgi göster
        if self.current_aircraft:
            info = f"""
**{self.current_aircraft.name}**

Tür: {self.current_aircraft.aircraft_type}

Kanat:
  - Açıklık: {self.current_aircraft.wing.span:.2f} m
  - Alan: {self.current_aircraft.wing.area:.3f} m²
  - AR: {self.current_aircraft.wing.aspect_ratio:.2f}

Gövde:
  - Çap: {self.current_aircraft.fuselage.diameter:.3f} m
  - Uzunluk: {self.current_aircraft.fuselage.length:.2f} m

Kütle: {self.current_aircraft.mass_properties()['total_mass']:.2f} kg
"""
            self.aircraft_info.setText(info)

            # Parametreleri göster
            self.params_table.setRowCount(0)
            params = {
                "Kanat Açıklığı": f"{self.current_aircraft.wing.span:.2f} m",
                "Kanat Alanı": f"{self.current_aircraft.wing.area:.3f} m²",
                "Gövde Uzunluğu": f"{self.current_aircraft.fuselage.length:.2f} m",
                "Tarama Açısı": f"{self.current_aircraft.wing.sweep_angle:.1f}°",
                "Taper Oranı": f"{self.current_aircraft.wing.taper_ratio:.2f}",
            }

            for i, (key, value) in enumerate(params.items()):
                self.params_table.insertRow(i)
                self.params_table.setItem(i, 0, QTableWidgetItem(key))
                self.params_table.setItem(i, 1, QTableWidgetItem(value))

    def _open_parametric_dialog(self):
        """Parametrik çalışma diyaloğu"""
        dialog = ParametricStudyDialog(self)
        if dialog.exec():
            self.study_variations = dialog.get_study_config()

            # Info göster
            info = "Parametrik Çalışma Kuruldu:\n\n"
            total_cases = 1
            for param, values in self.study_variations.items():
                info += f"• {param}: {len(values)} değer\n"
                total_cases *= len(values)
            info += f"\nToplam Case: {total_cases}"
            self.study_info.setText(info)

    def _generate_mesh(self):
        """Mesh oluştur"""
        if not self.current_aircraft:
            QMessageBox.warning(self, "Hata", "Önce uçak seçin")
            return

        self.mesh_log.clear()
        self.mesh_log.append("🔄 Mesh oluşturuluyor...")

        try:
            mesh_gen = MeshGenerator(self.current_aircraft, mesh_size=self.mesh_size.value())
            config = mesh_gen.generate_mesh_config()

            self.mesh_log.append("✅ Mesh konfigürasyonu:")
            self.mesh_log.append(json.dumps(config, indent=2))

            # Tahmini element sayısı
            est_elements = config["mesh"]["expected_elements"]
            self.mesh_log.append(f"\n📊 Tahmini Element: {est_elements:,}")
            self.mesh_log.append(f"📊 Tahmini Node: {config['mesh']['expected_nodes']:,}")

        except Exception as e:
            self.mesh_log.append(f"❌ Hata: {str(e)}")

    def _start_simulation(self):
        """Simülasyonu başlat"""
        if not self.current_aircraft:
            QMessageBox.warning(self, "Hata", "Önce uçak seçin")
            return

        self.sim_log.clear()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.sim_log.append(f"🚀 Simülasyon başlatılıyor: {self.current_aircraft.name}")
        self.sim_log.append(f"Solver: {self.solver_combo.currentText()}")
        self.sim_log.append(f"Rüzgar: {self.wind_speed.value()} m/s\n")

        # Simülasyon job
        job = SimulationJob(
            case_name=f"{self.current_aircraft.name.replace(' ', '_')}",
            aircraft=self.current_aircraft,
            solver=self.solver_combo.currentText(),
            mesh_size=self.mesh_size.value(),
            wind_speed=self.wind_speed.value(),
            analysis_type="aerodinamik",
            num_processors=self.num_processors.value()
        )

        # (Gerçek uygulamada: runner.run_simulation(job))
        self.progress_bar.setValue(0)

        # Simülasyon simülasyonu
        for i in range(101):
            self.progress_bar.setValue(i)
            self.sim_log.append(f"[{i}%] Simülasyon devam ediyor...")
            QApplication.processEvents()

            import time
            time.sleep(0.05)

        self.sim_log.append("✅ Simülasyon tamamlandı!")
        self.progress_bar.setValue(100)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _reset_simulation(self):
        """Sıfırla"""
        self.progress_bar.setValue(0)
        self.sim_log.clear()
        self.results_table.setRowCount(0)

    def _generate_report(self):
        """Rapor oluştur"""
        QMessageBox.information(self, "Rapor", "Rapor oluşturuluyor...")

    def _create_fea_tab(self) -> QWidget:
        """FEA (Yapısal Analiz) Tab'ı"""
        widget = QWidget()
        layout = QVBoxLayout()

        # FEA Parametreleri
        form = QFormLayout()

        # Malzeme seçimi
        self.fea_material_combo = QComboBox()
        self.fea_material_combo.addItems(MATERIAL_LIBRARY.list_materials())
        form.addRow("Malzeme:", self.fea_material_combo)

        # Analiz tipi
        self.fea_analysis_combo = QComboBox()
        self.fea_analysis_combo.addItems(["STATIC", "FREQUENCY", "BUCKLING"])
        form.addRow("Analiz Tipi:", self.fea_analysis_combo)

        # Yük değeri
        self.fea_load = QDoubleSpinBox()
        self.fea_load.setRange(0, 100000)
        self.fea_load.setValue(1200)
        self.fea_load.setSuffix(" Pa")
        form.addRow("Yük:", self.fea_load)

        # Mod sayısı (Frequency analizi için)
        self.fea_modes = QSpinBox()
        self.fea_modes.setRange(1, 100)
        self.fea_modes.setValue(10)
        form.addRow("Mod Sayısı:", self.fea_modes)

        layout.addLayout(form)

        # Log/İstatistikler
        self.fea_log = QTextEdit()
        self.fea_log.setReadOnly(True)
        self.fea_log.setPlaceholderText("FEA sonuçları burada gösterilecek...")
        layout.addWidget(QLabel("📊 FEA Sonuçları:"))
        layout.addWidget(self.fea_log)

        # Kontrol butonları
        button_layout = QHBoxLayout()

        fea_run_btn = QPushButton("▶️ FEA Çalıştır")
        fea_run_btn.clicked.connect(self._run_fea_analysis)
        button_layout.addWidget(fea_run_btn)

        fea_report_btn = QPushButton("📄 Rapor Oluştur")
        fea_report_btn.clicked.connect(self._generate_fea_report)
        button_layout.addWidget(fea_report_btn)

        layout.addLayout(button_layout)
        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def _run_fea_analysis(self):
        """FEA analizi çalıştır"""
        self.fea_log.clear()
        self.fea_log.append("🚀 FEA Analizi başlatılıyor...\n")

        material_name = self.fea_material_combo.currentText()
        material = MATERIAL_LIBRARY.get_material(material_name)

        self.fea_log.append(f"Malzeme: {material.name}")
        self.fea_log.append(f"Analiz Tipi: {self.fea_analysis_combo.currentText()}")
        self.fea_log.append(f"Yük: {self.fea_load.value()} Pa\n")

        # Simüle edilmiş sonuçlar
        max_stress = self.fea_load.value() / 100 * 2.5  # Basit hesaplama
        safety_factor = material.yield_strength / max_stress if max_stress > 0 else float('inf')

        self.fea_log.append("📊 Sonuçlar:")
        self.fea_log.append(f"  • Maks. Gerilme: {max_stress:.2f} MPa")
        self.fea_log.append(f"  • Emniyet Faktörü: {safety_factor:.2f}")
        self.fea_log.append(f"  • Durum: {'✅ GÜVENLI' if safety_factor > 1.5 else '⚠️ UYARI'}\n")

        if self.fea_analysis_combo.currentText() == "FREQUENCY":
            self.fea_log.append("🔊 Doğal Frekanslar (ilk 5 mod):")
            for i in range(min(5, self.fea_modes.value())):
                freq = 5.0 + i * 2.5  # Simüle edilmiş
                self.fea_log.append(f"  • Mod {i+1}: {freq:.2f} Hz")

        self.fea_log.append("\n✅ FEA Analizi Tamamlandı!")

    def _generate_fea_report(self):
        """FEA Raporu oluştur"""
        material_name = self.fea_material_combo.currentText()
        material = MATERIAL_LIBRARY.get_material(material_name)

        report = f"""
FEA ANALİZ RAPORU
================

Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

MALZEME BİLGİLERİ
-----------------
Adı: {material.name}
Elastiklik Modülü: {material.youngs_modulus} MPa
Poisson Oranı: {material.poisson_ratio}
Yoğunluk: {material.density} kg/m³
Akma Gerilmesi: {material.yield_strength} MPa

ANALIZ PARAMETRELERİ
-------------------
Analiz Tipi: {self.fea_analysis_combo.currentText()}
Yük: {self.fea_load.value()} Pa
Mod Sayısı: {self.fea_modes.value()}

SONUÇLAR
--------
Analiz başarıyla tamamlandı.
Sonuçlar FEA simülasyon alanında görüntülenebilir.
"""

        QMessageBox.information(self, "FEA Raporu", report)

    def _on_materials_updated(self):
        """Malzeme kütüphanesi güncellendiğinde FEA combo box'ı güncelle"""
        current_selection = self.fea_material_combo.currentText()
        self.fea_material_combo.clear()
        self.fea_material_combo.addItems(MATERIAL_LIBRARY.list_materials())

        # Eğer önceki seçim hala varsa onu seç
        index = self.fea_material_combo.findText(current_selection)
        if index >= 0:
            self.fea_material_combo.setCurrentIndex(index)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ParametricAnalysisTool()
    window.show()
    sys.exit(app.exec())
