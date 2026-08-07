"""GUI ekran görüntüsü — rapordaki arayüz figürleri, GERÇEK pencereden.

NEDEN: rapor arayüzü anlatıyor ama göstermiyordu. Elle çizilmiş bir "mockup"
koymak bu raporun kendi ilkesini çiğnerdi (her görsel yeniden üretilebilir
kanıttan gelir); bu yüzden görüntü uygulamanın kendisinden alınır.

NE YAPAR: `app_analyzer.AnalyzerWindow`'u açar, depodaki GERÇEK bir STL'i
yükler (geometri paneli ölçülen değerlerle dolar), pencereyi PNG'ye yazar.
Çözücü ÇALIŞTIRILMAZ — yakalanan şey kurulum ekranıdır.

DİKKAT: `app_analyzer` PySide6 kullanır. Süreçte önce PyQt5 yüklenirse iki Qt
bağlayıcısı aynı adres alanına girer ve süreç STATUS_STACK_BUFFER_OVERRUN ile
çöker (ölçüldü). Bu betik yalnız PySide6 içe aktarır.

    python experiments/gui_ekran_goruntusu.py
Çıktı: docs/figurler/gui_*.png
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "docs" / "figurler"
ORNEK_STL = KOK / "vehicle_runs" / "minihawk" / "minihawk_prep.stl"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "PyQt5" in sys.modules:
        print("HATA: PyQt5 zaten yüklü — iki Qt bağlayıcısı süreci çökertir")
        return 2
    from PySide6.QtWidgets import QApplication

    import app_analyzer

    CIKTI.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    w = app_analyzer.AnalyzerWindow()
    w.resize(1180, 780)
    w.show()
    app.processEvents()

    uretilen = []
    if ORNEK_STL.exists():
        # GERCEK geometri: panel olculen degerlerle dolsun, uydurma olmasin.
        w._load_model(ORNEK_STL)
        app.processEvents()
    else:
        print(f"UYARI: {ORNEK_STL} yok — geometri paneli boş yakalanacak")
    # SONUC PANELI GERCEK BIR KOSUDAN doldurulur: kayitli sonuc.json dataclass'a
    # geri yuklenip uygulamanin KENDI render yolundan (_on_done) gecirilir.
    # Ekrandaki her sayi boylece kanit dosyasindan gelir; hicbiri elle yazilmaz.
    sj = KOK / "vehicle_runs" / "minihawk" / "sonuc.json"
    if sj.exists():
        import json

        from vehicle_pipeline import VehicleAnalysisResult
        d = json.loads(sj.read_text(encoding="utf-8"))
        alanlar = set(VehicleAnalysisResult.__dataclass_fields__)
        r = VehicleAnalysisResult(**{k: v for k, v in d.items() if k in alanlar})
        w._on_done(r)
        app.processEvents()
    else:
        print(f"UYARI: {sj} yok — sonuç paneli boş yakalanacak")

    p = CIKTI / "gui_analiz_studyosu.png"
    w.grab().save(str(p))
    uretilen.append(p)

    # UC KIP — ayni pencere, ayni veri, farkli GORUNURLUK. Rapordaki iddia
    # ("kipler farkli yazilim yolu uretmez") ancak yan yana gorulunce
    # denetlenebilir; bu yuzden ucu de ayni kosunun sonucuyla yakalanir.
    from arayuz_kipleri import KIPLER
    for kip in KIPLER:
        w.cmb_kip.setCurrentIndex(KIPLER.index(kip))
        w._kip_degisti()
        app.processEvents()
        pk = CIKTI / f"gui_kip_{kip}.png"
        w.grab().save(str(pk))
        uretilen.append(pk)
    w.cmb_kip.setCurrentIndex(KIPLER.index("muhendis"))
    w._kip_degisti()
    app.processEvents()

    # Kosu gecmisi: depodaki TUM sonuc.json'lari tek tabloda gosterir.
    dlg = app_analyzer.KosularDialog(w)
    dlg.resize(1180, 470)
    dlg.show()
    app.processEvents()
    # Sutunlar varsayilan genislikte kirpiliyor ("0.01..."); figurde sayilar
    # OKUNABILIR olmali, yoksa ekran goruntusu bir sey KANITLAMAZ.
    dlg.tbl.resizeColumnsToContents()
    for _j in range(dlg.tbl.columnCount()):
        dlg.tbl.setColumnWidth(_j, max(dlg.tbl.columnWidth(_j), 74))
    app.processEvents()
    p2 = CIKTI / "gui_kosu_gecmisi.png"
    dlg.grab().save(str(p2))
    uretilen.append(p2)
    dlg.close()

    for x in uretilen:
        print(f"  ✓ {x.relative_to(KOK)}")
    print(f"\n{len(uretilen)} ekran görüntüsü -> {CIKTI.relative_to(KOK)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
