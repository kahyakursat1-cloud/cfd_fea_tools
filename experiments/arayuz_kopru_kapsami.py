r"""Arayüz ve dış-köprü kapsamı: "sınanamaz" iddiası SINANIR.

Rapor iki düşük katmanı (Arayüz \%40,2 ve Dış-süreç köprüleri \%41,4) şu
cümleyle savunuyor: ``Bunlar birim testiyle değil ÇAPA KOŞULARIYLA sınanır.''
Cümle makul görünüyor ve bu yüzden hiç sınanmadı. Oysa sınanabilir bir
iddiadır: kapsanmamış satırların ne kadarı gerçekten dış bir sürece ya da
bir ekrana muhtaç?

BU BETİK KARAR KATMANI İÇİN ZATEN YAPILANI (karar_katmani_kapsami.py) BU İKİ
KATMANA UYGULAR ve bir kova EKLER. Karar katmanında üç kova vardı --- metin/CLI,
savunma, karar dalı. Burada dördüncüsü gerekiyor:

  DIS BAGIMLI   : Qt widget/sinyal kurulumu, subprocess çağrısı, dosya
                  diyaloğu --- ekran ya da dış çözücü olmadan sürülemez.
                  Raporun iddiası TAM OLARAK bunlar içindir.
  SINANABILIR   : saf karar/dönüşüm mantığı. Ne ekran ister ne çözücü;
                  kapsanmamış olması bir tercihtir, bir zorunluluk değil.

HÜKÜM YÜZDEYE DEĞİL ORANA BAKAR: `sinanabilir` kova büyükse raporun cümlesi
KENDİNE FAZLA CÖMERTTİR ve daraltılmalıdır.

DESEN AYRIMI SEZGİSELDİR ve bu ölçümün sınırıdır: `sinanabilir` sayısı bir
ÜST SINIRDIR --- okunmadan "sınanmamış hüküm" sayılmaz. Karar katmanında ilk
sürüm 321 satırı karar dalı saymış, gözle bakılınca büyük kısmı metin
çıkmıştı; aynı hata burada da mümkündür ve örnekler kayda yazılır ki
denetlenebilsin.

ÖNKOŞUL: cov.json güncel olmalı
    python -m pytest -q --cov=. --cov-report=json:cov.json

    python experiments/arayuz_kopru_kapsami.py
Çıktı: arayuz_kopru_kapsami.json
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

CIKTI = KOK / "arayuz_kopru_kapsami.json"
# ORNEK TAVANI: kayit denetlenebilir olmali ama sisirilmemeli.
ORNEK = 25
# HUKUM ESIGI: kapsanmamis satirlarin bu kadarindan fazlasi ekran/cozucu
# GEREKTIRMIYORSA, "capa kosulariyla sinanir" cumlesi fazla comerttir.
COMERTLIK_ESIGI_PCT = 25.0

# EKRAN-BAGIMLILIGI YAPISAL OLARAK BELIRLENIR, REGEX ILE DEGIL.
#
# Ilk surum bir DIS_DESEN regex'i kullaniyordu ve gercek kaynakta denendiginde
# apacik Qt satirlarini "sinanabilir" kovasina dusurdu: `lay.addLayout(row)`,
# `self.spn_yplus.value()`, `self._set_combo(self.cmb_rejim, ...)`. Regex'i
# buyutmek bu oyunu kazandirmaz --- her widget metodu ayri bir desen ister ve
# eksik kalan her desen olcumu KENDI LEHINE bozar (sinanabilir sayisi sisip
# "rapor comert" hukmu haksiz cikar).
#
# YAPISAL OLCUT: bir ifade, TABANI Qt olan bir sinifin govdesindeyse ekran
# ister --- o metodu cagirmak once bir widget ORNEGI kurmayi, o da QApplication
# gerektirir. Modul duzeyindeki fonksiyonlar ve Qt-olmayan siniflar ise
# ekransiz cagrilabilir. Bu, "sinanabilir mi" sorusunun gercek karsiligidir.
QT_TABAN = re.compile(r"^Q[A-Z]")
# Qt ADI GECEN IFADE de ekran ister --- Qt sinifi DISINDA da olabilir
# (`launcher.py`de modul duzeyinde `QMessageBox.critical(...)` var). Yapisal
# olcut tek basina bunu kaciriyordu.
QT_ADI = re.compile(r"\bQ[A-Z]\w+\b")
# DIS SUREC: kopru katmaninda Qt yok; oradaki gercek engel dis cozucudur.
DIS_SUREC = re.compile(r"(?:subprocess\.|Popen\(|check_output\(|os\.startfile|"
                       r"webbrowser\.|_wsl_run\(|linux_run\()")


def _ithal_edilemeyenler(kaynak: str) -> set[str]:
    """Modulun ithal ettigi ama BU ORTAMDA bulunmayan adlar.

    NEDEN GEREKLI: `openvsp_bridge` satirlarinin cogu `vsp.SetParmValUpdate(...)`
    gibi cagrilar ve OpenVSP Python API'si burada KURULU DEGIL --- yani o
    satirlar ekran istemiyor ama yine de surulemiyor. Yapisal Qt olcutu bunu
    goremezdi ve satirlari "sinanabilir" sayip olcumu kendi lehine bozardi.
    Bagimlilik VARSAYILMAZ, ithal denenerek OLCULUR.
    """
    import importlib.util
    try:
        agac = ast.parse(kaynak)
    except SyntaxError:
        return set()
    yok: set[str] = set()
    for n in ast.walk(agac):
        adlar: list[tuple[str, str]] = []
        if isinstance(n, ast.Import):
            adlar = [(a.name, a.asname or a.name.split(".")[0]) for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            adlar = [(n.module, a.asname or a.name) for a in n.names]
        for modul, yerel in adlar:
            try:
                if importlib.util.find_spec(modul.split(".")[0]) is None:
                    yok.add(yerel)
            except (ImportError, ValueError, ModuleNotFoundError):
                yok.add(yerel)
    return yok


def _qt_satirlari(kaynak: str) -> set[int]:
    """Tabani Qt olan siniflarin GOVDESINDEKI tum satir numaralari."""
    try:
        agac = ast.parse(kaynak)
    except SyntaxError:
        return set()
    kapsanan: set[int] = set()
    for n in ast.walk(agac):
        if not isinstance(n, ast.ClassDef):
            continue
        if not any(QT_TABAN.match(ast.unparse(b)) for b in n.bases):
            continue
        for m in ast.walk(n):
            if hasattr(m, "lineno"):
                kapsanan.add(m.lineno)
    return kapsanan


def _norm(y: str) -> str:
    return y.replace("\\", "/")


def _katmanlar() -> dict[str, list[str]]:
    """Katman uyeligi TEK KAYNAKTAN. Burada yeniden yazmak, iki listeyi
    sessizce ayrisma riskine sokardi --- bu deponun tekrarlayan kusuru."""
    from kapsam_katmanlari import KATMANLAR
    return {ad: KATMANLAR[ad] for ad in ("Arayüz (GUI)", "Dış-süreç köprüleri")}


def _dis_bagimli_satirlar(kaynak: str, yok_deseni) -> set[int]:
    """Ekran/dis-surec bagimliligi FONKSIYON DUZEYINDE yayilir.

    OLCUM KENDI LEHINE BOZULUYORDU. Siniflandirma satir-yereldi: `vsp.…`
    cagrisini SARAN `_set_naca_profile(...)` satiri hicbir dis ad icermez ve
    "sinanabilir" sayiliyordu. Ayni sey `tablo = g.stdout` (g bir subprocess
    sonucu) ve `_run_python(...)` icin de gecerliydi. Bu yanlilik zararsiz
    degil: `sinanabilir` sisiyor, oran sisiyor ve ``rapor comert'' hukmu
    HAKSIZ yere tetiklenebiliyor --- yani olcut, olcenin isine gelen yone
    kayiyordu.

    KURAL: bir fonksiyonun govdesi dis bir ada (Qt, subprocess, ithal
    edilemeyen modul) DOKUNUYORSA o fonksiyonun TUM satirlari dis bagimlidir.
    Cagrilan yardimcilarin kendileri de ayni kuralla isaretlendiginden
    bulasma bir kat daha tasinir.
    """
    try:
        agac = ast.parse(kaynak)
    except SyntaxError:
        return set()
    satirlar = kaynak.splitlines()

    def _dis_mi(dugum) -> bool:
        for m in ast.walk(dugum):
            ln = getattr(m, "lineno", None)
            if ln is None or ln > len(satirlar):
                continue
            t = satirlar[ln - 1]
            if QT_ADI.search(t) or DIS_SUREC.search(t):
                return True
            if yok_deseni is not None and yok_deseni.search(t):
                return True
        return False

    dis: set[int] = set()
    kirli_ad: set[str] = set()
    for _ in range(2):          # bir kat daha bulasma
        for n in ast.walk(agac):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            cagirilan = {m.func.id for m in ast.walk(n)
                         if isinstance(m, ast.Call) and isinstance(m.func, ast.Name)}
            if _dis_mi(n) or (cagirilan & kirli_ad):
                kirli_ad.add(n.name)
                for m in ast.walk(n):
                    if hasattr(m, "lineno"):
                        dis.add(m.lineno)
    return dis


def _giris_noktasi_satirlari(kaynak: str) -> set[int]:
    """`if __name__ == "__main__"` bloku ve `main()` govdesindeki satirlar.

    Bunlar teknik olarak saf mantiktir ama sinanmamis bir HUKUM degildir ---
    CLI iskelesidir (`mode = sys.argv[1] if ...`). Yine de `sinanabilir`
    kovasindan DUSULMEZ, yalniz AYRICA sayilir: dusmek oran'i kucultur ve
    o yon raporun isine gelen yondur. Okur iki sayiyi da gorur, hukum
    UST SINIRDAN verilir.
    """
    try:
        agac = ast.parse(kaynak)
    except SyntaxError:
        return set()
    hedef: set[int] = set()
    for n in ast.walk(agac):
        giris = (isinstance(n, ast.If) and "__name__" in ast.unparse(n.test)) or                 (isinstance(n, ast.FunctionDef) and n.name == "main")
        if giris:
            for m in ast.walk(n):
                if hasattr(m, "lineno"):
                    hedef.add(m.lineno)
    return hedef


def _kovala(ad: str, v: dict) -> dict:
    from karar_katmani_kapsami import IO_DESEN, SAVUNMA_DESEN
    ham = (KOK / ad).read_text(encoding="utf-8", errors="replace")
    kaynak = ham.splitlines()
    qt = _qt_satirlari(ham)
    yok = _ithal_edilemeyenler(ham)
    _yok_deseni = (re.compile(r"\b(?:" + "|".join(map(re.escape, sorted(yok)))
                              + r")\b") if yok else None)
    yayilan = _dis_bagimli_satirlar(ham, _yok_deseni)
    giris = _giris_noktasi_satirlari(ham)
    io = savunma = dis = 0
    sinanabilir = []
    for ln in v["missing_lines"]:
        metin = kaynak[ln - 1] if ln - 1 < len(kaynak) else ""
        if IO_DESEN.match(metin) or not metin.strip():
            io += 1
        elif SAVUNMA_DESEN.match(metin):
            savunma += 1
        elif (ln in qt or ln in yayilan or QT_ADI.search(metin)
              or DIS_SUREC.search(metin)
              or (_yok_deseni is not None and _yok_deseni.search(metin))):
            dis += 1
        else:
            sinanabilir.append({"satir": ln, "kod": metin.strip()[:90],
                                "giris_noktasi": ln in giris})
    s = v["summary"]
    return {"modul": ad, "kapsam_pct": round(s["percent_covered"], 1),
            "ifade": s["num_statements"], "eksik": s["missing_lines"],
            "eksik_io": io, "eksik_savunma": savunma, "eksik_dis_bagimli": dis,
            "_ithal_edilemeyen": sorted(yok),
            "eksik_sinanabilir": len(sinanabilir),
            "_bunun_girisi": sum(1 for x in sinanabilir if x["giris_noktasi"]),
            "_ornekler": sinanabilir}


def olc(cov_json: Path) -> dict:
    d = json.loads(cov_json.read_text(encoding="utf-8"))
    dosyalar = {_norm(k): v for k, v in d["files"].items()}
    katmanlar, moduller = {}, []
    for katman, uyeler in _katmanlar().items():
        toplam = {"eksik": 0, "eksik_io": 0, "eksik_savunma": 0,
                  "eksik_dis_bagimli": 0, "eksik_sinanabilir": 0, "ifade": 0,
                  "_bunun_girisi": 0}
        for m in uyeler:
            v = next((x for y, x in dosyalar.items()
                      if y == _norm(m) or y.endswith("/" + _norm(m))), None)
            if not v:
                moduller.append({"modul": m, "durum": "cov.json'da YOK"})
                continue
            r = _kovala(m, v)
            moduller.append(r)
            for k in toplam:
                toplam[k] += r[k]
        katmanlar[katman] = toplam
    return _ozetle(katmanlar, moduller)


def _ozetle(katmanlar: dict, moduller: list) -> dict:
    # HUKUM KATMAN BASINA VERILIR, TOPLAM UZERINDEN DEGIL.
    #
    # Ilk surum toplami kullaniyordu ve sonuc %12,4 cikip esigin altinda
    # kaliyordu --- yani "rapor hakli" diyordu. Ama ayrisim asimetrik:
    # arayuzde %1,5, kopru katmaninda %29,0. Toplam, kopru katmanini
    # arayuzun buyuk paydasinda ERITIYORDU. Raporun kendi bolumu tam bunu
    # soyluyor: "Toplam yuzde tek basina yaniltcidir". Olcum o kusuru
    # kendi icinde tekrar ediyordu.
    for k in katmanlar.values():
        k["oran_pct"] = (round(100 * k["eksik_sinanabilir"] / k["eksik"], 1)
                         if k["eksik"] else 0.0)
        k["iddia_comert_mi"] = bool(k["oran_pct"] > COMERTLIK_ESIGI_PCT)
    ge = sum(k["eksik"] for k in katmanlar.values())
    gs = sum(k["eksik_sinanabilir"] for k in katmanlar.values())
    oran = round(100 * gs / ge, 1) if ge else 0.0
    ornekler = [{"modul": m["modul"], **o}
                for m in moduller for o in m.get("_ornekler", [])][:ORNEK]
    for m in moduller:
        m.pop("_ornekler", None)
    comert = [ad for ad, k in katmanlar.items() if k["iddia_comert_mi"]]
    return {
        "vaka": "Arayüz + dış-köprü kapsamı — 'çapa koşularıyla sınanır' iddiası",
        "_neden": ("Rapor iki dusuk katmani 'birim testiyle degil capa "
                   "kosulariyla sinanir' diye savunuyor. Cumle sinanabilir "
                   "bir iddiadir: kapsanmamis satirlarin ne kadari gercekten "
                   "ekran ya da dis surec istiyor?"),
        "katmanlar": katmanlar,
        "moduller": sorted(moduller, key=lambda m: -m.get("eksik_sinanabilir", 0)),
        "toplam_eksik": ge,
        "ekran_cozucu_GEREKTIRMEYEN_eksik": gs,
        "toplam_oran_pct": oran,
        # KATMAN ADI SABIT YAZILMAZ: ilk surum 'Dış-süreç köprüleri'ni dogrudan
        # indeksliyordu ve baska bir katman kumesiyle cagrilinca KeyError
        # veriyordu. En yuksek oranli katman OLCUMDEN secilir.
        "_toplam_neden_hukum_vermez": (
            "Toplam oran YAYIMLANIR ama HUKUM VERMEZ: buyuk paydali katman "
            f"kucugu eritir. Toplam %{oran}, en yuksek oranli katman ise "
            + (lambda a: f"{a[0]} %{a[1]['oran_pct']}")(
                max(katmanlar.items(), key=lambda x: x[1]["oran_pct"]))
            + f" (esik %{COMERTLIK_ESIGI_PCT})."),
        "esik_pct": COMERTLIK_ESIGI_PCT,
        "iddia_comert_katmanlar": comert,
        "iddia_comert_mi": bool(comert),
        "_ornekler": ornekler,
        "verdikt": _hukum(katmanlar, ge, gs, oran),
        "_kisit": ("Desen ayrimi SEZGISELDIR ve `sinanabilir` sayisi bir UST "
                   "SINIRDIR: okunmadan 'sinanmamis hukum' sayilmaz. Ornekler "
                   "kayda yazilir ki ayrim denetlenebilsin. Ayrica kapsam "
                   "SATIR kapsamidir; sinanmis satir dogru sinanmis demek "
                   "degildir."),
        "_uretim": "Üretim: python experiments/arayuz_kopru_kapsami.py",
    }


def _hukum(katmanlar: dict, ge: int, gs: int, oran: float) -> str:
    p = "; ".join(f"{ad}: {k['eksik']} eksikten {k['eksik_sinanabilir']}'i "
                  f"ekran/çözücü istemiyor (%{k['oran_pct']})"
                  for ad, k in katmanlar.items())
    comert = [ad for ad, k in katmanlar.items() if k["iddia_comert_mi"]]
    s = f"{p}. Toplam %{oran} --- ama hüküm TOPLAMDAN verilmez, çünkü büyük "
    s += "paydalı katman küçüğü eritir. "
    if not comert:
        return s + (f"Hiçbir katman %{COMERTLIK_ESIGI_PCT} eşiğini aşmıyor: "
                    "raporun 'çapa koşularıyla sınanır' cümlesi ÖLÇÜMLE "
                    "destekleniyor.")
    kalan = [ad for ad in katmanlar if ad not in comert]
    s += (f"EŞİĞİ AŞAN: {', '.join(comert)} --- bu katman(lar) için raporun "
          "cümlesi fazla cömert ve daraltılmalı: kapsanmamış satırların "
          "önemli bir kısmı ne ekran ne çözücü istiyor, yalnız yazılmamış "
          "test.")
    if kalan:
        s += f" Cümle {', '.join(kalan)} için ölçümle destekleniyor."
    return s


def _bayat_kaynaklar(cov_json: Path) -> list[str]:
    """`cov.json`dan SONRA değişmiş ölçülen kaynaklar.

    NEDEN KAPI. Kapsam kaydı SATIR NUMARASI tasir; siniflandirma o numarayla
    dosyanin BUGUNKU metnini okur. Kaynak arada degistiyse numaralar kayar ve
    olcum yanlis satirin metnini siniflandirir --- sessizce, cunku sonuc yine
    makul gorunur. Tam da bu oldu: `construct2d_bridge`e iki satir eklendi ve
    kayit 207'den 209'a ``degisti''; degisen kod degil HIZALAMAYDI.
    """
    t = cov_json.stat().st_mtime
    bayat = []
    for uyeler in _katmanlar().values():
        for m in uyeler:
            p = KOK / m
            if p.exists() and p.stat().st_mtime > t:
                bayat.append(m)
    return sorted(bayat)


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    cov = KOK / "cov.json"
    if not cov.exists():
        print("cov.json yok — önce: python -m pytest -q --cov=. "
              "--cov-report=json:cov.json")
        return 1
    bayat = _bayat_kaynaklar(cov)
    if bayat:
        print("cov.json BAYAT — şu kaynak(lar) ondan sonra değişti:\n  "
              + "\n  ".join(bayat)
              + "\n\nKapsam SATIR NUMARASI taşır; kaynak değişince numaralar "
                "kayar ve\nsınıflandırma YANLIŞ SATIRIN metnini okur. Ölçümü "
                "yenileyin:\n  python -m pytest -q --cov=. "
                "--cov-report=json:cov.json")
        return 1
    r = olc(cov)
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
