"""Küre çapası kararlı-RANS ile kapanabilir mi? URANS'a geçmek çare mi?

VAKA. Katman örgüsü düzeltildikten SONRA küre çapası ölçüldü (2026-08-19):
    y⁺ 59,08 → 5,54   (katman 0,535 → 6,82, hedef kalınlığın %96,7'si)
    Cd 0,142 → 0,243  (referans 0,47)
Duvar çözünürlüğü 10,7 kat iyileşti ve çapa YİNE düştü — ama bu kez başka
gerekçeyle: ince seviye YAKINSAMIYOR. Rezidüeller platoya oturuyor ve son
%20'de Cd sürüklenmesi %46,7 (sınır %2).

SORU. "Kararlı RANS yakınsamıyorsa URANS'a geçelim" akla yatkın görünüyor.
Bu betik o adımı ATMADAN ÖNCE elde ne olduğunu ölçer, çünkü URANS 4 ağ
seviyesiyle birlikte büyük bir iştir ve getirisi belirsizdir.

ÖLÇÜLEN. forceCoeffs geçmişinin ikinci yarısı (başlangıç geçicileri dışarıda):
salınım yapılı mı, geniş bantlı mı? En güçlü birkaç bileşen gücün büyük
kısmını tutuyorsa altta tutarlı bir hareket vardır; güç tabana yayılmışsa
salınım sayısal gürültüdür.

ÖLÇÜMÜN SINIRI — BU KRİTİK. Koşu KARARLI (SIMPLE) çözücüyle yapıldı, yani
eksen fiziksel zaman DEĞİL iterasyondur. Buradan çıkan "frekans" bir Strouhal
sayısı değildir ve fiziksel dökülme periyoduyla ilişkilendirilemez. Ölçüm
yalnız şunu ayırt eder: yakınsamama YAPILI bir limit çevrimi mi, yoksa
rastgele gürültü mü. Spektral aralık sorusunu ÇÖZMEZ.

    python experiments/kure_kararli_rans_hukmu.py
Çıktı: kure_kararli_rans_hukmu.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KOK = HERE.parent

KOSU = (KOK / "validation_anchors_runs" / "_anchor_sphere" / "_anchor_sphere"
        / "postProcessing" / "forceCoeffs1" / "0" / "forceCoeffs.dat")
CD_REF = 0.47


def _oku(p: Path):
    basliklar = [x for x in p.read_text().splitlines() if x.startswith("#")]
    kolon = basliklar[-1].lstrip("#").split()
    d = np.loadtxt(p)
    return d[:, 0], d[:, kolon.index("Cd")], kolon


def main() -> int:
    if not KOSU.exists():
        print(f"koşu yok: {KOSU}")
        return 1
    t, cd, _ = _oku(KOSU)
    # Baslangic gecicileri disarida: yalniz ikinci yari.
    son = cd[len(cd) // 2:]
    ort, std = float(son.mean()), float(son.std())
    salinim_pct = 100.0 * std / abs(ort)

    x = (son - son.mean()) * np.hanning(len(son))
    guc = np.abs(np.fft.rfft(x)) ** 2
    guc[0] = 0.0
    toplam = float(guc.sum())
    sirali = np.sort(guc)[::-1]
    ilk1 = 100.0 * float(sirali[0]) / toplam
    ilk5 = 100.0 * float(sirali[:5].sum()) / toplam
    yapili = ilk5 > 80.0

    rec = {
        "vaka": "küre çapası — kararlı RANS kapanır mı, URANS çare mi",
        "_tarih": "2026-08-19",
        "kosu": str(KOSU.relative_to(KOK)).replace("\\", "/"),
        "olculen": {
            "n_ornek": int(len(t)), "ikinci_yari_n": int(len(son)),
            "Cd_ort": round(ort, 4), "Cd_std": round(std, 4),
            "salinim_pct": round(salinim_pct, 1),
            "Cd_referans": CD_REF,
            "en_guclu_bilesen_pay_pct": round(ilk1, 1),
            "en_guclu_5_pay_pct": round(ilk5, 1),
            "salinim_yapili_mi": bool(yapili),
        },
        "_olcumun_siniri": (
            "Koşu KARARLI (SIMPLE) çözücüyle yapıldı; eksen fiziksel zaman "
            "DEĞİL iterasyondur. Buradan çıkan frekans bir Strouhal sayısı "
            "değildir. Ölçüm yalnız 'yapılı limit çevrimi mi, gürültü mü' "
            "sorusunu ayırt eder — spektral aralık sorusunu ÇÖZMEZ."),
        "urans_degerlendirmesi": {
            "ilkece_gecerli_mi": (
                "EVET. Referans Cd=0,47 zaten ZAMAN-ORTALAMALI deneysel bir "
                "değerdir; URANS zaman-ortalamasıyla kıyaslamak meşrudur."),
            "bu_vakada_neden_zayif": [
                "SPEKTRAL ARALIK YOK: URANS'ın anlamlı olması için çözülen "
                "tutarlı hareketle modellenen türbülans arasında frekans ayrımı "
                "gerekir. Re=1e5'te küre izi üç boyutlu ve geniş bantlıdır; 2B "
                "silindirin temiz Kármán dökülmesi gibi bir ayrım sunmaz. Tipik "
                "sonuç: ya eddy viskozitesi dalgalanmayı söndürüp aynı kararlı "
                "cevabı pahalıya verir, ya da fiziksel karşılığı olmayan yapay "
                "bir yarı-periyodik çözüm çıkar.",
                "ASIL ZORLUK ELE ALINMIYOR: subkritik kürede sınır tabaka "
                "ayrılmaya kadar LAMINERDIR, geçiş kopmuş kayma tabakasında "
                "olur. URANS bu sorunu hiç adreslemez — geçiş modeli (LM) zaten "
                "bu yüzden denenmişti.",
                "MALIYET x BELIRSIZLIK: GCI için 4 ağ seviyesi x URANS, bu "
                "makinede (13,7 GB) büyük bir iştir ve getirisi belirsizdir.",
            ],
            "fiziksel_olarak_dogru_tirmanis": (
                "DES/DDES ya da LES. Depoda kayıtlı tuzak: 10,5 saatlik silindir "
                "DES koşusu, y⁺≈1 ağında duvar fonksiyonu kullanıldığı için "
                "tümüyle geçersiz sayıldı. Yani bu yol da ucuz değil ve kendi "
                "kurulum kapısını ister."),
        },
        "verdikt": (
            "Küre KARARLI-RANS çapası olarak KAPSAM DIŞI. Gerekçe ölçülmüştür: "
            f"katman düzeltmesinden sonra bile ince seviye yakınsamıyor "
            f"(Cd salınımı %{salinim_pct:.1f}, sürüklenme %46,7). URANS'a geçmek "
            "İLKECE hatalı değildir ama bu vakada en zayıf seçenektir — "
            "spektral aralık yok, laminer-ayrılma sorunu ele alınmıyor, maliyet "
            "yüksek. Subkritik-küre çapası gerçekten isteniyorsa ayrı "
            "bütçelenmiş bir DES işi olmalıdır."),
    }
    (KOK / "kure_kararli_rans_hukmu.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"ikinci yarı: Cd = {ort:.4f} ± {std:.4f} (salınım %{salinim_pct:.1f}), "
          f"referans {CD_REF}")
    print(f"en güçlü bileşen gücün %{ilk1:.1f}'ini, ilk 5 bileşen "
          f"%{ilk5:.1f}'ini tutuyor → "
          f"{'YAPILI limit çevrimi' if yapili else 'GENİŞ BANTLI gürültü'}")
    print(f"\n{rec['verdikt']}")
    return 0


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
