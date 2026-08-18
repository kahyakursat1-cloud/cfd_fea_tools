"""BAĞIMSIZ DIŞ KORPUS — guard'ı, eşiklerinin ayarlanmadığı vakalarda ölç.

NEDEN GEREKLİ. `silent_failure_assay` guard'ı ikili bir detektör olarak ölçüyor
ve n=44'te sens=0,95 / spec=0,70 veriyor. Ama o korpus aracın KENDİ koşularından
tohumlandı ve guard'ın eşikleri (ALPHA_VALID_DEG, FEA_KABUL_SINIRI, fizik kapısı
Cd/Cl sınırları) BÜYÜK ÖLÇÜDE AYNI vakalara bakılarak konuldu. Böyle bir sayı
yeniden-yerine-koyma (resubstitution) tahminidir, genelleme tahmini değil; iyimser
olması beklenir. Bu modül farkı ÖLÇER.

İKİ TASARIM KARARI, ikisi de bu deponun tekrar tekrar öğrendiği derslerden:

1) BULAŞMA KAPI-BAZLIDIR, global değil. FEA kabul sınırını besleyen bir vaka,
   CFD taşıma kapısı için hâlâ BAĞIMSIZ kanıttır. "Bu dosya kullanıldı, tamamen
   at" demek, elde kalan az sayıda dış-referanslı vakayı da harcardı. Her hücre
   yalnız BESLEMEDİĞİ kapıya karşı puanlanır ve beslediği kapı kayda geçer.

2) HÜKÜM ELLE YAZILMAZ, SINIFLANDIRICI ÇAĞRILIR. Pilot korpus `flagged`/`gclass`
   alanlarını elle taşıyor; bu, guard'ı değil guard hakkındaki İNANCI ölçer.
   Burada `validity_envelope` gerçekten koşturulur — detektör testi ancak
   detektörü çalıştırınca detektör testidir.

Sayılar kanıt dosyalarından OKUNUR, elle kopyalanmaz: kanıt yenilenince korpus
kendiliğinden güncellenir, aksi halde sessizce eskir.

    python experiments/dis_korpus.py
Çıktı: dis_korpus.json
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for _a in (sys.stdout, sys.stderr):
    if hasattr(_a, "reconfigure"):
        _a.reconfigure(encoding="utf-8", errors="replace")

from validity_envelope import (  # noqa: E402
    VALIDATED,
    classify_cfd,
    classify_fea,
    overall_class,
)

# Sessiz-hata eşiği: `silent_failure_assay` ile AYNI olmalı, yoksa iki ölçüm
# kıyaslanamaz hale gelir.
TAU = 0.05


def _oku(ad: str) -> dict:
    p = ROOT / ad
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _silindir(dosya: str, etiket: str, kurulum_notu: str = "") -> dict | None:
    d = _oku(dosya)
    if not d:
        return None
    ref = (d.get("referans") or {}).get("Cd")
    olc = (d.get("olculen") or {}).get("Cd_ortalama")
    if ref is None or olc is None:
        return None
    return {
        "vaka": etiket,
        "nicelik": "Cd",
        "kaynak_dosya": dosya,
        "dis_referans": "Achenbach, J. Fluid Mech. 34 (1968); Norberg, "
                        "J. Fluids Struct. 17 (2003) — subkritik silindir Cd≈1,2",
        "truth": ref,
        "naive": olc,
        # Silindir küt bir cisimdir; akışa dik levha/küp ailesiyle aynı rejim.
        "arac_tipi": "kup",
        "alpha_deg": 0.0,
        "mach": 0.12,
        "gci_bandi": False,
        "ag_yeterli": None,
        "kurulum_notu": kurulum_notu,
        # Silindir vakaları `zarf.py` RAPORUNA girer; `validity_envelope`
        # eşiklerinin hiçbiri bu koşulardan türetilmedi (grep: validity_envelope
        # içinde silindir/Roshko/Norberg atfı YOK).
        "besledigi_kapilar": [],
    }


def korpus() -> list[dict]:
    h = []

    for dosya, etiket, not_ in (
            ("silindir_urans.json", "silindir 2B URANS", ""),
            ("silindir_urans_3b.json", "silindir 3B URANS", ""),
            ("silindir_des_3b.json", "silindir 3B DES", ""),
            ("silindir_des_3b_DUVARFONKSIYONU_GECERSIZ.json",
             "silindir 3B DES (duvar-fonksiyonu uyumsuz)",
             "BİLİNEN KURULUM KUSURU: nutkWallFunction y⁺≳30 ister, ölçülen y⁺≈0,009"),
    ):
        c = _silindir(dosya, etiket, not_)
        if c:
            h.append(c)

    # NACA2412 — profil NACA0012'DEN FARKLI. ALPHA_VALID_DEG=8 sınırı NACA0012
    # ölçümlerinden konuldu, dolayısıyla bu kesit taşıma kapısı için bağımsızdır.
    d = _oku("naca2412_kesit.json")
    if d and (d.get("referans") or {}).get("Cl_ince_kanat") is not None:
        olc = ((d.get("cfd") or {}).get("Cl") if isinstance(d.get("cfd"), dict)
               else None) or (d.get("olculen") or {}).get("Cl")
        if olc is not None:
            h.append({
                "vaka": "NACA2412 α=0 (Re=2,5e5)",
                "nicelik": "Cl",
                "kaynak_dosya": "naca2412_kesit.json",
                "dis_referans": "Abbott & von Doenhoff, Theory of Wing Sections "
                                "(ince-kanat Cl=0,227)",
                "truth": d["referans"]["Cl_ince_kanat"],
                "naive": olc,
                "arac_tipi": "ucak",
                "alpha_deg": 0.0,
                "mach": 0.044,
                "gci_bandi": False,
                "ag_yeterli": None,
                "kurulum_notu": "",
                "besledigi_kapilar": [],
            })

    # FEA kapalı-form — BULAŞIK: FEA_KABUL_SINIRI "mevcut altı benchmark
    # %0,0-4,8" bilgisiyle konuldu (validity_envelope, satır ~691) ve
    # fea_validation_grav tam %4,8 taşıyor. Korpusa GİRER ama FEA kapısına
    # karşı PUANLANMAZ; burada durması, dışlamanın gerekçesiyle birlikte
    # kayda geçmesi içindir.
    for dosya, etiket, alan in (
            ("fea_validation_grav.json", "öz-ağırlık çubuk (ρgL)", "sigma_hata_pct"),
            ("fea_validation_thermal.json", "termal gerilme (EαΔT)", "hata_pct"),
    ):
        d = _oku(dosya)
        if not d:
            continue
        hata = (d.get("fem") or {}).get(alan)
        if hata is None:
            continue
        h.append({
            "vaka": etiket,
            "nicelik": "gerilme",
            "kaynak_dosya": dosya,
            "dis_referans": (d.get("analitik") or {}).get("formul", "kapalı-form"),
            "referans_hata_pct": abs(float(hata)),
            "truth": None, "naive": None,
            "besledigi_kapilar": ["FEA_KABUL_SINIRI"],
        })

    h += _bandli_capalar()
    return h


def _bandli_capalar() -> list[dict]:
    """Dış referansı OLAN ve ağ ailesi koşulmuş vakalar --- negatif aday havuzu.

    Özgüllüğü ölçmek için "doğru çıkmış" hücre gerekir. Bu iki vaka o niyetle
    eklendi ve ikisi de ETİKETLENEMEDİ; nedeni aşağıda, `u_val_pct` alanında.
    """
    h = []
    d = _oku("duz_levha_aile.json")
    if d and d.get("seviyeler"):
        s = d["seviyeler"][-1]
        r = d["referans"]
        h.append({
            "vaka": "duzlevha Cf (Schlichting, y⁺≈50 ailesi)",
            "nicelik": "Cd", "kaynak_dosya": "duz_levha_aile.json",
            "dis_referans": "Schlichting 1/7-kuvvet + Schultz-Grunow 1941 — "
                            "İKİ korelasyonun farkı u_D=%3,36 olarak ölçüldü",
            "truth": r["Cf"], "naive": s["Cf"],
            "arac_tipi": "ucak", "alpha_deg": 0.0, "mach": 0.088,
            # Richardson YÖNLÜ ailede tanımsız → bu bir GCI bandı DEĞİL,
            # iki-seviye bağıl fark. Depo bu ayrımı zaten yapıyor.
            "gci_bandi": False, "ag_yeterli": None,
            "u_val_pct": 3.37,
            "kurulum_notu": "yönlü aile — Richardson tanımsız, band 2-seviye",
            "besledigi_kapilar": [],
        })
    d = _oku("gci_kup_arac.json")
    if d and d.get("Cd_ince") is not None:
        h.append({
            "vaka": "kup Cd (Hoerner, 4-seviye GCI)",
            "nicelik": "Cd", "kaynak_dosya": "gci_kup_arac.json",
            "dis_referans": "Hoerner 1965, Fluid-Dynamic Drag — küp Cd≈1,05",
            "truth": d["referans"]["Cd"], "naive": d["Cd_ince"],
            "arac_tipi": "kup", "alpha_deg": 0.0, "mach": 0.029,
            "gci_bandi": True, "ag_yeterli": None,
            "u_val_pct": (d.get("belirsizlik") or {}).get("u_sayisal_pct"),
            "kurulum_notu": "",
            # Küp FİZİK kapısını besledi (Cd≈1,05 referansı, satır ~26) ama
            # burada sınanan kapı BAND SERTİFİKASI; fizik kapısı Cd=1,11'de
            # zaten tetiklenmiyor. Bulaşma kapı-bazlı olduğu için puanlanır.
            "besledigi_kapilar": ["fizik_kapisi"],
        })
    return h


def _hata_pct(c) -> float | None:
    if c.get("referans_hata_pct") is not None:
        return c["referans_hata_pct"]
    t, n = c.get("truth"), c.get("naive")
    if not t:
        return None
    return abs(n - t) / abs(t) * 100.0


def degerlendir(h: list[dict]) -> list[dict]:
    """Her hücrede SINIFLANDIRICIYI KOŞ; flag = design-grade VERİLMEDİ mi."""
    out = []
    for c in dict_liste(h):
        hp = _hata_pct(c)
        if hp is None:
            continue
        if c["nicelik"] == "gerilme":
            v = classify_fea(referans_hata_pct=hp, nicelik="gerilme")
            kapi = "FEA_KABUL_SINIRI"
        else:
            v = classify_cfd(c["arac_tipi"], c["alpha_deg"], c["mach"],
                             has_gci_band=c["gci_bandi"],
                             Cl=c["naive"] if c["nicelik"] == "Cl" else None,
                             Cd=c["naive"] if c["nicelik"] == "Cd" else None,
                             ag_yeterli=c["ag_yeterli"])
            # SINANAN NİCELİĞİ AYIKLA. İlk sürüm küçük harf arıyordu
            # ("C_d") ama alan "C_D (sürükleme)"; filtre hiç tutmuyor ve
            # `or v` ile TÜM hükümlere düşüyordu. L/D her koşuda TREND
            # olduğundan her hücre TREND çıkıyordu: ölçülen şey Cd kapısı
            # değil, L/D'nin sabit hükmüydü.
            ad = f"C_{c['nicelik'][1].upper()}"
            secili = [x for x in v if x.quantity.startswith(ad)]
            if not secili:
                raise AssertionError(f"{ad} hükmü üretilmedi: "
                                     f"{[x.quantity for x in v]}")
            v = secili
            kapi = "classify_cfd"
        genel = overall_class(v)
        flagged = genel != VALIDATED
        gercek = hp > TAU * 100.0            # sessiz-hata VAR mı

        # ETİKETİN KENDİSİ ÖLÇÜLEBİLİR Mİ? |E| ≤ u_val ise gözlenen sapma
        # doğrulama belirsizliğinden AYRILAMAZ; o hücreye "sessiz hata yok"
        # demek, kanıtın desteklemediği bir etiket yayınlamaktır. Bu, aracın
        # kendi V&V disiplininin (R_E = |E|/u_val) korpusa uygulanmış hâlidir
        # ve üçüncü bir kategoriyi zorunlu kılar: BELİRSİZ.
        uval = c.get("u_val_pct")
        belirsiz = uval is not None and hp <= uval
        neden = ""
        if kapi in c["besledigi_kapilar"]:
            neden = f"bu vaka {kapi} eşiğini besledi"
        elif belirsiz:
            neden = (f"|E|=%{hp:.2f} ≤ u_val=%{uval:.2f} — sapma doğrulama "
                     "belirsizliğinden ayrılamıyor, ETİKET KURULAMAZ")

        out.append({**c, "hata_pct": round(hp, 2), "guard_sinif": genel,
                    "flagged": flagged, "sessiz_hata": None if belirsiz else gercek,
                    "hucre": ("BELİRSİZ" if belirsiz else
                              "TP" if (gercek and flagged) else
                              "FN" if gercek else
                              "FP" if flagged else "TN"),
                    "puanlanir": not neden,
                    "puanlanmama_nedeni": neden,
                    "sinanan_kapi": kapi})
    return out


def dict_liste(h):
    return h


# Bir oranı anlamlı biçimde kestirmek için gereken en az hücre. Tek bir negatif
# hücreden "spec=0,00" yayınlamak bir ÖLÇÜM DEĞİL, bir izlenimdir.
EN_AZ_HUCRE = 3


def _kume(v: str) -> str:
    """Hücreler BAĞIMSIZ DEĞİL: aynı geometrinin farklı kurulumları bir kümedir.

    Dört silindir koşusu dört bağımsız örnek gibi sayılırsa güven fazla dar
    çıkar --- tezin küme-önyüklemesi tarafında öğrenilen dersin aynısı.
    """
    return v.split(" ")[0].lower()


def ozet(sonuc: list[dict]) -> dict:
    p = [x for x in sonuc if x["puanlanir"]]
    say = {k: sum(1 for x in p if x["hucre"] == k) for k in ("TP", "FP", "TN", "FN")}
    tp, fn, tn, fp = say["TP"], say["FN"], say["TN"], say["FP"]
    poz, neg = tp + fn, tn + fp
    kumeler = sorted({_kume(x["vaka"]) for x in p})
    return {
        "n_toplam": len(sonuc), "n_puanlanan": len(p),
        "n_dislanan": len(sonuc) - len(p), **say,
        "n_kume": len(kumeler), "kumeler": kumeler,
        "sens": round(tp / poz, 3) if poz >= EN_AZ_HUCRE else None,
        "sens_notu": (
            f"pozitif hücre {poz} < {EN_AZ_HUCRE} — kestirilemez"
            if poz < EN_AZ_HUCRE else
            f"{len({_kume(x['vaka']) for x in p if x['hucre'] in ('TP', 'FN')})} "
            "bağımsız kümeden geliyor; hücre sayısı kümeleri saymaz, "
            "aynı geometrinin kurulumları birbirinin tekrarıdır"),
        "spec": round(tn / neg, 3) if neg >= EN_AZ_HUCRE else None,
        "spec_notu": ("" if neg >= EN_AZ_HUCRE else
                      f"negatif hücre {neg} < {EN_AZ_HUCRE} — KESTİRİLEMEZ; "
                      "dış-referanslı vakaların hemen tamamı bir tutarsızlığı "
                      "SORUŞTURMAK için koşulmuş, yani korpus yapısal olarak "
                      "hata-ağırlıklı"),
    }


def main() -> int:
    s = degerlendir(korpus())
    o = ozet(s)
    print("\n  BAĞIMSIZ DIŞ KORPUS — guard, eşiklerinin ayarlanmadığı vakalarda\n")
    for x in s:
        im = "  " if x["puanlanir"] else " ✗"
        print(f"  [{x['hucre']}]{im} {x['vaka']:44s} {x['nicelik']:8s} "
              f"hata={x['hata_pct']:8.2f}%  guard={x['guard_sinif']}")
        if not x["puanlanir"]:
            print(f"        DIŞLANDI — {x['puanlanmama_nedeni']}")
        if x.get("kurulum_notu"):
            print(f"        {x['kurulum_notu']}")
    print(f"\n  puanlanan={o['n_puanlanan']} (bağımsız küme={o['n_kume']}: "
          f"{', '.join(o['kumeler'])})  dışlanan={o['n_dislanan']}")
    print(f"  TP={o['TP']} FP={o['FP']} TN={o['TN']} FN={o['FN']}")
    for ad in ("sens", "spec"):
        d, n = o[ad], o[f"{ad}_notu"]
        print(f"  {ad}={d if d is not None else 'YOK'}" + (f"  — {n}" if n else ""))
    print("\n  YAPISAL UYARI: guard, GCI bandı ya da referans-ağ beyanı olmadan"
          "\n  neredeyse hiç DOĞRULANMIŞ demez. Bu kanıtı taşımayan bir korpusta"
          "\n  özgüllük yapı gereği düşük çıkar; ölçülen şey detektörün ayarı"
          "\n  değil, korpusun kanıt içeriğidir.")
    (ROOT / "dis_korpus.json").write_text(
        json.dumps({"tau": TAU, "ozet": o, "hucreler": s},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print("  YAZILDI dis_korpus.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
