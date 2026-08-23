"""Model-form tablosu daha çok değişkene KOŞULLANABİLİR Mİ — güç hesabı.

HAKEM İSTEDİ (#13): model-form belirsizliği bugün `rejim × duvar işlemi`
tablosundan geliyor; türbülans modeli, Reynolds sayısı, ağ kalitesi gibi
değişkenlere de koşullanmalı.

İSTEK MAKUL AMA VERİ TAŞIMIYOR --- ve bu dosya bunu SAYIYLA gösterir, "az
veri var" demekle bırakmaz.

Koşullamak, hücreleri BÖLMEK demektir. Bugün altı hücre var ve beşinde
tek çapa oturuyor; bir değişken daha eklemek hücre sayısını en az ikiye
katlar ve her yeni hücreye düşen çapa sayısı SIFIRA yaklaşır. Bir hücrede
tek örnek varken o hücrenin içindeki saçılma ÖLÇÜLEMEZ; dolayısıyla
tablonun kendisi de "koşullama işe yarıyor mu" sorusunu yanıtlayamaz.

NE ÖLÇÜLEBİLİR:
  * Tek çok-çapalı hücrede HÜCRE-İÇİ saçılma (σ_iç)
  * Hücreler ARASI saçılma (σ_dış)
  * σ_iç < σ_dış ise koşullama en azından bu veriyle ÇELİŞMİYOR demektir
  * Ve asıl soru: hücre başına KAÇ çapa gerekir ki iki hücrenin farklı
    olduğu gösterilebilsin (klasik iki-örnek güç hesabı)

NE ÖLÇÜLEMEZ: koşullamanın DOĞRU olduğu. n=3'lük tek hücreden bir tablo
yapısı doğrulanmaz; bu dosya yalnız BÜTÇEYİ verir.

    python experiments/model_form_kosullama.py
Çıktı: model_form_kosullama.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "model_form_kosullama.json"

# Iki-ornek t-sinavi icin olagan degerler (iki yanli %5, guc %80).
Z_ALFA, Z_BETA = 1.96, 0.84


def gereken_n(sigma: float, delta: float) -> int:
    """İki hücrenin farklı olduğunu gösterebilmek için HÜCRE BAŞINA çapa.

    n ≈ 2 (z_α + z_β)² σ² / Δ²  --- iki-örnek, eşit varyans, iki yanlı %5,
    güç %80. Kestirim KABA: σ tek hücreden ve n=3'ten geliyor, dolayısıyla
    kendisi de belirsizdir. Sayı bir HEDEF DEĞİL BÜYÜKLÜK MERTEBESİDİR.
    """
    # DELTA=0 "SIFIR CAPA YETER" DEGIL "HICBIR ZAMAN AYRILAMAZ" DEMEK. Ilk
    # surum 0 donuyordu ve iki hucre ayni degeri tasidiginda butce "0 capa
    # gerekir" diye okunuyordu — tam tersi. None doner ve cagiran bunu ayri
    # raporlar.
    if delta <= 0 or sigma <= 0:
        return None
    return max(2, math.ceil(2 * (Z_ALFA + Z_BETA) ** 2 * sigma ** 2 / delta ** 2))


def olc() -> dict:
    band = json.loads((KOK / "model_form_bandi.json").read_text(encoding="utf-8"))
    hucreler = band.get("olculen_hucreler") or {}

    kayit, coklu = [], None
    for rejim, ic in hucreler.items():
        for duvar, v in ic.items():
            capalar = v.get("capalar") or []
            sapmalar = [c["ham_sapma_pct"] for c in capalar
                        if c.get("ham_sapma_pct") is not None]
            # DEGERI ONCULE ESIT OLAN HUCRE VERI-GUDUMLU DEGILDIR. Capa
            # olculdu ama sapma onculden KUCUK cikti ve kod muhafazakar
            # davranip onculu korudu; hucre "olculen" listesinde duruyor ama
            # TASIDIGI SAYI literaturden geliyor. Bu ayrim yazilmazsa tablonun
            # veri-gudumlulugu OLDUGUNDAN COK gorunur.
            _onc = v.get("oncul_pct")
            _u = v.get("u_pct")
            kayit.append({"hucre": f"{rejim}.{duvar}", "n": len(capalar),
                          "u_pct": _u, "oncul_pct": _onc,
                          "deger_onculden_mi": (_onc is not None and _u is not None
                                                and abs(_u - _onc) < 1e-9),
                          "sapmalar": sapmalar})
            if len(sapmalar) >= 3:
                coklu = kayit[-1]

    n_toplam = sum(k["n"] for k in kayit)
    tekli = [k["hucre"] for k in kayit if k["n"] <= 1]

    # HUCRE-ICI sacilma: yalniz cok-capali hucrede olculebilir
    if coklu:
        s = coklu["sapmalar"]
        ort = sum(s) / len(s)
        sigma_ic = math.sqrt(sum((x - ort) ** 2 for x in s) / (len(s) - 1))
    else:
        sigma_ic = None

    # HUCRELER ARASI sacilma: hucre degerlerinin sacilmasi
    degerler = [k["u_pct"] for k in kayit if k["u_pct"] is not None]
    ort_d = sum(degerler) / len(degerler) if degerler else 0.0
    sigma_dis = (math.sqrt(sum((x - ort_d) ** 2 for x in degerler)
                           / (len(degerler) - 1)) if len(degerler) > 1 else None)

    # EN YAKIN IKI HUCRE: ayirt edilmesi en zor olan cift, butceyi O belirler
    # OZDES DEGERLI HUCRELER AYRI TUTULUR. Iki hucre ayni sayiyi tasiyorsa
    # tablo onlari AYIRIYOR ama veri AYIRMIYOR; butceyi o cift belirleyemez
    # (Delta=0 -> sonsuz capa). Bu bir bulgu olarak ayrica raporlanir.
    sirali = sorted(degerler)
    ozdes = [(a, b) for a, b in zip(sirali, sirali[1:]) if b - a < 1e-9]
    en_yakin = None
    for a, b in zip(sirali, sirali[1:]):
        if b - a < 1e-9:
            continue
        if en_yakin is None or (b - a) < en_yakin[2]:
            en_yakin = (a, b, b - a)

    # BUTCE TEK SAYI DEGIL, AYIRT EDILMEK ISTENEN FARKIN FONKSIYONU.
    #
    # Ilk surum butceyi "en yakin cift"ten hesapliyordu ve 7602 capa/hucre
    # cikti — dogru ama YANILTICI: en yakin cift 5,23 ve 5,41, yani aralarinda
    # 0,18 puan var ve o iki hucre zaten ANLAMLI bicimde farkli degil. Sonsuza
    # yakin bir butce, "kosullama imkansiz" gibi okunur; oysa soru "hangi
    # farki gormek istiyorsun" sorusudur.
    butce = {"mevcut_tablo_hucre": len(kayit),
             "ozdes_degerli_cift": [[round(a, 2), round(b, 2)] for a, b in ozdes]}
    if sigma_ic:
        tablo = []
        for delta in (1.0, 2.0, 5.0, 10.0):
            n = gereken_n(sigma_ic, delta)
            tablo.append({"ayirt_edilecek_fark_puan": delta,
                          "hucre_basina_capa": n,
                          "toplam_MEVCUT_TABLO": n * len(kayit) if n else None,
                          "toplam_BIR_DEGISKEN_DAHA": n * len(kayit) * 2 if n else None})
        butce["fark_basina"] = tablo
    if en_yakin:
        butce["en_yakin_farkli_cift_pct"] = [round(en_yakin[0], 2),
                                             round(en_yakin[1], 2)]
        butce["en_yakin_delta_puan"] = round(en_yakin[2], 2)
        butce["_en_yakin_notu"] = (
            "Bu cift ayirt edilebilir bir hedef DEGILDIR: aralarindaki fark "
            "hucre-ici sacilmanin cok altinda, yani iki hucre pratikte AYNI "
            "degeri tasiyor. Butce bu ciftten hesaplanirsa sonsuza yaklasir "
            "ve 'kosullama imkansiz' diye yanlis okunur.")

    return {
        "vaka": "Model-form tablosunun koşullanabilirliği — güç hesabı",
        "_neden": ("Hakem model-formun turbulans modeli / Re / ag kalitesi gibi "
                   "degiskenlere de kosullanmasini istedi. Kosullamak hucreleri "
                   "BOLMEK demektir ve bugun bes hucrede TEK capa var."),
        "mevcut_hucre": len(kayit),
        "mevcut_capa": n_toplam,
        "tek_capali_hucreler": tekli,
        "degeri_onculden_gelen_hucreler": [k["hucre"] for k in kayit
                                           if k["deger_onculden_mi"]],
        "veri_gudumlu_hucre": sum(1 for k in kayit if not k["deger_onculden_mi"]),
        "hucreler": kayit,
        "sigma_ic_pct": round(sigma_ic, 2) if sigma_ic else None,
        "sigma_ic_kaynak": coklu["hucre"] if coklu else None,
        "sigma_dis_pct": round(sigma_dis, 2) if sigma_dis else None,
        "kosullama_celismiyor_mu": (
            bool(sigma_ic and sigma_dis and sigma_ic < sigma_dis)
            if (sigma_ic and sigma_dis) else None),
        "butce": butce,
        "verdikt": (
            (f"BUGÜN KOŞULLANAMAZ: {len(kayit)} hücrenin {len(tekli)}'inde TEK "
             f"çapa var ({n_toplam} çapa toplam). Hücre-içi saçılma yalnız "
             f"{coklu['hucre']} hücresinde ölçülebiliyor (σ_iç=%{sigma_ic:.2f}); "
             f"hücreler arası σ_dış=%{sigma_dis:.2f}. σ_iç < σ_dış olması mevcut "
             f"koşullamayla ÇELİŞMİYOR ama onu DOĞRULAMIYOR da. "
             f"BÜTÇE: 5 puanlık bir farkı ayırt etmek için hücre başına ~"
             f"{gereken_n(sigma_ic, 5.0)} çapa (mevcut tabloda ~"
             f"{gereken_n(sigma_ic, 5.0) * len(kayit)}); 2 puan için hücre başına ~"
             f"{gereken_n(sigma_ic, 2.0)} (~"
             f"{gereken_n(sigma_ic, 2.0) * len(kayit)}). Bir değişken daha eklemek "
             f"bunları İKİYE KATLAR. Elde {n_toplam} çapa var. "
             f"AYRICA: {len(kayit)} 'ölçülen' hücrenin "
             f"{len(kayit) - sum(1 for k in kayit if not k['deger_onculden_mi'])}"
             f"'ü TAM OLARAK literatür öncülünü taşıyor — çapa ölçüldü ama sapma "
             f"öncülden küçük çıktı ve muhafazakâr davranılıp öncül korundu; "
             f"tablonun veri-güdümlü kısmı "
             f"{sum(1 for k in kayit if not k['deger_onculden_mi'])}/{len(kayit)}."
             + (f" İki hücre ÖZDEŞ değer taşıyor "
                f"({butce['ozdes_degerli_cift']}): tablo onları ayırıyor, veri "
                f"ayırmıyor." if butce.get("ozdes_degerli_cift") else ""))
            if (sigma_ic and sigma_dis) else
            "ÖLÇÜLEMEDİ — çok çapalı hücre yok, hücre-içi saçılma tanımsız"),
        "_kisit": (
            "sigma_ic TEK hucreden ve n=3'ten geliyor; kendisi belirsizdir ve "
            "guc hesabi ona dogrusal degil KARESEL baglidir, yani butce sayisi "
            "bir HEDEF DEGIL BUYUKLUK MERTEBESIDIR. Ayrica sigma_ic, capalarin "
            "KENDI sayisal bandiyla ayni mertebede (bkz. eslesik_korelasyon) — "
            "yani olculen sacilmanin ne kadari model ne kadari ag, bu veriden "
            "cikmaz ve sigma_ic bir UST SINIRDIR. Ust sinir kullanmak butceyi "
            "BUYUK tarafta tutar; muhafazakar yon."),
        "_uretim": "Üretim: python experiments/model_form_kosullama.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    print("Model-form koşullanabilirliği\n")
    print(f"{'hücre':<30}{'n':>4}{'u_pct':>8}  sapmalar")
    for h in r["hucreler"]:
        print(f"{h['hucre']:<30}{h['n']:>4}{h['u_pct'] or 0:>8.2f}  "
              f"{[round(x, 2) for x in h['sapmalar']]}")
    print(f"\nσ_iç  = %{r['sigma_ic_pct']} ({r['sigma_ic_kaynak']})")
    print(f"σ_dış = %{r['sigma_dis_pct']}")
    b = r["butce"]
    if b.get("fark_basina"):
        print(f"\n{'ayırt edilecek fark':<22}{'hücre başına':>14}"
              f"{'mevcut tablo':>14}{'+1 değişken':>14}")
        for x in b["fark_basina"]:
            print(f"{x['ayirt_edilecek_fark_puan']:>16.0f} puan "
                  f"{x['hucre_basina_capa']:>13}{x['toplam_MEVCUT_TABLO']:>14}"
                  f"{x['toplam_BIR_DEGISKEN_DAHA']:>14}")
        print(f"{'elde olan':<22}{r['mevcut_capa']:>14}")
    if b.get("ozdes_degerli_cift"):
        print(f"\nÖZDEŞ değerli hücre çifti: {b['ozdes_degerli_cift']} — "
              f"tablo ayırıyor, veri ayırmıyor")
    print(f"veri-güdümlü hücre: {r['veri_gudumlu_hucre']}/{r['mevcut_hucre']} "
          f"(öncülü koruyanlar: {', '.join(r['degeri_onculden_gelen_hucreler'])})")
    print(f"\n{r['verdikt']}")
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
