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
    h += _yeni_fea_capalari()
    h += _basamak_capalari()
    return h


def _basamak_capalari() -> list[dict]:
    """Geriye-basamaklı akış (Driver & Seegmiller 1985) — İKİNCİ pozitif küme.

    Duyarlılık tek kümeden (silindir) geliyordu ve bu, sayıyı olduğundan
    güvenli gösterir. Basamak ayrı bir geometri, ayrı bir rejim (separated)
    ve ayrı bir nicelik (yeniden-yapışma uzunluğu Xr/H).

    BANDI VAR AMA GCI DEĞİL: `basamak_yplus_ailesi` bandı salınım tabanlı
    (Eça-Hoekstra U=3·Δ, 3 seviye) ve dosyanın kendisi "Richardson asimptotik
    DEĞİL" diyor. Depo bu ayrımı zaten yapıyor, dolayısıyla `gci_bandi=False`.

    BULAŞMA: basamak `validity_envelope`'ta YAKINSAMA kapısının salınım
    gerekçesinde anılıyor (keskin kenarlı küt cisimde limit çevrimi). Sınanan
    kapı band-sertifikası olduğu için puanlanır; beslediği kapı kayda geçer.
    """
    d = _oku("model_form_bandi.json")
    if not d:
        return []
    out = []
    for c in d.get("capalar", []):
        if "basamak" not in c["capa"] or c.get("u_val_pct") is None:
            continue
        out.append({
            "vaka": "basamak " + c["capa"].split("(")[-1].rstrip(")"),
            "nicelik": "Cd",     # band-sertifikası yolu; nicelik Xr/H
            "kaynak_dosya": "model_form_bandi.json",
            "dis_referans": "Driver & Seegmiller, AIAA J. 23(2), 1985 — "
                            "deneysel yeniden-yapışma Xr/H=6,26",
            "truth": None, "naive": None,
            "referans_hata_pct": c["ham_sapma_pct"],
            "u_val_pct": c["u_val_pct"],
            "arac_tipi": "kup", "alpha_deg": 0.0, "mach": 0.13,
            "gci_bandi": False, "ag_yeterli": None,
            "kurulum_notu": "band SALINIM tabanlı (Eça-Hoekstra U=3·Δ), "
                            "Richardson asimptotik DEĞİL",
            "besledigi_kapilar": ["yakinsama_kapisi"],
        })
    return out


def _yeni_fea_capalari() -> list[dict]:
    """`fea_capa_bagimsiz` ile ÜRETİLEN çapalar — negatif etiket havuzu.

    Bunlar FEA_KABUL_SINIRI'nı belirleyen altı benchmark'ın DIŞINDA koşuldu:
    eşik sabitken yeni bir vaka geçerli bir dışarıda-bırakma testidir. Her biri
    3 ağ seviyesiyle koşuldu, yani u_num ÖLÇÜLDÜ --- tek ağla gelselerdi
    band bilinmediği için yine BELİRSİZ'e düşerlerdi.
    """
    d = _oku("fea_capa_bagimsiz.json")
    if not d:
        return []
    tanim = (("sehim", "kiris sehimi (5wL⁴/384EI)", "yer_degistirme"),
             ("frekans", "kiris 1. dogal frekansi (Euler-Bernoulli)", "ozdeger"),
             ("kure", "kalin kure ic yuzey gerilmesi (Lamé)", "gerilme"))
    out = []
    for anahtar, etiket, nicelik in tanim:
        b = d.get(anahtar) or {}
        if b.get("hata_pct") is None or b.get("u_val_pct") is None:
            continue
        out.append({
            "vaka": etiket, "nicelik": nicelik,
            "kaynak_dosya": "fea_capa_bagimsiz.json",
            "dis_referans": d.get("referans_kaynak", "kapalı-form"),
            "referans_hata_pct": b["hata_pct"],
            "u_val_pct": b["u_val_pct"],
            "truth": None, "naive": None,
            "kurulum_notu": b.get("uyari", ""),
            "besledigi_kapilar": [],
        })
    return out


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
    # KÜP: ARŞİV DEĞİL TAZE ÖLÇÜM. `gci_kup_arac.json` bir yapılandırma
    # düzeltmesinden (hücre tavanı 2,5M→4M) ÖNCEYE aitti ve çapa o düzeltmeden
    # sonra hiç koşulmamıştı: hata %6,03 / band %58,3. 2026-08-19'da yeniden
    # koşuldu → %0,38 / %2,67, asimptotik GCI. Eski dosyadan okumak, düzeltilmiş
    # bir kusuru ölçmeye devam etmek olurdu.
    d = (_oku("capa_yeniden_kosum.json").get("capalar") or {}).get("kup")
    if d:
        h.append({
            "vaka": "kup Cd (Hoerner, yeniden koşum)",
            "nicelik": "Cd", "kaynak_dosya": "capa_yeniden_kosum.json",
            "dis_referans": "Hoerner 1965, Fluid-Dynamic Drag — küp Cd≈1,05",
            "truth": d["Cd_ref"], "naive": d["Cd_yeni"],
            "arac_tipi": "kup", "alpha_deg": 0.0, "mach": 0.029,
            "gci_bandi": True, "ag_yeterli": None,
            "u_val_pct": d["u_sayisal_pct"],
            "kurulum_notu": f"y⁺ ort={d['yplus']['ort']} max={d['yplus']['max']} "
                            "— duvar-fonksiyonu bandında, üretim kapısı geçirdi",
            # Küp FİZİK kapısını besledi (Cd≈1,05 referansı, satır ~26) ama
            # burada sınanan kapı BAND SERTİFİKASI; fizik kapısı Cd=1,11'de
            # zaten tetiklenmiyor. Bulaşma kapı-bazlı olduğu için puanlanır.
            "besledigi_kapilar": ["fizik_kapisi"],
        })

    # KÜRE ve AHMED: 2026-08-19'da koşan ÇAPALAR — İKİ YENİ BAĞIMSIZ KÜME.
    #
    # NEDEN GEREKLİ: duyarlılık YALNIZ İKİ kümeden geliyordu (`sens_notu` bunu
    # açıkça yazıyordu). Küme sayısı bir oranın güven aralığını doğrudan
    # belirler; iki kümeyle "sens=1,0" demek, dar bir tabandan geniş bir iddia
    # üretmektir.
    #
    # BULAŞMA DENETİMİ (kapı-bazlı, bu modülün 1. tasarım kararı): bu iki koşu
    # `duvar_hukmu`'nun modele-duyarlı hâlini ve snappy katman kalitesi
    # ayarlarını BESLEDİ. Ama burada sınanan kapı `classify_cfd` ve o kapı
    # `duvar_hukmu`'nu ÇAĞIRMIYOR, y⁺'ı hiç GÖRMÜYOR (imzasında yok). Yani
    # besledikleri kapı ile sınandıkları kapı ayrı; hücreler puanlanabilir.
    for _ad, _dizin, _ref, _kaynak, _mach in (
        ("kure", "_anchor_sphere", 0.47,
         "White, Fluid Mechanics; Schlichting BL Theory — küre subkritik Cd≈0,47",
         30.0 / 340.0),
        ("ahmed", "_anchor_ahmed_25", 0.299,
         "Meile vd. 2011, CFD Letters 3(1) — Ahmed 25° cD=0,299 @ Re=2,784e6",
         40.0 / 340.0),
    ):
        _p = ROOT / "validation_anchors_runs" / _dizin / "sonuc.json"
        if not _p.exists():
            continue
        _d = json.loads(_p.read_text(encoding="utf-8"))
        if _d.get("cd") is None:
            continue
        _md = _d.get("mesh_duyarlilik") or {}
        _u = ((_md.get("lsr") or {}).get("u_pct")
              or (_md.get("gci") or {}).get("gci_fine_pct"))
        _yp = (_d.get("sinir_tabaka") or {}).get("yplus") or {}
        h.append({
            "vaka": f"{_ad} Cd (çapa koşusu 2026-08-19)",
            "nicelik": "Cd", "kaynak_dosya": f"validation_anchors_runs/{_dizin}/sonuc.json",
            "dis_referans": _kaynak,
            "truth": _ref, "naive": _d["cd"],
            "arac_tipi": "genel", "alpha_deg": 0.0, "mach": round(_mach, 3),
            # Ikisinde de ince seviye YAKINSAMADI, dolayisiyla mesh-bagimsizlik
            # calismasi YAPILAMADI — band YOK. Bu bir eksiklik degil OLCUM:
            # kosunun kendi kaydi nedeni yaziyor.
            "gci_bandi": _u is not None, "ag_yeterli": None,
            "u_val_pct": _u,
            "kurulum_notu": (
                f"y⁺ ort={_yp.get('ort')} max={_yp.get('max')}; "
                f"model={_d.get('turbulence_model') or 'kayıtsız'}; "
                + ((_md.get("durum") or "")[:90] if not _u else "band var")),
            "besledigi_kapilar": ["duvar_hukmu", "katman_kalitesi"],
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
        # Nicelik SINIFI yolu seçer: FEA kapısı sınıf-bazlı eşik kullanır
        # (gerilme 0,10 · yer_degistirme 0,05 · ozdeger 0,05), CFD kapısı ise
        # zarf koşullarına bakar. Yolu `nicelik` üzerinden ayırmak, hücreye
        # ayrıca bir "yol" alanı taşıtmaktan daha az ayrışır.
        if c["nicelik"] in ("gerilme", "yer_degistirme", "ozdeger"):
            v = classify_fea(referans_hata_pct=hp, nicelik=c["nicelik"])
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
            # REFERANS HATASI GUARD'A GEÇİRİLMEZ --- DAİRESELLİK.
            # `classify_cfd` artık `referans_hata_pct` kapısı taşıyor (FEA ile
            # simetrik, 2026-08-19). Ama buradaki `hp` referans hatasının TA
            # KENDİSİDİR: onu guard'a vermek, dedektöre cevabı söyleyip sonra
            # "buldun mu?" diye sormak olurdu ve duyarlılık yapay olarak 1'e
            # çıkardı. Dedektör testi, guard'ın referansı GÖRMEDEN ne dediğini
            # ölçer. Kapı üretimde referans BEYAN EDİLEN koşular için vardır.
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

        # ETİKET, EŞİĞE GÖRE ve BANDIYLA BİRLİKTE kurulur:
        #   pozitif (sessiz hata VAR) : |E| − u_val > τ
        #   negatif (sessiz hata YOK) : |E| + u_val < τ
        #   ikisi de değilse          : BELİRSİZ
        # İlk sürüm "|E| ≤ u_val → belirsiz" diyordu; bu POZİTİF için doğru
        # ama NEGATİF için yanlış testti. Frekans çapası bunu gösterdi:
        # |E|=%0,087 < u_val=%0,112 olmasına rağmen ikisinin TOPLAMI eşiğin
        # çok altında, yani "sessiz hata yok" GÜVENLE söylenebilir.
        uval = c.get("u_val_pct")
        bilinmiyor = uval is None
        u = 0.0 if bilinmiyor else float(uval)
        esik = TAU * 100.0
        poz, neg = (hp - u) > esik, (hp + u) < esik
        belirsiz = not (poz or neg)

        neden = ""
        if kapi in c["besledigi_kapilar"]:
            neden = f"bu vaka {kapi} eşiğini besledi"
        elif belirsiz:
            neden = (f"|E|=%{hp:.2f} ± u_val=%{u:.2f} eşiği (%{esik:.0f}) "
                     "iki yönden de aşmıyor — ETİKET KURULAMAZ")

        out.append({**c, "hata_pct": round(hp, 2), "guard_sinif": genel,
                    "flagged": flagged, "sessiz_hata": None if belirsiz else poz,
                    "u_val_bilinmiyor": bilinmiyor,
                    "hucre": ("BELİRSİZ" if belirsiz else
                              "TP" if (poz and flagged) else
                              "FN" if poz else
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
    return v.split(" ")[0].lower().replace("kiris","kiris")


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
        # SINIRA YAKIN ETİKET, sağlam etiket değildir: eşiğe 1 puandan az
        # kalan bir hücrenin işareti ölçüm gürültüsüyle dönebilir.
        pay = TAU * 100.0 - (x["hata_pct"] + (x.get("u_val_pct") or 0.0))
        if x["puanlanir"] and x["hucre"] == "TN" and pay < 1.0:
            print(f"        ⚠ eşiğe yalnız {pay:.2f} puan kaldı — etiket SINIRDA")
    print(f"\n  puanlanan={o['n_puanlanan']} (bağımsız küme={o['n_kume']}: "
          f"{', '.join(o['kumeler'])})  dışlanan={o['n_dislanan']}")
    print(f"  TP={o['TP']} FP={o['FP']} TN={o['TN']} FN={o['FN']}")
    for ad in ("sens", "spec"):
        d, n = o[ad], o[f"{ad}_notu"]
        print(f"  {ad}={d if d is not None else 'YOK'}" + (f"  — {n}" if n else ""))
    # Bu blok bir zamanlar AÇIK bir kusuru anlatıyordu ve kusur kapatıldıktan
    # sonra metin olduğu gibi kalırsa belge kendi kodunu YANLIŞ anlatır.
    print("\n  KAPATILDI (2026-08-19): `classify_fea` referans hatasını kapı olarak"
          "\n  kullanıyor ama `classify_cfd` C_D hükmünü YALNIZ banda bakarak"
          "\n  veriyordu — GCI bandı olan bir koşu referanstan ne kadar uzak olursa"
          "\n  olsun DOĞRULANMIŞ alıyordu. Kapı eklendi ve DÜZ YÜZDE değil BEYAN"
          "\n  EDİLEN u_val'e karşı sınıyor (ASME V&V 20, R_E).")

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
