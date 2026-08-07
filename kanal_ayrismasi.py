"""Kanal ayrışması tarayıcı — BİR kanal söylüyor, ÖBÜRÜ susuyor.

`oksuz_alan` HİÇ okunmayan alanı yakalar. Bu tarayıcı bir adım ötesini
yakalar: alan okunuyor, ama yalnız BİR tüketici kanalında. Kullanıcı öbür
kanaldan bakıyorsa o bilgiyi hiç görmez.

Bu, bu depoda tekrar tekrar çıkan kusurun asıl biçimiydi ve HER SEFERİNDE
ELLE bulundu:

  - `kurulum` (yanlış ölçek/eksen/A_ref) raporun en üstünde "aşağıdaki tüm
    bölümleri geçersizler" diye duruyordu; arayüz alanı hiç okumuyordu. Ekranda
    makul görünümlü bir Cd vardı ve kullanıcı raporu açmadıkça öğrenmiyordu.
  - `gerilemeler` (bir çapraz-kontrol düştü, koşu sürdü) aynı durumdaydı.
  - `yapisal_hukum(...)["gerekce"]` arayüzde yazılıyor, raporda yazılmıyordu.

Elle tarama bir sonraki alan eklendiğinde tekrar tutmaz. Bu betik onu
mekanikleştirir.

SİMETRİ HEDEF DEĞİLDİR. Rapor geometri ayrıntısını, VTK yollarını, A_ref
kipini de yazar; arayüz özet gösterir ve göstermelidir. Bu yüzden çıktı bir
İDDİA değil İNCELEME LİSTESİDİR: incelenen ve gerekçesi yazılan her ayrışma
KABUL sözlüğüne geçer, izlenen sayı `incelenmemis`tir. (Aynı deyim
`sessiz_yutma` ve `arka_uc_sayaci` için de kullanılıyor.)

    python kanal_ayrismasi.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent

# Sonucu kullaniciya SUNAN kanallar. Uretici (vehicle_pipeline) burada yok:
# uretmek sunmak degildir.
KANALLAR = {
    "arayüz": "app_analyzer.py",
    "rapor": "vehicle_report.py",
}

URETICI = "vehicle_pipeline.py"

# Incelenmis ayrismalar: alan -> neden tek kanalda olmasi DOGRU.
# Bir alani buraya eklemek bilincli bir karardir; gerekce yazilmadan eklenmez.
KABUL = {
    "status": "koşu durumu; arayüz akışı buna göre dallanır, rapor zaten "
              "yalnız başarılı koşu için üretilir",
    "error": "hata metni; rapor üretilmediği için raporda karşılığı yok",
    "case_dir": "disk yolu; raporun kendisi o dizinde durur",
    "stl": "girdi dosyası yolu; rapor geometri bölümünde adıyla yazar",
    "report": "raporun kendi yolu; rapor kendi yolunu yazmaz",
    "kalite": "arayüzdeki mesh-kalite ön ayarı (hızlı/standart/hassas); "
              "rapor sonucu değil ayarı anlatmaz, hücre sayısını yazar",
    "aref_m2": "referans alan sayısı; arayüz Cd'yi gösterir, raporda "
               "katsayının tanımı tam yazılır",
    "aref_mode": "referans alan kipi; yukarıdakiyle birlikte gelir",
    "cd_wake": "iz-momentum çapraz kontrolü; arayüz özet Cd gösterir, "
               "çapraz kontrol raporun savunulabilirlik bölümünde",
    "cda_m2": "türetilmiş sürükleme alanı; arayüzde Cd ve kuvvet var",
    "cp_vtk": "figür üretimi için VTK yolu; arayüz 3B görüntüleyici değil",
    "kesit_vtk": "yukarıdakiyle aynı",
    "geometry": "geometri ayrıntısı (üçgen sayısı, su-geçirmezlik, alanlar); "
                "arayüz geometri panelinde ayrı gösterir",
    "mesh_duyarlilik": "GCI/LSR tablosu; arayüz bandı ±U%% olarak koşu "
                       "geçmişi tablosunda gösterir",
    "pervane": "aktüatör disk parametreleri; arayüzde pervane girdisi YOK "
               "(yalnız CLI) — bkz. test_giris_noktasi_esdegerligi",
    "sinir_tabaka": "y⁺ ve katman ölçümü; arayüz bunu uyarı metni olarak "
                    "`uyarilar` üzerinden gösterir",
    "validity": "zarf sınıfı; arayüz aynı bilgiyi `sonuc_kapisi` hükmüyle "
                "rozette gösterir",
}


def _alanlar() -> list[str]:
    sys.path.insert(0, str(KOK))
    from vehicle_pipeline import VehicleAnalysisResult as V
    return sorted(V.__dataclass_fields__)


def _desen(alan: str) -> re.Pattern:
    e = re.escape(alan)
    return re.compile(
        rf"""(\.{e}\b)|(\[["']{e}["']\])"""
        rf"""|(get\(\s*["']{e}["'])"""
        rf"""|(getattr\([^,)]+,\s*["']{e}["'])""")


def tara() -> list[dict]:
    kaynak = {ad: (KOK / yol).read_text(encoding="utf-8", errors="replace")
              for ad, yol in KANALLAR.items()}
    out = []
    for alan in _alanlar():
        d = _desen(alan)
        okuyan = [ad for ad, s in kaynak.items() if d.search(s)]
        if not okuyan or len(okuyan) == len(KANALLAR):
            continue                      # hic okunmuyor (oksuz_alan'in isi) ya da simetrik
        out.append({"alan": alan, "okuyan": okuyan,
                    "susan": [a for a in KANALLAR if a not in okuyan],
                    "kabul": KABUL.get(alan)})
    return out


def ozet() -> dict:
    b = tara()
    inc = [x for x in b if not x["kabul"]]
    return {"toplam": len(b), "kabul": len(b) - len(inc),
            "incelenmemis": len(inc), "bulgular": b}


def main() -> int:
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    o = ozet()
    print(f"Kanal ayrışması ({' / '.join(KANALLAR)}): {o['toplam']} alan\n")
    for x in o["bulgular"]:
        im = "  " if x["kabul"] else "→ "
        print(f"{im}{x['alan']:<20} okuyan: {','.join(x['okuyan']):<12} "
              f"susan: {','.join(x['susan'])}")
        if not x["kabul"]:
            print("     İNCELENMEMİŞ — gerekçe yazılmalı ya da eksik kanal düzeltilmeli")
    print(f"\n**Kabul edilmiş (gerekçesi KABUL'de yazılı):** {o['kabul']}")
    print(f"**İNCELENMEMİŞ:** {o['incelenmemis']} — asıl izlenen sayı")
    print("\nAyrışma, bir kusurun tek kanalda söylenmesidir: kullanıcı öbür "
          "kanaldan bakıyorsa kusurdan habersiz karar verir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
