"""Basınç-yalnız yük aktarımı NE ZAMAN yeter? --- deponun kendi koşularından.

NEDEN BU ÖLÇÜM. `coupling_fsi` bugüne kadar yalnız basınç taşıyordu ve
bunun bedeli Turek--Hron bayrağında ölçüldü: viskoz eksenel kuvvet basıncın
9,6 katı, uç yer değiştirmesi bir mertebe yanlış. Kanal eklendi ve sapma
kapandı. Ama oradan ``o hâlde her yerde şart'' sonucu ÇIKMAZ --- ve
``bayrak özel bir vaka, araçlarda önemsiz'' sonucu da çıkmaz. İkisi de
tahmin olurdu.

Bu betik tahmin etmez. Depoda ZATEN diskte duran OpenFOAM `forces` kayıtları
basınç ve viskoz bileşenleri AYRI yazar. Hepsi taranır ve şu soru vaka vaka
cevaplanır: taşınmayan viskoz bileşen, o vakadaki toplam yükün yüzde kaçı?

NE KAPATMAZ. Bu bir yük-BÜYÜKLÜĞÜ taramasıdır, yapısal yanıt taraması
değil. Küçük bir kuvvet bileşeni yanlış YERDEYSE büyük bir moment
üretebilir; tersi de olur. Yani buradaki yüzdeler ``şu vakada sehim şu
kadar yanlış'' demez, yalnız hangi vakalarda sorunun sorulması gerektiğini
söyler. Turek--Hron'da soru soruldu ve cevaplandı; ötekilerde sorulmadı.

AYRICA: `forces` kaydı bir yamalar kümesi üzerinden alınır ve o küme
FEA'ya aktarılan yüzeyle aynı olmak zorunda değildir. Oran bu yüzden
yönlendiricidir, bir düzeltme katsayısı değil.

    python experiments/kayma_payi.py
Çıktı: kayma_payi.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "kayma_payi.json"
# Viskoz pay bu esigin ustundeyse basinc-yalniz aktarim o vakada
# SORGULANMALIDIR. Esik keyfi degil: Turek-Hron bayraginda eksenel viskoz
# pay %90 idi ve uc yer degistirmesini bir mertebe kaydirdi; %5'lik bir pay
# ise bu deponun kendi sayisal bandlarinin (GCI %1-3) icinde kaybolmaz ama
# mertebe de degistirmez. Yani %5 "bak" esigidir, "yanlis" esigi degil.
ESIK_PCT = 5.0


def _oku(dat: Path) -> tuple[dict | None, str]:
    """forces.dat'in SON satirindan basınç ve viskoz kuvvet vektörleri.

    OKUNAMAMA SEBEBI DE DONER. Ilk surumde her basarisiz yol ciplak
    `return None` idi ve okunamayan dosya sessizce "sayilmayan" oluyordu.
    Bir KAPSAM taramasinda bu, olcumun kendisini bozar: "cevap yok" ile
    "cevap onemsiz" ayni gorunur. Sebep artik kayda cikar ve orada
    gruplanir --- forceCoeffs bir BICIM farkidir, bozuk dosya degil.
    """
    try:
        satir = [s for s in dat.read_text(encoding="utf-8",
                                          errors="replace").splitlines()
                 if s.strip() and not s.lstrip().startswith("#")]
    except OSError as e:
        return None, f"okunamadi: {type(e).__name__}"
    if not satir:
        return None, "veri satiri yok"
    # Bicim: Time ((px py pz) (vx vy vz)) ((mpx ...) (mvx ...))
    # Moment blogunu ALMA: ilk parantez grubunu ayikla.
    s = satir[-1]
    if "(" not in s:
        return None, "vektor blogu yok (forceCoeffs bicimi: yalniz Cd/Cl)"
    kuvvet_blogu = s[s.index("("):]
    gruplar = re.findall(r"\(([^()]*)\)", kuvvet_blogu)
    if len(gruplar) < 2:
        return None, "basinc/viskoz ikilisi yok"
    try:
        p = [float(x) for x in gruplar[0].split()]
        v = [float(x) for x in gruplar[1].split()]
    except ValueError as e:
        return None, f"sayiya cevrilemedi: {e}"
    if len(p) != 3 or len(v) != 3:
        return None, f"bilesen sayisi 3 degil ({len(p)}/{len(v)})"
    return {"basinc": p, "viskoz": v}, ""


def _pay(basinc, viskoz) -> dict:
    """Atilan yuk, TASINAN yukun yuzde kaci?

    OLCUT BIR KEZ YANLIS KURULDU ve duzeltmesi kayda gecer. Ilk surum
    bileseni KENDI paydasiyla normalize ediyordu: |v_i| / (|p_i| + |v_i|).
    O ifade, basincin neredeyse sifir oldugu bir bilesende (2B vakanin z
    ekseni, ya da simetrik bir yan kuvvet) %100 verir --- fiziksel olarak
    onemsiz bir sayinin icinde. Kapi o yuzden her aileyi isaretledi ve
    hicbir sey ayirt etmedi.

    Dogru payda TASINAN TOPLAM yuktur: bir bilesen ancak GENEL yuke gore
    buyukse yapiya is yaptirir. Metrik bu yuzden |F_v| / |F_p| ve
    max_i |v_i| / |F_p| --- yani "attigim sey, tasidigimin kac kati".
    """
    p, v = basinc, viskoz

    def mag(a):
        return (a[0] ** 2 + a[1] ** 2 + a[2] ** 2) ** 0.5
    mp = mag(p)
    if mp <= 1e-30:
        return {"eksik_oran_pct": None, "eksik_bilesen_pct": None,
                "viskoz_tam_sifir": bool(mag(v) == 0.0)}
    return {
        "eksik_oran_pct": round(100 * mag(v) / mp, 2),
        "eksik_bilesen_pct": round(100 * max(abs(x) for x in v) / mp, 2),
        # VISKOZ TAM SIFIR = SUPHE. Bu tarama sirasinda OpenFOAM 11'in
        # wallShearStress fonksiyon nesnesinin laminer bir vakada her yuzde
        # tam sifir yazdigi olculdu. Ayni imza burada da cikarsa kayit
        # "viskoz onemsiz" DEMEZ, "viskoz hesaplanmamis" demis olabilir --
        # ve o iki okuma zit yonlere goturur.
        "viskoz_tam_sifir": bool(mag(v) == 0.0),
    }


def olc() -> dict:
    kayitlar = sorted(KOK.glob("**/postProcessing/**/force*.dat"))
    aile: dict[str, list] = {}
    # CEVAPSIZ AILELER AYRI SAYILIR. Ilk surumde okunamayan dosya sessizce
    # atlaniyordu ve hukum "16 ailenin 16'si esigi asiyor" diyordu ---
    # oysa 34 aile vardi ve yarisi HIC OKUNAMAMISTI. Bir kapsam taramasinda
    # cevaplanamayanin sayilmamasi, cevabin kendisini bozar.
    cevapsiz: dict[str, int] = {}
    sebepler: dict[str, int] = {}
    for dat in kayitlar:
        # glob KOK altindan geldigi icin relative_to duşmez; yine de
        # duserse dosya taranamamis sayilir ve sebebi kayda girer.
        try:
            rel = dat.relative_to(KOK)
        except ValueError:
            sebepler["kok disinda"] = sebepler.get("kok disinda", 0) + 1
            continue
        ad = rel.parts[0]
        d, neden = _oku(dat)
        if d is None:
            cevapsiz[ad] = cevapsiz.get(ad, 0) + 1
            sebepler[neden] = sebepler.get(neden, 0) + 1
            continue
        aile.setdefault(ad, []).append({"yol": str(rel), **_pay(**d)})

    ozet = []
    for ad, kayit in sorted(aile.items()):
        oran = [k["eksik_oran_pct"] for k in kayit
                if k["eksik_oran_pct"] is not None]
        bil = [k["eksik_bilesen_pct"] for k in kayit
               if k["eksik_bilesen_pct"] is not None]
        if not oran:
            continue
        ozet.append({
            "aile": ad, "n": len(kayit),
            "viskoz_tam_sifir_kayit": sum(1 for k in kayit
                                          if k.get("viskoz_tam_sifir")),
            "eksik_oran_min_pct": round(min(oran), 2),
            "eksik_oran_max_pct": round(max(oran), 2),
            "eksik_bilesen_max_pct": round(max(bil), 2) if bil else None,
            "esigi_asiyor": bool(max(oran) > ESIK_PCT),
        })
    return _ozetle(ozet, len(kayitlar),
                   sorted((a, n) for a, n in cevapsiz.items() if a not in aile),
                   dict(sorted(sebepler.items(), key=lambda kv: -kv[1])))


def _ozetle(ozet: list, n_dosya: int, cevapsiz: list, sebepler: dict) -> dict:
    asan = [o for o in ozet if o["esigi_asiyor"]]
    return {
        "vaka": "Basınç-yalnız yük aktarımının eksik bıraktığı pay",
        "_neden": ("Turek-Hron bayraginda basinc-yalniz aktarim eksenel "
                   "yukun ~%10'unu tasiyordu. 'Her yerde sart' da 'orada "
                   "ozeldi' de TAHMIN olurdu; depo kendi kosularinda "
                   "basinc/viskoz ayrimini zaten diskte tutuyor."),
        "esik_pct": ESIK_PCT,
        "_esik_gerekcesi": (
            "%5 BAK esigidir, YANLIS esigi degil. Turek-Hron'da eksenel pay "
            "%90 idi ve sonucu bir mertebe kaydirdi; %5'lik bir pay bu "
            "deponun sayisal bandlarinin (GCI %1-3) icinde kaybolmaz ama "
            "mertebe de degistirmez."),
        "taranan_dosya": n_dosya,
        "aileler": ozet,
        "esigi_asan_aile": [o["aile"] for o in asan],
        # BU ALAN HUKMUN YARISIDIR. Cevaplanamayan aileler, cevaplananlar
        # kadar bilgi tasir: onlarda soru SORULAMIYOR.
        "cevapsiz_aile": [{"aile": a, "dosya": n} for a, n in cevapsiz],
        "cevapsizlik_sebep_dagilimi": sebepler,
        "_cevapsizlik_sebebi": (
            "Bu ailelerde diskte YALNIZ forceCoeffs.dat var. O fonksiyon "
            "nesnesi Cd/Cl yazar ve basinc/viskoz AYRIMI TASIMAZ. Yani "
            "sorunun cevabi 'onemsiz' degil, 'bilinmiyor'."),
        "verdikt": _hukum(ozet, asan, cevapsiz),
        "_kisit": (
            "YUK-BUYUKLUGU taramasidir, YAPISAL YANIT taramasi DEGIL: kucuk "
            "bir bilesen yanlis yerdeyse buyuk moment uretebilir, tersi de "
            "olur. Yuzdeler 'sehim su kadar yanlis' DEMEZ, yalnizca sorunun "
            "nerede sorulmasi gerektigini soyler. Ayrica `forces` kaydinin "
            "yama kumesi FEA'ya aktarilan yuzeyle AYNI olmak zorunda degil; "
            "oran yonlendiricidir, duzeltme katsayisi degil. Son zaman "
            "adimi alinir --- salinimli kosuda o an temsili olmayabilir."),
        "_uretim": "Üretim: python experiments/kayma_payi.py",
    }


def _hukum(ozet: list, asan: list, cevapsiz: list) -> str:
    if not ozet:
        return ("KOŞULAMADI: hiçbir forces kaydı okunamadı --- "
                "postProcessing dizinleri .gitignore'da olabilir.")
    n_c = sum(n for _, n in cevapsiz)
    s = (f"{len(ozet)} vaka ailesinde basınç/viskoz ayrımı okundu; "
         f"{len(cevapsiz)} ailede ({n_c} dosya) AYRIM YOK. ")
    if asan:
        en = max(asan, key=lambda o: o["eksik_oran_max_pct"])
        s += (f"{len(asan)} ailede atılan viskoz yük, taşınanın "
              f"%{ESIK_PCT}'ini aşıyor: {', '.join(o['aile'] for o in asan)}. "
              f"En yüksek {en['aile']} ({en['n']} koşu): "
              f"%{en['eksik_oran_max_pct']}. ")
    else:
        s += (f"Okunabilen hiçbir ailede atılan yük taşınanın "
              f"%{ESIK_PCT}'ini aşmıyor. ")
    if cevapsiz:
        s += (f"CEVAPSIZ AİLELER ASIL BULGUDUR: {', '.join(a for a, _ in cevapsiz)} "
              "yalnızca forceCoeffs yazıyor, yani Cd/Cl --- basınç/viskoz "
              "ayrımı hiç kaydedilmemiş. Bunların içinde ÜRETİM araç yolu da "
              "var. Yani basınç-yalnız aktarımın orada savunulabilir olup "
              "olmadığı bilinmiyor ve bugüne kadar SORULAMAZDI; sorulabilmesi "
              "için vaka yazıcısının `forces` fonksiyonunu da eklemesi gerekir. ")
    return s + (
        "Aşan ailelerde `kayma=True` yolu vardır. Aşmayanlarda basınç-yalnız "
        "savunulabilir --- ama yalnız YÜK BÜYÜKLÜĞÜ anlamında: yapısal yanıt "
        "yalnız Turek-Hron'da ölçüldü, ötekilerde ölçülmedi.")


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
