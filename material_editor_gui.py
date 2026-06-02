"""
Material Editor GUI — Kullanıcı tarafından malzeme eklemesi/düzenlemesi
Advanced material database arayüzü
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QDoubleSpinBox, QComboBox, QTableWidget, QTableWidgetItem, QDialog,
    QMessageBox, QCheckBox, QTextEdit, QSpinBox, QGroupBox, QFormLayout,
    QTabWidget
)
from PySide6.QtCore import Qt, Signal
from material_database import MaterialLibrary, MaterialProperties, MaterialType
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# MATERIAL EDITOR DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class MaterialEditorDialog(QDialog):
    """Yeni malzeme ekleme/düzenleme diyaloğu"""

    def __init__(self, parent=None, material: Optional[MaterialProperties] = None):
        super().__init__(parent)
        self.material = material
        self.setWindowTitle("Malzeme Editörü" if not material else f"Düzenle: {material.name}")
        self.setGeometry(100, 100, 600, 700)
        self._create_ui()

        # Eğer düzenleme ise değerleri doldur
        if material:
            self._load_material_data()

    def _create_ui(self):
        """UI oluştur"""
        layout = QVBoxLayout()

        # ─── TEMEL BİLGİLER ───
        basic_group = QGroupBox("Temel Bilgiler")
        basic_layout = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Örn: Aluminum 7075")
        basic_layout.addRow("Adı:", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems([t.value for t in MaterialType])
        basic_layout.addRow("Tür:", self.type_combo)

        self.density_spin = QDoubleSpinBox()
        self.density_spin.setRange(10, 20000)
        self.density_spin.setValue(2700)
        self.density_spin.setSuffix(" kg/m³")
        basic_layout.addRow("Yoğunluk (ρ):", self.density_spin)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # ─── MEKANİK ÖZELLİKLER ───
        mech_group = QGroupBox("Mekanik Özellikler")
        mech_layout = QFormLayout()

        self.young_spin = QDoubleSpinBox()
        self.young_spin.setRange(0.1, 500)
        self.young_spin.setValue(69)
        self.young_spin.setSuffix(" GPa")
        mech_layout.addRow("Young Modülü (E):", self.young_spin)

        self.poisson_spin = QDoubleSpinBox()
        self.poisson_spin.setRange(0, 0.5)
        self.poisson_spin.setValue(0.33)
        self.poisson_spin.setSingleStep(0.01)
        mech_layout.addRow("Poisson Oranı (ν):", self.poisson_spin)

        self.yield_spin = QDoubleSpinBox()
        self.yield_spin.setRange(1, 10000)
        self.yield_spin.setValue(275)
        self.yield_spin.setSuffix(" MPa")
        mech_layout.addRow("Akma Mukavemeti (σ_y):", self.yield_spin)

        self.tensile_spin = QDoubleSpinBox()
        self.tensile_spin.setRange(1, 10000)
        self.tensile_spin.setValue(310)
        self.tensile_spin.setSuffix(" MPa")
        mech_layout.addRow("Çekme Mukavemeti (σ_max):", self.tensile_spin)

        self.compress_spin = QDoubleSpinBox()
        self.compress_spin.setRange(0, 10000)
        self.compress_spin.setSuffix(" MPa")
        mech_layout.addRow("Basma Mukavemeti (σ_c):", self.compress_spin)

        mech_group.setLayout(mech_layout)
        layout.addWidget(mech_group)

        # ─── TERMAL ÖZELLİKLER ───
        thermal_group = QGroupBox("Termal Özellikler (Opsiyonel)")
        thermal_layout = QFormLayout()

        self.thermal_cond_spin = QDoubleSpinBox()
        self.thermal_cond_spin.setRange(0.001, 500)
        self.thermal_cond_spin.setSuffix(" W/(m·K)")
        thermal_layout.addRow("Isıl İletkenlik:", self.thermal_cond_spin)

        self.thermal_exp_spin = QDoubleSpinBox()
        self.thermal_exp_spin.setRange(-100, 100)
        self.thermal_exp_spin.setSuffix(" ×10⁻⁶ /K")
        thermal_layout.addRow("Isıl Genleşme:", self.thermal_exp_spin)

        self.melting_spin = QDoubleSpinBox()
        self.melting_spin.setRange(0, 5000)
        self.melting_spin.setSuffix(" °C")
        thermal_layout.addRow("Erime Noktası:", self.melting_spin)

        thermal_group.setLayout(thermal_layout)
        layout.addWidget(thermal_group)

        # ─── DIĞ ÖZELLİKLER ───
        other_group = QGroupBox("Diğer Özellikler")
        other_layout = QFormLayout()

        self.cost_spin = QDoubleSpinBox()
        self.cost_spin.setRange(0, 1000)
        self.cost_spin.setSuffix(" $/kg")
        other_layout.addRow("Maliyet:", self.cost_spin)

        self.recyclable_check = QCheckBox("Geri Dönüştürülebilir")
        other_layout.addRow("", self.recyclable_check)

        self.applications_edit = QLineEdit()
        self.applications_edit.setPlaceholderText("Örn: Aerospace, Automotive (virgülle ayır)")
        other_layout.addRow("Uygulamalar:", self.applications_edit)

        other_group.setLayout(other_layout)
        layout.addWidget(other_group)

        # ─── BUTONLAR ───
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Kaydet")
        save_btn.clicked.connect(self._save_material)
        cancel_btn = QPushButton("İptal")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _load_material_data(self):
        """Malzeme verilerini UI'ye yükle"""
        mat = self.material
        self.name_edit.setText(mat.name)
        self.type_combo.setCurrentText(mat.material_type.value)
        self.density_spin.setValue(mat.density)
        self.young_spin.setValue(mat.youngs_modulus)
        self.poisson_spin.setValue(mat.poisson_ratio)
        self.yield_spin.setValue(mat.yield_strength)
        self.tensile_spin.setValue(mat.tensile_strength)

        if mat.compressive_strength:
            self.compress_spin.setValue(mat.compressive_strength)
        if mat.thermal_conductivity:
            self.thermal_cond_spin.setValue(mat.thermal_conductivity)
        if mat.thermal_expansion:
            self.thermal_exp_spin.setValue(mat.thermal_expansion * 1e6)
        if mat.melting_point:
            self.melting_spin.setValue(mat.melting_point)
        if mat.cost_per_kg:
            self.cost_spin.setValue(mat.cost_per_kg)

        self.recyclable_check.setChecked(mat.recyclable)
        self.applications_edit.setText(", ".join(mat.typical_applications))

    def _save_material(self):
        """Malzemeyi kaydet ve diyaloğu kapat"""
        try:
            name = self.name_edit.text().strip()
            if not name:
                raise ValueError("Malzeme adı boş olamaz")

            applications = [app.strip() for app in self.applications_edit.text().split(',')
                          if app.strip()]

            material = MaterialProperties(
                name=name,
                material_type=MaterialType(self.type_combo.currentText()),
                density=self.density_spin.value(),
                youngs_modulus=self.young_spin.value(),
                poisson_ratio=self.poisson_spin.value(),
                yield_strength=self.yield_spin.value(),
                tensile_strength=self.tensile_spin.value(),
                compressive_strength=self.compress_spin.value() or None,
                thermal_conductivity=self.thermal_cond_spin.value() or None,
                thermal_expansion=(self.thermal_exp_spin.value() / 1e6) or None,
                melting_point=self.melting_spin.value() or None,
                cost_per_kg=self.cost_spin.value() or None,
                recyclable=self.recyclable_check.isChecked(),
                typical_applications=applications
            )

            # Validasyon otomatik yapılır __post_init__'de
            self.material = material
            self.accept()

        except ValueError as e:
            QMessageBox.critical(self, "Hata", f"Geçersiz veri:\n{str(e)}")

    def get_material(self) -> MaterialProperties:
        """Düzenlenmiş malzemeyi getir"""
        return self.material

# ─────────────────────────────────────────────────────────────────────────────
# MATERIAL MANAGER GUI TAB
# ─────────────────────────────────────────────────────────────────────────────

class MaterialManagerTab(QWidget):
    """Malzeme yönetimi sekmesi"""

    # Signal: Malzeme kütüphanesi değiştiğinde emit edilir
    materials_changed = Signal()

    def __init__(self, material_lib: MaterialLibrary):
        super().__init__()
        self.lib = material_lib
        self._create_ui()
        self._refresh_table()

    def _create_ui(self):
        """UI oluştur"""
        layout = QVBoxLayout()

        # ─── BAŞLIK ───
        title = QLabel("Malzeme Kütüphanesi Yönetimi")
        title.setStyleSheet("color: #7ff7f1; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        # ─── BUTONLAR ───
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("+ Malzeme Ekle")
        add_btn.clicked.connect(self._add_material)
        edit_btn = QPushButton("✎ Düzenle")
        edit_btn.clicked.connect(self._edit_material)
        delete_btn = QPushButton("✕ Sil")
        delete_btn.clicked.connect(self._delete_material)
        export_btn = QPushButton("📊 CSV'ye Dışa Aktar")
        export_btn.clicked.connect(self._export_csv)

        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(export_btn)

        layout.addLayout(btn_layout)

        # ─── TABLO ───
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Adı", "Tür", "Yoğunluk\n(kg/m³)", "Young\n(GPa)",
            "Akma (MPa)", "Çekme (MPa)", "Str/W\n(m/s²)", "Maliyet\n($/kg)"
        ])
        self.table.horizontalHeader().setStretchLastSection(False)

        layout.addWidget(self.table)

        # ─── DETAY ───
        detail_group = QGroupBox("Seçilen Malzeme Detayları")
        detail_layout = QVBoxLayout()
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(150)
        detail_layout.addWidget(self.detail_text)
        detail_group.setLayout(detail_layout)

        layout.addWidget(detail_group)

        self.setLayout(layout)

        # Table seçimi güncellemeleri
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

    def _refresh_table(self):
        """Tabloyu yenile"""
        self.table.setRowCount(len(self.lib.materials))

        for row, (name, material) in enumerate(self.lib.materials.items()):
            self.table.setItem(row, 0, QTableWidgetItem(material.name))
            self.table.setItem(row, 1, QTableWidgetItem(material.material_type.value))
            self.table.setItem(row, 2, QTableWidgetItem(f"{material.density:.0f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{material.youngs_modulus:.1f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{material.yield_strength:.0f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{material.tensile_strength:.0f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{material.strength_to_weight/1e6:.2f}"))
            cost_str = f"{material.cost_per_kg:.1f}" if material.cost_per_kg else "—"
            self.table.setItem(row, 7, QTableWidgetItem(cost_str))

    def _on_selection_changed(self):
        """Seçim değiştiğinde detayları göster"""
        rows = self.table.selectionModel().selectedRows()
        if rows:
            row = rows[0].row()
            material_name = self.table.item(row, 0).text()
            material = self.lib.get_material(material_name)
            self.detail_text.setText(str(material))

    def _add_material(self):
        """Yeni malzeme ekle"""
        dialog = MaterialEditorDialog(self)
        if dialog.exec() == QDialog.Accepted:
            material = dialog.get_material()
            self.lib.add_material(material)
            self.lib.save_to_file()
            self._refresh_table()
            self.materials_changed.emit()
            QMessageBox.information(self, "Başarılı", f"'{material.name}' eklendi")

    def _edit_material(self):
        """Malzemeyi düzenle"""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "Uyarı", "Düzenlemek için malzeme seçin")
            return

        row = rows[0].row()
        material_name = self.table.item(row, 0).text()
        material = self.lib.get_material(material_name)

        dialog = MaterialEditorDialog(self, material)
        if dialog.exec() == QDialog.Accepted:
            edited = dialog.get_material()
            # Eski adda olanı sil, yeniyi ekle
            if edited.name != material.name:
                self.lib.remove_material(material.name)
            self.lib.add_material(edited)
            self.lib.save_to_file()
            self._refresh_table()
            self.materials_changed.emit()
            QMessageBox.information(self, "Başarılı", f"'{edited.name}' güncellendi")

    def _delete_material(self):
        """Malzemeyi sil"""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "Uyarı", "Silmek için malzeme seçin")
            return

        row = rows[0].row()
        material_name = self.table.item(row, 0).text()

        reply = QMessageBox.question(self, "Onay", f"'{material_name}' silinsin mi?")
        if reply == QMessageBox.Yes:
            self.lib.remove_material(material_name)
            self.lib.save_to_file()
            self._refresh_table()
            self.materials_changed.emit()

    def _export_csv(self):
        """CSV'ye dışa aktar"""
        output_path = Path(__file__).parent / "materials_export.csv"
        self.lib.export_csv(output_path)
        QMessageBox.information(self, "Başarılı", f"CSV dışa aktarıldı:\n{output_path}")

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    lib = MaterialLibrary()
    window = MaterialManagerTab(lib)
    window.show()
    sys.exit(app.exec())
