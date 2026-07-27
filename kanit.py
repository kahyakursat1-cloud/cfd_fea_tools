"""Kanıt manifesti — "bu araç neyi doğrulanmış olarak biliyor?" tek komutta.

Kök dizinde 50'yi aşkın JSON var: bir kısmı gerçek V&V kanıtı, bir kısmı çalışma-zamanı
artefaktı, bir kısmı kaynak veri. İsimlendirme tutarsız (gci_cgrid_base/mid/fine/xfine/
xxfine/final/finding…) ve indeks yok. Mühendis "delikli plaka doğrulandı mı?" sorusuna
dosya adı tahmin ederek cevap arıyordu.

Bu araç dosyaları SINIFLAR ve kanıt olanları verdiktleriyle listeler:
  kanit     — vaka + hüküm taşıyan V&V dosyası
  artefakt  — çalışma-zamanı çıktısı (öğrenme kütüphanesi, tarama sonucu, polar)
  kaynak    — girdi verisi (materials.json)
  bozuk     — okunamayan dosya (sebebiyle)

    python kanit.py            # tablo
    python kanit.py --json     # kanit_manifest.json yaz
    python kanit.py --eksik    # hükmü/üretim komutu olmayan veya eskimiş kanıtlar
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "kanit_manifest.json"

# Hüküm taşıyan anahtarlar — öncelik sırasıyla
HUKUM_ANAHTARLARI = ("strict_gci_verdict", "verdikt", "sonuc", "verdict_yuzey",
                     "degerlendirme", "trend_degerlendirme", "status")
# Kanıt SAYILMAYAN, çalışma-zamanı üreten dosyalar (ad öneki)
ARTEFAKT_ONEKLERI = ("batch_learn", "surrogate_cv", "design_explore", "aoa_polar",
                     "vspaero_polar", "transition_results", "openrocket_result",
                     "regresyon_sonuc", "kuyruk", "envelope", "fea_critical",
                     "coupling_result", "mesh_quality", "overnight_summary",
                     "silent_failure_assay")
KAYNAK = {"materials.json", "config.yaml"}


def _oku(p: Path):
    """BOM'lu (PowerShell çıktısı) ve BOM'suz dosyayı birlikte okur."""
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _hukum_adaylari(d: dict):
    """Hüküm taşıyabilecek metin alanları — üst düzey ve BİR seviye iç içe.

    Kanıt dosyaları tek bir şemaya uymuyor: kimi `sonuc`, kimi `degerlendirme`,
    kimi `ozet.yorum` altında hüküm veriyor. Yalnız üst düzeye bakmak, hükmü OLAN
    dosyaları "hükümsüz" göstererek manifesti yanıltıyordu.
    """
    for k in HUKUM_ANAHTARLARI:
        yield d.get(k)
    for ic in ("ozet", "tekil_dogrulama", "degerlendirme_ozeti"):
        v = d.get(ic)
        if isinstance(v, dict):
            for k in ("yorum", "sonuc", "verdikt", "degerlendirme"):
                yield v.get(k)


def _hukum(d: dict) -> tuple[str, str]:
    """(sembol, metin) — hüküm metnini ✅/⚠️/❌ ile normalleştirir."""
    for v in _hukum_adaylari(d):
        if isinstance(v, str) and v.strip():
            s = v.strip()
            if s.startswith("✅") or s.upper().startswith(("GECTI", "GEÇTI", "GEÇTİ", "OK")):
                return "✅", s
            if s.startswith("⚠️") or "GÖSTERİLEMEDİ" in s.upper() or "SUPHELI" in s.upper():
                return "⚠️", s
            if s.startswith("❌") or s.upper().startswith(("KALDI", "FAILED", "HATA")):
                return "❌", s
            return "•", s
    return "—", ""


# Kanıtı ÜRETEN komut — yeniden-üretilebilirlik (yayın/hakem için kritik).
# FEA ailesi bu geleneği kurmuş ("Üretim: python experiments/…"); indeks onu görünür kılar.
# Nokta komutun PARÇASI olabilir (vehicle_pipeline.py); cümle sonunu ". " ile ayır.
_URETIM = re.compile(r"(?:Üretim|Uretim|Reproduce)\s*:\s*(python[^\"\n]{3,120}?)"
                     r"(?=\.\s|\.$|$|\")")


def _uretim_komutu(d: dict) -> str:
    m = _URETIM.search(" ".join(str(v) for v in d.values()))
    return m.group(1).strip() if m else ""


def sinifla(p: Path) -> dict:
    kayit = {"dosya": p.name, "sinif": "?", "vaka": "", "hukum": "", "sembol": "—",
             "eskimis": False, "uretim": "", "hukum_turetilir": False, "not": ""}
    if p.name in KAYNAK:
        kayit["sinif"] = "kaynak"
        return kayit
    try:
        d = _oku(p)
    except Exception as e:
        kayit.update(sinif="bozuk", **{"not": f"{type(e).__name__}: {e}"})
        return kayit
    if not isinstance(d, dict):
        kayit.update(sinif="artefakt", **{"not": f"liste ({len(d)} kayıt)"})
        return kayit
    if any(p.name.startswith(o) for o in ARTEFAKT_ONEKLERI):
        kayit["sinif"] = "artefakt"
        return kayit
    sembol, metin = _hukum(d)
    # ÜÇÜNCÜ DURUM: hüküm bu dosyada saklanmaz ama BAŞKA YERDE hesaplanır
    # (ör. mesh_independence.json ham seviye verisi; verdikti zarf.py hesaplar).
    # "hüküm alanı YOK" demek yanıltıcı olurdu — kanıt eksik değil, hüküm türetilir.
    if sembol == "—" and d.get("_hukum_kaynagi"):
        sembol, metin = "↗", "hüküm türetilir — " + str(d["_hukum_kaynagi"])[:120]
        kayit["hukum_turetilir"] = True
    kayit["vaka"] = str(d.get("vaka") or d.get("_kaynak") or "")[:90]
    kayit["eskimis"] = bool(d.get("_SUPERSEDED"))
    kayit["sembol"], kayit["hukum"] = sembol, metin[:150]
    kayit["uretim"] = _uretim_komutu(d)
    kayit["sinif"] = "kanit" if (kayit["vaka"] or metin) else "artefakt"
    if kayit["eskimis"]:
        kayit["not"] = "ESKİMİŞ — güncel dosya için _SUPERSEDED notuna bak"
    return kayit


def manifest() -> list[dict]:
    return sorted((sinifla(p) for p in ROOT.glob("*.json") if p.name != MANIFEST.name),
                  key=lambda k: (k["sinif"] != "kanit", k["dosya"]))


def tablo(kayitlar: list[dict], yalniz_kanit: bool = True) -> str:
    k = [x for x in kayitlar if x["sinif"] == "kanit"] if yalniz_kanit else kayitlar
    sat = ["| Dosya | Vaka | Hüküm | Yeniden üretim |", "|---|---|---|---|"]
    for x in k:
        vaka = x["vaka"] or "—"
        hukum = (x["hukum"] or "hüküm alanı YOK").replace("|", "/")
        if x["eskimis"]:
            hukum = "🕰 ESKİMİŞ — " + hukum
        ur = f"`{x['uretim']}`" if x["uretim"] else "⚠ komut kayıtlı değil"
        sat.append(f"| `{x['dosya']}` | {vaka} | {x['sembol']} {hukum} | {ur} |")
    ozet = {}
    for x in kayitlar:
        ozet[x["sinif"]] = ozet.get(x["sinif"], 0) + 1
    sat.append("")
    sat.append("**Özet:** " + ", ".join(f"{v} {a}" for a, v in sorted(ozet.items())))
    kanitlar = [x for x in kayitlar if x["sinif"] == "kanit"]
    uretilebilir = sum(1 for x in kanitlar if x["uretim"])
    if kanitlar:
        sat.append(f"**Yeniden üretilebilir:** {uretilebilir}/{len(kanitlar)} kanıt "
                   "üreten komutu kaydediyor")
    bozuk = [x for x in kayitlar if x["sinif"] == "bozuk"]
    if bozuk:
        sat.append("")
        sat.append("**Okunamayan dosyalar:**")
        sat += [f"- `{x['dosya']}` — {x['not']}" for x in bozuk]
    return "\n".join(sat)


def main() -> int:
    kayitlar = manifest()
    if "--json" in sys.argv:
        MANIFEST.write_text(json.dumps(kayitlar, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        print(f"{MANIFEST.name} yazıldı ({len(kayitlar)} dosya)")
        return 0
    if "--eksik" in sys.argv:
        eksik = [x for x in kayitlar
                 if x["sinif"] == "kanit"
                 and (not x["hukum"] or x["eskimis"] or not x["uretim"])
                 and not x["hukum_turetilir"]]
        print(tablo(eksik) if eksik else "Tüm kanıt dosyaları hüküm taşıyor ve güncel.")
        return 0
    print(tablo(kayitlar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
