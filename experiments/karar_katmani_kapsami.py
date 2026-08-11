"""Kapsanmamış satır SINIFLANDIRILIR — daha iyi bir yüzde aranmaz.

NEDEN: yayımlanan satır kapsamı %47 ve raporun kendi ilkesi şudur: bulduran şey
kapsam YÜZDESİ değil, kapsamın NEREDE düşük olduğudur. Katman ayrımı zaten var
(`experiments/kapsam_katmanlari.py`, karar/V&V motoru %81). Bu betik onun
yerine geçmez; bir adım ötesini yapar: kapsanmamış satırları TEK TEK okuyup
metin/CLI mi, savunma (except/pass) mı, yoksa gerçek bir KARAR DALI mı diye
ayırır.

DİKKAT --- bu betiğin ürettiği "karar katmanı yüzdesi" YAYIMLANMAZ. Raporun
§Kapsam bölümü açıkça şunu söyler: yüzdeyi yükseltmek için testi kolay olanı
sayıp zoru dışarıda bırakmak, bu raporun savunduğu ilkenin tersidir. Manşet
sayı %47 olarak kalır; buradaki döküm yalnız "hangi karar yolu sınanmamış"
sorusunu cevaplamak içindir.

İLK KULLANIMDA BULDUĞU: karar üreten katmanda gerçekten sınanmamış tek kapı
`gci_advisor.py:83` idi (bandı türetilemeyen koşunun öncül havuzuna alınmaması).
`tests/test_gci_advisor_kapisi.py` ile bağlandı.

ÖNKOŞUL: cov.json güncel olmalı
    python -m pytest -q --cov=. --cov-report=json:cov.json

    python experiments/karar_katmani_kapsami.py
Çıktı: karar_katmani_kapsami.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

# HUKUM URETEN KATMAN: bir sayinin yayimlanip yayimlanmayacagina, hangi banda
# gireceginee, hangi hucreye atanacagina karar veren moduller. Liste burada
# ACIKCA tutulur --- "karar katmani" tanimi olcumun parcasidir ve gizli
# kalmamalidir.
KARAR_KATMANI = [
    "validity_envelope.py",      # geçerlilik sınıfı ve ret hükmü
    "report_generator.py",       # GCI hesabı ve verdikt
    "gci_advisor.py",            # öncül havuzu giriş kapısı
    "kosu_gecmisi.py",           # eşleşik A/B karşılaştırma hükmü
    "bellek_kapisi.py",          # bütçe kapısı
    "urans_kapisi.py",           # zaman-çözünür reçete ve salınım ölçümü
    "girdi_belirsizligi.py",     # u_input yayılımı
    "validation_anchors.py",     # çapa → rejim ataması
    "arayuz_kipleri.py",         # kip görünürlüğü (aynı yapılandırma)
    "kanal_ayrismasi.py",        # sunum-kanalı denetimi
    "arka_uc_sayaci.py",         # ortak katman denetimi
    "zarf.py",                   # çalışma zarfı hükümleri
    "ortam.py",                  # ortam damgası
    "analysis/openfoam_runner.py",   # kapılar + case yazıcı
    "experiments/model_form_bandi.py",  # rejim×duvar tablosu
]

# UC KOVA. Ilk iki kova KARAR DALI DEGILDIR --- kapsanmamis olmalari
# "sinanmamis hukum" anlamina gelmez. Ayrimi tek regex'le yapmak yetmedi:
# ilk surum 321 satiri "karar dali" saydi, ama icinde `md.append(...)`,
# `cli.add_argument(...)`, `txt += ...` gibi METIN/CLI satirlari vardi.
# Sayiyi yayimlamadan once gozle bakildi ve siniflandirma buna gore ayrildi.
IO_DESEN = re.compile(
    r"^\s*(?:print\(|sys\.exit|raise SystemExit|argparse|import |from |"
    r"if __name__|def main\(|return 0\b|_akis\.reconfigure|cli\.add_argument|"
    r"if hasattr\(sys\.|for _akis|args\s*=|subprocess\.run|linux_run\(|"
    r"\w*(?:md|lines|labels|txt|metin|rapor|satir\w*|errs?|all_stderr|"
    r"parcalar|bloklar)\s*(?:\.append\(|\.extend\(|\+=)|"
    r"\w+\.write\(|\w+\.write_text\(|plt\.|ax\d?\.|fig\.|progress_callback)")

# SAVUNMA satirlari: hata yakalama ve bos-gecis. Sinanmamis olmalari bir
# hukmun sinanmadigi anlamina gelmez; "beklenmedik durumda cokme" korumasidir.
SAVUNMA_DESEN = re.compile(
    r"^\s*(?:except\b|pass\s*$|continue\s*$|try:\s*$|finally:|"
    r"return None\s*$|raise\s*$)")


def _norm(yol: str) -> str:
    return yol.replace("\\", "/")


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    cov = KOK / "cov.json"
    if not cov.exists():
        print("cov.json yok — önce: python -m pytest -q --cov=. "
              "--cov-report=json:cov.json")
        return 1
    d = json.loads(cov.read_text(encoding="utf-8"))
    dosyalar = {_norm(k): v for k, v in d["files"].items()}

    satirlar, k_ifade, k_eksik = [], 0, 0
    karar_dali_eksik = []
    for ad in KARAR_KATMANI:
        v = dosyalar.get(_norm(ad))
        if not v:
            satirlar.append({"modul": ad, "durum": "cov.json'da YOK"})
            continue
        s = v["summary"]
        k_ifade += s["num_statements"]
        k_eksik += s["missing_lines"]
        # Kapsanmamis satirlari KARAR / IO diye ayir
        kaynak = (KOK / ad).read_text(encoding="utf-8",
                                      errors="replace").splitlines()
        karar, io, savunma = [], 0, 0
        for ln in v["missing_lines"]:
            metin = kaynak[ln - 1] if ln - 1 < len(kaynak) else ""
            if IO_DESEN.match(metin) or not metin.strip():
                io += 1
            elif SAVUNMA_DESEN.match(metin):
                savunma += 1
            else:
                karar.append({"satir": ln, "kod": metin.strip()[:90]})
        satirlar.append({
            "modul": ad, "kapsam_pct": round(s["percent_covered"], 1),
            "ifade": s["num_statements"], "eksik": s["missing_lines"],
            "eksik_io": io, "eksik_savunma": savunma,
            "eksik_karar_dali": len(karar),
        })
        for k in karar:
            karar_dali_eksik.append({"modul": ad, **k})

    genel = d["totals"]
    rec = {
        "vaka": "Kapsam — karar katmanı vs genel",
        "_neden": ("Raporun ilkesi: bulduran sey kapsam YUZDESI degil, kapsamin "
                   "NEREDE dusuk oldugudur. Bu betik kapsanmamis satirlari "
                   "metin/CLI - savunma - karar dali diye ayirir."),
        "_yayimlanmaz": ("Asagidaki 'karar_katmani.kapsam_pct' MANSET DEGILDIR "
                         "ve rapora yazilmaz. Raporun Kapsam bolumu, yuzdeyi "
                         "yukseltmek icin testi kolay olani sayip zoru disarida "
                         "birakmayi acikca reddeder; yayimlanan sayi %47'dir."),
        "genel": {"ifade": genel["num_statements"],
                  "kapsam_pct": round(genel["percent_covered"], 1)},
        "karar_katmani": {
            "modul_sayisi": len(KARAR_KATMANI),
            "ifade": k_ifade, "eksik": k_eksik,
            "kapsam_pct": round(100 * (1 - k_eksik / max(k_ifade, 1)), 1),
        },
        "moduller": satirlar,
        "sinanmamis_karar_dallari": karar_dali_eksik,
        "_sinirlar": ("Karar katmani listesi ELLE tutulur ve olcumun parcasidir; "
                      "bir modul eklendiginde buraya da eklenmeli. Uc-kova "
                      "ayrimi DESEN-TABANLIDIR (sezgisel) ve ust sinir verir: "
                      "ilk surum 321 satiri 'karar dali' saydi, gozle bakilinca "
                      "buyuk kismi metin/CLI cikti. 'karar dali' kovasindaki "
                      "satirlar tek tek okunmadan sinanmamis hukum sayilmaz."),
        "_uretim": "Üretim: python experiments/karar_katmani_kapsami.py",
    }
    rec["verdikt"] = (
        f"Yayımlanan satır kapsamı %{rec['genel']['kapsam_pct']:.1f} "
        f"({genel['num_statements']:,} ifade) ve manşet bu kalır. Hüküm üreten "
        f"{len(KARAR_KATMANI)} modülde ({k_ifade:,} ifade) kapsanmamış "
        f"{k_eksik} satırın {sum(m.get('eksik_io', 0) for m in satirlar)}'ü "
        f"metin/CLI, {sum(m.get('eksik_savunma', 0) for m in satirlar)}'ü "
        f"savunma (except/pass); karar dalı adayı {len(karar_dali_eksik)}. Bu "
        f"son sayı ÜST SINIRDIR — tek tek okunmadan 'sınanmamış hüküm' "
        f"sayılmaz. İlk okumada bulunan gerçek kapı: gci_advisor.py:83.")

    import ortam
    ortam.damgala(rec)
    (KOK / "karar_katmani_kapsami.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(rec["vaka"] + "\n" + "=" * 78)
    print(f"{'Modül':<38}{'Kapsam':>8}{'İfade':>8}{'Eksik':>7}"
          f"{'I/O':>6}{'Svn':>5}{'Karar':>7}")
    for m in satirlar:
        if "kapsam_pct" not in m:
            print(f"{m['modul']:<38}{m['durum']:>36}")
            continue
        print(f"{m['modul']:<38}{m['kapsam_pct']:>7.1f}%{m['ifade']:>8}"
              f"{m['eksik']:>7}{m['eksik_io']:>6}{m['eksik_savunma']:>5}"
              f"{m['eksik_karar_dali']:>7}")
    print("=" * 78)
    print(f"GENEL (yayımlanan manşet): %{rec['genel']['kapsam_pct']:.1f} "
          f"({genel['num_statements']:,} ifade)")
    print(f"karar katmanı [YAYIMLANMAZ]: %{rec['karar_katmani']['kapsam_pct']:.1f}"
          f" ({k_ifade:,} ifade)")
    if karar_dali_eksik:
        print(f"\nSINANMAMIŞ KARAR DALLARI ({len(karar_dali_eksik)}):")
        for k in karar_dali_eksik[:15]:
            print(f"  {k['modul']}:{k['satir']}  {k['kod'][:70]}")
    print("\n" + rec["verdikt"])
    print("-> karar_katmani_kapsami.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
