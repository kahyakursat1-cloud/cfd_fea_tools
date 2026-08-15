"""Raporun KENDİ HAKKINDA yazdığı sayılar — tek kaynak.

Teknik rapor kendi kod tabanını anlatan sayılar taşır: satır, modül, test
dosyası, geçen test, kapsam. Bunlar iki ayrı yerde (kapak ve kalite tablosu)
elle yazılıydı ve kaçınılmaz olarak ayrıştı — hakem incelemesi kapakta 31.322,
tabloda 31.307 buldu. On beş satırlık fark önemli değil; ayrışmanın KENDİSİ
önemli, çünkü rapor tam da bunu avlayan bir sistemi anlatıyor.

Betik sayıları ölçer ve JSON'a yazar; `test_rapor_sayilari` hem tex'teki
tekrarların birbirini tuttuğunu hem de ölçümden makul sapmada olduğunu bağlar.
Tolerans var çünkü rapor her commit'te yeniden derlenmiyor — ama sapma
büyürse test söyler.

    python experiments/rapor_sayilari.py
Çıktı: rapor_sayilari.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent


def kod_satiri() -> int:
    """Kök + analysis/ Python satırı — raporun kapakta yazdığı sayı."""
    n = 0
    for p in list(KOK.glob("*.py")) + list((KOK / "analysis").glob("*.py")):
        n += len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
    return n


def olc(pytest_calistir: bool = False) -> dict:
    d = {
        "kod_satiri": kod_satiri(),
        "kok_modul": len(list(KOK.glob("*.py"))),
        "deney_betigi": len(list((KOK / "experiments").glob("*.py"))),
        "test_dosyasi": len(list((KOK / "tests").glob("test_*.py"))),
    }
    cov = KOK / "cov.json"
    if cov.exists():
        t = json.loads(cov.read_text(encoding="utf-8"))["totals"]
        d["ifade"] = t["num_statements"]
        d["kapsanmamis"] = t["missing_lines"]
        d["kapsam_pct"] = int(t["percent_covered"])
    if pytest_calistir:
        # IKI SAYI AYNI ANDA OLCULUR. Rapor "1465 gecen test" ile "1434 gecen
        # test (coverage acik)" yaziyordu ve hakem hakli olarak "neden 23 test
        # eksik?" diye sordu. Olculdu: FARK YOKTU — iki sayi FARKLI ZAMANLARDA
        # olculup yan yana konmustu ve aradaki bosluk gercek bir olgu gibi
        # gorunuyordu. Bu, raporun kendi avladigi kusur sinifidir: birlikte
        # okunan iki sayi birlikte olculmelidir.
        d["gecen_test"], d["dusen_test"] = _pytest_sayisi([])
        d["gecen_test_cov"], d["dusen_test_cov"] = _pytest_sayisi(
            ["--cov=.", "--cov-report=json:cov.json"])
        # Raporda yayımlanabilir mi: hükmü tüketici verir, üretici SAKLAMAZ.
        d["suit_yesil"] = d["dusen_test"] == 0 and d["dusen_test_cov"] == 0
        d["_sayimdan_haric"] = ["tests/test_rapor_sayilari.py "
                                "(raporun kendi sayısını denetler; sayıma girerse salınım üretir)"]
        if None not in (d["gecen_test"], d["gecen_test_cov"]):
            d["_test_sayisi_farki"] = d["gecen_test"] - d["gecen_test_cov"]
    return d


def _pytest_sayisi(ek: list[str]) -> tuple[int | None, int]:
    """(geçen, düşen) test sayısı.

    ÖLÇÜLDÜ (2026-08-15): bu fonksiyon yalnız "N passed" dizgisini okuyordu ve
    `pytest`in geri kalanını YOK SAYIYORDU. Süitte 5 test düşmüşken üretici
    sorunsuz koştu, "1593 geçen test" yazdı ve o sayı rapora girmeye hazır hale
    geldi. Kırmızı süitten alınan sayı yanlış bir iddiadır: "1593 test geçiyor"
    diye okunur, oysa doğrusu "1593 geçti, 5 düştü"dür.

    İlk düzeltme kırmızı süitte `None` döndürüyordu; bu, sayıyı SAKLAYARAK
    sorunu çözmeye çalışıyordu ve KİLİTLENME üretti: rapor bayatken süit kırmızı
    olur, süit kırmızıyken sayı yayımlanmaz, sayı yayımlanmayınca rapor
    güncellenemez. Üstelik tüketici `None`u biçimlendirmeye çalışıp TypeError
    veriyordu. Doğru çözüm veriyi saklamak değil, KIRMIZILIĞI GÖRÜNÜR kılmak:
    iki sayı da yazılır, hükmü tüketici verir.

    `test_rapor_sayilari.py` ÖLÇÜMÜN DIŞINDA TUTULUR. O modül raporun taşıdığı
    sayıyı bu dosyayla karşılaştırır, yani sonucu ÖLÇÜLEN NİCELİĞİN KENDİSİNE
    bağlıdır: sayı tutarsa geçer (+1 geçen test), tutmazsa düşer. Ölçüldü
    (2026-08-15): bu geri besleme 1601 ile 1602 arasında SALINIM üretiyordu ve
    rapor hiçbir değerde durulmuyordu. Durumu kendi ölçümüne bağlı bir prob ile
    ölçüm yapılamaz; modül dışarıda tutulunca sayı sabitlenir. Modülün kendisi
    süitte koşmaya devam eder --- yalnız SAYIM'a girmez.
    """
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header",
                        f"--ignore={KOK / 'tests' / 'test_rapor_sayilari.py'}", *ek],
                       cwd=KOK, capture_output=True, text=True)
    ozet = next((s for s in (r.stdout or "").splitlines()[::-1] if " passed" in s), "")
    if not ozet:
        return None, 0
    gecen = int(ozet.split(" passed")[0].split()[-1])
    dusen = 0
    for anahtar in (" failed", " error", " errors"):
        if anahtar in ozet:
            dusen += int(ozet.split(anahtar)[0].split()[-1])
    if dusen:
        print(f"  UYARI: süit KIRMIZI ({dusen} düşen) -> {ozet.strip()}", file=sys.stderr)
    return gecen, dusen


def main() -> int:
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    d = olc(pytest_calistir="--test" in sys.argv)
    d["_neden"] = ("Rapor kendi hakkinda yazdigi sayilari iki ayri yerde elle "
                   "tasiyordu ve ayrismisti (kapak 31.322, tablo 31.307). "
                   "Sayilar artik olculur ve tekrarlari testle baglanir.")
    d["_uretim"] = "Üretim: python experiments/rapor_sayilari.py [--test]"

    # KISMI KOSU DOSYAYI BUDAMAZ. Olculdu (2026-08-15): `--test` bayragi
    # olmadan kosuldugunda `gecen_test` anahtari cikti sozlugunde hic
    # olusmuyor ve dosya UZERINE yaziliyordu; tek-kaynak dosya sessizce
    # kirpiliyordu. Tuketici (tez kanit denetimi) KeyError ile durdu, yani
    # bu sefer gurultuluydu; ama ayni kirpma `kapsam_pct` icin de gecerli ve
    # orada BAYAT bir deger sessizce hayatta kalabilirdi.
    #
    # Cozum: eski dosyayla BIRLESTIR, ve bu kosunun neyi GERCEKTEN olctugunu
    # yaz. Boylece tasinan deger ile yeni olculen deger ayirt edilebilir.
    hedef = KOK / "rapor_sayilari.json"
    if hedef.exists():
        try:
            onceki = json.loads(hedef.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            onceki = {}
        tasinan = [k for k in onceki if not k.startswith("_") and k not in d]
        if tasinan:
            d["_onceki_kosudan_tasinan"] = sorted(tasinan)
            for k in tasinan:
                d[k] = onceki[k]
    d["_bu_kosuda_olculen"] = sorted(k for k in d if not k.startswith("_")
                                     and k not in d.get("_onceki_kosudan_tasinan", []))
    hedef.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    for k, v in d.items():
        if not k.startswith("_"):
            print(f"  {k:<16} {v}")
    print("-> rapor_sayilari.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
