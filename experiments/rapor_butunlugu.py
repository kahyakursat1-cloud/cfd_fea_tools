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
    say = collections.Counter(re.findall(r"Şekil (\d+):", t))
    tekrar = {k: v for k, v in say.items() if v > 1}

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
    if d["pdf_bayat"]:
        sorun.append("PDF kaynağından ESKİ")
    if sorun:
        return ("RAPOR YAYINA HAZIR DEĞİL: " + "; ".join(sorun)
                + ". Düzeltme genelde tek satır: pdflatex'i çapraz "
                  "referanslar oturana kadar (tipik 2-3 kez) koş.")
    return (f"Bütün: çözülmemiş referans yok, içindekiler "
            f"{d['icindekiler_girdi']} girdi taşıyor, {d['sekil_numaralari']} "
            f"şekil numarası tekil, PDF kaynağından yeni. Bu bir DİZGİ "
            f"hükmüdür --- içeriğin kanıtla uyumu ayrı testlerin işidir.")


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
