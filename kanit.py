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
    python kanit.py --bayat    # onu üreten koddan ESKİ kanıtlar (exit 1)
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
# Komut YALNIZ "python" ile başlayabiliyordu; NX journal kanıtları (run_journal.exe) ve
# ortam-değişkenli koşular (NX_AILE=kor …) bu yüzden "komut kayıtlı değil" görünüyordu —
# kanıt vardı, manifest göremiyordu. Kabul edilen ilk sözcük kümesi genişletildi;
# yine de bir ÇALIŞTIRILABİLİR gerekiyor ki düz metin komut sanılmasın.
_URETIM = re.compile(
    r"(?:Üretim|Uretim|Reproduce)\s*:\s*"
    r"((?:[A-Z][A-Z0-9_]*=\S+\s+)*"                  # isteğe bağlı ortam değişkenleri
    r"(?:python|bash|sh|\"?[^\"\n]*run_journal[^\"\n]*?\.exe\"?)"
    r"[^\"\n]{3,160}?)(?=\.\s|\.$|$|\")")


_YAZMA = re.compile(r"json\.dump|write_text|open\([^)]*[\"']w")


def uretici_kod_var(ad: str) -> bool:
    """Depoda bu kanıt dosyasını YAZAN bir kaynak var mı?

    "Komut kayıtlı değil" iki çok farklı durumu aynı gösteriyordu: (a) üretici script
    duruyor, yalnız kanıta not düşülmemiş — bir satırlık iş; (b) üreten kod depoda HİÇ
    YOK (silinmiş ya da ad-hoc koşulmuş) — kanıt gerçekten yeniden üretilemez. İkincisi
    çok daha ağır ve ayrı görünmeli.
    """
    for f in ROOT.rglob("*.py"):
        if set(f.parts) & {"tests", "__pycache__", ".venv", "Construct2D", "sources"}:
            continue
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        # sessiz-yutma: kabul — okunamayan kaynak taranmaz; sonuç yalnız 'üretici bulunamadı' tarafına yanılır (temkinli)
        except OSError:
            continue
        for satir in t.splitlines():
            if ad in satir and _YAZMA.search(satir):
                return True
        # write_text çok satıra yayılmış olabilir: dosya adı geçen bloğu gevşek tara
        if ad in t:
            i = t.index(ad)
            if _YAZMA.search(t[max(0, i - 200):i + 200]):
                return True
    return False


def _uretim_komutu(d: dict) -> str:
    # Değerleri BİRLEŞTİRMEK kırılgan: komşu alan komutun peşine yapışıp uzunluk
    # sınırını aştırınca eşleşme tamamen kayboluyordu (_son_dogrulama eklenince
    # fea_validation.json'da yaşandı). Her alan AYRI taranır.
    for v in d.values():
        m = _URETIM.search(str(v))
        if m:
            return m.group(1).strip()
    return ""


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


def _git_tarih(yol: str) -> int:
    """Yolun son commit zamanı (unix). Git yoksa/izlenmiyorsa 0."""
    import subprocess
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%ct", "--", yol],
                           cwd=ROOT, capture_output=True, text=True, timeout=30)
        return int(r.stdout.strip()) if r.stdout.strip().isdigit() else 0
    # sessiz-yutma: kabul — git yoksa 0 döner ve bayatlık kontrolü ATLANIR — kanıt hükmü değişmez
    except Exception:
        return 0


# Kanıtı ÜRETEN kod: bunlar kanıttan SONRA değiştiyse kanıt eski kodla üretilmiş olabilir.
URETEN_KOD = ["vehicle_pipeline.py", "analysis", "report_generator.py", "validity_envelope.py"]


def _uretim_scripti(komut: str) -> str:
    """`python experiments/fea_validation.py …` -> `experiments/fea_validation.py`."""
    for p in komut.split():
        if p.endswith(".py"):
            return p
    return ""


def _bagimli_kod(script: str, derinlik: int = 2) -> list[str]:
    """Script + içe aktardığı PROJE modülleri (derinlik seviyeye kadar).

    `check_vehicle_validation.py` -> `vehicle_pipeline.py` -> `analysis/openfoam_runner.py`
    zincirini izler; `experiments/fea_validation.py` ise yalnız calculix/frd yoluna iner.
    """
    import re as _re
    gorulen, kuyruk, cikti = set(), [(script, 0)], []
    _imp = _re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", _re.M)
    while kuyruk:
        yol, d = kuyruk.pop()
        if yol in gorulen:
            continue
        gorulen.add(yol)
        p = ROOT / yol
        if not p.exists():
            continue
        cikti.append(yol)
        if d >= derinlik:
            continue
        for ad in _imp.findall(p.read_text(encoding="utf-8", errors="replace")):
            kok = ad.split(".")[0]
            aday = f"{ad.replace('.', '/')}.py" if kok == "analysis" else f"{kok}.py"
            if (ROOT / aday).exists():
                kuyruk.append((aday, d + 1))
    return cikti


def bayatlik(kayitlar: list[dict]) -> list[dict]:
    """Kanıt dosyası, ONU ÜRETEN koddan eski mi?

    Somut vaka: vehicle_validation.json (küp ↔ Hoerner çapası) 2026-06-10'da üretildi;
    o tarihten sonra kuvvet tarihçesi pencere-ortalaması (trailing_mean) dahil çok şey
    değişti. Dosya "✅ %2.4 hata" diyor ama güncel kod aynı mesh'te %6.0 veriyor.

    KESİNLİK: üretim komutu kayıtlıysa YALNIZ o script + kanonik katman ile kıyaslanır
    (kesin). Değilse geniş kod kümesiyle kıyaslanır ve "tahmin" olarak işaretlenir —
    FEA kanıtını CFD değişikliğiyle bayat ilan etmek sinyali gürültüye çevirir.
    """
    genel_ts = max((_git_tarih(y) for y in URETEN_KOD), default=0)
    analysis_ts = _git_tarih("analysis")
    out = []
    for k in kayitlar:
        if k["sinif"] != "kanit":
            continue
        ts = _git_tarih(k["dosya"])
        if not ts:
            continue
        script = _uretim_scripti(k["uretim"])
        if script:
            # `analysis/` KLASÖRÜNÜN tamamıyla kıyaslamak yanlış: FEA kanıtı
            # calculix_writer/frd_parser'a bağlıdır, openfoam_runner'a değil. Script'in
            # GERÇEK import'larını izle — aksi halde her CFD değişikliği tüm FEA
            # kanıtlarını "bayat" ilan eder ve sinyal gürültüye gömülür.
            kod_ts, kesin = max((_git_tarih(y) for y in _bagimli_kod(script)),
                                default=0), True
        else:
            kod_ts, kesin = genel_ts, False
        if kod_ts and ts < kod_ts:
            out.append({**k, "bayat_gun": round((kod_ts - ts) / 86400, 1),
                        "kesin": kesin, "kiyas": script or "genel kod kümesi"})
    return out


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
        if x["uretim"]:
            ur = f"`{x['uretim']}`"
        elif uretici_kod_var(x["dosya"]):
            ur = "⚠ komut kayıtlı değil (üretici kod depoda var)"
        else:
            ur = "❌ ÜRETİCİ KOD DEPODA YOK — yeniden üretilemez"
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
    if "--bayat" in sys.argv:
        b = bayatlik(kayitlar)
        if not b:
            print("Hiçbir kanıt onu üreten koddan eski değil.")
            return 0
        kesin = [x for x in b if x["kesin"]]
        tahmin = [x for x in b if not x["kesin"]]
        print("| Dosya | Kıyas | Gün | Hüküm |")
        print("|---|---|---|---|")
        for x in sorted(kesin, key=lambda z: -z["bayat_gun"]):
            print(f"| `{x['dosya']}` | `{x['kiyas']}` | {x['bayat_gun']:.0f} | "
                  f"{x['sembol']} {x['hukum'][:50]} |")
        if tahmin:
            print()
            print(f"Üretim komutu kayıtlı olmayan {len(tahmin)} kanıt genel kod kümesiyle "
                  "kıyaslandı (TAHMİN, kesin değil): "
                  + ", ".join(f"`{x['dosya']}`" for x in tahmin[:8]))
        print()
        print("Bu dosyalar ESKİ KODLA üretilmiş olabilir; üretim komutuyla tazeleyin.")
        return 1 if kesin else 0
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
