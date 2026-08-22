"""Çapa koşularının ortam damgasına ÇÖZÜCÜ sürümünü ekle — log'dan okuyarak.

NEDEN: `vehicle_pipeline` sonucu damgalıyordu ama `parmak_izi()` varsayılanıyla,
yani python/paket/os/çekirdek ile. Çözücü sürümü YOKTU --- oysa `ortam.py`'nin
varoluş gerekçesi tam da o: aynı komut farklı bir OpenFOAM ile farklı sayı
verir. Hat düzeltildi (2026-08-22, `cozucu=True`), ama diskteki altın çapa seti
düzeltmeden ÖNCE üretilmişti.

NE YAPILMIYOR: bugünkü çözücü sürümünü eski koşulara YAZMAK. Koşuyu üreten
sürüm bugünkü olmayabilir ve kanıt tam da bu soruyu yanıtlamak için var;
bugünkünü yazmak boşluğu kapatmaz, YALAN söyler.

NE YAPILIYOR: OpenFOAM her log'un başına kendi yapı özetini basar. Sürüm
koşunun KENDİ kaydında zaten duruyor; buradan okumak bir kestirim değil
alıntıdır. Kaynağı da (`_kaynak`) damgaya yazılır ki koşu-anında damgalanmış
olanla sonradan tamamlanmış olan karışmasın.

    python experiments/capa_ortam_tamamla.py [--yaz]
Varsayılan KURU KOŞU: ne yapılacağını yazar, dosyaya dokunmaz.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

KOSU_KOKLERI = ("validation_anchors_runs", "vehicle_runs")


def _case_dizini(kosu: Path, s: dict) -> Path | None:
    cd = s.get("case_dir")
    if cd and Path(cd).exists():
        return Path(cd)
    ic = [d for d in kosu.iterdir() if d.is_dir() and (d / "system").exists()]
    return ic[0] if len(ic) == 1 else None


def tara() -> list[dict]:
    """Her koşu için: damga var mı, çözücü var mı, log'dan okunabiliyor mu."""
    import ortam

    out = []
    for kok in KOSU_KOKLERI:
        for sj in sorted((KOK / kok).glob("*/sonuc.json")):
            s = json.loads(sj.read_text(encoding="utf-8"))
            o = s.get("ortam") or {}
            kayit = {"kosu": f"{kok}/{sj.parent.name}", "yol": sj,
                     "damga_var": bool(o), "cozucu_var": bool(o.get("cozucu"))}
            if kayit["damga_var"] and not kayit["cozucu_var"]:
                case = _case_dizini(sj.parent, s)
                kayit["logdan"] = ortam.logdan_cozucu(case) if case else None
            out.append(kayit)
    return out


def uygula(kayitlar: list[dict], yaz: bool) -> dict:
    tamamlanan, okunamayan, zaten = [], [], []
    for k in kayitlar:
        if k["cozucu_var"]:
            zaten.append(k["kosu"])
            continue
        if not k["damga_var"]:
            # Damgasi HIC olmayan kosu bu betigin isi degil: eksik olan yalniz
            # cozucu degil damganin tamami ve o retroaktif kurulamaz (python
            # ve paket surumleri logda yazmaz). Adiyla listelenir.
            okunamayan.append(f"{k['kosu']} — damga YOK, tamamlanamaz")
            continue
        if not k.get("logdan"):
            okunamayan.append(f"{k['kosu']} — log'da yapı özeti bulunamadı")
            continue
        if yaz:
            s = json.loads(k["yol"].read_text(encoding="utf-8"))
            s["ortam"]["cozucu"] = k["logdan"]
            k["yol"].write_text(json.dumps(s, indent=2, ensure_ascii=False),
                                encoding="utf-8")
        tamamlanan.append(f"{k['kosu']} → {k['logdan']['openfoam']}")
    return {"tamamlanan": tamamlanan, "okunamayan": okunamayan,
            "zaten_tam": zaten, "yazildi": yaz}


CIKTI = KOK / "kosu_ortam_kapsami.json"


def kanit_yaz(kayitlar: list[dict], r: dict) -> dict:
    capa = [k for k in kayitlar if k["kosu"].startswith("validation_anchors_runs/")]
    capa_tam = [k for k in capa if k["cozucu_var"] or k.get("logdan")]
    rec = {
        "vaka": "Koşu ortam damgası kapsamı — çözücü sürümü taşıyan koşular",
        "_neden": ("vehicle_pipeline sonucu damgaliyordu ama parmak_izi() "
                   "VARSAYILANIYLA: python/paket/os/cekirdek vardi, COZUCU "
                   "SURUMU YOKTU. Oysa ortam.py'nin varolus gerekcesi tam da o."),
        "toplam_kosu": len(kayitlar),
        "capa_kosusu": len(capa),
        "capa_cozucu_tam": len(capa_tam),
        "tamamlanan": r["tamamlanan"],
        "tamamlanamayan": r["okunamayan"],
        "verdikt": (
            f"ÇAPA SETİ TAM: {len(capa_tam)}/{len(capa)} çapa koşusu çözücü "
            f"sürümünü taşıyor. Kalan {len(capa) - len(capa_tam)} çapada damga "
            f"HİÇ yok ve retroaktif KURULAMAZ."
            if len(capa_tam) >= len(capa) - 1 else
            f"EKSİK: {len(capa_tam)}/{len(capa)} çapa çözücü sürümü taşıyor"),
        "_kisit": (
            "Tamamlama BUGUNKU surumu yazmaz — kosunun KENDI log'undaki yapi "
            "ozetini alintilar ve kaynagini (`_kaynak`) damgaya yazar. Damgasi "
            "HIC olmayan kosular tamamlanmaz: eksik olan yalniz cozucu degil "
            "damganin tamami ve python/paket surumleri logda YAZMAZ. Onlar "
            "damgalama hatta baglanmadan once uretildi ve adiyla listeleniyor. "
            "Bundan sonraki her kosu (basarili VE dusen) cozucu surumuyle "
            "damgalanir."),
        "_uretim": "Üretim: python experiments/capa_ortam_tamamla.py --yaz",
    }
    # Ortam kapsamini olcen dosyanin KENDISI damgasiz kalirsa, olcer kendi
    # olcutunun disinda durur.
    import ortam
    ortam.damgala(rec)
    CIKTI.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    return rec


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    yaz = "--yaz" in sys.argv
    kayitlar = tara()
    r = uygula(kayitlar, yaz)
    print("Çapa ortam damgası — çözücü sürümü tamamlama"
          + ("" if yaz else "  [KURU KOŞU — dosyaya dokunulmadı]") + "\n")
    for x in r["tamamlanan"]:
        print(f"  ✓ {x}")
    for x in r["okunamayan"]:
        print(f"  — {x}")
    print(f"\ntamamlanan {len(r['tamamlanan'])} · zaten tam "
          f"{len(r['zaten_tam'])} · tamamlanamayan {len(r['okunamayan'])}")
    if not yaz and r["tamamlanan"]:
        print("\nYazmak için: python experiments/capa_ortam_tamamla.py --yaz")
        return 0
    # KANIT YALNIZ YAZILDIKTAN SONRA URETILIR: kuru kosuda uretilseydi dosya
    # "tamamlandi" der ama sonuc.json'lar tamamlanmamis olurdu.
    rec = kanit_yaz(tara(), r)
    print(f"\n{rec['verdikt']}\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
