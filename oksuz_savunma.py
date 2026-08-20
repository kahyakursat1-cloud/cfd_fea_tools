"""Öksüz savunma tarayıcı — HÜKÜM üreten ama HİÇ ÇAĞRILMAYAN fonksiyonlar.

NEDEN: `oksuz_alan` üretilip okunmayan ALANLARI yakalıyor. Bu tarayıcı bir
kademe yukarısını yakalar: fonksiyonun kendisi hiç çağrılmıyor. Bu deponun
kayıtlı baskın kusuru tam olarak budur — kapı VAR ama üretim yolu onu
çağırmıyor:

  - `duvar_hukmu` küre koşusunu zaten reddediyordu; bandı üreten yol ona hiç
    sormuyordu → `bluff.wall_function` %8,15'ten %69,85'e çıktı (8,5 kat)
  - `salinim_analizi` hesaplanıyordu, tüketicisi yoktu → salınan çözüme
    "yakınsadı" dendi
  - `birim_uyarisi` üretilse de `info` sözlüğünde ölü kalacaktı; yalnız
    `auto_configure`'a bağlanınca kullanıcıya ulaştı

ÖLÇER AİLESİNDEKİ BOŞLUK: `sessiz_yutma`, `kanal_ayrismasi`, `oksuz_alan` ve
`kanit` dördü de bu sınıfı görmüyor — hiçbiri "fonksiyon tanımlı ama çağrılmıyor"
sorusunu sormuyor. Bu tarayıcı onu sorar.

DÜRÜSTLÜK NOTU: bu araç `urans_kapisi.frekans_capraz_kontrol` öksüz sanıldığı
için yazıldı; o iddia YANLIŞ çıktı — `experiments/silindir_des_3b.py:357` onu
çağırıyor ve sonucunu çıktıya yazıyor. Yanılgının kaynağı çok satırlı
`from x import (...)` bloğunun içine bakmayan bir aramaydı. Aracın kendisi
geçerli: sınıf gerçek (yukarıdaki üç olay ölçülü) ve şu anda AÇIK madde yok.
Araç bundan sonrakini yakalamak için duruyor.

YÖNTEM: adı ya da dönüş şekli HÜKÜM ürettiğini gösteren fonksiyonlar aranır,
sonra çağrıları AST ile sayılır (grep çok satırlı çağrıda ve `from x import y`
sonrası yalın adda yanılır). Testlerdeki çağrı SAYILMAZ: bir savunmanın yalnız
testten çağrılması, üretim yolunun ondan geçmediği anlamına gelir.

KALAN SINIR: dolaylı çağrı (getattr, sözlükten fonksiyon seçme, dekoratör
kaydı) görülmez. Bu yüzden çıktı bir İDDİA değil İNCELEME LİSTESİDİR;
incelenip gerekçesi yazılan fonksiyon muafiyet listesine geçer — [[kanit]]
ve `sessiz_yutma` ile aynı sözleşme.

    python oksuz_savunma.py            # tablo
    python oksuz_savunma.py --json     # oksuz_savunma.json
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent

# HUKUM izi: ad savunma/karar uretimini ima ediyor.
AD_IZI = re.compile(r"kapi|gate|hukum|hüküm|dogrula|doğrula|gecerli|geçerli"
                    r"|guard|reddet|denetle|kontrol|uyari|uyarı|capraz|çapraz",
                    re.I)

# TANIM yalniz urun katmaninda aranir; CAGRI ise deneylerde de sayilir.
# Ilk surumde `experiments/` tumden disaridaydi ve `salinim_olc` ile
# `spektral_olc` OKSUZ sanildi — oysa experiments/silindir_urans.py onlari
# cagiriyor. V&V betigi mesru bir tuketicidir; onu gormeyen olcer yanlis
# pozitif uretir ve yanlis pozitif ureten olcer kullanilmaz hale gelir.
ATLA_TANIM = {"tests", "experiments", ".git", "__pycache__", "build", "dist",
              "tmr_cfd", "_cgrid_calisma"}
ATLA_CAGRI = {"tests", ".git", "__pycache__", "build", "dist",
              "tmr_cfd", "_cgrid_calisma"}

# MUAFIYET — incelendi, cagrilmamasi KABUL. Gerekce ZORUNLU: gerekcesiz muafiyet
# olcerin kendisini susturur ve bu depoda "olcemedim" ile "iyi" karistirilmaz.
MUAF: dict[str, str] = {
    "design_explorer.evaluate_surrogate":
        "KABUL — sekil optimizasyonu surucusu 2026-08-20'de KAPATILDI (gorev #38: "
        "onerilen ucuz katman VSPAERO'nun induklenen direnci %21/%62 sapiyor). "
        "Vekil degerlendirici o yonun kalintisi; canlandirilirsa cagrilir.",
}


# KAPSAM BOSLUGU YUTULMAZ, SAYILIR. Okunamayan ya da ayristirilamayan dosya
# taranamaz; onu sessizce atlamak olcerin "0 acik madde" hukmunu DAYANAKSIZ
# birakir — tarayamadigim dosyada oksuz savunma olabilir. Bu yuzden atlananlar
# biriktirilip ciktida beyan edilir. (Deponun `sessiz_yutma` kapisi bu modulun
# ilk surumundeki gerekcesiz `except: continue`'lari zaten yakaladi.)
ATLANAN: list[str] = []


def _kaynaklar(atla: set) -> dict[str, str]:
    out = {}
    for p in KOK.rglob("*.py"):
        if set(p.parts) & atla or p.name == Path(__file__).name:
            continue
        yol = p.relative_to(KOK).as_posix()
        try:
            out[yol] = p.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as e:
            ATLANAN.append(f"{yol}: okunamadı ({type(e).__name__})")
    return out


def _hukum_donuyor(n: ast.FunctionDef) -> bool:
    """Govde bir HUKUM donduruyor mu — sozluk icinde karar/gerekce alani ya da
    bool. Ad izi olmayan ama hukum ureten fonksiyonlari da yakalar."""
    ANAHTAR = {"karar", "verdikt", "hukum", "gecerli", "uyumlu", "kosulabilir",
               "neden", "gerekce", "mesaj", "reddedildi"}
    for x in ast.walk(n):
        if isinstance(x, ast.Return) and isinstance(x.value, ast.Dict):
            adlar = {k.value for k in x.value.keys
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if adlar & ANAHTAR:
                return True
    return False


def tara() -> list[dict]:
    def _agac(atla):
        d = {}
        for yol, metin in _kaynaklar(atla).items():
            try:
                d[yol] = ast.parse(metin)
            except SyntaxError as e:
                ATLANAN.append(f"{yol}: ayrıştırılamadı (satır {e.lineno})")
        return d

    tanim_agac = _agac(ATLA_TANIM)
    cagri_agac = _agac(ATLA_CAGRI)

    # Cagri sayimi AST ile: `x.f()`, `f()` ve `from m import f` sonrasi yalin ad.
    # TAKMA AD COZULUR: `from bellek_kapisi import hukum as _bellek_hukmu` sonrasi
    # cagri `_bellek_hukmu(...)` gorunur ve `hukum` OKSUZ sanilirdi — ilk surumde
    # tam bu yasandi.
    cagrilan: dict[str, int] = {}
    for yol, a in cagri_agac.items():
        takma: dict[str, str] = {}
        for x in ast.walk(a):
            if isinstance(x, (ast.Import, ast.ImportFrom)):
                for al in x.names:
                    if al.asname:
                        takma[al.asname] = al.name.split(".")[-1]
        for x in ast.walk(a):
            if not isinstance(x, ast.Call):
                continue
            f = x.func
            ad = f.attr if isinstance(f, ast.Attribute) else (
                f.id if isinstance(f, ast.Name) else None)
            if not ad:
                continue
            for isim in {ad, takma.get(ad, ad)}:
                cagrilan[isim] = cagrilan.get(isim, 0) + 1

    bulunan = []
    for yol, a in tanim_agac.items():
        for n in ast.walk(a):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if n.name.startswith("_test") or n.name.startswith("test_"):
                continue
            savunma = bool(AD_IZI.search(n.name)) or _hukum_donuyor(n)
            if not savunma:
                continue
            if cagrilan.get(n.name):
                continue
            modul = yol[:-3].replace("/", ".")
            anahtar = f"{modul}.{n.name}"
            bulunan.append({
                "fonksiyon": n.name, "dosya": yol, "satir": n.lineno,
                "anahtar": anahtar,
                "ad_izi": bool(AD_IZI.search(n.name)),
                "hukum_donuyor": _hukum_donuyor(n),
                "muaf": anahtar in MUAF,
                "gerekce": MUAF.get(anahtar, ""),
            })
    bulunan.sort(key=lambda x: (x["muaf"], x["dosya"], x["satir"]))
    return bulunan


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    b = tara()
    acik = [x for x in b if not x["muaf"]]
    muaf = [x for x in b if x["muaf"]]

    print("Öksüz savunma (hüküm üretir, üretim yolundan hiç çağrılmaz)\n")
    for x in acik:
        etiket = "ad+hüküm" if x["ad_izi"] and x["hukum_donuyor"] else (
            "ad izi" if x["ad_izi"] else "hüküm döner")
        print(f"  ❗ {x['fonksiyon']:<32}{x['dosya']}:{x['satir']}  [{etiket}]")
    if not acik:
        print("  (yok)")
    if muaf:
        print("\n  Muaf (incelendi, gerekçesi kodda):")
        for x in muaf:
            print(f"  ✓ {x['fonksiyon']:<32}{x['gerekce'][:70]}")

    print(f"\n**İNCELENMEMİŞ: {len(acik)}** — asıl izlenen sayı")
    print(f"**Muaf (gerekçeli): {len(muaf)}**")
    # Kapsam BEYAN EDILIR: taranamayan dosya varken "0 acik madde" dayanaksizdir.
    if ATLANAN:
        print(f"\n  ⚠ TARANAMAYAN {len(ATLANAN)} dosya — bu hüküm onları KAPSAMAZ:")
        for x in dict.fromkeys(ATLANAN):
            print(f"    {x}")
    else:
        print("Kapsam: tüm ürün-katmanı .py dosyaları tarandı (atlanan yok).")
    print("\nÇağrılmayan bir savunma, kurulmuş ama devreye alınmamış bir "
          "kapıdır: hükmü doğrudur, kimse sormaz.")

    if "--json" in sys.argv:
        (KOK / "oksuz_savunma.json").write_text(
            json.dumps({"vaka": "Öksüz savunma taraması",
                        "_uretim": "Üretim: python oksuz_savunma.py --json",
                        "verdikt": (f"{len(acik)} incelenmemiş, {len(muaf)} muaf"
                                    if acik else
                                    f"✅ İncelenmemiş öksüz savunma YOK "
                                    f"({len(muaf)} muaf, gerekçeli)"),
                        "bulunan": b}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        print("-> oksuz_savunma.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
