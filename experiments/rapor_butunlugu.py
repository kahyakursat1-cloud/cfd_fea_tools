"""Rapor PDF'i BÜTÜN MÜ --- çözülmemiş referans, boş içindekiler, bayat çıktı.

BU KAPI BİR DIŞ HAKEM RAPORUNDAN DOĞDU. Hakem 61 sayfalık PDF'de 32 adet
``§??'' saydı, içindekilerin boş olduğunu ve iki ayrı şeklin ``Şekil 1''
diye numaralandığını bildirdi ve bunu haklı olarak P0 saydı: raporun ana
iddiası izlenebilirlik, ve okur ``bkz. §??'' gördüğünde o zincir kopuyor.

SEBEP TEKNİK OLARAK SIRADANDI VE TAM DA BU YÜZDEN KAPI GEREKİYOR: PDF'i
pdflatex ile BİR KEZ derlemiştim. LaTeX çapraz referansları ve
içindekileri ikinci geçişte çözer; dosyanın kendi başlığında ``(iki kez)''
yazıyordu. Üç geçişten sonra sayım sıfıra indi. Yani kusur ne yazımda ne
içerikteydi --- ÜRETİM ADIMINDAYDI ve hiçbir şey onu denetlemiyordu.

NE DENETLER:
  1. Çözülmemiş referans: ``??'' hiçbir biçimde geçmemeli.
  2. İçindekiler GERÇEKTEN dolu olmalı (başlık var, liste yok hâli).
  3. Şekil numaraları TEKRARLAMAMALI.
  4. PDF, KAYNAĞINDAN ESKİ OLMAMALI --- bayat bir PDF denetimden geçer ve
     yayımlanan başka bir belge olur.

NE DENETLEMEZ: içeriğin doğruluğunu. Bu bir DİZGİ bütünlüğü kapısıdır;
sayıların kanıtla uyumu ayrı testlerin işidir.

    python experiments/rapor_butunlugu.py
Çıktı: rapor_butunlugu.json
"""
from __future__ import annotations

import collections
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "rapor_butunlugu.json"
TEX = KOK / "docs" / "teknik_rapor.tex"
PDF = KOK / "docs" / "teknik_rapor.pdf"


def _metin(pdf: Path) -> tuple[str | None, str]:
    """PDF metni --- pdftotext yoksa AÇIKÇA söyle, sessizce geçme."""
    arac = shutil.which("pdftotext")
    if arac is None:
        return None, "pdftotext yok (poppler kurulu değil)"
    cikti = pdf.with_suffix(".butunluk.txt")
    try:
        r = subprocess.run([arac, "-enc", "UTF-8", str(pdf), str(cikti)],
                           capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"pdftotext çalışmadı: {type(e).__name__}"
    if r.returncode != 0 or not cikti.exists():
        return None, f"pdftotext rc={r.returncode}"
    t = cikti.read_text(encoding="utf-8", errors="replace")
    cikti.unlink(missing_ok=True)
    return t, ""


# Kirilan bir makronun DIZILMIS kalintisi. Susluler dizgide yenildigi
# icin desen "{" ARAMAZ --- ilk denememde ariyordu ve kusuru hic
# bulamadi. Aranan sey: kirilan makronun kuyrugu + etiket ad-uzayi.
_KALINTI = re.compile(
    r"(?:ef|able|ig|ite|mph|extbf|exttt)(?:sub|sec|fig|tab|eq):"
    r"[A-Za-z0-9:_-]+")


def ham_latex_kalintisi(metin: str) -> list[str]:
    """Dizilmis metne sizmis LaTeX kalintilari (tekil, sirali).

    Modul duzeyinde, cunku olcut DAVRANISLA sinanmali: bir test gercek
    bir sizinti dizgesini verip yakalandigini, temiz bir metni verip
    yakalanmadigini gorebilsin.
    """
    return sorted(set(_KALINTI.findall(metin)))


def olc() -> dict:
    if not PDF.exists():
        return _ozetle(None, "PDF yok — önce docs/ içinde pdflatex koşulmalı")
    t, neden = _metin(PDF)
    if t is None:
        return _ozetle(None, neden)

    # 1) COZULMEMIS REFERANS. LaTeX cozemedigi her referansi "??" basar;
    #    bicimi (§??, Sekil ??, [??]) atifa gore degisir, o yuzden HAM
    #    dizge sayilir --- alt bicimleri ayrica raporlanir.
    ham = t.count("??")
    bicim = {ad: t.count(ad) for ad in ("§??", "Şekil ??", "Tablo ??",
                                        "Bölüm ??", "[??]")}

    # 2) ICINDEKILER: baslik var ama liste yok hali. Baslikten sonraki
    #    1500 karakterde "<numara> <baslik> <sayfa>" deseni aranir.
    i = t.find("İçindekiler")
    toc = t[i:i + 1500] if i >= 0 else ""
    toc_girdi = len(re.findall(r"\n\d+(?:\.\d+)?\s+\S", toc))

    # 3) SEKIL NUMARALARI: ayni numara iki kez basiliyorsa numaralandirma
    #    sifirlanmis demektir (hakem "cift Sekil 1" gordu).
    #
    #    OLCUT BIR KEZ FAZLA DARDI VE KAPI IDDIASINDAN AZ SEY OLCUYORDU.
    #    Yalniz "Sekil N:" (iki nokta) araniyordu --- yani `\caption`
    #    ailesini. Elle yazilmis TikZ basliklari ise "Sekil N." (nokta)
    #    biciminde ve AYRI bir numaralandirma yuruTuyordu; ikisi 1-4'te
    #    cakisiyordu ve kapi "11 numara tekil" diyordu. Hakem cakismayi
    #    gordu, kapi gormedi. Artik HER IKI bicim de sayilir.
    say = collections.Counter(re.findall(r"Şekil (\d+)[:.]", t))
    tekrar = {k: v for k, v in say.items() if v > 1}
    # Ve numaralar ARTAN olmali: tekrar olmadan da atlama/geri sarma
    # numaralandirmanin bozuldugunu gosterir.
    sira = [int(x) for x in re.findall(r"Şekil (\d+)[:.]", t)]
    monoton = sira == sorted(set(sira)) if sira else True

    # 5) HAM LaTeX KALINTISI. "\S\ref{...}" satir sonunda kirilinca LaTeX
    #    hic \ref gormez: cikti "??" DEGIL, duz metin "efsub:fsi-korunum"
    #    olur. Kapinin "cozulmemis referans yok" iddiasi bu kusuru
    #    kapsamiyordu --- hakem sayfa 21'de gordu. Susluler dizgide
    #    yenildigi icin desen "{" ARAMAZ; kirilan makronun kuyrugu +
    #    etiket ad-uzayi aranir.
    kalinti = ham_latex_kalintisi(t)

    # 4) BAYATLIK: PDF kaynagindan eskiyse denetlenen sey YAYIMLANAN sey
    #    degildir. Bu kapiyi bugun ogrendik --- ayni sinif hatayi FSI
    #    dongusunde de odedik.
    bayat = None
    if TEX.exists():
        bayat = PDF.stat().st_mtime < TEX.stat().st_mtime

    return _ozetle({
        "sayfa_metni_bayt": len(t),
        "cozulmemis_ham": ham,
        "cozulmemis_bicim": bicim,
        "icindekiler_girdi": toc_girdi,
        "sekil_numaralari": len(say),
        "tekrar_eden_sekil": tekrar,
        "sekil_monoton": monoton,
        "sekil_sirasi": sira,
        "ham_latex_kalintisi": sorted(set(kalinti)),
        "pdf_bayat": bayat,
        "tex_var": TEX.exists(),
    }, None)


def _ozetle(d: dict | None, neden: str | None) -> dict:
    return {
        "vaka": "Rapor PDF bütünlüğü — dizgi kapısı",
        "_neden": ("Dis hakem 61 sayfalik PDF'de 32 adet '§??' saydi, bos "
                   "icindekiler ve cift 'Sekil 1' bildirdi ve P0 saydi. "
                   "Sebep yazimda degil URETIM ADIMINDAYDI: pdflatex bir "
                   "kez kosulmustu, oysa capraz referanslar ikinci gecişte "
                   "cozulur. Hicbir sey bunu denetlemiyordu."),
        "olcum": d,
        "verdikt": _hukum(d, neden),
        "_kisit": (
            "DIZGI butunlugu kapisidir, ICERIK dogrulugunu denetlemez --- "
            "sayilarin kanitla uyumu ayri testlerin isi. 'Sekil ??' gibi "
            "alt bicimler pdftotext'in satir kirmasina bagli olarak "
            "bolunebilir; bu yuzden asil olcut HAM '??' sayimidir ve "
            "bicim dokumu yalnizca teshis icindir. pdftotext yoksa kapi "
            "SESSIZCE gecmez, acikca 'olculemedi' der."),
        "_uretim": "Üretim: python experiments/rapor_butunlugu.py",
    }


def _hukum(d: dict | None, neden: str | None) -> str:
    if d is None:
        return f"ÖLÇÜLEMEDİ: {neden}"
    sorun = []
    if d["cozulmemis_ham"]:
        sorun.append(f"{d['cozulmemis_ham']} çözülmemiş referans "
                     f"({d['cozulmemis_bicim']})")
    if d["icindekiler_girdi"] < 5:
        sorun.append(f"içindekiler yalnız {d['icindekiler_girdi']} girdi "
                     f"gösteriyor")
    if d["tekrar_eden_sekil"]:
        sorun.append(f"tekrar eden şekil numarası {d['tekrar_eden_sekil']}")
    elif not d.get("sekil_monoton", True):
        # ELIF: tekrar zaten bildirildiyse ayni kusuru iki kez saymayalim.
        sorun.append(f"şekil numaraları artan değil: {d['sekil_sirasi']}")
    if d.get("ham_latex_kalintisi"):
        sorun.append("ham LaTeX kalıntısı metne sızmış: "
                     + ", ".join(d["ham_latex_kalintisi"]))
    if d["pdf_bayat"]:
        sorun.append("PDF kaynağından ESKİ")
    if sorun:
        # TAVSIYE KUSURA GORE VERILIR. Once tek bir cumle vardi ("pdflatex'i
        # 2-3 kez kos") ve kapi genisletilince o tavsiye YANLIS oldu: ham
        # kalinti ve cakisan numaralandirma yeniden derlemekle gecmez,
        # KAYNAK duzeltmesi ister. Yanlis bir care, kusurun kendisi kadar
        # zarar verir --- kullanici uc kez derler ve "gecmiyor" der.
        care = []
        if d["cozulmemis_ham"] or d["pdf_bayat"]:
            care.append("çapraz referanslar oturana kadar pdflatex'i "
                        "(tipik 2-3 kez) koş")
        if d.get("ham_latex_kalintisi"):
            care.append("KAYNAK düzeltmesi: kırılan makro satır sonunda "
                        "bölünmüş, tek satıra al")
        if d["tekrar_eden_sekil"] or not d.get("sekil_monoton", True):
            care.append("KAYNAK düzeltmesi: elle numaralanan başlıkları "
                        "gerçek sayaca bağla (\\refstepcounter{figure})")
        return ("RAPOR YAYINA HAZIR DEĞİL: " + "; ".join(sorun)
                + ". Çare: " + "; ".join(care) + ".")
    return (f"Bütün: çözülmemiş referans yok, ham LaTeX kalıntısı yok, "
            f"içindekiler {d['icindekiler_girdi']} girdi taşıyor, "
            f"{d['sekil_numaralari']} şekil numarası tekil ve artan, PDF "
            f"kaynağından yeni. Bu bir DİZGİ hükmüdür --- içeriğin kanıtla "
            f"uyumu ayrı testlerin işidir.")


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
