"""Turek--Hron kıyaslama zinciri --- tek yerden DURUM, tek komutla KOŞU.

NEDEN. Zincir dokuz betiğe dağılmış durumda ve her biri kendi kanıtını
yazıyor. ``Bu platform FSI'da nerede duruyor'' sorusunun cevabı bugün dokuz
JSON'u elle açmayı gerektiriyor --- yani ölçüm var, TOPLU HÜKÜM yok. Bu
modül o boşluğu kapatır.

İKİ KİP:
    python experiments/turek_hron_kiyaslama.py          # DURUM (koşmaz)
    python experiments/turek_hron_kiyaslama.py --kos    # eksikleri koşar

SAYILAR BURADA YENİDEN HESAPLANMAZ, KAYITTAN OKUNUR. Her aşamanın sapması
kendi kanıt dosyasında zaten var; buraya kopyalansaydı iki kaynak olur ve
biri sessizce eskirdi --- bu deponun tekrar tekrar ödediği kusur. Bu dosya
yalnızca YOL bilir (hangi alan, hangi dosya), DEĞER bilmez.

BAYATLIK DA DURUMUN PARÇASI: bir aşamanın kanıtı kendi betiğinden eskiyse
"geçti" demek yanıltıcıdır --- kod değişmiş, sayı değişmemiş olabilir.

NE KAPSAMAZ: FSI2/FSI3. Yapısal ön koşulları (CSM3) doğrulandı ama
zaman-bağımlı kuplaj YAZILMADI; zincir onları "eksik" diye değil, HİÇ
listelemez --- olmayan bir aşamayı "başarısız" göstermek yanlış olurdu.

Çıktı: turek_hron_kiyaslama.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

CIKTI = KOK / "turek_hron_kiyaslama.json"

# ZINCIR: sira BAGIMLILIK sirasidir, onem sirasi degil. Her asama kendinden
# oncekinin ciktisini kullanir; `--kos` bu siraya uyar.
#
# `olcut`: (etiket, kanit icindeki YOL, kabul bandi %). Yol bir demettir ve
# ic ice sozluklerde gezer. Band `None` ise asama bir SAPMA olcmez (ornegin
# ag uretimi) ve yalnizca kosup kosmadigi bakilir.
ZINCIR = (
    {"ad": "ağ (gmsh)", "betik": "turek_hron_gmsh.py",
     "kanit": "turek_hron_gmsh.json", "olcut": ()},
    {"ad": "ağ kapısı", "betik": "turek_hron_ag_kapisi.py",
     "kanit": "turek_hron_ag_kapisi.json", "olcut": ()},
    {"ad": "CFD1 (rijit)", "betik": "turek_hron_cfd1.py",
     "kanit": "turek_hron_cfd1.json",
     "olcut": (("sürükleme", ("sapma", "surukleme_pct"), 2.0),
               ("taşıma", ("sapma", "tasima_pct"), 5.0))},
    {"ad": "CFD1 ağ ailesi", "betik": "turek_hron_ag_bagimsizligi.py",
     "kanit": "turek_hron_ag_bagimsizligi.json",
     # BU BIR SAPMA DEGIL YAYILIMDIR ve band da o yuzden gevsek: aile
     # referansa degil KENDINE karsi olculur.
     "olcut": (("sürükleme yayılımı", ("surukleme", "yayilim_pct"), 5.0),
               ("taşıma yayılımı", ("tasima", "yayilim_pct"), 10.0))},
    {"ad": "CSM1 (yapı, statik)", "betik": "turek_hron_csm1.py",
     "kanit": "turek_hron_csm1.json",
     "olcut": (("uy", ("sapma_nlgeom", "uy_pct"), 5.0),
               ("ux", ("sapma_nlgeom", "ux_pct"), 10.0))},
    {"ad": "CSM3 (yapı, geçici)", "betik": "turek_hron_csm3.py",
     "kanit": "turek_hron_csm3.json",
     "olcut": (("uy ortalama", ("sapma_uy", "ortalama_pct"), 5.0),
               ("uy genlik", ("sapma_uy", "genlik_pct"), 5.0),
               ("frekans", ("sapma_uy", "frekans_pct"), 3.0))},
    {"ad": "FSI1 (tek yönlü)", "betik": "turek_hron_fsi1.py",
     "kanit": "turek_hron_fsi1.json",
     # TEK YONLU KOSU uy'yi TUTTURMAZ ve tutturmasi BEKLENMEZ: akis rijit
     # bayrakla cozulur. Band bu yuzden yalniz ux icin dardir; uy asamanin
     # KENDI kisitinda aciklanir ve burada olcut olarak KULLANILMAZ.
     "olcut": (("ux", ("sapma", "ux_pct"), 10.0),)},
    {"ad": "FSI1 (iki yönlü)", "betik": "turek_hron_fsi1_iki_yonlu.py",
     "kanit": "turek_hron_fsi1_iki_yonlu.json",
     "olcut": (("uy", ("sapma", "uy_pct"), 5.0),
               ("ux", ("sapma", "ux_pct"), 5.0),
               ("sürükleme", ("surukleme_sapma_pct",), 2.0),
               ("taşıma", ("tasima_sapma_pct",), 5.0))},
)


def _gez(d: dict, yol: tuple):
    """İç içe sözlükte yol izle --- eksikse None, patlamaz."""
    for k in yol:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def _asama(a: dict) -> dict:
    kanit = KOK / a["kanit"]
    betik = HERE / a["betik"]
    if not kanit.exists():
        return {"ad": a["ad"], "durum": "KOŞULMADI", "kanit": a["kanit"],
                "neden": "kanıt dosyası yok"}
    try:
        d = json.loads(kanit.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"ad": a["ad"], "durum": "OKUNAMADI", "kanit": a["kanit"],
                "neden": f"{type(e).__name__}: {e}"}
    # BAYATLIK: kanit betiginden eskiyse "gecti" demek yaniltici olur.
    bayat = (betik.exists()
             and kanit.stat().st_mtime < betik.stat().st_mtime)
    olcum, asan = [], []
    for etiket, yol, band in a["olcut"]:
        v = _gez(d, yol)
        if v is None:
            olcum.append({"etiket": etiket, "deger_pct": None, "band": band,
                          "durum": "ÖLÇÜLMEDİ"})
            asan.append(etiket)
            continue
        gecti = abs(float(v)) <= band
        olcum.append({"etiket": etiket, "deger_pct": round(float(v), 3),
                      "band": band, "durum": "içinde" if gecti else "AŞIYOR"})
        if not gecti:
            asan.append(etiket)
    durum = ("BAYAT" if bayat else
             "AŞIYOR" if asan else
             "KOŞTU" if not a["olcut"] else "BANDINDA")
    return {"ad": a["ad"], "durum": durum, "kanit": a["kanit"],
            "bayat": bayat, "olcum": olcum, "asan": asan,
            "verdikt_ozet": (d.get("verdikt") or "")[:220]}


def olc(kos: bool = False) -> dict:
    kosulan = []
    if kos:
        for a in ZINCIR:
            if (KOK / a["kanit"]).exists():
                continue
            r = subprocess.run([sys.executable, str(HERE / a["betik"])],
                               cwd=str(KOK), capture_output=True, timeout=43200)
            kosulan.append({"betik": a["betik"], "rc": r.returncode})
            if r.returncode != 0:
                break
    return _ozetle([_asama(a) for a in ZINCIR], kosulan)


def _ozetle(asamalar: list, kosulan: list) -> dict:
    return {
        "vaka": "Turek-Hron kıyaslama zinciri — toplu durum",
        "_neden": ("Zincir dokuz betige dagilmis ve her biri kendi kanitini "
                   "yaziyor. 'Bu platform FSI'da nerede duruyor' sorusunun "
                   "cevabi bugune kadar dokuz JSON'u elle acmayi "
                   "gerektiriyordu: olcum var, TOPLU HUKUM yoktu."),
        "asamalar": asamalar,
        "kosulan": kosulan,
        "verdikt": _hukum(asamalar),
        "_kisit": (
            "SAYILAR BURADA HESAPLANMAZ, kanit dosyalarindan OKUNUR --- bu "
            "dosya YOL bilir, DEGER bilmez. Bandlar BEYANDIR ve her asamanin "
            "kendi kaydindaki kisitlarin yerine GECMEZ: 'bandinda' demek "
            "'GCI var' demek degildir. FSI2/FSI3 zincire DAHIL DEGILDIR "
            "cunku kuplaj yazilmadi; olmayan bir asamayi 'basarisiz' "
            "gostermek yanlis olurdu. Tek yonlu FSI1'in uy sapmasi olcut "
            "ALINMAZ --- akis rijit bayrakla cozuldugu icin tutturmasi "
            "beklenmez ve bunu o asamanin kendi kaydi acikliyor."),
        "_uretim": "Üretim: python experiments/turek_hron_kiyaslama.py",
    }


def _hukum(asamalar: list) -> str:
    yok = [a["ad"] for a in asamalar if a["durum"] == "KOŞULMADI"]
    bayat = [a["ad"] for a in asamalar if a.get("bayat")]
    asan = [a["ad"] for a in asamalar if a["durum"] == "AŞIYOR"]
    n_band = sum(1 for a in asamalar if a["durum"] == "BANDINDA")
    n_olcut = sum(1 for a in asamalar if a.get("olcum"))
    s = f"{len(asamalar)} aşamalı zincir. "
    if yok:
        s += f"KOŞULMAYAN: {', '.join(yok)}. "
    if bayat:
        s += (f"BAYAT (kanıt betiğinden eski): {', '.join(bayat)} --- kod "
              f"değişmiş, sayı değişmemiş olabilir. ")
    if asan:
        s += f"BANDI AŞAN: {', '.join(asan)}. "
    if not (yok or bayat or asan):
        s += (f"Tümü koştu; ölçüt taşıyan {n_olcut} aşamanın {n_band}'i "
              f"kendi bandında. ")
    return s + (
        "BU BİR GCI BEYANI DEĞİLDİR: bandlar kabul eşikleridir, sayısal "
        "belirsizlik değil. Zaman-bağımlı kuplaj (FSI2/FSI3) zincirde YOK "
        "--- yapısal ön koşulu CSM3 ile doğrulandı, kuplajın kendisi "
        "yazılmadı.")


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    r = olc(kos="--kos" in sys.argv)
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{'aşama':22s} {'durum':10s} ölçümler")
    for a in r["asamalar"]:
        o = ", ".join(f"{m['etiket']} %{m['deger_pct']}"
                      for m in a.get("olcum", []))
        print(f"{a['ad'][:22]:22s} {a['durum']:10s} {o}")
    print(f"\n{r['verdikt']}\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
