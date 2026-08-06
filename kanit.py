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
    python kanit.py --damgala <dosya...>   # yeniden koşulup DOĞRULANMIŞ kanıtı damgala
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Windows konsolu cp1254: Türkçe karakter / ok / ✓ basan her satır
# UnicodeEncodeError ile SÜRECİ DÜŞÜRÜYOR. Ölçüldü: kanit.py tabloyu hiç
# basamadı, check_integration.py bunu "[ERROR] ... entegrasyon" diye
# raporladı — yani KODLAMA sorunu ARIZA gibi göründü.
for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        _akis.reconfigure(encoding="utf-8", errors="replace")

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
    # `conda run -n <ortam>` ONEKI: OpenVSP/XFOIL kanitlari ayri bir conda
    # ortamindan uretiliyor ve komut o onekle KAYITLI. Onek tanınmadigi icin
    # denetleyici "komut kayitli degil" diyordu — yani YENIDEN URETILEBILIR bir
    # kanit, uretilemez gibi raporlaniyordu (olculdu: vlm_capa,
    # vlm_panel_yakinsamasi, vlm_iki_yonlu_yakinsama).
    r"(?:conda\s+run\s+(?:-n\s+\S+\s+|--no-capture-output\s+)*)?"
    r"(?:python|bash|sh|\"?[^\"\n]*run_journal[^\"\n]*?\.exe\"?)"
    r"[^\"\n]{3,160}?)(?=\.\s|\.$|$|\")")


_YAZMA = re.compile(r"json\.dump|write_text|open\([^)]*[\"']w")

# Çıktı adı HESAPLANMIŞ olabilir: exp_gci_xfine.py `f"gci_{lbl}.json"` yazıyor ve
# literal "gci_xfine.json" kaynakta HİÇ geçmiyor. Literal arayan denetim buna
# "üretici kod depoda YOK — yeniden üretilemez" diyordu; yani aracın İDDİASI
# KANITINDAN GÜÇLÜYDÜ (bu oturumun tekrarlayan kusuru, bu kez denetleyicide).
_KALIP = re.compile(r"[\"']([^\"'\n]*\{[^\"'\n]*\}[^\"'\n]*\.json)[\"']")


def _kalip_uyuyor(govde: str, ad: str) -> int:
    """Kaynaktaki f-string çıktı adı bu kanıt dosyasına uyuyor mu? → özgüllük skoru.

    `{...}` yer tutucusu dosya-adı parçası kabul edilir (ayraç geçemez), böylece
    `gci_{lbl}.json` → gci_xfine.json EŞLEŞİR ama alt/üst dizinlere taşmaz.

    SKOR = kalıptaki SABİT karakter sayısı. Gerekli, çünkü `gci_{lbl}.json` HER
    `gci_*.json` ile eşleşiyor: gci_cgrid_base.json için hem exp_gci_xfine.py
    (`gci_{lbl}.json`) hem exp_cgrid_run.py (`gci_cgrid_{lbl}.json`) uyuyor ve
    doğru cevap ikincisi. En ÖZGÜL kalıp kazanır. Skorlar eşitse ilk bulunan.
    """
    en_iyi = 0
    for m in _KALIP.finditer(govde):
        parcalar = [p for p in re.split(r"(\{[^{}]*\})", m.group(1)) if p]
        desen = "".join(r"[^/\\]*" if p.startswith("{") else re.escape(p)
                        for p in parcalar)
        if not re.fullmatch(desen, ad):
            continue
        if _YAZMA.search(govde[max(0, m.start() - 200):m.start() + 200]):
            en_iyi = max(en_iyi, sum(len(p) for p in parcalar
                                     if not p.startswith("{")))
    return en_iyi


def uretici_kod(ad: str) -> str:
    """Depoda bu kanıt dosyasını YAZAN kaynağın yolu (yoksa "").

    "Komut kayıtlı değil" iki çok farklı durumu aynı gösteriyordu: (a) üretici script
    duruyor, yalnız kanıta not düşülmemiş — bir satırlık iş; (b) üreten kod depoda HİÇ
    YOK (silinmiş ya da ad-hoc koşulmuş) — kanıt gerçekten yeniden üretilemez. İkincisi
    çok daha ağır ve ayrı görünmeli.

    BOOL YETMİYOR: "üretici var" demek, onu KOŞMAK için yeterli değil. Yolu döndürmek
    kaydedilmemiş komutu bir satırda yazılabilir hâle getirir.

    LİTERAL eşleşme, ad-kalıbı eşleşmesini her zaman yener; kalıplar arasında en
    ÖZGÜL olan kazanır (bkz. _kalip_uyuyor).
    """
    kalip_aday = ("", 0)
    for f in sorted(ROOT.rglob("*.py")):
        # Denetçi KENDİ dokümantasyonuyla eşleşmemeli: bu dosyanın yorumunda örnek
        # olarak `gci_{lbl}.json` geçiyor ve kendini üretici sanıyordu.
        if f.name == Path(__file__).name:
            continue
        if set(f.parts) & {"tests", "__pycache__", ".venv", "Construct2D", "sources"}:
            continue
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        # sessiz-yutma: kabul — okunamayan kaynak taranmaz; sonuç yalnız 'üretici bulunamadı' tarafına yanılır (temkinli)
        except OSError:
            continue
        yol = str(f.relative_to(ROOT)).replace("\\", "/")
        for satir in t.splitlines():
            if ad in satir and _YAZMA.search(satir):
                return yol
        # write_text çok satıra yayılmış olabilir: dosya adı geçen HER yeri tara.
        # İLK geçiş yetmiyordu: ad önce bir sabitte (CIKTI_JSON sözlüğü) geçip
        # yazma çok aşağıda olduğunda üretici görünmez oluyordu.
        for m in re.finditer(re.escape(ad), t):
            if _YAZMA.search(t[max(0, m.start() - 200):m.start() + 200]):
                return yol
        skor = _kalip_uyuyor(t, ad)
        if skor > kalip_aday[1]:
            kalip_aday = (yol, skor)
    return kalip_aday[0]


def uretici_kesin(ad: str) -> bool:
    """Eşleşme LİTERAL mi (dosya adı kaynakta aynen geçiyor) yoksa AD KALIBINDAN
    mı çıkarıldı? Kalıp eşleşmesi "bu script bu adda bir dosya YAZABİLİR" der;
    "bu dosyayı üretmiştir" DEMEZ. İki iddia ayrı gösterilmeli."""
    yol = uretici_kod(ad)
    if not yol:
        return False
    t = (ROOT / yol).read_text(encoding="utf-8", errors="replace")
    return any(_YAZMA.search(t[max(0, m.start() - 200):m.start() + 200])
               for m in re.finditer(re.escape(ad), t))


def uretici_kod_var(ad: str) -> bool:
    return bool(uretici_kod(ad))


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
             "eskimis": False, "uretim": "", "hukum_turetilir": False, "not": "",
             "dogrulama_ts": 0}
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
    kayit["dogrulama_ts"] = d.get("_son_dogrulama_ts") or 0
    kayit["sinif"] = "kanit" if (kayit["vaka"] or metin) else "artefakt"
    # Komut kayıtlıysa üretici zaten bellidir; kayıtsızsa ARANIR ve YOLU YAZILIR.
    # "yeniden üretilemez" ağır bir iddiadır ve yalnız arama BOŞ dönünce kurulur.
    if kayit["sinif"] == "kanit" and not kayit["uretim"]:
        kayit["uretici"] = uretici_kod(p.name)
        kayit["uretici_kesin"] = bool(kayit["uretici"]) and uretici_kesin(p.name)
        # GEREKÇESİZ ❌ bir bilgi vermiyor: "yeniden üretilemez" ile NEDEN
        # üretilemediği ayrı şeyler ve ikincisi eylem planı üretir.
        kayit["uretilemez_neden"] = str(d.get("_uretilemez") or "")[:300]
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
            # DOĞRULAMA DAMGASI: kanıt yeniden koşulup sonuç BİREBİR AYNI çıkarsa git
            # yeni commit görmez ve dosya sonsuza dek "bayat" kalır — "hiç koşulmadı"
            # ile "koşuldu ve doğrulandı" ayırt edilemezdi. `_son_dogrulama_ts` alanı
            # (unix) üreten koddan yeniyse kanıt GÜNCEL sayılır.
            if (k.get("dogrulama_ts") or 0) >= kod_ts:
                continue
            out.append({**k, "bayat_gun": round((kod_ts - ts) / 86400, 1),
                        "kesin": kesin, "kiyas": script or "genel kod kümesi"})
    return out


def damgala(dosyalar: list[str], not_metni: str = "") -> int:
    """Yeniden koşulup DOĞRULANMIŞ kanıtlara zaman damgası basar.

    Damga elle atılmaz: bu komut, kanıtın üretim komutunu yeniden koşup sonucun aynı
    çıktığını GÖRMÜŞ olan kişi/ajan tarafından çağrılır. Damga yalnız "o an geçerli
    koda karşı doğrulandı" der; içeriğin doğruluğunu garanti etmez.
    """
    import time
    n = 0
    for ad in dosyalar:
        p = ROOT / ad
        if not p.exists():
            print(f"  yok: {ad}")
            continue
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        d["_son_dogrulama_ts"] = int(time.time())
        d["_son_dogrulama"] = (time.strftime("%Y-%m-%d") + " — üretim komutuyla yeniden "
                               "koşuldu; sonuç güncel kodla karşılaştırıldı."
                               + (f" {not_metni}" if not_metni else ""))
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        n += 1
        print(f"  damgalandı: {ad}")
    return n


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
        elif x.get("uretici"):
            # Yol GÖSTERİLİR: "üretici var" demek onu koşmak için yetmiyordu.
            # Kalıptan çıkarılan eşleşme AYRI işaretlenir: "bu script bu adda bir
            # dosya yazabilir" ile "bu dosyayı üretmiştir" aynı iddia değil.
            kesin = x.get("uretici_kesin")
            ur = (f"⚠ komut kayıtlı değil — üretici: `{x['uretici']}`" if kesin else
                  f"⚠ komut kayıtlı değil — üretici (ad kalıbı): `{x['uretici']}`")
        else:
            ur = "❌ ÜRETİCİ KOD DEPODA YOK — yeniden üretilemez"
            if x.get("uretilemez_neden"):
                ur += f" — {x['uretilemez_neden']}"
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
    if "--damgala" in sys.argv:
        i = sys.argv.index("--damgala")
        hedef = [a for a in sys.argv[i + 1:] if not a.startswith("--")]
        if not hedef:
            print("kullanım: python kanit.py --damgala <kanit.json> [...]")
            return 1
        print(f"{damgala(hedef)} kanıt doğrulama damgası aldı.")
        return 0
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
