"""Analiz yolculuğu — kullanıcıyı adım adım ANALİZ MÜHENDİSİNE dönüştüren rehber motor.

Kullanıcı bir geometri yükleyince (auto_pilot cfg'sinden) sıralı bir yolculuk planı üretir:
her adımda YAPILACAK + NEDEN (mentor ders bloğu, seviyeli) + KONTROL SORUSU + İPUCU.
Adımlar tamamlandıkça öğrenci profili (ogrenci_profili.json) büyür; seviye (BYF→ÖYG→PROJE)
DETERMİNİSTİK ve açıklanabilir kuralla ilerler — kara-kutu değerlendirme yok.

Kontrol soruları cevap-anahtarsızdır (öz-açıklama pedagojisi): amaç puanlama değil,
kullanıcının kararın 'neden'ini kendi kelimeleriyle kurması. GUI/CLI soruyu gösterir,
kullanıcı düşünüp adımı işaretler.

CLI: python yolculuk.py plan <stl>   |   durum   |   tamamla <adim_adi>
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from mentor import egitim_notu

HERE = Path(__file__).resolve().parent
PROFIL = HERE / "ogrenci_profili.json"

# Seviye eşikleri (şeffaf kural): ÖYG = ≥3 tamamlanmış analiz; PROJE = ≥8 analiz VE
# en az bir kez doğrulama (GCI) + savunma adımı tamamlanmış.
ESIK_OYG = 3
ESIK_PROJE = 8

_ADIMLAR = {
    "geometri_kontrol": {
        "baslik": "1) Geometriyi tanı",
        "yapilacak": "Modelin boyutlarını, su-geçirmezliğini ve yönelimini kontrol et "
                     "(uygulama otomatik onarır ama SEN de bak — girdiyi tanımayan "
                     "mühendis çıktıyı savunamaz).",
        "soru": "Modelin en uzun boyutu kaç metre? Bu değer gerçek araç için mantıklı mı, "
                "yoksa birim mm kalmış olabilir mi?",
        "ipucu": "CAD ihracı çoğu zaman mm'dir; 50'den büyük 'metre' gördüysen şüphelen.",
        "ders": None,
    },
    "tip_onay": {
        "baslik": "2) Araç tipini onayla",
        "yapilacak": "Otopilotun sınıflandırmasını ve gerekçesini oku; katılmıyorsan "
                     "düzelt (düzeltmen sistemi de eğitir).",
        "soru": "Uygulama bu tipi hangi geometrik ipuçlarından çıkardı (incelik? "
                "yassılık? genişlik)?",
        "ipucu": "Plan metnindeki 'gerekçe' satırı tam bunu anlatır.",
        "ders": None,
    },
    "mesh_secim": {
        "baslik": "3) Mesh kalitesini seç",
        "yapilacak": "Kalite preset'ini (hizli/standart/hassas) ve mesh-öncülü uyarılarını "
                     "değerlendir; hız-doğruluk takasını BİLEREK seç.",
        "soru": "Cismin yüzeyine yakın yerde neden küçük hücre gerekir de uzakta "
                "büyük hücre yeterlidir?",
        "ipucu": "Değişimin hızlı olduğu yerde çözünürlük gerekir — sınır tabakası.",
        "ders": "mesh",
    },
    "ilk_kosu": {
        "baslik": "4) İlk koşuyu yap",
        "yapilacak": "Analizi başlat; koşarken rezidüel ve Cd eğrisini izle.",
        "soru": "Koşu bittiğinde ilk bakacağın İKİ şey ne olmalı (sonuç sayısı değil)?",
        "ipucu": "Yakınsama (drift+rezidüel) ve mesh kalite uyarıları — sayı sonra.",
        "ders": "yakinsama",
    },
    "yakinsama_kontrol": {
        "baslik": "5) Yakınsamayı yorumla",
        "yapilacak": "Rapordaki drift ve rezidüel satırlarını oku; ✅/⚠️ işaretlerinin "
                     "NEDENİNİ söyleyebilir ol.",
        "soru": "Rezidüeller 1e-4'ün altına indi ama Cd eğrisi hâlâ kayıyor — sonuca "
                "güvenir misin, ne yaparsın?",
        "ipucu": "residual≠force: kuvvet platosu ayrı kriterdir; koşuyu uzat.",
        "ders": "yakinsama",
    },
    "dogrulama_gci": {
        "baslik": "6) Mesh-bağımsızlık (GCI) çalış",
        "yapilacak": "--duyarlilik ile 3-mesh GCI koş; verdikti oku. Asimptotik değilse "
                     "bu bir başarısızlık DEĞİL — dürüst band ver (LSR).",
        "soru": "GCI %2 çıkan ve %40 çıkan iki analiz arasında tasarım kararı açısından "
                "ne fark var?",
        "ipucu": "%2 → sayı tasarımda kullanılabilir; %40 → yalnız A/B karşılaştırma.",
        "ders": "belirsizlik",
    },
    "cd_mach_tarama": {
        "baslik": "7) Cd-Mach taraması",
        "yapilacak": "Roket/füze için Cd'yi Mach ile tara (transonik→süpersonik); "
                     "drag-divergence tepesini ve süpersonik düşüşü gözle.",
        "soru": "Cd neden ses hızı civarında (M≈1) tepe yapar da M=3'te düşer?",
        "ipucu": "Dalga sürüklemesi transonikte doğar; süpersonikte Mach-açısı "
                 "daraldıkça dalga drag katsayısı düşer (sürtünme kalıcıdır).",
        "ders": "belirsizlik",
    },
    "zemin_etkisi": {
        "baslik": "3b) Zemin düzlemini kur",
        "yapilacak": "Kara aracında taban serbest-akış DEĞİL zemindir: clearance'ı "
                     "(şasi-yer boşluğu) gir ya da otomatik Ahmed-oranını (0.17·H) onayla.",
        "soru": "Aynı gövdeyi zeminli ve zeminsiz koşsan Cd neden farklı çıkar?",
        "ipucu": "Zemin, altdan akışı sıkıştırır ve iz yapısını değiştirir — Ahmed "
                 "deneyleri bu yüzden zeminlidir; zeminsiz Cd o referanslarla kıyaslanamaz.",
        "ders": "zemin",
    },
    "polar_tarama": {
        "baslik": "7) Polar taraması (Cl-α)",
        "yapilacak": "Birden çok hücum açısı koş; Cl-α eğrisini ve çalışma-zarfı "
                     "uyarısını incele.",
        "soru": "α=12°'de hesaplanan Cl'yi kanat tasarımında neden KULLANMAYIZ?",
        "ipucu": "Doğrulanmış zarf |α|≤8°; üstünde RANS stall'ı ~%45 düşük verir.",
        "ders": "aoa",
    },
    "fea_kontrol": {
        "baslik": "8) Yapısal kontrol (FEA)",
        "yapilacak": "CFD basınçlarını yapıya aktar; sehim, von Mises ve emniyet "
                     "faktörünü değerlendir.",
        "soru": "Sivri bir iç köşedeki tepe gerilme neden yanıltıcı olabilir?",
        "ipucu": "Tekillik: mesh inceldikçe büyür — temsili (%99) değerle karşılaştır.",
        "ders": "fea_sf",
    },
    "rapor_savunma": {
        "baslik": "9) Sonucu savun",
        "yapilacak": "Raporun geçerlilik-banner'ını ve belirsizlik bandını kullanarak "
                     "sonucu bir hakeme anlatır gibi 3 cümlede özetle.",
        "soru": "Sonucunu tek sayı olarak mı, band olarak mı raporlarsın? Neden?",
        "ipucu": "Bandsız mutlak sayı savunulamaz — V&V 20 çerçevesi tam bunun için.",
        "ders": "belirsizlik",
    },
}

_LIFTING = ("ucak", "tilt_rotor", "kanatli_vtol")
_SUPERSONIC = ("roket", "kanatli_roket", "kaldirici_govde")


def plan(cfg: dict, seviye: str | None = None) -> list[dict]:
    """auto_pilot cfg'sinden (tip/analiz) TİP-UYARLAMALI yolculuk planı: kanatlı→polar,
    roket→Cd-Mach, araba→zemin adımı. Her adım: baslik, yapilacak, soru, ipucu,
    ders_md (seviyeli mentor bloğu | None)."""
    seviye = seviye or profil_seviye()
    tip = cfg.get("tip", "genel")
    sira = ["geometri_kontrol", "tip_onay", "mesh_secim"]
    if tip == "araba":
        sira.append("zemin_etkisi")
    sira += ["ilk_kosu", "yakinsama_kontrol", "dogrulama_gci"]
    if tip in _LIFTING or cfg.get("analiz") == "polar":
        sira.append("polar_tarama")
    elif tip in _SUPERSONIC or cfg.get("analiz") == "cd_mach":
        sira.append("cd_mach_tarama")
    sira += ["fea_kontrol", "rapor_savunma"]
    out = []
    for ad in sira:
        a = _ADIMLAR[ad]
        ders = (egitim_notu({"tip": tip, "analiz": cfg.get("analiz"),
                             "fea": ad == "fea_kontrol"}, seviye)
                if a["ders"] else None)
        out.append({"ad": ad, "baslik": a["baslik"], "yapilacak": a["yapilacak"],
                    "soru": a["soru"], "ipucu": a["ipucu"], "ders_md": ders,
                    "seviye": seviye})
    return out


# ───────────────────── Öğrenci profili (ilerleme) ─────────────────────

def _profil_yukle() -> dict:
    if PROFIL.exists():
        try:
            return json.loads(PROFIL.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"analiz_sayisi": 0, "adimlar": {}, "gecmis": []}


def _profil_kaydet(p: dict) -> None:
    PROFIL.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")


def adim_tamamla(ad: str, profil_dosya: Path | None = None) -> dict:
    """Bir yolculuk adımını tamamlandı olarak işle; analiz-sayacı 'rapor_savunma'da artar
    (bir tam analiz döngüsü = savunulmuş rapor). Güncel profil döner."""
    global PROFIL
    if profil_dosya:
        PROFIL = Path(profil_dosya)
    if ad not in _ADIMLAR:
        raise ValueError(f"bilinmeyen adım: {ad} (geçerli: {list(_ADIMLAR)})")
    p = _profil_yukle()
    p["adimlar"][ad] = p["adimlar"].get(ad, 0) + 1
    if ad == "rapor_savunma":
        p["analiz_sayisi"] += 1
    p["gecmis"].append({"ts": time.strftime("%Y-%m-%d %H:%M"), "adim": ad})
    p["seviye"] = _seviye_from(p)
    _profil_kaydet(p)
    return p


def _seviye_from(p: dict) -> str:
    n = p.get("analiz_sayisi", 0)
    adim = p.get("adimlar", {})
    if n >= ESIK_PROJE and adim.get("dogrulama_gci") and adim.get("rapor_savunma"):
        return "proje"
    if n >= ESIK_OYG:
        return "oyg"
    return "byf"


def profil_seviye() -> str:
    return _seviye_from(_profil_yukle())


if __name__ == "__main__":
    import argparse
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cli = argparse.ArgumentParser()
    cli.add_argument("komut", choices=["plan", "durum", "tamamla"])
    cli.add_argument("arg", nargs="?")
    args = cli.parse_args()
    if args.komut == "plan":
        if not args.arg:
            sys.exit("plan için STL yolu gerekli")
        from auto_pilot import auto_configure
        cfg = auto_configure(args.arg)
        for a in plan(cfg):
            print(f"\n== {a['baslik']} [{a['seviye'].upper()}] ==")
            print("YAP:  " + a["yapilacak"])
            print("SORU: " + a["soru"])
            print("İPUCU:" + a["ipucu"])
            if a["ders_md"]:
                print(a["ders_md"])
    elif args.komut == "durum":
        p = _profil_yukle()
        p["seviye"] = _seviye_from(p)
        print(json.dumps(p, indent=2, ensure_ascii=False))
    else:
        if not args.arg:
            sys.exit("tamamla için adım adı gerekli")
        print(json.dumps(adim_tamamla(args.arg), indent=2, ensure_ascii=False))
