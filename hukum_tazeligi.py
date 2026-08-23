"""Kayıtlı hükümler BUGÜNKÜ kodla aynı mı — bayat hüküm sessizce gevşek olur.

NEDEN: `sonuc.json` her koşunun geçerlilik hükmünü SAKLAR. Kod sıkılaştığında
eski kayıt eski hükmü taşımaya devam eder ve onu okuyan biri, bugünkü aracın
VERMEYECEĞİ bir hükümle karar verir.

ÖLÇÜLDÜ (2026-08-23): 23 kayıtlı koşunun 15'inde KALEM düzeyinde hüküm bayat
ve hepsi AYNI yönde --- kayıt `C_L: VALIDATED, tasarım-güvenli EVET` diyor,
bugünkü kod `TREND, HAYIR` diyor. Yani bayat hüküm DAHA GEVŞEK.

NEDEN MEVCUT KAPILAR GÖRMEDİ: genel sınıf (`validity.sinif`) ikisinde de aynı
kalıyor; fark yalnız `kalemler` içinde. Genel sınıfa bakan bir denetim
23/23 "aynı" der ve bayatlığı hiç göremez.

NE YAPILMIYOR: eski kayıtları sessizce YENİDEN YAZMAK. Hüküm, koşunun
üretildiği andaki kodun ifadesidir; üstüne bugünkü hükmü yazmak tarihi siler
ve koşunun girdileri tam olarak geri kurulamıyorsa YANLIŞ da olabilir.

NE YAPILIYOR: fark ÖLÇÜLÜR, YÖNÜYLE birlikte raporlanır. Yön kritik:
gevşeyen bir bayatlık TEHLİKELİ, sıkılaşan yalnız muhafazakârdır.

    python hukum_tazeligi.py [--json]
"""
from __future__ import annotations

import json
import sys
import tempfile
import warnings
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

# Gevseklik sirasi: kucuk = daha gevsek (daha cok sey vaat eder).
_SIRA = {"VALIDATED": 0, "TREND": 1, "OUT": 2}


def _yeniden_hukum(kayit: dict) -> dict | None:
    """Bu koşunun hükmü BUGÜNKÜ kodla ne olurdu.

    Rapor üreticisi hükmü kendi hesaplayıp sonuca geri yazıyor; aynı yol
    kullanılır ki ölçüt İKİNCİ BİR KAYNAK olmasın.
    """
    from vehicle_pipeline import VehicleAnalysisResult
    from vehicle_report import build_vehicle_report

    alanlar = set(VehicleAnalysisResult.__dataclass_fields__)
    r = VehicleAnalysisResult(**{k: v for k, v in kayit.items() if k in alanlar})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_vehicle_report(r, [], (r.convergence or {}).get("residuals") or {},
                             Path(tempfile.mkdtemp()))
    return r.validity


def _yon(eski: str, yeni: str) -> str:
    a, b = _SIRA.get(eski, 9), _SIRA.get(yeni, 9)
    return "gevşek" if a < b else ("sıkı" if a > b else "aynı")


def tara(kok: Path | None = None) -> dict:
    kok = kok or (KOK / "vehicle_runs")
    taze, bayat, olcumsuz = [], [], []
    for sj in sorted(kok.glob("*/sonuc.json")):
        try:
            d = json.loads(sj.read_text(encoding="utf-8"))
        # sessiz-yutma: kabul — bozuk kayıt ADIYLA listeleniyor, atlanmıyor
        except json.JSONDecodeError as e:
            olcumsuz.append({"kosu": sj.parent.name, "neden": f"okunamadı: {e}"})
            continue
        eski = (d.get("validity") or {}).get("kalemler")
        if d.get("status") != "ok" or not eski:
            continue
        try:
            yeni = (_yeniden_hukum(d) or {}).get("kalemler")
        except Exception as e:      # noqa: BLE001 — sebep KAYDEDILIYOR
            olcumsuz.append({"kosu": sj.parent.name,
                             "neden": f"{type(e).__name__}: {e}"[:120]})
            continue
        e_t = [tuple(x) for x in eski]
        y_t = [tuple(x) for x in (yeni or [])]
        if e_t == y_t:
            taze.append(sj.parent.name)
            continue
        farklar = [{"nicelik": a[0], "kayitli": a[1], "bugun": b[1],
                    "yon": _yon(a[1], b[1]),
                    "kayitli_tasarim_guvenli": a[2], "bugun_tasarim_guvenli": b[2]}
                   for a, b in zip(e_t, y_t) if a != b]
        bayat.append({"kosu": sj.parent.name, "farklar": farklar,
                      "gevseyen": sum(1 for f in farklar if f["yon"] == "gevşek")})
    return {"taze": taze, "bayat": bayat, "olcumsuz": olcumsuz}


def ozet(t: dict | None = None) -> dict:
    t = t or tara()
    n = len(t["taze"]) + len(t["bayat"])
    gevsek = [b for b in t["bayat"] if b["gevseyen"]]
    return {
        "vaka": "Kayıtlı hüküm tazeliği — sonuc.json bugünkü kodla aynı mı",
        "_neden": ("Kod sikistiginda eski kayit eski hukmu tasimaya devam eder "
                   "ve onu okuyan biri bugunku aracin VERMEYECEGI bir hukumle "
                   "karar verir. Genel sinif degismedigi icin mevcut denetimler "
                   "bunu goremiyordu — fark yalniz `kalemler` icinde."),
        "toplam_kosu": n, "taze": len(t["taze"]), "bayat": len(t["bayat"]),
        "gevseyen_kosu": len(gevsek),
        "olculemeyen": t["olcumsuz"],
        "bayat_kosular": t["bayat"],
        "verdikt": (
            (f"{len(t['bayat'])}/{n} koşuda kalem-düzeyi hüküm BAYAT; "
             f"{len(gevsek)}'inde bayat hüküm bugünküden DAHA GEVŞEK "
             f"(kayıt vaat ediyor, bugünkü kod vermiyor). Genel sınıf "
             f"değişmediği için hiçbir mevcut kapı bunu görmüyordu.")
            if t["bayat"] else
            f"{n}/{n} koşuda kayıtlı hüküm bugünkü kodla AYNI"),
        "_kisit": (
            "Eski kayitlar YENIDEN YAZILMIYOR: hukum, kosunun uretildigi andaki "
            "kodun ifadesidir; ustune bugunku hukmu yazmak tarihi siler ve "
            "kosunun girdileri tam geri kurulamiyorsa YANLIS da olabilir. "
            "Olculen sey farkin KENDISI ve YONUDUR. Ayrica yeniden-hukum, "
            "rapor ureticisinin KENDI yolundan gecer; ayri bir olcut kurmak "
            "ikinci kaynak yaratirdi."),
        "_uretim": "Üretim: python hukum_tazeligi.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    o = ozet()
    # KANIT DOSYASINI OLCERIN KENDISI YAZAR VE DAMGALAR. Kabuk yonlendirmesiyle
    # uretilen dosya ortam damgasi tasimaz ve `kanit` olceri onu "damgasiz"
    # sayar — olcerin kendi olcutunun disinda kalmasi olurdu.
    import ortam
    ortam.damgala(o)
    (KOK / "hukum_tazeligi.json").write_text(
        json.dumps(o, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if "--json" in sys.argv:
        print(json.dumps(o, indent=2, ensure_ascii=False))
        return 0
    print("Kayıtlı hüküm tazeliği\n")
    for b in o["bayat_kosular"]:
        print(f"→ {b['kosu']}")
        for f in b["farklar"]:
            im = "⚠️ " if f["yon"] == "gevşek" else "  "
            print(f"   {im}{f['nicelik']:<28} kayıt={f['kayitli']:<10} "
                  f"bugün={f['bugun']:<10} ({f['yon']})")
    for x in o["olculemeyen"]:
        print(f"  — {x['kosu']}: {x['neden']}")
    print(f"\ntaze {o['taze']} · bayat {o['bayat']} · "
          f"gevşeyen {o['gevseyen_kosu']} / toplam {o['toplam_kosu']}")
    print(f"\n{o['verdikt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
