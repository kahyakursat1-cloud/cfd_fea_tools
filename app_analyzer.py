"""
Araç Aerodinamik Analiz Stüdyosu — tek pencere endüstriyel arayüz.
==================================================================
Akış: katı model yükle (STL/OBJ, sürükle-bırak destekli) → araç tipi ve akış
koşullarını seç → Analiz Et → canlı ilerleme/log → sonuç kartları → Raporu Aç.
Motor: vehicle_pipeline.run_vehicle_analysis (snappyHexMesh + OpenFOAM kOmegaSST).

Başlatma: python app_analyzer.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from vehicle_pipeline import (
    AXIS_VECTORS,
    MESH_QUALITY,
    VEHICLE_PRESETS,
    inspect_geometry,
    prepare_geometry,
    run_vehicle_analysis,
)

ACCENT = "#0e639c"
STYLE = f"""
QMainWindow, QWidget {{ background: #1e1e1e; color: #d4d4d4; font-size: 13px; }}
QGroupBox {{ border: 1px solid #3c3c3c; border-radius: 6px; margin-top: 10px;
             padding-top: 14px; font-weight: bold; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: #9cdcfe; }}
QPushButton {{ background: {ACCENT}; color: white; border: none; border-radius: 4px;
               padding: 8px 16px; font-weight: bold; }}
QPushButton:hover {{ background: #1177bb; }}
QPushButton:disabled {{ background: #3c3c3c; color: #777; }}
QComboBox, QDoubleSpinBox, QSpinBox {{ background: #2d2d2d; border: 1px solid #3c3c3c;
               border-radius: 4px; padding: 4px; }}
QPlainTextEdit {{ background: #111; color: #9fdf9f; border: 1px solid #3c3c3c;
               font-family: Consolas, monospace; font-size: 12px; }}
QProgressBar {{ background: #2d2d2d; border: 1px solid #3c3c3c; border-radius: 4px;
               text-align: center; color: white; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QLabel#drop {{ border: 2px dashed #3c3c3c; border-radius: 8px; color: #888;
               padding: 24px; font-size: 14px; }}
QLabel#metric {{ background: #252526; border: 1px solid #3c3c3c; border-radius: 6px;
               padding: 10px; font-size: 13px; }}
"""


class AnalysisWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    def run(self):
        try:
            r = run_vehicle_analysis(
                progress_cb=lambda p, m: self.progress.emit(p, m), **self.params)
            if r.status == "ok":
                self.finished_ok.emit(r)
            else:
                self.failed.emit(r.error or "Bilinmeyen hata — case loglarına bakın: " + r.case_dir)
        except Exception as e:
            self.failed.emit(str(e))


class FEAWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    def run(self):
        try:
            from vehicle_fea import run_structural_check
            out = run_structural_check(progress_cb=lambda p, m: self.progress.emit(p, m),
                                       **self.params)
            if out.get("status") == "ok":
                self.finished_ok.emit(out)
            else:
                self.failed.emit(out.get("error", "FEA başarısız"))
        except Exception as e:
            self.failed.emit(str(e))


class SupersonicWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    def run(self):
        try:
            from supersonic_cfd import run_supersonic
            out = run_supersonic(progress_cb=lambda p, m: self.progress.emit(p, m),
                                 **self.params)
            if out.get("status") == "ok":
                self.finished_ok.emit(out)
            else:
                self.failed.emit(f"[{out.get('asama', '')}] {out.get('error', '')[-600:]}")
        except Exception as e:
            self.failed.emit(str(e))


class MachSweepWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    def run(self):
        try:
            from supersonic_cfd import run_mach_sweep
            out = run_mach_sweep(progress_cb=lambda p, m: self.progress.emit(p, m),
                                 **self.params)
            if out.get("status") == "ok":
                self.finished_ok.emit(out)
            else:
                self.failed.emit(out.get("error", "Mach taraması başarısız"))
        except Exception as e:
            self.failed.emit(str(e))


class PolarWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    def run(self):
        try:
            from vehicle_polar import run_polar
            out = run_polar(progress_cb=lambda p, m: self.progress.emit(p, m),
                            **self.params)
            if out.get("status") == "ok":
                self.finished_ok.emit(out)
            else:
                self.failed.emit(out.get("error", "Polar başarısız"))
        except Exception as e:
            self.failed.emit(str(e))


class YolculukDialog(QDialog):
    """Rehberli Mod: adım adım analiz-mühendisliği yolculuğu (yolculuk.py).
    Sol liste = adımlar; sağ panel = yap/kontrol-sorusu/ipucu + seviyeli ders bloğu.
    Sorular cevap-anahtarsızdır (öz-açıklama); 'tamamladım' öğrenci profilini ilerletir,
    seviye şeffaf kuralla atlar (BYF→ÖYG→PROJE)."""

    def __init__(self, parent, tip: str, analiz: str | None):
        super().__init__(parent)
        import yolculuk
        self._yol = yolculuk
        self.setWindowTitle("🎓 Rehberli Mod — Analiz Yolculuğu")
        self.resize(880, 540)
        self.plan = yolculuk.plan({"tip": tip, "analiz": analiz})
        lay = QVBoxLayout(self)
        self.lbl_seviye = QLabel()
        lay.addWidget(self.lbl_seviye)
        mid = QHBoxLayout()
        self.lst = QListWidget()
        for a in self.plan:
            self.lst.addItem(a["baslik"])
        self.lst.currentRowChanged.connect(self._show_step)
        mid.addWidget(self.lst, 1)
        self.det = QTextBrowser()
        self.det.setOpenExternalLinks(False)
        mid.addWidget(self.det, 2)
        lay.addLayout(mid, 1)
        row = QHBoxLayout()
        self.btn_done = QPushButton("✓ Bu adımı tamamladım")
        self.btn_done.setToolTip("Kontrol sorusunu kendi kelimelerinle cevapladıysan işaretle "
                                 "— profil ilerler, seviye kuralla atlar.")
        self.btn_done.clicked.connect(self._tamamla)
        row.addWidget(self.btn_done)
        row.addStretch(1)
        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_close)
        lay.addLayout(row)
        self._refresh_seviye()
        self.lst.setCurrentRow(0)

    def _refresh_seviye(self):
        p = self._yol.profil()
        self.lbl_seviye.setText(
            f"Öğrenci seviyesi: {p['seviye'].upper()}   |   tamamlanmış analiz: "
            f"{p.get('analiz_sayisi', 0)}   (ÖYG ≥{self._yol.ESIK_OYG} analiz; "
            f"PROJE ≥{self._yol.ESIK_PROJE} + GCI + savunma)")

    def _show_step(self, row: int):
        if row < 0:
            return
        a = self.plan[row]
        md = [f"## {a['baslik']}", "", f"**Yap:** {a['yapilacak']}", "",
              f"**Kontrol sorusu:** {a['soru']}", "", f"*İpucu: {a['ipucu']}*"]
        if a["ders_md"]:
            md += ["", "---", "", a["ders_md"]]
        self.det.setMarkdown("\n".join(md))

    def _tamamla(self):
        row = self.lst.currentRow()
        if row < 0:
            return
        self._yol.adim_tamamla(self.plan[row]["ad"])
        item = self.lst.item(row)
        if not item.text().startswith("✓"):
            item.setText("✓ " + item.text())
        self._refresh_seviye()
        if row + 1 < self.lst.count():
            self.lst.setCurrentRow(row + 1)


class AnalyzerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arac Aerodinamik Analiz Studyosu")
        self.resize(1080, 720)
        self.setAcceptDrops(True)
        self.model_path: Path | None = None
        self.worker: AnalysisWorker | None = None
        self.last_result = None
        self._pending_learn = None       # otopilot öğrenme vakası (koşu bitince kaydedilir)
        self._build_ui()

    # ── UI ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)

        # Sol: girişler
        left = QVBoxLayout()
        gb_model = QGroupBox("1 — Katı Model")
        v = QVBoxLayout(gb_model)
        self.drop_label = QLabel("STL/OBJ dosyasını buraya sürükleyin\nveya Gözat'a tıklayın")
        self.drop_label.setObjectName("drop")
        self.drop_label.setAlignment(Qt.AlignCenter)
        v.addWidget(self.drop_label)
        btn_browse = QPushButton("Gözat…")
        btn_browse.clicked.connect(self._browse)
        v.addWidget(btn_browse)
        self.geo_label = QLabel("")
        self.geo_label.setWordWrap(True)
        v.addWidget(self.geo_label)
        left.addWidget(gb_model)

        gb_cfg = QGroupBox("2 — Araç ve Akış Koşulları")
        form = QFormLayout(gb_cfg)
        self.cmb_type = QComboBox()
        for key, p in VEHICLE_PRESETS.items():
            self.cmb_type.addItem(p["ad"], key)
        form.addRow("Araç tipi", self.cmb_type)

        self.cmb_rejim = QComboBox()
        self.cmb_rejim.addItem("Ses altı (incompressible)", "subsonik")
        self.cmb_rejim.addItem("Ses üstü (shockFluid, M>0.8)", "supersonik")
        self.cmb_rejim.currentIndexChanged.connect(self._rejim_changed)
        form.addRow("Akış rejimi", self.cmb_rejim)

        self.spn_v = QDoubleSpinBox(); self.spn_v.setRange(0.5, 340); self.spn_v.setValue(30.0)
        self.spn_v.setSuffix(" m/s")
        form.addRow("Hız", self.spn_v)
        self.spn_mach = QDoubleSpinBox(); self.spn_mach.setRange(0.8, 6.0)
        self.spn_mach.setValue(2.0); self.spn_mach.setSingleStep(0.1)
        self.spn_mach.setSuffix(" Mach"); self.spn_mach.setEnabled(False)
        form.addRow("Mach (ses üstü)", self.spn_mach)
        self.spn_aoa = QDoubleSpinBox(); self.spn_aoa.setRange(-20, 20); self.spn_aoa.setValue(0.0)
        self.spn_aoa.setSuffix(" °")
        form.addRow("Hücum açısı", self.spn_aoa)
        self.cmb_quality = QComboBox()
        for key in MESH_QUALITY:
            self.cmb_quality.addItem(key, key)
        self.cmb_quality.setCurrentIndex(1)
        form.addRow("Mesh kalitesi", self.cmb_quality)
        self.cmb_nose = QComboBox()
        self.cmb_up = QComboBox()
        for ax in AXIS_VECTORS:
            self.cmb_nose.addItem(ax, ax)
            self.cmb_up.addItem(ax, ax)
        self.cmb_nose.setCurrentText("+x")
        self.cmb_up.setCurrentText("+z")
        form.addRow("Burun ekseni", self.cmb_nose)
        form.addRow("Üst eksen", self.cmb_up)
        self.spn_proc = QSpinBox(); self.spn_proc.setRange(0, 16); self.spn_proc.setValue(0)
        self.spn_proc.setSpecialValueText("otomatik")
        form.addRow("İşlemci", self.spn_proc)
        self.spn_layers = QSpinBox(); self.spn_layers.setRange(0, 10); self.spn_layers.setValue(0)
        self.spn_layers.setSpecialValueText("kapalı")
        form.addRow("Sınır tabaka katmanı", self.spn_layers)
        self.spn_yplus = QDoubleSpinBox(); self.spn_yplus.setRange(1, 300)
        self.spn_yplus.setValue(30.0)
        form.addRow("Hedef y⁺", self.spn_yplus)
        self.chk_sens = QCheckBox("Mesh duyarlılık bandı (2. kaba koşu)")
        form.addRow("", self.chk_sens)
        left.addWidget(gb_cfg)

        self.btn_auto = QPushButton("🤖  OTOMATİK ANALİZ (otopilot)")
        self.btn_auto.setMinimumHeight(40)
        self.btn_auto.setEnabled(False)
        self.btn_auto.setToolTip("Geometriyi inceler, araç tipini ve tüm ayarları "
                                 "seçer; planı gösterir, onayınızla koşar.")
        self.btn_auto.clicked.connect(self._otomatik_analiz)
        left.addWidget(self.btn_auto)

        self.btn_run = QPushButton("▶  ANALİZ ET")
        self.btn_run.setMinimumHeight(44)
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self._run)
        left.addWidget(self.btn_run)

        self.btn_yolculuk = QPushButton("🎓  REHBERLİ MOD (adım adım öğren)")
        self.btn_yolculuk.setEnabled(False)
        self.btn_yolculuk.setToolTip(
            "Analiz-mühendisi yolculuğu: her adımda ne yapılacağı, NEDENİ ve bir kontrol "
            "sorusu. Adımları tamamladıkça profiliniz BYF→ÖYG→PROJE seviye atlar.")
        self.btn_yolculuk.clicked.connect(self._open_yolculuk)
        left.addWidget(self.btn_yolculuk)

        gb_polar = QGroupBox("Polar Taraması (opsiyonel)")
        pf = QFormLayout(gb_polar)
        self.edt_alphas = QLineEdit("-4, 0, 4, 8")
        pf.addRow("α listesi (°)", self.edt_alphas)
        self.btn_polar = QPushButton("📈  POLAR TARA")
        self.btn_polar.setEnabled(False)
        self.btn_polar.clicked.connect(self._run_polar)
        pf.addRow(self.btn_polar)
        self.edt_machs = QLineEdit("0.8, 1.2, 2.0, 3.0")
        pf.addRow("Mach listesi", self.edt_machs)
        self.btn_mach = QPushButton("🚀  Cd-MACH TARA (ses üstü)")
        self.btn_mach.setEnabled(False)
        self.btn_mach.clicked.connect(self._run_mach_sweep)
        pf.addRow(self.btn_mach)
        left.addWidget(gb_polar)

        gb_fea = QGroupBox("Yapısal Kontrol (CFD basınçlarıyla)")
        ff = QFormLayout(gb_fea)
        from fea_runner import MATERIAL_LIBRARY
        from vehicle_fea import CONSTRAINT_PRESETS
        self.cmb_mat = QComboBox()
        for key, mt in MATERIAL_LIBRARY.items():
            self.cmb_mat.addItem(mt.name, key)
        ff.addRow("Malzeme", self.cmb_mat)
        self.cmb_fix = QComboBox()
        for key, (desc, _, _) in CONSTRAINT_PRESETS.items():
            self.cmb_fix.addItem(desc, key)
        ff.addRow("Mesnet", self.cmb_fix)
        self.cmb_femodel = QComboBox()
        self.cmb_femodel.addItem("Dolu katı (parça)", "dolu")
        self.cmb_femodel.addItem("Kabuk S3 (tam araç derisi)", "kabuk")
        ff.addRow("Yapı modeli", self.cmb_femodel)
        self.spn_thick = QDoubleSpinBox(); self.spn_thick.setRange(0.2, 20.0)
        self.spn_thick.setValue(2.0); self.spn_thick.setSuffix(" mm")
        ff.addRow("Kabuk kalınlığı", self.spn_thick)
        self.spn_gyuk = QDoubleSpinBox(); self.spn_gyuk.setRange(0.0, 10.0)
        self.spn_gyuk.setValue(0.0); self.spn_gyuk.setSuffix(" g")
        self.spn_gyuk.setToolTip("Manevra yük faktörü n: CFD basıncına ek n·g eylemsizlik "
                                 "(gövde) yükü. 0 = yalnız aero-basınç. FlightEnvelope n_max ile.")
        ff.addRow("Manevra g-yükü", self.spn_gyuk)
        self.spn_itki = QDoubleSpinBox(); self.spn_itki.setRange(0.0, 1e6)
        self.spn_itki.setValue(0.0); self.spn_itki.setSuffix(" N")
        self.spn_itki.setToolTip("Motor itkisi: aft (kuyruk) patch'ine +x dağıtık nokta-yük "
                                 "(thrust-mount). 0 = yok.")
        ff.addRow("Motor itkisi", self.spn_itki)
        self.spn_dt = QDoubleSpinBox(); self.spn_dt.setRange(-500.0, 500.0)
        self.spn_dt.setValue(0.0); self.spn_dt.setSuffix(" K")
        self.spn_dt.setToolTip("Üniform sıcaklık değişimi ΔT: termal genleşme gerilmesi "
                               "(α·ΔT, malzeme CTE'sinden). 0 = izotermal.")
        ff.addRow("Termal ΔT", self.spn_dt)
        self.btn_fea = QPushButton("🛠  FEA ÇALIŞTIR")
        self.btn_fea.setEnabled(False)
        self.btn_fea.clicked.connect(self._run_fea)
        ff.addRow(self.btn_fea)
        left.addWidget(gb_fea)
        left.addStretch(1)

        # Sağ: ilerleme + log + sonuç
        right = QVBoxLayout()
        gb_prog = QGroupBox("3 — Analiz")
        pv = QVBoxLayout(gb_prog)
        self.progress = QProgressBar()
        pv.addWidget(self.progress)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        pv.addWidget(self.log, 1)
        right.addWidget(gb_prog, 2)

        gb_res = QGroupBox("4 — Sonuçlar")
        grid = QGridLayout(gb_res)
        self.metric_labels = {}
        for i, (key, title) in enumerate([
                ("cd", "C_D"), ("cl", "C_L"), ("ld", "L/D"),
                ("drag", "Sürükleme"), ("cells", "Hücre"), ("verdict", "Yakınsama")]):
            lab = QLabel(f"{title}\n—")
            lab.setObjectName("metric")
            lab.setAlignment(Qt.AlignCenter)
            lab.setFont(QFont("Segoe UI", 11))
            grid.addWidget(lab, i // 3, i % 3)
            self.metric_labels[key] = (title, lab)
        self.btn_report = QPushButton("📄  Raporu Aç")
        self.btn_report.setEnabled(False)
        self.btn_report.clicked.connect(self._open_report)
        grid.addWidget(self.btn_report, 2, 0, 1, 3)
        right.addWidget(gb_res, 1)

        layout.addLayout(left, 1)
        layout.addLayout(right, 2)
        self.setCentralWidget(root)
        self.setStyleSheet(STYLE)

    # ── Model yükleme ───────────────────────────────────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    MODEL_EXTS = (".stl", ".obj", ".step", ".stp", ".iges", ".igs")

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() in self.MODEL_EXTS:
                self._load_model(p)
                return

    def _browse(self):
        f, _ = QFileDialog.getOpenFileName(self, "Katı model seç", "",
                                           "3B Model (*.stl *.obj *.step *.stp *.iges *.igs)")
        if f:
            self._load_model(Path(f))

    def _load_model(self, path: Path):
        try:
            prepared, prep = prepare_geometry(path, Path("vehicle_runs") / path.stem)
            geo = inspect_geometry(prepared)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Model okunamadı:\n{e}")
            return
        self.model_path = path
        d = geo["boyutlar_m"]
        wt = "kapalı ✓" if geo["su_gecirmez"] else "açık ⚠"
        extra = ""
        if prep.get("govde_sayisi", 1) > 1:
            extra += f"   gövde: {prep['govde_sayisi']}"
        if prep.get("onarimlar"):
            extra += f"\nHazırlık: {'; '.join(prep['onarimlar'])}"
        self.drop_label.setText(f"✅ {path.name}")
        thin = geo.get("ince_kalinlik_m")
        thin_s = f"   et-kalınlığı≈{thin} m" if thin else ""
        self.geo_label.setText(
            f"Boyut: {d[0]} × {d[1]} × {d[2]} m   |   üçgen: {geo['ucgen_sayisi']:,}{extra}\n"
            f"Yüzey: {geo['yuzey_alani_m2']} m²   ön: {geo['on_alan_m2']} m²   "
            f"planform: {geo['planform_alan_m2']} m²{thin_s}   |   yüzey {wt}")
        self.btn_run.setEnabled(True)
        self.btn_polar.setEnabled(True)
        self.btn_auto.setEnabled(True)
        self.btn_mach.setEnabled(True)
        self.btn_yolculuk.setEnabled(True)

    def _open_yolculuk(self):
        tip = self.cmb_type.currentData()
        analiz = "polar" if VEHICLE_PRESETS.get(tip, {}).get("lift_relevant") else None
        YolculukDialog(self, tip, analiz).exec()

    def _set_combo(self, combo, data):
        for i in range(combo.count()):
            if combo.itemData(i) == data:
                combo.setCurrentIndex(i)
                return

    def _otomatik_analiz(self):
        if not self.model_path:
            return
        try:
            import auto_pilot
            cfg = auto_pilot.auto_configure(self.model_path)
        except Exception as e:
            QMessageBox.critical(self, "Otopilot", f"Sınıflandırma başarısız:\n{e}")
            return
        uy = ("\n\n⚠ " + "\n⚠ ".join(cfg["uyarilar"])) if cfg.get("uyarilar") else ""
        ger = ("\n• " + "\n• ".join(cfg["gerekce"])) if cfg.get("gerekce") else ""
        msg = (f"Araç tipi: {cfg['tip'].upper()}  (güven %{cfg['guven']*100:.0f})\n"
               f"Gerekçe:{ger}\n\nÖnerilen plan:\n{cfg['plan']}{uy}\n\nBu planla koşulsun mu?")
        if QMessageBox.question(self, "🤖 Otopilot — Öner + Onayla", msg) \
                != QMessageBox.StandardButton.Yes:
            return
        # Öğrenme: tipi onayla/düzelt (etiket); düzeltilirse ayarlar yeniden kurulur
        from PySide6.QtWidgets import QInputDialog

        import auto_pilot
        adlar = {"roket": "Roket", "ucak": "Uçak/İHA",
                 "multikopter": "Multikopter", "genel": "Genel",
                 "kanatli_roket": "Kanatlı Roket/Füze", "tilt_rotor": "Tilt-Rotor/VTOL",
                 "kanatli_vtol": "Sabit-kanat VTOL (quadplane)",
                 "kaldirici_govde": "Kaldırıcı Gövde / Uzay-uçağı"}
        secenekler = [adlar[t] for t in auto_pilot.TIPLER]
        cur = list(auto_pilot.TIPLER).index(cfg["tip"])
        sec, ok = QInputDialog.getItem(
            self, "Tip onayı (öğrenme)",
            "Otopilot bu tipi seçti. Doğruysa onaylayın, değilse düzeltin —\n"
            "sistem bu geri bildirimden öğrenir:", secenekler, cur, False)
        if not ok:
            return
        onayli = auto_pilot.TIPLER[secenekler.index(sec)]
        if onayli != cfg["tip"]:
            auto_pilot.apply_type_settings(cfg, onayli, cfg.get("viscous", False))
            self._log(f"🤖 Tip düzeltildi: {cfg['kural_tip']} → {onayli} (öğrenildi).")
        self._pending_learn = {"metrik": cfg["metrik"], "otopilot_tip": cfg.get("kural_tip"),
                               "onayli_tip": onayli, "dosya": self.model_path.name,
                               "cfg": dict(cfg)}
        # Ayarları (gerekirse düzeltilmiş) tipe göre kur, uygun koşuyu tetikle.
        # Hibrit tipler CFD preset'ine (vehicle_preset) eşlenir.
        self._set_combo(self.cmb_type, cfg.get("vehicle_preset", cfg["tip"]))
        self._set_combo(self.cmb_quality, cfg["kalite"])
        if cfg["rejim"] == "supersonic":
            self._set_combo(self.cmb_rejim, "supersonik")
            self._rejim_changed()
            self.edt_machs.setText(", ".join(str(x) for x in cfg["mach_listesi"]))
            self._log(f"🤖 Otopilot: {cfg['tip']} → Cd-Mach taraması başlatılıyor.")
            self._run_mach_sweep()
        elif cfg.get("analiz") == "polar":
            self._set_combo(self.cmb_rejim, "subsonik"); self._rejim_changed()
            self.spn_v.setValue(cfg.get("hiz_ms", 25.0))
            self.edt_alphas.setText(", ".join(str(a) for a in cfg["aoa_listesi"]))
            self._log(f"🤖 Otopilot: {cfg['tip']} → polar taraması başlatılıyor.")
            self._run_polar()
        else:
            self._set_combo(self.cmb_rejim, "subsonik"); self._rejim_changed()
            self.spn_v.setValue(cfg.get("hiz_ms", 20.0))
            self._log(f"🤖 Otopilot: {cfg['tip']} → tekil ses-altı analiz başlatılıyor.")
            self._run()

    def _record_learning(self, result: dict | None):
        """Analiz bitince bekleyen otopilot vakasını kütüphaneye kaydet (öğrenme)
        ve aykırı C_D bayrağını logla."""
        pend = getattr(self, "_pending_learn", None)
        if not pend:
            return
        self._pending_learn = None
        try:
            import auto_pilot
            gate = auto_pilot.record_case(pend["metrik"], pend["otopilot_tip"],
                                          pend["onayli_tip"], result, pend["dosya"])
            n = len(auto_pilot._load_cases())
            if gate.get("suspect"):
                # hakem-kapısı: tip etiketi öğrenildi ama Cd güvenilmez → çapa değil
                self._log(f"🧠 Öğrenme: tip etiketi kaydedildi; C_D ŞÜPHELİ, çapa "
                          f"alınmadı (kütüphane: {n}). Neden: {'; '.join(gate.get('gerekce', []))}")
            else:
                self._log(f"🧠 Öğrenme: vaka + güvenilir C_D çapası kaydedildi (kütüphane: {n}).")
            cfg = dict(pend.get("cfg") or {})
            cfg["tip"] = pend["onayli_tip"]
            yorum = auto_pilot.narrate(cfg, result if isinstance(result, dict) else None)
            self._log("🧑‍⚖️ Hakem değerlendirmesi:\n" + yorum)
        except Exception:
            pass

    def _rejim_changed(self):
        ust = self.cmb_rejim.currentData() == "supersonik"
        self.spn_mach.setEnabled(ust)
        self.spn_v.setEnabled(not ust)
        # ses üstünde polar/FEA/duyarlılık akışı farklı; sadece temel CFD
        self.spn_aoa.setEnabled(not ust)

    # ── Çalıştırma ──────────────────────────────────────────────────────────
    def _run(self):
        if not self.model_path:
            return
        if self.cmb_rejim.currentData() == "supersonik":
            self._run_supersonic()
            return
        self.btn_run.setEnabled(False)
        self.btn_report.setEnabled(False)
        self.progress.setValue(0)
        self.log.clear()
        self._log("Ses altı analiz başlatılıyor…")
        if self.cmb_nose.currentText()[1] == self.cmb_up.currentText()[1]:
            QMessageBox.warning(self, "Eksen hatası",
                                "Burun ve üst eksenleri dik olmalı (farklı eksen seçin).")
            self.btn_run.setEnabled(True)
            return
        params = {
            "stl_path": self.model_path,
            "vehicle_type": self.cmb_type.currentData(),
            "velocity": self.spn_v.value(),
            "alpha_deg": self.spn_aoa.value(),
            "quality": self.cmb_quality.currentData(),
            "n_processors": self.spn_proc.value(),
            "nose_axis": self.cmb_nose.currentText(),
            "up_axis": self.cmb_up.currentText(),
            "mesh_sensitivity": self.chk_sens.isChecked(),
            "n_layers": self.spn_layers.value(),
            "yplus_target": self.spn_yplus.value(),
        }
        self.worker = AnalysisWorker(params)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _run_supersonic(self):
        self.btn_run.setEnabled(False)
        self.btn_polar.setEnabled(False)
        self.btn_report.setEnabled(False)
        self.progress.setValue(0)
        self.log.clear()
        mach = self.spn_mach.value()
        self._log(f"Ses üstü analiz (shockFluid) başlatılıyor — M={mach}…")
        params = {
            "stl_path": self.model_path,
            "mach": mach,
            "vehicle_type": self.cmb_type.currentData(),
            "quality": self.cmb_quality.currentData(),
        }
        self.worker = SupersonicWorker(params)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_supersonic_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _run_mach_sweep(self):
        if not self.model_path:
            return
        try:
            machs = [float(x) for x in self.edt_machs.text().replace(";", ",").split(",")
                     if x.strip()]
        except ValueError:
            QMessageBox.warning(self, "Mach listesi", "Virgülle ayrılmış sayılar: 0.8, 1.2, 2, 3")
            return
        if len(machs) < 2:
            QMessageBox.warning(self, "Mach listesi", "En az 2 Mach değeri gerekli.")
            return
        self.btn_run.setEnabled(False)
        self.btn_polar.setEnabled(False)
        self.btn_mach.setEnabled(False)
        self.progress.setValue(0)
        self.log.clear()
        self._log(f"Cd-Mach taraması (shockFluid): M = {machs}")
        self.worker = MachSweepWorker({
            "stl_path": self.model_path,
            "machs": machs,
            "vehicle_type": self.cmb_type.currentData(),
            "quality": self.cmb_quality.currentData(),
        })
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_mach_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _on_mach_done(self, out: dict):
        self.progress.setValue(100)
        self._log("✅ Cd-Mach taraması tamamlandı.")
        for row in out["egri"]:
            self._log(f"  M={row['mach']}: Cd={row.get('Cd')}")
        self.last_result = type("R", (), {"report": out.get("report", "")})()
        self.btn_report.setEnabled(bool(out.get("report")))
        self.btn_run.setEnabled(True)
        self.btn_polar.setEnabled(True)
        if hasattr(self, "btn_mach"):
            self.btn_mach.setEnabled(True)
        self._record_learning(None)   # taramada tek Cd yok; tip etiketi kaydedilir

    def _on_supersonic_done(self, out: dict):
        self.progress.setValue(100)
        self._log(f"✅ Ses üstü tamamlandı — {out['rejim']}.")
        self._set_metric("cd", f"{out['Cd']}")
        self._set_metric("cl", "—")
        self._set_metric("ld", f"M={out['mach']}")
        self._set_metric("drag", f"{out['drag_N']} N")
        self._set_metric("cells", "—")
        d = out.get("Cd_drift_pct")
        self._set_metric("verdict", f"drift {d}%" if d is not None else "✓")
        self._log(f"Cd(M={out['mach']}) = {out['Cd']}  |  {out['U_ms']} m/s  |  "
                  f"drag {out['drag_N']} N")
        self._log(out.get("_not", ""))
        self.btn_run.setEnabled(True)
        self.btn_polar.setEnabled(True)
        self.btn_mach.setEnabled(True)
        self._record_learning(out)

    def _run_polar(self):
        if not self.model_path:
            return
        try:
            alphas = [float(x) for x in self.edt_alphas.text().replace(";", ",").split(",")
                      if x.strip()]
        except ValueError:
            QMessageBox.warning(self, "α listesi", "Virgülle ayrılmış sayılar girin: -4, 0, 4, 8")
            return
        if len(alphas) < 2:
            QMessageBox.warning(self, "α listesi", "En az 2 hücum açısı gerekli.")
            return
        if self.cmb_nose.currentText()[1] == self.cmb_up.currentText()[1]:
            QMessageBox.warning(self, "Eksen hatası", "Burun ve üst eksenleri dik olmalı.")
            return
        self.btn_run.setEnabled(False)
        self.btn_polar.setEnabled(False)
        self.btn_report.setEnabled(False)
        self.progress.setValue(0)
        self.log.clear()
        self._log(f"Polar taraması: α = {alphas}")
        params = {
            "stl_path": self.model_path,
            "vehicle_type": self.cmb_type.currentData(),
            "velocity": self.spn_v.value(),
            "alphas": alphas,
            "quality": self.cmb_quality.currentData(),
            "n_layers": self.spn_layers.value(),
            "nose_axis": self.cmb_nose.currentText(),
            "up_axis": self.cmb_up.currentText(),
            "n_processors": self.spn_proc.value(),
        }
        self.worker = PolarWorker(params)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_polar_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _on_polar_done(self, out: dict):
        self.progress.setValue(100)
        self._log("✅ Polar tamamlandı.")
        for row in out["polar"]:
            self._log(f"  α={row['alpha']}°: Cl={row.get('Cl')} Cd={row.get('Cd')} "
                      f"Cm={row.get('Cm')}")
        self.last_result = type("R", (), {"report": out.get("report", "")})()
        self.btn_report.setEnabled(bool(out.get("report")))
        self.btn_run.setEnabled(True)
        self.btn_polar.setEnabled(True)
        self._log(f"Rapor: {out.get('report')}")

    def _run_fea(self):
        if not self.model_path:
            return
        run_dir = Path("vehicle_runs") / self.model_path.stem
        if not (run_dir / "sonuc.json").exists():
            QMessageBox.warning(self, "FEA", "Önce ANALİZ ET ile CFD koşusu tamamlanmalı.")
            return
        self.btn_fea.setEnabled(False)
        self.btn_run.setEnabled(False)
        self.progress.setValue(0)
        self._log(f"Yapısal kontrol: {self.cmb_mat.currentText()} / "
                  f"{self.cmb_fix.currentText()}")
        self.worker = FEAWorker({
            "run_dir": run_dir,
            "material": self.cmb_mat.currentData(),
            "constraint": self.cmb_fix.currentData(),
            "model": self.cmb_femodel.currentData(),
            "shell_thickness_mm": self.spn_thick.value(),
            "g_yuk": self.spn_gyuk.value(),
            "itki_n": self.spn_itki.value(),
            "delta_t": self.spn_dt.value(),
        })
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_fea_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _on_fea_done(self, out: dict):
        self.progress.setValue(100)
        self._log("✅ Yapısal kontrol tamamlandı.")
        self._log(f"  Max sehim: {out['max_sehim_mm']} mm | "
                  f"von Mises: {out['max_von_mises_MPa']} MPa | "
                  f"SF: {out['emniyet_faktoru']}")
        self._set_metric("verdict",
                         f"SF={out['emniyet_faktoru']}" if out.get("emniyet_faktoru") else "FEA ✓")
        self._log("Rapora Bölüm 7 eklendi (Raporu Aç ile gör).")
        self.btn_fea.setEnabled(True)
        self.btn_run.setEnabled(True)
        self.btn_report.setEnabled(True)

    def _log(self, msg: str):
        self.log.appendPlainText(msg)

    def _on_progress(self, pct: int, msg: str):
        self.progress.setValue(pct)
        self._log(f"[{pct:3d}%] {msg}")

    def _set_metric(self, key: str, value: str):
        title, lab = self.metric_labels[key]
        lab.setText(f"{title}\n{value}")

    def _on_done(self, r):
        self.last_result = r
        self.progress.setValue(100)
        self._log("✅ Analiz tamamlandı.")
        self._set_metric("cd", f"{r.cd}")
        self._set_metric("cl", f"{r.cl}" if r.cl is not None else "—")
        self._set_metric("ld", f"{r.ld}" if r.ld is not None else "—")
        self._set_metric("drag", f"{r.drag_N} N")
        cells = (r.mesh or {}).get("cells")
        self._set_metric("cells", f"{cells:,}" if cells else "—")
        conv = r.convergence or {}
        ok = conv.get("drift_ok") and conv.get("rezidual_ok")
        self._set_metric("verdict", "✅ yakınsadı" if ok else "⚠️ sınırda")
        self.btn_report.setEnabled(bool(r.report))
        self.btn_run.setEnabled(True)
        self._log(f"Rapor: {r.report}")
        self._record_learning({"Cd_toplam": getattr(r, "cd", None)})

    def _on_fail(self, err: str):
        self.progress.setValue(0)
        self._log("❌ HATA:\n" + err)
        self._pending_learn = None   # başarısız koşudan öğrenme
        self.btn_run.setEnabled(True)
        self.btn_polar.setEnabled(True)
        if hasattr(self, "btn_mach"):
            self.btn_mach.setEnabled(True)
        QMessageBox.critical(self, "Analiz başarısız",
                             "Detay için log panelini ve case dizinindeki "
                             "log.* dosyalarını inceleyin.")

    def _open_report(self):
        if self.last_result and self.last_result.report:
            os.startfile(self.last_result.report)  # noqa: S606


def main():
    app = QApplication(sys.argv)
    win = AnalyzerWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
