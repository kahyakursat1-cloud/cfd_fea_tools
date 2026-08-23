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
    QTableWidget,
    QTableWidgetItem,
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
            p = dict(self.params)
            # `duzeltici` bir ÇÖZÜCÜ argümanı değil, bu worker'ın yol seçimi;
            # run_vehicle_analysis'e geçerse TypeError olur.
            duzeltici_acik = p.pop("duzeltici", False)
            ilerleme = lambda pc, m: self.progress.emit(pc, m)   # noqa: E731

            if duzeltici_acik:
                from duzeltici_adaptor import duzelterek_analiz
                r, duzeltme = duzelterek_analiz(
                    p.pop("stl_path"), progress_cb=ilerleme, **p)
                # Sonuca İLİŞTİRİLİR, ayrı sinyal açılmaz: rapor ve arayüz
                # zaten sonucu taşıyor, ikinci bir kanal iki yerin ayrışması
                # demek olurdu.
                r.duzeltici = duzeltme
            else:
                r = run_vehicle_analysis(progress_cb=ilerleme, **p)

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


class KosularDialog(QDialog):
    """Koşu geçmişi: tüm sonuc.json'lar tek tabloda; 2 satır seç → A/B karşılaştırma
    (Δ% + belirsizlik-bandına göre ayırt-edilebilirlik hükmü — kosu_gecmisi.py)."""

    _KOL = [("ad", "Koşu"), ("tip", "Tip"), ("kalite", "Kalite"), ("hiz", "V"),
            ("alpha", "α"), ("cd", "Cd"), ("u_pct", "±U%"), ("cl", "Cl"),
            ("cells", "Hücre"), ("status", "Durum")]

    def __init__(self, parent):
        super().__init__(parent)
        import kosu_gecmisi
        self._kg = kosu_gecmisi
        self.setWindowTitle("📂 Koşu Geçmişi")
        self.resize(980, 560)
        lay = QVBoxLayout(self)
        self.kayitlar = kosu_gecmisi.tara()
        self.tbl = QTableWidget(len(self.kayitlar), len(self._KOL))
        self.tbl.setHorizontalHeaderLabels([b for _, b in self._KOL])
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        for i, k in enumerate(self.kayitlar):
            for j, (a, _) in enumerate(self._KOL):
                v = k.get(a)
                self.tbl.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))
        self.tbl.resizeColumnsToContents()
        lay.addWidget(self.tbl, 2)
        self.det = QTextBrowser()
        lay.addWidget(self.det, 1)
        row = QHBoxLayout()
        btn_cmp = QPushButton("⇄ Seçili İKİ koşuyu karşılaştır")
        btn_cmp.clicked.connect(self._karsilastir)
        row.addWidget(btn_cmp)
        btn_rapor = QPushButton("📄 Raporu Aç")
        btn_rapor.clicked.connect(self._rapor_ac)
        row.addWidget(btn_rapor)
        row.addStretch(1)
        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_close)
        lay.addLayout(row)

    def _secili(self) -> list[dict]:
        rows = sorted({i.row() for i in self.tbl.selectedIndexes()})
        return [self.kayitlar[r] for r in rows]

    def _karsilastir(self):
        sec = self._secili()
        if len(sec) != 2:
            self.det.setPlainText("Karşılaştırma için tam İKİ satır seçin (Ctrl+tık).")
            return
        c = self._kg.karsilastir(sec[0], sec[1])
        md = [f"## {c['A']}  ⇄  {c['B']}", "",
              "| Metrik | A | B | Δ% | Band |", "|---|---|---|---|---|"]
        for s in c["satirlar"]:
            # CIPLAK Δ% BIRAKILMAZ. Bandi olculmemis bir metrigin yuzde farki
            # tek basina hukum tasimaz; tabloda hangi satirin hukumlenebilir
            # oldugu YAZILI olmali, yoksa okuyan hepsini esit sanir.
            bt = s.get("band_tasir")
            md.append(f"| {s['metrik']} | {s['A']} | {s['B']} | "
                      f"{s['delta_pct'] if s['delta_pct'] is not None else '—'} | "
                      f"{bt or '⚠️ bu metriğin bandı ölçülmedi'} |")
        ay = c.get("ayirt_edilebilirlik")
        if ay and ay.get("band_rss_pct") is not None:
            md += ["", f"**Ayırt-edilebilirlik:** ΔCd %{ay['dCd_pct']} vs "
                       f"{ay['band_tipi']} band %{ay['band_rss_pct']} → **{ay['hukum']}**",
                   "", f"> Band seçimi: {ay['gerekce']}"]
        elif ay:
            md += ["", f"**Ayırt-edilebilirlik:** ΔCd %{ay['dCd_pct']} — "
                       f"**{ay['hukum']}**", "", f"> Band seçimi: {ay['gerekce']}"]
        else:
            # BAND YOKSA SATIR HIC YAZILMIYORDU. Kullanici iki ciplak sayiyi
            # yanyana gorup farki GERCEK saniyordu; oysa bandi olmayan iki
            # kosunun farki hakkinda hicbir sey soylenemez. "Olcemedim" ile
            # "fark yok" ayni sey degildir ve bu artik ekranda yaziyor.
            _eksik = [k["ad"] for k in (sec[0], sec[1]) if k.get("cd") is None]
            md += ["", "**Ayırt-edilebilirlik: HÜKÜM VERİLEMEZ** — Cd kaydı "
                       "olmayan koşu(lar): " + (", ".join(_eksik) or "—") +
                   ". İki sayının farkı, bantları bilinmeden gerçek sayılamaz; "
                   "mesh duyarlılık bandı için `--duyarlilik` ile yeniden koşun."]
        for u in c["uyarilar"]:
            md.append(f"\n> ⚠️ {u}")
        self.det.setMarkdown("\n".join(md))

    def _rapor_ac(self):
        sec = self._secili()
        if sec and sec[0].get("rapor") and Path(sec[0]["rapor"]).exists():
            os.startfile(sec[0]["rapor"])
        else:
            self.det.setPlainText("Seçili koşunun raporu yok/bulunamadı.")


class KuyrukDialog(QDialog):
    """İş kuyruğu görünümü: bekleyen/koşan/biten işler + worker başlat (ayrık süreç —
    GUI kapansa da kuyruk koşar; kilit dosyası ikinci worker'ı engeller)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("🗂 İş Kuyruğu")
        self.resize(820, 420)
        lay = QVBoxLayout(self)
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["Durum", "ID", "Model", "Tip", "Kalite", "Sonuç"])
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.tbl, 1)
        # KILIT DURUMU GORUNUR OLMALI: bayat kilit sessiz kaldiginda kullanici
        # "worker basladi" sanip bekliyor, oysa kuyruk bloke.
        self.lbl_kilit = QLabel("")
        self.lbl_kilit.setWordWrap(True)
        lay.addWidget(self.lbl_kilit)
        row = QHBoxLayout()
        btn_worker = QPushButton("▶ Worker Başlat")
        btn_worker.setToolTip("Bekleyen işleri sırayla koşan ayrık süreç başlatır; "
                              "zaten koşuyorsa kilit nedeniyle ikinci başlamaz.")
        btn_worker.clicked.connect(self._worker_baslat)
        row.addWidget(btn_worker)
        btn_yenile = QPushButton("⟳ Yenile")
        btn_yenile.clicked.connect(self._yenile)
        row.addWidget(btn_yenile)
        btn_iptal = QPushButton("✖ Seçili işi iptal et")
        btn_iptal.setToolTip("Yalnız 'bekliyor' işler iptal edilir; koşan iş "
                             "yarım bir case dizini bırakacağı için iptal edilmez.")
        btn_iptal.clicked.connect(self._iptal)
        row.addWidget(btn_iptal)
        btn_devam = QPushButton("↻ Yarım kalanları devam ettir")
        btn_devam.setToolTip("Worker çökerse ya da makine kapanırsa iş 'yarim' "
                             "kalır; sessizce yeniden koşulmaz, bu düğme ile "
                             "AÇIKÇA kuyruğa geri alınır.")
        btn_devam.clicked.connect(self._devam)
        row.addWidget(btn_devam)
        btn_temizle = QPushButton("🧹 Bitenleri temizle")
        btn_temizle.clicked.connect(self._temizle)
        row.addWidget(btn_temizle)
        row.addStretch(1)
        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_close)
        lay.addLayout(row)
        self._yenile()

    def _yenile(self):
        import kuyruk
        isler = kuyruk.listele()
        self.tbl.setRowCount(len(isler))
        for i, is_ in enumerate(isler):
            p = is_["params"]
            son = is_.get("sonuc") or {}
            hucre = [is_["durum"], is_["id"], Path(p["stl_path"]).name,
                     str(p.get("vehicle_type", "")), str(p.get("quality", "")),
                     (f"Cd={son.get('cd')} ±%{son.get('u_pct')}" if son.get("cd") is not None
                      else (son.get("hata", "") or "")[:60])]
            for j, v in enumerate(hucre):
                self.tbl.setItem(i, j, QTableWidgetItem(v))
        self.tbl.resizeColumnsToContents()
        k = kuyruk.kilit_durumu()
        yarim = sum(1 for i in isler if i["durum"] == "yarim")
        # Okunamayan kayit bir ISIN KAYBIDIR; tabloda yok ve sessiz kalirsa
        # kullanici "5 ekledim 4 goruyorum" ile bas basa kalir.
        _bozuk = kuyruk.bozuk_kayitlar()
        if _bozuk:
            self.lbl_kilit.setText(
                f"⚠ KUYRUK DOSYASINDA {len(_bozuk)} OKUNAMAYAN KAYIT "
                f"({'; '.join(_bozuk[:3])}) — o işler listede YOK.")
            return
        if not k["kilitli"]:
            self.lbl_kilit.setText("Worker koşmuyor." + (
                f"  ⚠ {yarim} iş YARIM kaldı — 'devam ettir' ile geri alınabilir."
                if yarim else ""))
        elif k.get("bayat"):
            self.lbl_kilit.setText(
                f"⚠ BAYAT KİLİT: sahibi PID {k['pid']} artık yaşamıyor (çökme ya da "
                "makine kapanması). Worker başlatıldığında kilit devralınacak.")
        else:
            self.lbl_kilit.setText(f"Worker koşuyor (PID {k['pid']})."
                                   if k.get("yasiyor") else
                                   f"Kilit PID {k['pid']}; süreç durumu sorulamadı — "
                                   "güvenli tarafta bırakıldı, kilit devralınmaz.")

    def _secili_id(self) -> str | None:
        r = sorted({i.row() for i in self.tbl.selectedIndexes()})
        return self.tbl.item(r[0], 1).text() if r else None

    def _iptal(self):
        import kuyruk
        is_id = self._secili_id()
        if not is_id:
            QMessageBox.information(self, "Kuyruk", "Önce bir satır seçin.")
            return
        r = kuyruk.iptal(is_id)
        if not r["ok"]:
            QMessageBox.warning(self, "İptal edilemedi", r.get("mesaj", ""))
        self._yenile()

    def _devam(self):
        import kuyruk
        kuyruk.yarim_isaretle()
        n = kuyruk.devam()
        QMessageBox.information(self, "Kuyruk",
                                f"{n} yarım iş yeniden kuyruğa alındı."
                                if n else "Yarım kalan iş yok.")
        self._yenile()

    def _worker_baslat(self):
        from PySide6.QtCore import QProcess
        ok = QProcess.startDetached(sys.executable,
                                    [str(Path(__file__).parent / "kuyruk.py"), "calis"],
                                    str(Path(__file__).parent))
        QMessageBox.information(self, "Kuyruk",
                                "Worker ayrık süreç olarak başlatıldı." if ok
                                else "Worker başlatılamadı.")

    def _temizle(self):
        import kuyruk
        kuyruk.temizle()
        self._yenile()


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
        self._son_otopilot_cfg = None    # 'neden bu ayarlar?' gerekcesi
        self._build_ui()
        self._kip_uygula()      # baslangicta kip gorunurlugu

    # ── UI ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)

        # Sol: girişler
        left = QVBoxLayout()

        # KIP SECICI — aynı yapılandırmanın üç yüzü. Kip yalnız GÖRÜNÜRLÜĞÜ
        # değiştirir; gizlenen alanın değeri korunur ve çözücüye aynen gider.
        # Farklı kipler farklı case kursaydı tek kanonik çekirdek ilkesi
        # bozulurdu (bkz. arayuz_kipleri).
        from arayuz_kipleri import KIP_ACIKLAMA, KIP_ETIKET, KIPLER
        gb_kip = QGroupBox("Çalışma kipi")
        kv = QVBoxLayout(gb_kip)
        self.cmb_kip = QComboBox()
        for k in KIPLER:
            self.cmb_kip.addItem(KIP_ETIKET[k], k)
        self.cmb_kip.setCurrentIndex(KIPLER.index("muhendis"))
        self.cmb_kip.currentIndexChanged.connect(self._kip_degisti)
        kv.addWidget(self.cmb_kip)
        self.lbl_kip = QLabel(KIP_ACIKLAMA["muhendis"])
        self.lbl_kip.setWordWrap(True)
        self.lbl_kip.setStyleSheet("color:#9aa0a6; font-size:11px;")
        kv.addWidget(self.lbl_kip)
        left.addWidget(gb_kip)

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
        self._form_cfg = form
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
        # DÜZELTİCİ VARSAYILAN KAPALI. Açıkken araç, guard bir kurulum kusuru
        # bulursa kurulumu onarıp YENİDEN KOŞAR — yani koşu süresi katlanabilir
        # ve kullanıcının seçtiği ayarlar değişir. İkisi de sürpriz olmamalı;
        # bu yüzden istem dışı değil, açıkça istenen bir davranıştır.
        self.chk_duzeltici = QCheckBox(
            "Düzeltici: kusur bulunursa kurulumu onar ve yeniden koş")
        self.chk_duzeltici.setToolTip(
            "Guard bir kurulum kusuru bulursa (duvar işlemi ağa uymuyor, çözüm "
            "patlıyor, katsayı fiziksel değil) araç kurulumu düzeltip yeniden "
            "koşar.\nSONUÇ DEĞİŞTİRİLMEZ — yalnız kurulum değişir ve her "
            "müdahale rapora yazılır.\nDüzeltilemeyen kusurlar da gerekçesiyle "
            "raporlanır.\nKoşu süresi düzeltme başına katlanır.")
        form.addRow("", self.chk_duzeltici)
        # YERLEŞİK REFERANS (isteğe bağlı). Beyan edilirse sapma hükme girer:
        # yakınsamış ama referanstan uzak bir koşu tasarım sınıfı ALMAZ
        # (CD_REFERANS_HATASI). CLI/REST bunu zaten yapabiliyordu; arayüzde
        # girdi YOKTU ve bu bir borç olarak kayıtlıydı.
        # 0 = beyan yok → kapı hiç kurulmaz, davranış eskisi gibi.
        self.spn_ref_cd = QDoubleSpinBox()
        self.spn_ref_cd.setRange(0.0, 10.0)
        self.spn_ref_cd.setDecimals(4)
        self.spn_ref_cd.setSingleStep(0.01)
        self.spn_ref_cd.setValue(0.0)
        self.spn_ref_cd.setSpecialValueText("— beyan yok")
        self.spn_ref_cd.setToolTip(
            "Bu geometri için YERLEŞİK bir referans Cd biliyorsanız girin "
            "(ör. küp 1.05, Ahmed 25° 0.285).\nSapma, koşunun kendi belirsizlik "
            "bütçesini (u_val) aşarsa C_D tasarım kararında KULLANILMAZ olarak "
            "işaretlenir.\nBoş bırakılırsa (— beyan yok) hüküm yalnız ağ "
            "bandına dayanır; davranış değişmez.")
        form.addRow("Referans C_D (varsa):", self.spn_ref_cd)
        # SEVIYE SAYISI ARAYUZDE YOKTU: GUI `mesh_levels`'i hic gecmiyordu, yani
        # her zaman varsayilan 3 seviye kosuyordu. LSR (Eca-Hoekstra) EN AZ 4
        # grid ister — yani arayuz kullanicisi LSR bandini HIC alamiyordu,
        # yalnizca GCI. CLI 4 seviye yapabiliyordu. Ayni motorun iki kullanicisi
        # farkli V&V yeteneğine sahipti.
        self.spn_seviye = QSpinBox()
        self.spn_seviye.setRange(3, 4)
        self.spn_seviye.setValue(3)
        self.spn_seviye.setToolTip("Duyarlılık kademesi sayısı. 4 seviye LSR "
                                   "(Eça–Hoekstra) bandını açar; 3 seviye yalnız "
                                   "GCI verir.")
        form.addRow("Duyarlılık seviyesi", self.spn_seviye)
        # OTOPILOT PLANI — gizlenen ayarlar SILINMEZ, burada salt-okunur
        # gosterilir. "Karmasikligi gizle ama izlenebilirligi kaybetme"
        # kuralinin arayuzdeki karsiligi budur.
        self.gb_plan = QGroupBox("Otomatik seçilen ayarlar")
        pv = QVBoxLayout(self.gb_plan)
        self.lbl_plan = QLabel("Bir model yükleyin — plan burada görünecek.")
        self.lbl_plan.setWordWrap(True)
        self.lbl_plan.setStyleSheet("color:#c8c8c8; font-size:11px;")
        pv.addWidget(self.lbl_plan)
        self.btn_plan_neden = QPushButton("❓ Neden bu ayarlar?")
        self.btn_plan_neden.clicked.connect(self._plan_gerekce)
        pv.addWidget(self.btn_plan_neden)
        left.addWidget(self.gb_plan)
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

        hq = QHBoxLayout()
        self.btn_queue_add = QPushButton("➕ Kuyruğa Ekle")
        self.btn_queue_add.setEnabled(False)
        self.btn_queue_add.setToolTip("Bu formdaki ayarlarla işi kuyruğa yaz — hemen koşmaz; "
                                      "worker sırayla koşar (5 varyant + yemeğe git).")
        self.btn_queue_add.clicked.connect(self._kuyruga_ekle)
        hq.addWidget(self.btn_queue_add)
        btn_queue = QPushButton("🗂 Kuyruk")
        btn_queue.setToolTip("Kuyruk görünümü: bekleyen/koşan/biten işler + worker başlat.")
        btn_queue.clicked.connect(lambda: KuyrukDialog(self).exec())
        hq.addWidget(btn_queue)
        left.addLayout(hq)

        # KANIT GEZGINI — yalniz arastirma kipinde. Yayimlanacak bir sayi
        # uretiliyorsa hangi kanit dosyasinin hangi ortamda uretildigi
        # gorulebilmeli; bu, raporun "kanitin ortami da kanitin parcasidir"
        # ilkesinin arayuzdeki karsiligi.
        self.btn_kanit = QPushButton("🔬  KANIT GEZGİNİ (V&V dosyaları)")
        self.btn_kanit.setToolTip("Kanıt dosyaları, hükümleri, üretim komutları "
                                  "ve ortam damgaları.")
        self.btn_kanit.clicked.connect(self._kanit_gezgini)
        left.addWidget(self.btn_kanit)

        self.btn_yolculuk = QPushButton("🎓  REHBERLİ MOD (adım adım öğren)")
        self.btn_yolculuk.setEnabled(False)
        self.btn_yolculuk.setToolTip(
            "Analiz-mühendisi yolculuğu: her adımda ne yapılacağı, NEDENİ ve bir kontrol "
            "sorusu. Adımları tamamladıkça profiliniz BYF→ÖYG→PROJE seviye atlar.")
        self.btn_yolculuk.clicked.connect(self._open_yolculuk)
        left.addWidget(self.btn_yolculuk)

        self.gb_polar = gb_polar = QGroupBox("Polar Taraması (opsiyonel)")
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

        self.gb_fea = gb_fea = QGroupBox("Yapısal Kontrol (CFD basınçlarıyla)")
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
        grid.addWidget(self.btn_report, 2, 0, 1, 2)
        btn_kosular = QPushButton("📂  Koşular")
        btn_kosular.setToolTip("Tüm koşu geçmişi: tablo + A/B karşılaştırma "
                               "(belirsizlik-bandına göre ayırt-edilebilirlik hükmüyle).")
        btn_kosular.clicked.connect(lambda: KosularDialog(self).exec())
        grid.addWidget(btn_kosular, 2, 2)
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

    # ── Kipler ──────────────────────────────────────────────────────────────
    def _kip(self) -> str:
        from arayuz_kipleri import kip_dogrula
        return kip_dogrula(self.cmb_kip.currentData())

    def _kip_degisti(self):
        from arayuz_kipleri import KIP_ACIKLAMA
        k = self._kip()
        self.lbl_kip.setText(KIP_ACIKLAMA[k])
        self._kip_uygula()

    def _kip_uygula(self):
        """Görünürlüğü kipe göre ayarla — DEĞERLERE DOKUNMADAN.

        Gizlemek sıfırlamak değildir: gizlenen alanın değeri korunur ve
        `_params` onu aynen çözücüye taşır. Aksi hâlde kullanıcının göremediği
        bir ayar sessizce değişirdi ve bu, deponun avladığı kusur sınıfının ta
        kendisi olurdu.
        """
        from arayuz_kipleri import gorunur_mu
        k = self._kip()
        for ad in ("cmb_rejim", "spn_mach", "cmb_quality", "cmb_nose", "cmb_up",
                   "spn_proc", "spn_layers", "spn_yplus", "chk_sens",
                   "spn_seviye"):
            w = getattr(self, ad, None)
            if w is None:
                continue
            gor = gorunur_mu(ad, k)
            w.setVisible(gor)
            et = self._form_cfg.labelForField(w)
            if et is not None:
                et.setVisible(gor)
        for ad in ("btn_queue_add", "gb_polar", "gb_fea", "btn_kanit"):
            w = getattr(self, ad, None)
            if w is not None:
                w.setVisible(gorunur_mu(ad, k))
        # Plan kutusu YALNIZ otopilotta: öbür kiplerde ayarlar zaten görünür.
        self.gb_plan.setVisible(k == "otopilot")
        if k == "otopilot":
            self._plan_yenile()

    def _plan_ozeti(self) -> list[str]:
        """Gizlenen ayarların ŞU ANKİ değerleri — çözücüye gidecek olanlar."""
        return [
            f"Akış rejimi: {self.cmb_rejim.currentText()}",
            f"Mesh kalitesi: {self.cmb_quality.currentText()}",
            f"Burun/üst eksen: {self.cmb_nose.currentText()} / "
            f"{self.cmb_up.currentText()}",
            f"Sınır tabaka katmanı: {self.spn_layers.value()}",
            f"Hedef y⁺: {self.spn_yplus.value():g}",
            f"İşlemci: {self.spn_proc.value() or 'otomatik'}",
        ]

    def _plan_yenile(self):
        self.lbl_plan.setText("• " + "\n• ".join(self._plan_ozeti()))

    def _plan_gerekce(self):
        """'Neden bu ayarlar?' — otopilotun kendi gerekçe metni."""
        metin = ["Şu an çözücüye gidecek ayarlar:", ""]
        metin += [f"  • {x}" for x in self._plan_ozeti()]
        cfg = getattr(self, "_son_otopilot_cfg", None)
        if cfg:
            metin += ["", "Otopilotun gerekçesi:"]
            metin += ([f"  • {u}" for u in (cfg.get("uyarilar") or [])]
                      or ["  (ek gerekçe yazılmadı)"])
        else:
            metin += ["", "Bu değerler ön ayardan geliyor. Geometriye göre "
                      "seçilmeleri için 🤖 OTOMATİK ANALİZ'i çalıştırın; "
                      "otopilot ölçtüğü gerekçeleri buraya yazar."]
        QMessageBox.information(self, "Ayarların gerekçesi", "\n".join(metin))

    def _kanit_gezgini(self):
        """Kanıt dosyaları + ortam damgası — araştırma kipinin V&V penceresi."""
        import json as _j
        satir = []
        damgali = damgasiz = 0
        for pth in sorted(Path(__file__).parent.glob("*.json")):
            try:
                d = _j.loads(pth.read_text(encoding="utf-8-sig"))
            # sessiz-yutma: kabul — bozuk/JSON-olmayan dosya gezginde atlanir;
            # asagidaki sayimda gorunmez ve kanit.py ayrica denetler
            except Exception:
                continue
            if not isinstance(d, dict) or not d.get("_uretim"):
                continue
            o = d.get("_ortam") or {}
            if o:
                damgali += 1
                dmg = f"✓ {o.get('python', '?')}"
                cz = (o.get("cozucu") or {}).get("openfoam")
                if cz:
                    dmg += f" · {cz}"
            else:
                damgasiz += 1
                dmg = "— damgasız (bu kanıt damga eklenmeden önce üretildi)"
            hukum = str(d.get("verdikt") or d.get("sonuc") or "")[:70]
            satir.append(f"{pth.name}\n    {dmg}\n    {hukum}")
        ust = (f"{damgali + damgasiz} kanıt · {damgali} ortam damgalı, "
               f"{damgasiz} damgasız\n"
               "Damgasız kanıtlar BİLEREK damgalanmadı: bugünkü ortamla "
               "damgalamak, o sayının bu yığında üretildiğini söylemek olurdu.\n")
        govde = "\n".join(satir[:25])
        if len(satir) > 25:
            govde += f"\n… +{len(satir) - 25} dosya"
        QMessageBox.information(self, "Kanıt gezgini", ust + "\n" + govde)

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
        self.btn_queue_add.setEnabled(True)

    def _kuyruga_ekle(self):
        if not self.model_path:
            return
        import kuyruk
        is_ = kuyruk.ekle({
            "stl_path": str(self.model_path),
            "vehicle_type": self.cmb_type.currentData(),
            "velocity": self.spn_v.value(),
            "alpha_deg": self.spn_aoa.value(),
            "quality": self.cmb_quality.currentData(),
            # ref_bump="oto": y+'i banda sokan tek kaldirac; geometri BASINA
            # hesaplanir. Bu satir olmadan GUI varsayilan (0) ile kosuyordu ve
            # olculen %83'luk basari orani kullanici-yuzu yolda GECERSIZDI.
            "ref_bump": "oto",
            "n_processors": self.spn_proc.value(),
            "nose_axis": self.cmb_nose.currentText(),
            "up_axis": self.cmb_up.currentText(),
            "mesh_sensitivity": self.chk_sens.isChecked(),
            "mesh_levels": self.spn_seviye.value(),
            "n_layers": self.spn_layers.value(),
            "yplus_target": self.spn_yplus.value(),
            "duzeltici": self.chk_duzeltici.isChecked(),
            # 0 = beyan yok → None geçilir, kapı kurulmaz.
            "referans_cd": (self.spn_ref_cd.value() or None),
        })
        n = sum(1 for i in kuyruk.listele() if i["durum"] == "bekliyor")
        self._log(f"🗂 Kuyruğa eklendi: {is_['id']} ({self.model_path.name}) — "
                  f"bekleyen iş: {n}. Worker için: Kuyruk → Worker Başlat.")

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
            # 'Neden bu ayarlar?' otopilotun KENDI gerekcesini gostersin —
            # yoksa otopilot kipinde gizlenen ayarlar gerekcesiz kalirdi.
            self._son_otopilot_cfg = cfg
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
        except Exception as e:
            # OGRENME SESSIZCE DUSUYORDU. Kutuphaneye vaka eklenmezse bir sonraki
            # kosunun onculu zayif kalir ve kullanici bunu HIC ogrenmez: ekranda
            # 'Ogrenme:' satiri yoktur, ama yoklugu bir sey soylemez. Kosu yine
            # bozulmaz (ogrenme yan urun), sebep yazilir.
            self._log(f"⚠ Öğrenme kaydı DÜŞTÜ ({type(e).__name__}: {e}) — bu koşu "
                      "kütüphaneye girmedi; sonraki koşunun öncülü zayıf kalır.")

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
            # ref_bump="oto": y+'i banda sokan TEK kaldirac. Bu satir kuyruk
            # yoluna eklenmisti ama ANA "ANALIZ ET" dugmesine eklenmemisti;
            # yani duzeltme bes cagiranin yalnizca birine ulasmisti ve
            # kullanicinin en cok kullandigi yol varsayilan (0) ile kosuyordu.
            "ref_bump": "oto",
            "n_processors": self.spn_proc.value(),
            "nose_axis": self.cmb_nose.currentText(),
            "up_axis": self.cmb_up.currentText(),
            "mesh_sensitivity": self.chk_sens.isChecked(),
            "mesh_levels": self.spn_seviye.value(),
            "n_layers": self.spn_layers.value(),
            "yplus_target": self.spn_yplus.value(),
            "duzeltici": self.chk_duzeltici.isChecked(),
            # 0 = beyan yok → None geçilir, kapı kurulmaz.
            "referans_cd": (self.spn_ref_cd.value() or None),
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
            "ref_bump": "oto",     # polar = tasimanin olculdugu yer; y+ kritik
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
        # ARAYUZ FIZIK KAPISINI YOK SAYIYORDU. CFD yolu `sonuc_kapisi`'ndan
        # geciyor ve fizik-disi Cd'yi isaretliyor; FEA yolu ise ciplak
        # `emniyet_faktoru`'nu basiyordu. Motor `fizik_kabul`'u ZATEN
        # hesapliyordu (stress_admissibility) — arayuze ulasmiyordu.
        # En tehlikeli hal: yuk hic aktarilmamissa ccx temiz cikar, gerilme ~0,
        # SF astronomik olur ve ekran "SF=9999" yazar. Hukum artik tek kaynaktan
        # (vehicle_fea.yapisal_hukum) gelir — rapor da ayni kurali kullanir.
        from vehicle_fea import yapisal_hukum
        self.progress.setValue(100)
        self._log("✅ Yapısal kontrol tamamlandı.")
        h = yapisal_hukum(out)
        self._log(f"  Max sehim: {out['max_sehim_mm']} mm | "
                  f"von Mises: {out['max_von_mises_MPa']} MPa | "
                  f"SF (tepe): {out['emniyet_faktoru']}"
                  + (f" | SF (temsili): {h['sf_temsili']}" if h.get("tekillik") else ""))
        self._log(f"  Hüküm: {h['metin']}")
        for g in h["gerekce"]:
            self._log(f"⚠ {g}")
        self._set_metric("verdict",
                         h["metin"] if h["engel"] else
                         (f"SF={h['sf']}" if h["sf"] else "FEA ✓"))
        if h["engel"]:
            QMessageBox.warning(
                self, "Yapısal sonuç kapıdan geçmedi",
                "\n".join(h["gerekce"])
                + "\n\nBu emniyet faktörü TASARIM KARARINDA KULLANILMAZ.")
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

    @staticmethod
    def _ref_hata_pct(r):
        """Beyan edilen referansa göre sapma [%]; beyan yoksa None.

        Sonuç `referans_cd`'yi TAŞIR (boru hattı koyar), yani arayüz kendi
        girdisini hatırlamak zorunda değil --- hüküm koşunun kendi kaydından
        kurulur ve rapor ile aynı sayıya dayanır.
        """
        ref, cd = getattr(r, "referans_cd", None), getattr(r, "cd", None)
        if not ref or cd is None:
            return None
        return abs(cd - ref) / abs(ref) * 100.0

    def _qoi_siniflari(self, r) -> dict:
        """QoI başına geçerlilik sınıfı — raporun banner'ıyla AYNI kaynaktan.

        `classify_cfd` C_L/C_D/(L/D) için ayrı hüküm üretiyor ve rapor bunu en
        üstte gösteriyordu; arayüz hiç okumuyordu. Aynı kanal-ayrışması sınıfı:
        bir sayının "tasarım kararında kullanılabilir" olup olmadığı raporda
        yazıyor, ekranda yazmıyordu.
        """
        try:
            from validity_envelope import (
                OUT,
                TREND,
                VALIDATED,
                apply_ince_ozellik_gate,
                apply_physics_gate,
                classify_cfd,
            )
            _mds = getattr(r, "mesh_duyarlilik", None) or {}
            v = classify_cfd(
                getattr(r, "vehicle_type", "genel"), r.alpha_deg or 0.0,
                (r.velocity or 0.0) / 340.0,
                has_gci_band=bool(_mds.get("gci"))
                and str(_mds.get("verdikt", "")).startswith("✅"),
                band_pct=_mds.get("fark_pct"),
                # Arayüz artık referans BEYAN EDEBİLİYOR; rozetin de o hükmü
                # göstermesi gerekir. Geçirilmezse rapor bir hüküm, ekran
                # başka bir hüküm verir --- kanal ayrışması tarayıcısı bunu
                # "rapor okuyor, arayüz susuyor" diye yakaladı.
                referans_hata_pct=self._ref_hata_pct(r),
                u_val_pct=((r.belirsizlik or {}).get("u_toplam_pct")
                           if getattr(r, "belirsizlik", None) else None))
            v = apply_physics_gate(v, getattr(r, "fizik_kabul", None) or {})
            v = apply_ince_ozellik_gate(
                v, ((getattr(r, "sinir_tabaka", None) or {})
                    .get("yuzey_cozunurlugu") or {}).get("geometri_goreli"))
            # GECIS ve SUBKRITIK kapilari — ayni yardimcilar IKI kanalda da.
            from validity_envelope import _gecis_kapisi, _subkritik_uyari
            v = _gecis_kapisi(v, r)
            _subk = _subkritik_uyari(r)
            if _subk.get("tetiklendi"):
                self._log("\n🔴 " + _subk["hukum"])
            im = {VALIDATED: "\n✅ tasarım", TREND: "\n🟡 eğilim",
                  OUT: "\n🔴 zarf-dışı"}
            out = {}
            for x in v:
                ad = ("C_D" if x.quantity.startswith("C_D") else
                      "C_L" if x.quantity.startswith("C_L") else
                      "L/D" if x.quantity.startswith("L/D") else None)
                if ad:
                    out[ad] = im.get(x.klass, "")
            return out
        # sessiz-yutma: kabul — sınıf rozeti EK bilgidir; üretilemezse kart
        # değeri ve bandı yine gösterilir, hüküm rozeti de günlükte durur
        except Exception:
            return {}

    def _on_done(self, r):
        from validity_envelope import rejim_arac_tipinden, sonuc_kapisi
        self.last_result = r
        self.progress.setValue(100)
        # KOSUM KOSULU SONUCUN KENDISINDEN yazilir, formdan DEGIL. Ekrandaki
        # metrikler bir kosuya aittir ama form o sirada degistirilmis olabilir
        # (ozellikle kuyrukta: tek pencere, cok kosu). Formdan okumak, ekranda
        # yanlis kosum kosuluyla dogru sayilar gostermek demektir.
        self._log(f"✅ Analiz tamamlandı — V={r.velocity} m/s, α={r.alpha_deg}°")
        # KOSU BAGLAMI: salinan kosuya URANS recetesi ancak uzunluk/hiz/maliyet
        # bilinirse hesaplanabilir. Bunlari gecmemek, "kesin cozum URANS'tir"
        # cumlesini uygulanamaz birakir.
        _geo = getattr(r, "geometry", None) or {}
        # Cozucu maliyeti asama telemetrisinden gelir: foamRun asamasi hem sure
        # hem iterasyon tasir, yani URANS tahmini AYNI agda AYNI makinede olculmus
        # iterasyon maliyetine dayanir — uydurma bir katsayiya degil.
        _fr = next((a for a in (getattr(r, "asama_sureleri", None) or [])
                    if a.get("asama") == "foamRun"), {})
        kapi = sonuc_kapisi(getattr(r, "fizik_kabul", None), r.convergence,
                            getattr(r, "belirsizlik", None),
                            kosu={"lref_m": _geo.get("lmax_m"),
                                  "velocity": r.velocity,
                                  "rejim": rejim_arac_tipinden(
                                      getattr(r, "vehicle_type", None)),
                                  "sure_s": _fr.get("sure_s"),
                                  "iterasyon": _fr.get("iterasyon")})
        # EKRANDA CIPLAK SAYI OLMAMALI — rapor bunu ilke olarak yaziyordu ama
        # kartlar C_D'yi bandsiz gosteriyordu. Her metrik ya BANDIYLA ya da
        # bandin nicin hesaplanmadigini soyleyen etiketle gosterilir; QoI
        # sinifi (DOGRULANMIS/EGILIM) da rapor banner'inda vardi, arayuzde
        # yoktu — ayni ayrisma sinifi.
        _u = (getattr(r, "belirsizlik", None) or {}).get("u_toplam_pct")
        _band = (f" ±%{_u:.2f}" if isinstance(_u, (int, float))
                 else "\nband YOK (mesh-duyarlılık koşulmadı)")
        _sinif = self._qoi_siniflari(r)
        self._set_metric("cd", f"{r.cd}{_band}"
                         + (" ⛔" if kapi["seviye"] == "engel" else "")
                         + _sinif.get("C_D", ""))
        self._set_metric("cl", (f"{r.cl}{_sinif.get('C_L', '')}"
                                if r.cl is not None else "—"))
        self._set_metric("ld", (f"{r.ld}{_sinif.get('L/D', '')}"
                                if r.ld is not None else "—"))
        self._set_metric("drag", f"{r.drag_N} N")
        cells = (r.mesh or {}).get("cells")
        self._set_metric("cells", f"{cells:,}" if cells else "—")
        self._set_metric("verdict", kapi["etiket"])
        for g in kapi["gerekce"]:
            self._log(f"⚠ {g}")
        # KURULUM UYARILARI ARAYUZDE HIC GORUNMUYORDU. Rapor bunlari en uste
        # koyup "asagidaki tum bolumleri gecersizler" diyor (yanlis birim
        # olcegi, yanlis eksen, yanlis A_ref); arayuzde ise ekranda dogru
        # gorunumlu bir Cd duruyordu ve kullanici raporu acmadikca ogrenmiyordu.
        # Ana giris noktasi arayuz oldugu icin bu, raporda cozulmus bir tehlikeyi
        # uygulamada acik birakiyordu.
        kurulum = list(getattr(r, "kurulum", None) or [])
        for k in kurulum:
            self._log(f"🟠 KURULUM: {k}")
        # Guvence kayiplari: sonuc uretildi ama bir capraz-kontrol dustu.
        for gg in (getattr(r, "gerilemeler", None) or []):
            self._log(f"🟡 GÜVENCE KAYBI: {gg}")
        for u in (getattr(r, "uyarilar", None) or []):
            if u not in kurulum:
                self._log(f"⚠ {u}")
        self.btn_report.setEnabled(bool(r.report))
        self.btn_run.setEnabled(True)
        self._log(f"Rapor: {r.report}")
        if kapi["seviye"] == "engel":
            QMessageBox.warning(self, "Sonuç fizik kapısından geçmedi",
                                "\n".join(kapi["gerekce"]) +
                                "\n\nBu kuvvet katsayıları TASARIM KARARINDA KULLANILMAZ. "
                                "Mesh çözünürlüğünü (özellikle iz/wake bölgesi) artırın.")
        elif kurulum:
            # Kurulum kusuru fizik kapisindan GECEBILIR: sayilar kendi
            # iclerinde tutarli ama YANLIS problemin cevabidir. Sessiz kalirsa
            # ekranda makul gorunen bir Cd tasarim kararina girer.
            QMessageBox.warning(
                self, "Kurulum uyarısı — sayılar başka bir problemi anlatıyor",
                "\n".join(kurulum)
                + "\n\nÇözüm sayısal olarak geçerli olabilir; ancak ölçek, eksen "
                  "ya da referans alan yanlışsa katsayılar bu geometriye ait "
                  "DEĞİLDİR. Raporun tamamını okumadan karar vermeyin.")
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
