"""Öksüz alan tarayıcı — ÜRETİLEN ama HİÇ OKUNMAYAN sonuç alanları.

NEDEN: bu depoda tekrar tekrar aynı kusur çıktı — bir büyüklük ÖLÇÜLÜYOR, sonuç
nesnesine yazılıyor, ama hiçbir tüketici onu okumuyor. Örnekler (hepsi ölçüldü):

  - `ref_bump="oto"` beş çağırandan yalnız birine ulaşmıştı
  - küp çapasının y⁺'ı ölçülüydü, çapa dosyasına hiç yazılmamıştı
  - `en_kucuk_boyut_m` yüzey kapısının imzasındaydı, gövdede hiç kullanılmıyordu
  - `fizik_kabul` FEA motorunda hesaplanıyordu, arayüz onu yok sayıyordu
  - `mesh_levels` arayüzden hiç geçmiyordu

Bu kusur sınıfı SESSİZDİR: hiçbir test kırılmaz, hiçbir log uyarmaz. Ölçüm
yapılır, maliyeti ödenir ve karar ondan habersiz verilir.

BU TARAYICI onu mekanikleştirir: sonuç dataclass'larının her alanı için, ONU
ÜRETEN modül DIŞINDA en az bir okuyucu var mı diye bakar.

OKUMA BİÇİMLERİ: `.alan`, `["alan"]`, `.get("alan")` ve `getattr(x, "alan")`.
Son biçim ilk sürümde YOKTU ve tarayıcı `pervane` alanını öksüz sanmıştı —
oysa `vehicle_report` onu tam da `getattr` ile okuyor. Aracın kendi yanlış
pozitifi, aracın kendi düzeltmesiyle kapandı.

KALAN SINIR: değişken adla erişim (`getattr(r, ad)`) ve `asdict()` üzerinden
dolaşma görülmez. Bu yüzden çıktı bir İDDİA değil, İNCELEME LİSTESİDİR;
incelenip gerekçesi yazılan alan muafiyet listesine geçer.

    python oksuz_alan.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent

# Alanin "uretildigi" yer — burada gecmesi TUKETIM sayilmaz.
URETICI = {
    "VehicleAnalysisResult": ("vehicle_pipeline.py",),
    "CFDResult": ("analysis/openfoam_runner.py",),
}

# Serilestirme yoluyla tuketilenler: sonuc.json'a yazilip disarida okunur.
# Bunlar dataclass alanı olarak aranmaz ama OKSUZ de degildir.
SERILESTIRME_MUAFI = {
    "status", "error", "case_dir", "stl", "report",
}


def _alanlar(sinif: str) -> list[str]:
    if sinif == "VehicleAnalysisResult":
        sys.path.insert(0, str(KOK))
        from vehicle_pipeline import VehicleAnalysisResult as V
        return sorted(V.__dataclass_fields__)
    sys.path.insert(0, str(KOK))
    from analysis.openfoam_runner import CFDResult as C
    return sorted(C.__dataclass_fields__)


def _kaynaklar() -> dict[str, str]:
    out = {}
    for p in KOK.rglob("*.py"):
        r = p.relative_to(KOK).as_posix()
        if r.startswith((".venv/", "_")) or "site-packages" in r:
            continue
        out[r] = p.read_text(encoding="utf-8-sig", errors="replace")
    return out


def tara() -> list[dict]:
    kaynak = _kaynaklar()
    bulgu = []
    for sinif, ureticiler in URETICI.items():
        for alan in _alanlar(sinif):
            if alan in SERILESTIRME_MUAFI:
                continue
            e = re.escape(alan)
            desen = re.compile(
                rf"""(\.{e}\b)|(\[["']{e}["']\])"""
                rf"""|(get\(\s*["']{e}["'])"""
                rf"""|(getattr\([^,)]+,\s*["']{e}["'])""")
            okuyan = [r for r, s in kaynak.items()
                      if r not in ureticiler and desen.search(s)]
            if not okuyan:
                bulgu.append({"sinif": sinif, "alan": alan,
                              "uretici": ureticiler[0]})
    return bulgu


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    b = tara()
    print(f"Öksüz alan (üretilir, üreticisi dışında hiç okunmaz): {len(b)}\n")
    for x in b:
        print(f"  {x['sinif']}.{x['alan']:<22} ← {x['uretici']}")
    if not b:
        print("  (yok)")
    print("\nÖksüz alan bir ölçümün boşa gitmesi demektir: maliyeti ödenir, "
          "karar ondan habersiz verilir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
