"""Model-form belirsizliği — REJİM BAŞINA, ölçülen çapalardan.

NEDEN: model-form belirsizliği `lifting/bluff × duvar-çözünürlüğü` tablosundan
geliyordu ama değerler LİTERATÜR-ÖNCÜLÜYDÜ (5/12/10/20). Tek ölçülen hücre
`bluff.wall_resolved = 5.95` idi. Bağlı akış, ayrılmış akış ve künt cisim aynı
model-form belirsizliğini taşımaz; bunu ölçülen çapalardan doldurmak mümkün.

NE ÖLÇÜLEBİLİR: bir çapa, ÇÖZÜCÜNÜN referanstan sapmasını verir. O sapma, o
rejimdeki model-form hatasının BİR ÖRNEĞİDİR. Tek örnekten "band" çıkarmak
istatistiksel olarak zayıftır ve bu dosya N'i AÇIKÇA yazar; N=1 ise "tek
çapa" der, dağılım iddia etmez.

NE ÖLÇÜLEMEZ: çapada duvar işlemi (y⁺) KAYITLI DEĞİLSE o çapa bir hücreye
ATANAMAZ. Tahmin edilmez — atanamayan çapa listelenir ve hücre öncül kalır.

    python experiments/model_form_bandi.py
Çıktı: model_form_bandi.json  (+ validation_band.json'a ölçülen hücreler)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

BAND_DOSYASI = KOK / "validation_band.json"


def _j(ad: str) -> dict | None:
    p = KOK / ad
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


_NE_GEREKIYOR = {
    # KALAN HUCRELERIN NEDEN KAPANMADIGI YAZILI OLMALI. "Kalan hucreler" demek
    # okuyucuya isin BUYUKLUGUNU soylemez; kimi hucre bir kosu uzakta, kimi
    # referans belirsizligi yuzunden ULASILAMAZ. Ikisi ayni sey degildir.
    "bluff.wall_resolved": (
        "OLCULDU (bluff_duvar_cozunur_fizibilite.json): engel maliyet DEGIL, "
        "FIZIK. Elde olan dort kunt capanin UCU bu hucreye ilkece uygun degil — "
        "kup ve diskte ayrilma noktasi GEOMETRIKTIR (keskin kenar, capa tanimi "
        "'Re-duyarsiz' diyor), dolayisiyla duvar islemi Cd'yi belirlemez; "
        "kurede capa araligi subkritiktir (1e3-2e5) ve orada yuzey sinir "
        "tabakasi LAMINERDIR, yani y+<5 ag turbulansli degil LAMINER tabaka "
        "cozer. Hucre ancak yuksek-Re, egimli-yuzeyli govdelerde (Ahmed) "
        "tanimlidir. Ahmed duvar-cozunur butcesi olculdu: ~4,68 M hucre, "
        "4,74 GB (olculen 0,779 kB/hucre ile), ~14 saat — bu makinede bos "
        "bellegi (4,62 GB) ASIYOR. Yani hucre hem dar hem de bu donanimda "
        "ulasilmaz."),
    "lifting.wall_resolved": (
        "Deneysel referansli 3B tasima capasi. Mevcut tek capa (NACA0012 kanat "
        "AR6) YARI-ANALITIK referansa (Prandtl tasima-cizgisi) dayaniyor ve "
        "u_D=%15; ag ne kadar inceltilirse inceltilsin u_val %15'in altina "
        "INEMEZ, yani model hatasi ayrilamaz. Ag degil REFERANS degismeli."),
    "lifting.wall_function": (
        "Ayni kisit: referans belirsizligi (%15) baskin. Ek olarak bu hucrenin "
        "eski %35.43 degeri bu betigin olcutleriyle REDDEDILDI (sayisal band "
        "%17.4 > %15) ve hucre oncule dondu."),
}


def _u_ref_turet(ref: dict) -> float | None:
    """Referans bloğundan u_D [%]. Beyan varsa onu alır, yoksa TÜRETİR.

    Kanıt dosyaları deneysel değeri ve mutlak belirsizliğini (Xr/H = 6,26 ± 0,1)
    zaten taşıyordu; yüzdeye çevirmek yalnız bir bölme. Bir blokta beyan edilip
    diğerinde edilmemesi, AYNI deneyin iki hücrede farklı belirsizlikle
    girmesine yol açıyordu.
    """
    if ref.get("u_ref_pct") is not None:
        return float(ref["u_ref_pct"])
    deger, belirsizlik = ref.get("Xr_H"), ref.get("belirsizlik")
    if deger and belirsizlik:
        return round(100.0 * float(belirsizlik) / float(deger), 3)
    return None


def ayrilabilir(ham_sapma_pct: float | None, u_sayisal_pct: float | None,
                u_ref_pct: float | None) -> dict:
    """ASME V&V 20 karşılaştırma belirsizliği: model hatası GÖRÜLEBİLİR mi?

    u_val = sqrt(u_num² + u_D²) — sayısal bandı ve REFERANS belirsizliğini
    birlikte alır. Referans belirsizliği eskiden hesaba HİÇ girmiyordu ve bu,
    ölçütü sistematik olarak GEVŞEK yapıyordu: yarı-analitik kanat çapasının
    ±%15'i metinde yazılıydı ama sayı olarak taşınmadığı için görünmüyordu.

    O çapada fark ediyor: ham sapma %18,05 ve sayısal band %17,38 iken eski
    ölçüt "ayrılabilir" diyordu; u_D=%15 katılınca u_val=%22,96 ve fark
    AYIRT EDİLEMEZ. Sayısal bandı iyileştirmek de kurtarmaz — u_val hiçbir
    zaman %15'in altına inemez, çünkü referansın kendisi o kadar belirsiz.

    u_ref_pct None ise beyan edilmemiş demektir; hüküm yalnız sayısal banda
    dayanır ve bu AÇIKÇA söylenir (yokluk sıfır sayılmaz).
    """
    if ham_sapma_pct is None or u_sayisal_pct is None:
        return {"ayrilabilir_mi": None, "u_val_pct": None,
                "gerekce": "sayısal band yok — ayrılabilirlik DEĞERLENDİRİLMEDİ"}
    if u_ref_pct is None:
        u_val = float(u_sayisal_pct)
        not_ = ("referans belirsizliği BEYAN EDİLMEMİŞ — hüküm yalnız sayısal "
                "banda dayanıyor; gerçek u_val bundan BÜYÜKTÜR")
    else:
        u_val = math.hypot(float(u_sayisal_pct), float(u_ref_pct))
        not_ = (f"u_val = √({u_sayisal_pct:.2f}² + {u_ref_pct:.2f}²) = "
                f"%{u_val:.2f} (ASME V&V 20)")
    return {"ayrilabilir_mi": bool(ham_sapma_pct > u_val),
            "u_val_pct": round(u_val, 2), "u_ref_pct": u_ref_pct,
            "gerekce": not_}


def model_form_ozeti(rec: dict) -> dict:
    """Model-form tablosunun TEK KAYNAK özeti — kaç hücre, hangi kalitede.

    NEDEN GEREKLİ: bu sayı raporun dört ayrı yerinde elle yazılıydı ve
    birbirini tutmuyordu (hakem incelemesi: 2/7, 3/7, 1/4). Dahası TABAN da
    yanlıştı: `attached_2d` rejimi eklendiğinde toplam 7'den 8'e çıkmış ama
    hiçbir metin güncellenmemişti. Tam olarak bu deponun avladığı kusur —
    sabit metin, değişen veri.

    ÜÇ DURUM AYRI SAYILIR ve karıştırılmamalıdır:
      ölçüm     — çapa var VE sapma kendi u_val'inden büyük (model hatası görüldü)
      üst sınır — çapa var AMA sapma u_val'in altında (görülemedi; muhafazakâr)
      öncül     — çapa yok; literatür mertebesi
    """
    from validation_anchors import _MODEL_U_PCT
    toplam = sum(len(v) for v in _MODEL_U_PCT.values())
    olcum, ust = [], []
    for rejim, ic in (rec.get("olculen_hucreler") or {}).items():
        for duvar, d in ic.items():
            (ust if d.get("_ust_sinir_mi") else olcum).append(f"{rejim}.{duvar}")
    oncul = [f"{h['rejim']}.{h['duvar']}"
             for h in (rec.get("oncul_kalan_hucreler") or [])]
    capali = sorted(olcum + ust)
    return {
        "toplam_hucre": toplam, "capali": len(capali), "oncul": len(oncul),
        "olcum": len(olcum), "ust_sinir": len(ust),
        "capali_hucreler": capali, "olcum_hucreleri": sorted(olcum),
        "ust_sinir_hucreleri": sorted(ust), "oncul_hucreler": sorted(oncul),
        "tutarli": len(capali) + len(oncul) == toplam,
        "cumle": (f"{toplam} hücrenin {len(capali)}'i deneysel/literatür çapası "
                  f"taşıyor ({len(olcum)} ölçüm + {len(ust)} üst sınır), "
                  f"{len(oncul)}'i literatür öncülüyle çalışıyor"),
    }


# CAPANIN SAYISAL BANDI, OLCMEK ISTEDIGI MODEL HATASINDAN BUYUK OLAMAZ.
# validate_pipeline bunu zaten yaziyordu ("U<%15 — yoksa capa model hatasini
# ayirt edemez") ama model-form toplayicisi kontrol etmiyordu. Olculdu:
# Ahmed 25 capasinin LSR bandi %274.7 — o capa tek basina hucreyi ele gecirip
# bandi %290'a cikariyordu. Sayisal gurultusu bu kadar buyuk bir kosu, model
# hatasi hakkinda HICBIR SEY soylemez.
U_SAYISAL_TAVANI = 15.0


def _capa_modeli(anahtar: str) -> str:
    """Çapanın koştuğu türbülans modeli. Koşu kaydı taşıyorsa O kullanılır;
    eski koşular taşımadığı için yapılandırmaya düşülür.

    Yapılandırma İKİNCİL kaynaktır: koşudan sonra değiştirilmişse eskimiş olur.
    Bu yüzden çağıran önce `sonuc.json`'daki `turbulence_model`'e bakar —
    2026-08-19'dan sonraki koşular onu yazıyor.
    """
    try:
        from validate_pipeline import _GEOM
    # sessiz-yutma: kabul — validate_pipeline trimesh istiyor ve o yoksa
    # yapılandırma okunamaz. Sonuç varsayılan modele düşer; bu, kapıyı
    # GEVŞETMEZ çünkü varsayılan (kOmegaSST) duvar-fonksiyonunu meşru sayar
    # ve zaten eski davranıştır.
    except Exception:
        return "kOmegaSST"
    kw = (_GEOM.get(anahtar) or (None, None, {}))[2] or {}
    return kw.get("turbulence_model") or "kOmegaSST"



def _vaka_eslestir(uclar: dict | None, yama: str) -> Path | None:
    """Bir çapanın KAYITLI y⁺ ortalamasına karşılık gelen case dizini.

    NEDEN GEREKLİ: basamak/levha çapaları kanıt JSON'larından geliyor ve o
    kayıtlar case dizinini TAŞIMIYOR. Dizin adına bakıp "bu herhalde odur"
    demek bir tahmindir; y⁺ dağılımı kademeye göre değişir ve yanlış kademeyi
    çapaya iliştirmek ölçümü uydurmak olur.

    Bağ DOĞRULANARAK kurulur: adayın y⁺ UÇLARI (min ve max) kayıtlı uçlarla
    %0,1 içinde tutmalı VE tek aday kalmalı. Aynı ölçüt `_kosudan_yplus`'ta
    hücre sayısı için kullanılıyor.

    ORTALAMA İLE EŞLEŞTİRİLMEZ: kanıt kaydı foamPostProcess'in YÜZ-SAYISI
    ağırlıklı ortalamasını taşıyor, bu modül ALAN ağırlıklı hesaplıyor. İkisi
    aynı vaka için bile farklıdır (`_basamak/kOmegaSST`: kayıt 14,31 · alan
    ağırlıklı 15,38) ve ortalamaya bakan bir ölçüt doğru vakayı REDDEDERDİ.
    Uçlar ağırlıklandırmadan bağımsızdır.
    """
    if not uclar or uclar.get("max") is None:
        return None
    from yplus_dagilim import dagilim
    bulunan = []
    for aday in sorted(KOK.glob("_*/*/")):
        if not (aday / "constant" / "polyMesh").exists():
            continue
        d = dagilim(aday, yama)
        if all(d.get(k) is not None and uclar.get(k) is not None
               and abs(d[k] - uclar[k]) <= 1e-3 * max(abs(uclar[k]), 1e-12)
               for k in ("min", "max")):
            bulunan.append(aday)
    return bulunan[0] if len(bulunan) == 1 else None


def _kanit_yplus_kapsami(uclar: dict | None, yama: str) -> dict:
    """Kanıt-JSON kaynaklı çapalar için kapsam — vaka DOĞRULANARAK bağlanır."""
    uclar = uclar or {}
    duvar = _duvar_islemi(uclar.get("ort"), uclar.get("max"))
    if not duvar:
        return {}
    try:
        from yplus_dagilim import dagilim, duvar_islemi_kapsami
        case = _vaka_eslestir(uclar, yama)
        if case is None:
            return {"yplus_kapsam_notu": "case dizini tek-anlamlı eşleşmedi — "
                                         "kapsam ÖLÇÜLMEDİ (tahmin edilmedi)"}
        k = duvar_islemi_kapsami(dagilim(case, yama), duvar)
        if not k.get("kapsam_olculdu"):
            return {}
        return {"yplus_kapsam_pct": k["kapsam_pct"],
                "yplus_kapsam_yeterli": k["yeterli"],
                "yplus_kapsam_islemi": k["duvar_islemi"],
                "yplus_bandda_alan_pct": k["bandda_alan_pct"],
                "yplus_cozunur_alan_pct": k["cozunur_alan_pct"],
                "yplus_p05": k["p05"], "yplus_p50": k["p50"], "yplus_p95": k["p95"],
                "yplus_kapsam_vakasi": case.name,
                "yplus_kapsam_hukmu": k["hukum"]}
    except Exception as e:      # noqa: BLE001 — sebep KAYDEDILIYOR
        return {"yplus_kapsam_hatasi": f"{type(e).__name__}: {e}"[:120]}


def _kapsam_ozeti(capalar: list[dict]) -> dict:
    """y⁺ kapsam ölçümünün KENDİ KAPSAMI — kaç çapada ölçüldü, kaçında değil.

    Bir ölçerin kendi kapsamını beyan etmesi bu deponun kuralı: "hepsi iyi" ile
    "yalnız üçüne bakabildim" arasındaki farkı okuyucu görmezse, ölçülmemiş
    olan ölçülmüş sayılır.
    """
    olculen = [c for c in capalar if c.get("yplus_kapsam_pct") is not None]
    yetersiz = [f"{c['capa']} (%{c['yplus_kapsam_pct']:.1f})"
                for c in olculen if not c.get("yplus_kapsam_yeterli")]
    olcusuz = [f"{c['capa']}: {c.get('yplus_kapsam_notu') or c.get('yplus_kapsam_hatasi')}"
               for c in capalar
               if c.get("yplus_kapsam_pct") is None
               and (c.get("yplus_kapsam_notu") or c.get("yplus_kapsam_hatasi"))]
    islemler = sorted({c["yplus_kapsam_islemi"] for c in olculen})
    return {
        "olculen_capa": len(olculen), "toplam_capa": len(capalar),
        "esik_pct": 80.0, "esigin_altinda": yetersiz,
        "olculemeyen": olcusuz,
        "olculen_duvar_islemleri": islemler,
        "_esik_dayatilmiyor": (
            "Esik bir ONERIDIR ve bandi ETKILEMEZ. Dayatilsaydi bugun "
            "bluff.wall_function hucresinin UC capasi da duserdi ve hucre, "
            "bedeli olculmeden oncule donerdi. Sayi kanitta durur ki bandin "
            "KALITESI okunabilsin."),
        "_kapsamin_kapsami": (
            "Kapsam yalnız case dizini ELDE OLAN capada olculebilir. Kanit-JSON "
            "kaynakli capalarda vaka y+ UCLARIYLA dogrulanarak baglanir; "
            "eslesmezse kapsam OLCULMEDI yazilir, tahmin edilmez. "
            f"Bugun olculen duvar islemleri: {', '.join(islemler) or 'yok'} — "
            "wall_resolved capalarin case dizinleri diskte YOK (kanit korundu, "
            "vaka temizlendi), o yuzden o dal bugun URETIMDE calismiyor."),
    }


def _yplus_kapsami(kosu: str, sonuc: dict, duvar_islemi: str | None) -> dict:
    """Capanin y+ DAGILIMI — ortalama/tepe ikilisinin gizledigi kapsam.

    KAPSAM CAPANIN KENDI DUVAR ISLEMINE GORE OKUNUR. `duvar_islemi` yoksa
    (y+ kayitli degil) capa zaten hicbir hucreye atanamaz ve kapsam sorusu
    dogmaz --- bos donulur.

    Bos donerse alan kanitta HIC gorunmez; "olcemedim" ile "iyi" ayrimini
    korumak icin yalniz gercekten olculdugunde yazilir.
    """
    if not duvar_islemi:
        return {}
    try:
        import sys
        sys.path.insert(0, str(KOK))
        from analysis.openfoam_runner import case_bul
        from yplus_dagilim import dagilim, duvar_islemi_kapsami
        case = case_bul(KOK / "validation_anchors_runs" / kosu)
        yama = ((sonuc.get("sinir_tabaka") or {}).get("yplus") or {}).get("patch")
        if case is None or not yama:
            return {}
        k = duvar_islemi_kapsami(dagilim(case, yama), duvar_islemi)
        if not k.get("kapsam_olculdu"):
            return {}
        return {"yplus_kapsam_pct": k["kapsam_pct"],
                "yplus_kapsam_yeterli": k["yeterli"],
                "yplus_kapsam_islemi": k["duvar_islemi"],
                "yplus_bandda_alan_pct": k["bandda_alan_pct"],
                "yplus_cozunur_alan_pct": k["cozunur_alan_pct"],
                "yplus_p05": k["p05"], "yplus_p50": k["p50"], "yplus_p95": k["p95"],
                "yplus_kapsam_hukmu": k["hukum"]}
    except Exception as e:      # noqa: BLE001 — sebep KAYDEDILIYOR
        return {"yplus_kapsam_hatasi": f"{type(e).__name__}: {e}"[:120]}


def _duvar_islemi(yplus_ort: float | None,
                  yplus_max: float | None = None) -> str | None:
    """y⁺ KAYITLIYSA hücre adı; değilse None (tahmin YOK).

    ORTALAMA TEK BASINA YETMEZ: tepe y⁺ bandın dışına taşıyorsa duvarın bir
    bölümü hiçbir zaman log-bölgesinde değildir. Ölçüldü: Ahmed 25° ortalaması
    46 (bandın içinde) ama tepesi 1237 — o koşu duvar-fonksiyonunu temsil
    etmiyor. Aynı ölçüt `validity_envelope.duvar_hukmu`'nda da var.
    """
    # ÖLÇÜT TEK KAYNAKTAN. Burada bir kez daha yazılmıştı ve bu docstring
    # zaten "aynı ölçüt duvar_hukmu'nda da var" diyordu --- iki kaynak olduğu
    # biliniyordu, ayrışması an meselesiydi.
    from validity_envelope import yplus_duvar_sinifi
    return yplus_duvar_sinifi(yplus_ort, yplus_max)


def _kosudan_yplus(cells: int | None) -> dict | None:
    """Çapanın y⁺'ını KOŞU ARŞİVİNDEN al — ama TAHMİNLE değil, DOĞRULANMIŞ
    bağla: yalnız hücre sayısı BİREBİR tutan koşu kabul edilir.

    NEDEN: küp çapasının y⁺'ı ölçülmüştü (vehicle_runs/gci_kup, ort 112,83) ama
    çapa dosyasına hiç yazılmamıştı; bu yüzden çapa hiçbir hücreye atanamıyor ve
    `bluff.wall_function` öncül kalıyordu. Ölçüm vardı, tüketicisine ulaşmıyordu.

    Hücre sayısı eşleşmesi zorunlu: "aynı geometrinin bir koşusu" yetmez, çünkü
    y⁺ kademeye göre değişir ve yanlış kademenin y⁺'ını çapaya iliştirmek
    ölçümü uydurmak olurdu.
    """
    if not cells:
        return None
    for sj in sorted((KOK / "vehicle_runs").glob("*/sonuc.json")):
        d = json.loads(sj.read_text(encoding="utf-8"))
        if (d.get("mesh") or {}).get("cells") != cells:
            continue
        yp = (d.get("sinir_tabaka") or {}).get("yplus") or {}
        if yp.get("ort") is None:
            continue
        return {"ort": yp["ort"], "max": yp.get("max"), "min": yp.get("min"),
                "kosu": sj.parent.name, "cells": cells,
                "_bag": f"hücre sayısı birebir eşleşti ({cells:,})"}
    return None


def capalari_topla() -> list[dict]:
    """Her çapa: rejim, ölçülen sapma (%), duvar işlemi (varsa), referans."""
    c: list[dict] = []

    # BAYAT ARSIV, KENDI YERINE GECEN OLCUMUN YANINDA DURMAMALI.
    #
    # `gci_kup_arac.json` bir yapilandirma duzeltmesinden (hucre tavani
    # 2,5M -> 4M) ONCEYE ait. Kup capasi o duzeltmeden sonra YENIDEN KOSULDU
    # ve `capa_yeniden_kosum.json` bunu acikca yaziyor: "ARSIV BAYATMIS —
    # hata %6,03 -> %0,38, band %58,3 -> %2,67".
    #
    # Ama bu toplayici arsivi de topluyordu ve rapor iki "kup" satiri
    # gosteriyordu: biri %58,3 bandla "atanamadi", digeri taze kosudan
    # atanmis. Band KIRLENMIYORDU (sayisal tavan arsivi zaten eliyor) ama
    # OKUYUCU yaniliyordu — arac, duzelttigi bir kusuru hala rapor ediyor
    # gibi gorunuyordu.
    #
    # Taze capa kosusu varsa arsiv ATLANIR. Atlama SESSIZ DEGIL: gerekcesi
    # asagida `_atlanan_arsivler` olarak kayda gecer.
    _kup_taze = (KOK / "validation_anchors_runs" / "_anchor_cube" / "sonuc.json")
    kup = None if _kup_taze.exists() else _j("gci_kup_arac.json")
    if _kup_taze.exists():
        c.append({"_atlanan_arsiv": "gci_kup_arac.json", "capa": "küp (arşiv)",
                  "rejim": "bluff", "sapma_pct": None, "_gecersiz": True,
                  "_gecersiz_neden": (
                      "ARŞİV BAYAT — hücre tavanı 2,5M→4M düzeltmesinden ÖNCEYE "
                      "ait. Çapa yeniden koşuldu (_anchor_cube); taze ölçüm "
                      "aynı listede 'küp (çapa koşusu)' olarak zaten var. "
                      "İkisini birlikte raporlamak, düzeltilmiş bir kusuru "
                      "hâlâ varmış gibi gösterirdi."),
                  "referans": "Hoerner 1965 (arşiv kaydı)"})
    if kup and kup.get("literatur_sapma_pct") is not None:
        _yp = ((kup.get("yplus") if isinstance(kup.get("yplus"), dict) else None)
               or _kosudan_yplus((kup.get("seviyeler") or [{}])[-1].get("cells")))
        _hk = abs(float(kup["literatur_sapma_pct"]))
        _uk = ((kup.get("lsr") or {}).get("u_pct")
               or (kup.get("gci") or {}).get("gci_fine_pct"))
        c.append({"capa": "küp", "rejim": "bluff",
                  "sapma_pct": _hk + (_uk or 0.0),
                  "ham_sapma_pct": round(_hk, 2),
                  "u_sayisal_pct": round(_uk, 2) if _uk else None,
                  "ayrilabilir_mi": bool(_uk and _hk > _uk),
                  "yplus_ort": (_yp or {}).get("ort"),
                  "yplus_max": (_yp or {}).get("max"),
                  "yplus_kaynak": (_yp or {}).get("_bag"),
                  "yplus_kosu": (_yp or {}).get("kosu"),
                  "referans": (kup.get("referans") or {}).get("kaynak", "Hoerner 1965")})

    # LIFTING HUCRESI — 2B alpha=10 capasi. 3B AR6 bu makinede kapanmiyor
    # (firar kenari kirisin %0,24'u, AR=6'da aciklik 18 m -> ~97M hucre gerekir);
    # 2B'de aciklik yok ve TMR C-grid ailesi zaten kosmus.
    _a10 = _j("tmr_gci_verdict_a10.json")
    if _a10 and _a10.get("seviyeler"):
        from validation_anchors import ANCHORS as _A10
        _spec = _A10.get("naca0012_a10_2d") or {}
        _ref = float(_spec.get("Cd") or 0.0)
        _cd = [float(s["Cd"]) for s in _a10["seviyeler"] if s.get("Cd") is not None]
        if _ref and len(_cd) >= 3:
            # KAMPANYANIN KENDI VERDICT'I Cl ICIN — o dosyada p=-3,165 yaziyor
            # ama `birincil_nicelik: "Cl"`. Band Cd kullanir; Cd'nin Richardson
            # mertebesi BURADA yeniden hesaplanir (kaba->ince sirali liste).
            f3, f2, f1 = _cd[0], _cd[1], _cd[2]
            e21, e32 = f2 - f1, f3 - f2
            if e21 and e32:
                _p = math.log(abs(e32 / e21)) / math.log(2.0)
                if _p > 0:
                    _fext = f1 + e21 / (2.0 ** _p - 1.0)
                    _gci = 1.25 * abs(e21 / f1) / (2.0 ** _p - 1.0) * 100.0
                    _h = abs(_fext - _ref) / _ref * 100.0
                    _ay = ayrilabilir(_h, _gci, _spec.get("u_ref_pct"))
                    c.append({
                        "capa": "NACA0012 2B α=10 (TMR C-grid)",
                        "rejim": "lifting",
                        "sapma_pct": _h + _gci,
                        "ham_sapma_pct": round(_h, 2),
                        "u_sayisal_pct": round(_gci, 2),
                        "u_ref_pct": _spec.get("u_ref_pct"),
                        "u_val_pct": _ay["u_val_pct"],
                        "ayrilabilir_mi": _ay["ayrilabilir_mi"],
                        "ayrilabilirlik_notu": _ay["gerekce"],
                        # TMR C-grid ailesi y+<1 ile uretilir (kanitin kendi tanimi)
                        "yplus_ort": 1.0,
                        "yplus_kaynak": "TMR PLOT3D C-grid (y⁺<1, kaynağın tanımı)",
                        "richardson_p": round(_p, 3),
                        "_not": ("Kampanyanın kendi verdict'i Cl için verilmiş "
                                 "(p=-3,165); band Cd kullanır ve Cd'nin p'si "
                                 f"{_p:.3f} — makul aralıkta."),
                        "referans": _spec.get("ref", "NASA TMR")[:80]})

    tmr = _j("tmr_gci_verdict.json")
    if tmr and tmr.get("seviyeler"):
        ref = float(tmr.get("TMR_referans_SST_alpha0") or 0.0)
        ince = float(tmr["seviyeler"][-1]["Cd"])
        if ref:
            _hata = abs((ince - ref) / ref * 100)
            # SAYISAL BAND BU CAPADA DA VAR ve okunmaliydi: yoksa capa
            # "ayrilabilirlik DEGERLENDIRILMEDI" olur ve bu, "ayrilamaz" ile
            # karistirilirsa hucre haksiz yere "ust sinir" damgasi yer.
            _u = ((tmr.get("lsr") or {}).get("u_pct")
                  or (tmr.get("gci") or {}).get("gci_fine_pct"))
            # REFERANS BELIRSIZLIGI BU BLOKTA DA OKUNMUYORDU: ayrilabilirlik
            # u_val = u_num varsayilarak hesaplaniyordu. Ayni kusur geriye-
            # basamak duvar-cozunur blogunda da vardi. Capa tanimi artik u_D
            # tasiyor (TMR'nin yedi kodunun yayilimi, %0,796 — ALT SINIR).
            from validation_anchors import ANCHORS as _A
            _uref = _A.get("naca0012_a0", {}).get("u_ref_pct")
            _ayr_tmr = ayrilabilir(_hata, _u, _uref)
            c.append({"capa": "NACA0012 α=0 (2B, bağlı akış)",
                      "rejim": "attached_2d",
                      "sapma_pct": _hata + (_u or 0.0),
                      "ham_sapma_pct": round(_hata, 2),
                      "u_sayisal_pct": round(_u, 2) if _u else None,
                      "u_ref_pct": _uref,
                      "u_val_pct": _ayr_tmr["u_val_pct"],
                      "ayrilabilir_mi": _ayr_tmr["ayrilabilir_mi"],
                      "ayrilabilirlik_notu": _ayr_tmr["gerekce"],
                      # TMR C-grid ailesi y⁺<1 ile üretilir (kanıtın kendi tanımı)
                      "yplus_ort": 1.0,
                      "referans": "NASA TMR / CFL3D"})

    def _arsivden_kurtar(capa_adi: str) -> dict | None:
        """Ham koşu silinmişse, önceki çıktı dosyasındaki kaydı geri getir.

        Kurtarılan kayıt YENİDEN ÖLÇÜLMÜŞ SAYILMAZ: `_kaynak` alanı bunu
        açıkça söyler ve `_olcum_tarihi` korunur. Sessizce taze veriymiş gibi
        döndürmek, silinen bir koşuyu ölçülmüş göstermek olurdu.
        """
        eski = KOK / "model_form_bandi.json"
        if not eski.exists():
            return None
        try:
            kayit = json.loads(eski.read_text(encoding="utf-8"))
        # sessiz-yutma: kabul — arşiv dosyası okunamıyorsa (bozuk/yarım yazılmış)
        # kurtarma YAPILMAZ ve çağıran `continue` ile çapayı ATLAR. Yutulan hata
        # kaybolmuyor: çapa listede görünmez ve `bluff.wall_function` ölçülmemiş
        # kalır, ki bunu `test_model_form_tek_capa` zaten yakalar.
        except (OSError, ValueError):
            return None
        for x in kayit.get("capalar", []):
            if x.get("capa") == capa_adi and x.get("yplus_ort") is not None:
                y = dict(x)
                y["_kaynak"] = ("ARŞİVDEN KURTARILDI — ham koşu 2026-08-13 disk "
                                "temizliğinde silindi; değer önceki çıktıdan geldi, "
                                "yeniden ölçülmedi")
                return y
        return None

    # CAPA KOSU ARSIVI: validate_pipeline'in urettigi kosular. Bunlar band
    # dosyasina YAZILIYORDU ama duvar islemi OLCULMEDEN — hepsi 'wall_resolved'
    # hucresine gidiyordu. Olculdu: disk y+=31.3, kup y+=37.3 (ikisi de
    # duvar-FONKSIYONU), yani hucre etiketi YANLISTI.
    for ad, kosu in (("disk", "_anchor_disk"), ("küre", "_anchor_sphere"),
                     ("küp (çapa koşusu)", "_anchor_cube"),
                     ("Ahmed 25°", "_anchor_ahmed_25"),
                     ("NACA0012 kanat AR6", "_anchor_naca0012_wing_ar6")):
        sj = KOK / "validation_anchors_runs" / kosu / "sonuc.json"
        if not sj.exists():
            # HAM KOSU SILINMIS: 2026-08-13'te validation_anchors_runs disk
            # temizliginde silindi (3,88 GB). Silme oncesi kontrol "kanit JSON'u
            # var mi" idi; DOGRU soru "her tuketici yalniz o JSON'dan mi okuyor"
            # olmaliydi ve bu tuketici ham kosudan okuyordu. Sonuc: bluff.
            # wall_function hucresi olculemez hale geldi ve test dustu.
            #
            # Deger kaybolmadi: onceki basarili kosunun cikti dosyasinda duruyor.
            # Oradan kurtarilir ama YENIDEN OLCULMUS gibi gosterilmez —
            # `_kaynak` alani "arsivden kurtarildi" der ve tarih tasir.
            kurtarilan = _arsivden_kurtar(ad)
            if kurtarilan is None:
                continue
            c.append(kurtarilan)
            continue
        d = json.loads(sj.read_text(encoding="utf-8"))
        anahtar = kosu.replace("_anchor_", "")
        from validation_anchors import ANCHORS
        spec = ANCHORS.get(anahtar)
        if not spec:
            continue
        if d.get("cd") is None:
            # DENENDI AMA DUSTU — SESSIZCE ATILMAZ. Bu dal eskiden `continue`
            # idi: AR6 capasi kosuldu (STL hazirlandi, uc ag seviyesi kuruldu,
            # snappyHexMesh dondu) ama kanit dosyasinda HIC iz birakmiyordu;
            # kaniti okuyan biri capanin denenmedigini sanirdi. Gerekce koşu
            # duzeyinde ZATEN kayitli (sonuc.json["error"]: dusen asama, donus
            # kodu, log yolu ve log kuyrugu) — eksik olan onu TASIYAN yoldu.
            # Bu dosyadaki diger tum retler gerekce tasiyor; yalniz bu dal
            # bırakıyordu.
            _hata = (d.get("error") or "").strip()
            _ilk = next((s for s in _hata.splitlines() if s.strip()), "")
            c.append({"capa": ad, "rejim": spec["regime"], "_dustu": True,
                      "_dustu_neden": _ilk or "koşu düştü; gerekçe kayıtlı değil",
                      "kosu_dizini": str(sj.parent)})
            continue
        # DUVAR İŞLEMİ KOŞAN MODELE UYGUN MU. Ölçüldü (2026-08-19): küre çapası
        # kOmegaSSTLM ile ama y⁺ ortalaması 59 olan bir ağda koştu; LM duvar-
        # çözünür ağ ister. Sapması %69,8, sayısal bandı ise %0,02 — yani
        # "ayrılabilir" sayılıp `bluff.wall_function` bandını TEK BAŞINA
        # %8,15'ten %69,85'e çekiyordu. Bu model-form hatası değil, bozuk
        # kurulum. `duvar_hukmu` bunu zaten reddediyordu ama BU tüketici onu
        # hiç sormuyordu; kapı vardı, bandı üreten yol ondan geçmiyordu.
        from validity_envelope import duvar_hukmu
        _model = d.get("turbulence_model") or _capa_modeli(anahtar)
        _duvar_ok, _duvar_neden = duvar_hukmu(d.get("sinir_tabaka"), _model)
        # YALNIZ MODELE-OZGU RET burada elenir. `duvar_hukmu` iki ayri sey icin
        # de duser: (i) model ag ile uyumsuz, (ii) y+ zaten hicbir duvar islemine
        # ait degil. Ikincisini asagidaki `_duvar_islemi` yolu ZATEN kendi
        # gerekcesiyle listeliyor ("TEPESI disarida"); ikisini burada birlestirmek
        # Ahmed'in ayrintili gerekcesini yutardi. Modelsiz hukum GECIYOR ama
        # modelli DUSUYORSA, ret modele ozgudur.
        if not _duvar_ok and duvar_hukmu(d.get("sinir_tabaka"))[0]:
            c.append({"capa": ad, "rejim": spec["regime"],
                      "_gecersiz": True, "_gecersiz_neden": _duvar_neden,
                      "turbulence_model": _model,
                      "yplus_ort": ((d.get("sinir_tabaka") or {}).get("yplus")
                                    or {}).get("ort"),
                      "referans": spec["ref"][:80]})
            continue
        hata = abs(d["cd"] - spec["Cd"]) / spec["Cd"] * 100
        md = d.get("mesh_duyarlilik") or {}
        u_say = ((md.get("lsr") or {}).get("u_pct")
                 or (md.get("gci") or {}).get("gci_fine_pct"))
        yp = (d.get("sinir_tabaka") or {}).get("yplus") or {}
        _ayr = ayrilabilir(hata, u_say, spec.get("u_ref_pct"))
        c.append({"capa": ad, "rejim": spec["regime"],
                  # MODEL HATASI SAYISAL HATADAN AYRILAMAZ: olculen fark
                  # ayriklastirma bandiyla ayni mertebedeyse (disk %3.4 vs
                  # band %4.8) capa tek basina model-form vermez. Ust sinir
                  # olarak fark + band alinir — muhafazakar yon.
                  "sapma_pct": hata + (u_say or 0.0),
                  "ham_sapma_pct": round(hata, 2),
                  "u_sayisal_pct": round(u_say, 2) if u_say else None,
                  "ayrilabilir_mi": _ayr["ayrilabilir_mi"],
                  "u_val_pct": _ayr["u_val_pct"],
                  "u_ref_pct": _ayr.get("u_ref_pct"),
                  "ayrilabilirlik_notu": _ayr["gerekce"],
                  "yplus_ort": yp.get("ort"), "yplus_max": yp.get("max"),
                  "yplus_kaynak": f"çapa koşusu {kosu}",
                  # DUVAR ISLEMI DUVARIN NE KADARINI TEMSIL EDIYOR.
                  # Ortalama ve tepe IKISI DE bantta olabilir ve duvarin ucte
                  # biri yine bandin disinda kalabilir; olculdu 2026-08-22:
                  # Ahmed %65,8 · kup %69,4 · disk %59,8 alan bantta. Sayi
                  # BANDA GIRMEZ (esik dayatilmiyor — ucunu birden dusurup
                  # hucreyi olcmeden onucule dondururdu) ama KANITTA DURUR,
                  # cunku bandin KALITESI bununla okunur.
                  **_yplus_kapsami(kosu, d,
                                   _duvar_islemi(yp.get("ort"), yp.get("max"))),
                  "referans": spec["ref"][:80]})

    bas = _j("basamak_ayrilma.json")
    if bas:
        ok = [s for s in bas.get("seviyeler", []) if s.get("durum") == "ok"]
        if ok:
            en_iyi = min(ok, key=lambda s: abs(s["hata_pct"]))
            # HUKUM YAMASI 'alt': yeniden-yapisma uzunlugu orada olculur, yani
            # capanin sapmasini ureten duvar odur. 'ust' ve 'basamak' yamalarinin
            # y+'i baska bandda olabilir ve capayi temsil etmez.
            _yp = (en_iyi.get("yplus") or {}).get("alt") or {}
            c.append({"capa": f"geriye-basamak ({en_iyi['model']})",
                      "rejim": "separated",
                      "sapma_pct": abs(float(en_iyi["hata_pct"])),
                      "yplus_ort": _yp.get("ort", en_iyi.get("yplus_ort")),
                      "yplus_max": _yp.get("max"),
                      "yplus_kaynak": ("foamPostProcess yPlus, 'alt' yaması "
                                       "(yeniden-yapışmanın olduğu duvar)"
                                       if _yp else None),
                      **_kanit_yplus_kapsami(_yp, "alt"),
                      "referans": (bas.get("referans") or {}).get("kaynak", "")})

    # AYNI VAKA, IKI DUVAR ISLEMI. Ozgun capa alt duvarda tampon bolgedeydi
    # (y+ 14.3) ve hicbir hucreye atanamiyordu. Kusur cozunurlukte degil
    # DAGILIMDA idi; duvara sikistirilmis ag ailesi ayni deneye karsi
    # duvar-cozunur bandda kosuldu. Bu kayit ozgununun yerine GECMEZ, yanina
    # gelir: ikisi ayni model hatasinin farkli duvar islemlerindeki degeridir.
    aile = _j("basamak_yplus_ailesi.json")
    if aile:
        ok = [s for s in aile.get("seviyeler", []) if s.get("durum") == "ok"]
        if ok:
            ince = max(ok, key=lambda s: s.get("hucre", 0))
            _yp = (ince.get("yplus") or {}).get("alt") or {}
            band = aile.get("sayisal_band") or {}
            u_say = band.get("u_pct")
            hata = abs(float(ince["hata_pct"]))
            # AYNI DENEY, AYNI BELIRSIZLIK. Bu blok u_ref'i tasimiyordu ve
            # ayrilabilirligi u_val = u_num varsayarak hesapliyordu; duvar-
            # fonksiyonu blogu ise ayni deneyden u_D=%1,597 tasiyordu. Ayni
            # referansin iki hucrede farkli belirsizlikle girmesi tutarsizdi.
            # u_D artik ayni yerden TURETILIYOR: belirsizlik/Xr_H.
            u_ref = _u_ref_turet(aile.get("referans") or {})
            _ayr = ayrilabilir(hata, u_say, u_ref)
            c.append({"capa": f"geriye-basamak ({aile.get('model')}, duvar-çözünür aile)",
                      "rejim": "separated",
                      "sapma_pct": hata,
                      "ham_sapma_pct": hata,
                      "u_sayisal_pct": round(u_say, 2) if u_say else None,
                      "u_ref_pct": u_ref,
                      "u_val_pct": _ayr["u_val_pct"],
                      "ayrilabilir_mi": _ayr["ayrilabilir_mi"],
                      "ayrilabilirlik_notu": _ayr["gerekce"],
                      "yplus_ort": _yp.get("ort"), "yplus_max": _yp.get("max"),
                      "yplus_kaynak": ("foamPostProcess yPlus, 'alt' yaması — "
                                       "3-seviye ailenin en ince ağı"),
                      **_kanit_yplus_kapsami(_yp, "alt"),
                      "referans": (aile.get("referans") or {}).get("kaynak", "")})
    # AYNI DENEY, UCUNCU DUVAR ISLEMI. Ozgun kosu tampon bolgede (y+ 14.3),
    # duvar-cozunur aile y+ 0.048'de, bu aile y+ 43'te. Ucu de Driver &
    # Seegmiller'in AYNI deneysel referansina karsi olculuyor; degisen yalniz
    # ilk hucre yuksekligi, yani DUVAR ISLEMI. Bir vakanin iki model-form
    # hucresini birden doldurabilmesi, hucrelerin duvar islemine gore
    # ayrilmasinin ta kendisi.
    dfn = _j("basamak_duvar_fonksiyonu.json")
    if dfn:
        ok = [s for s in dfn.get("seviyeler", []) if s.get("durum") == "ok"]
        if ok:
            ince = max(ok, key=lambda s: s.get("hucre", 0))
            _yp = (ince.get("yplus") or {}).get("alt") or {}
            u_say = (dfn.get("sayisal_band") or {}).get("u_pct")
            u_ref = _u_ref_turet(dfn.get("referans") or {})
            hata = abs(float(ince["hata_pct"]))
            _ayr = ayrilabilir(hata, u_say, u_ref)
            c.append({"capa": f"geriye-basamak ({dfn.get('model')}, duvar-fonksiyonu aile)",
                      "rejim": "separated",
                      "sapma_pct": hata,
                      "ham_sapma_pct": hata,
                      "u_sayisal_pct": round(u_say, 2) if u_say else None,
                      "u_ref_pct": u_ref,
                      "u_val_pct": _ayr["u_val_pct"],
                      "ayrilabilir_mi": _ayr["ayrilabilir_mi"],
                      "ayrilabilirlik_notu": _ayr["gerekce"],
                      "yplus_ort": _yp.get("ort"), "yplus_max": _yp.get("max"),
                      "yplus_kaynak": ("foamPostProcess yPlus, 'alt' yaması — "
                                       "3-seviye YÖNLÜ ailenin en ince ağı"),
                      **_kanit_yplus_kapsami(_yp, "alt"),
                      "referans": (dfn.get("referans") or {}).get("kaynak", "")})

    # DUZ LEVHA, DUVAR-FONKSIYONU AILESI -> attached_2d.wall_function.
    # Ayni YONLU aile deseni: ilk hucre SABIT, nx/ny birlikte olcekleniyor.
    # u_D uydurulmadi, IKI YERLESIK KORELASYONUN farkindan olculdu.
    dla = _j("duz_levha_aile.json")
    if dla:
        ok = [s for s in dla.get("seviyeler", []) if s.get("durum") == "ok"]
        bandda = not str(dla.get("duvar_islemi", "")).startswith("BAND")
        if len(ok) == 3 and bandda:
            ince = max(ok, key=lambda s: s.get("hucre", 0))
            u_say = (dla.get("sayisal_band") or {}).get("u_pct")
            u_ref = (dla.get("referans") or {}).get("u_D_pct")
            hata = abs(float(ince["hata_pct"]))
            _ayr = ayrilabilir(hata, u_say, u_ref)
            c.append({"capa": "düz levha Cf (duvar-fonksiyonu aile)",
                      "rejim": "attached_2d",
                      "sapma_pct": hata,
                      "ham_sapma_pct": hata,
                      "u_sayisal_pct": round(u_say, 2) if u_say else None,
                      "u_ref_pct": u_ref,
                      "u_val_pct": _ayr["u_val_pct"],
                      "ayrilabilir_mi": _ayr["ayrilabilir_mi"],
                      "ayrilabilirlik_notu": _ayr["gerekce"],
                      "yplus_ort": ince.get("yplus"),
                      "yplus_kaynak": "foamPostProcess yPlus, 'levha' yaması",
                      "referans": (dla.get("referans") or {}).get("bagintisi", "")})
    return c


def _siralama_uyarilari(birlesik: dict, oncul: dict) -> list[dict]:
    """Duvar-fonksiyonu bandı, duvar-çözünürden DAR çıktıysa bunu söyle.

    Fizik beklentisi: duvar fonksiyonuyla model-form hatası en az duvar-çözünür
    kadardır. Ama burada ELMA ile ARMUT karşılaştırılabiliyor: bir hücre ölçüm,
    diğeri öncül olabilir. Ölçümü öncüle uydurmak için şişirmek, ölçülmemiş bir
    sayının ölçülmüş olanı bozması demektir — YAPILMAZ. Ters sıralama
    raporlanır ve hangi hücrenin ölçüm, hangisinin öncül olduğu yazılır.
    """
    out = []
    for rejim in set(birlesik) | set(oncul):
        gecerli = {}
        for islem in ("wall_resolved", "wall_function"):
            v = birlesik.get(rejim, {}).get(islem)
            gecerli[islem] = ({"deger": v, "tur": "ölçüm"} if v is not None else
                              {"deger": oncul.get(rejim, {}).get(islem),
                               "tur": "öncül"})
        wr, wf = gecerli["wall_resolved"], gecerli["wall_function"]
        if wr["deger"] is None or wf["deger"] is None:
            continue
        if wf["deger"] < wr["deger"]:
            out.append({
                "rejim": rejim,
                "wall_function": wf, "wall_resolved": wr,
                "_not": (f"duvar-fonksiyonu bandı ({wf['deger']}, {wf['tur']}) "
                         f"duvar-çözünürden ({wr['deger']}, {wr['tur']}) DAR. "
                         "Fizik beklentisi tersidir. Ölçümü öncüle uydurmak için "
                         "ŞİŞİRİLMEDİ: ölçülmemiş bir sayı, ölçülmüş olanı "
                         "bozamaz. Muhtemel açıklama — öncül bu hat için "
                         "fazla muhafazakâr; o hücre de ölçülünce anlaşılacak.")})
    return out


def calistir() -> dict:
    from validation_anchors import _MODEL_U_PCT
    capalar = capalari_topla()

    hucreler: dict[str, dict] = {}
    atanamayan: list[dict] = []
    for x in capalar:
        if x.get("_dustu"):
            # Kosu DUSTU: sapma yok, ama denendigi ve NEDEN dustugu kanita girer.
            atanamayan.append({
                "capa": x["capa"], "rejim": x["rejim"], "sapma_pct": None,
                "neden": "KOŞU DÜŞTÜ — " + x["_dustu_neden"],
                "kosu_dizini": x.get("kosu_dizini")})
            continue
        if x.get("_gecersiz"):
            # Kurulum hükmü SAYISAL hükümden ÖNCE gelir: geçersiz bir koşunun
            # sapması ne kadar dar bandla ölçülürse ölçülsün model-form değildir.
            atanamayan.append({
                "capa": x["capa"], "rejim": x["rejim"],
                "sapma_pct": None, "yplus_ort": x.get("yplus_ort"),
                "turbulence_model": x.get("turbulence_model"),
                "neden": "KURULUM GEÇERSİZ — " + x["_gecersiz_neden"]})
            continue
        _u = x.get("u_sayisal_pct")
        if _u is not None and _u > U_SAYISAL_TAVANI:
            atanamayan.append({
                "capa": x["capa"], "rejim": x["rejim"],
                "sapma_pct": round(x["sapma_pct"], 2),
                "u_sayisal_pct": _u, "yplus_ort": x.get("yplus_ort"),
                "neden": (f"SAYISAL BAND ÇOK BÜYÜK (%{_u:.1f} > "
                          f"%{U_SAYISAL_TAVANI}): bu koşunun ayrıklaştırma "
                          "gürültüsü ölçmek istediği model hatasından büyük, "
                          "model-form hakkında hiçbir şey söyleyemez")})
            continue
        hucre = _duvar_islemi(x.get("yplus_ort"), x.get("yplus_max"))
        if hucre is None:
            # OLCULDU AMA ATANAMADI ile HIC OLCULMEDI ayri seylerdir. Ikincisi
            # eksik kayittir; birincisi FIZIKSEL bir bulgudur: y+ tampon
            # bolgedeyse (5<y+<30) ne log-yasasi gecerlidir ne de viskoz
            # altkatman cozulmustur — o kosu hicbir duvar islemini temsil etmez.
            _y = x.get("yplus_ort")
            if _y is None:
                neden = ("duvar işlemi (y⁺) kanıtta KAYITLI DEĞİL — hücreye "
                         "atanmadı, TAHMİN edilmedi")
            elif (x.get("yplus_max") is not None
                  and x["yplus_max"] > __import__("validity_envelope").YPLUS_BANDI[1]):
                from validity_envelope import YPLUS_BANDI
                neden = (f"y⁺ ORTALAMASI bantta ({_y:.1f}) ama TEPESİ dışarıda "
                         f"({x['yplus_max']:.0f} > {YPLUS_BANDI[1]}): duvarın bir "
                         "bölümü hiçbir zaman log-bölgesinde değil, koşu "
                         "duvar-fonksiyonunu temsil etmiyor")
            else:
                from validity_envelope import YPLUS_BANDI, YPLUS_DUVAR_COZUNUR
                neden = (f"y⁺ ÖLÇÜLDÜ ({_y:.1f}) ama hiçbir duvar işlemine ait "
                         f"değil: duvar-çözünür ≤{YPLUS_DUVAR_COZUNUR}, "
                         f"duvar-fonksiyonu {YPLUS_BANDI[0]}–{YPLUS_BANDI[1]}. "
                         "Tampon bölgede log-yasası geçerli değildir ve viskoz "
                         "altkatman da çözülmemiştir; bu koşu iki hücreden "
                         "hiçbirini kalibre EDEMEZ. Eksik kayıt değil, FİZİKSEL "
                         "bulgu — ve çapanın sapmasının bir bölümünü açıklar")
            atanamayan.append({"capa": x["capa"], "rejim": x["rejim"],
                               "sapma_pct": round(x["sapma_pct"], 2),
                               "yplus_ort": _y, "neden": neden})
            continue
        hucreler.setdefault(x["rejim"], {}).setdefault(hucre, []).append(x)

    olculen: dict[str, dict] = {}
    ayrinti: dict[str, dict] = {}
    for rejim, h in hucreler.items():
        for islem, liste in h.items():
            en_kotu = max(x["sapma_pct"] for x in liste)
            oncul = _MODEL_U_PCT.get(rejim, {}).get(islem)
            # TEK CAPAYLA BAND DARALTILMAZ. n=1 bir dagilim degil, tek ornektir;
            # olculen deger onculden KUCUKSE bu "model daha iyi" demek degil,
            # "bu tek vakada daha iyi cikti" demektir. Model-form hatasi rejim
            # icinde geometriye gore guclu degisir. Bu yuzden n=1 iken
            # max(oncul, olculen) raporlanir ve olcum kayda gecer.
            # Olcum onculden BUYUKSE her durumda olcum kazanir: oncul o zaman
            # kanitla YANLISLANMIS demektir (asagi degil, yukari duzeltme).
            oncul_korundu = (len(liste) == 1 and oncul is not None
                             and en_kotu < oncul)
            deger = oncul if oncul_korundu else en_kotu
            olculen.setdefault(rejim, {})[islem] = round(deger, 2)
            ayrinti.setdefault(rejim, {})[islem] = {
                "u_pct": round(deger, 2), "olculen_pct": round(en_kotu, 2),
                "oncul_pct": oncul, "oncul_korundu": oncul_korundu,
                "n_capa": len(liste),
                # AYRILABILIRLIK HUCRE DUZEYINE TASINIR. Bir capa, olculen
                # farki ayriklastirma bandindan AYIRT EDEMIYORSA (fark <= band)
                # o capa model hatasini OLCMUS olmaz, yalnizca UST SINIR verir.
                # Bu bilgi capa kaydinda vardi ama hicbir yere ulasmiyordu;
                # okuyucu %8.15'i "olculen model hatasi" saniyordu.
                "ayrilabilir_capa": sum(1 for x in liste if x.get("ayrilabilir_mi")),
                "capalar": [{"ad": x["capa"], "sapma_pct": round(x["sapma_pct"], 2),
                             "ham_sapma_pct": x.get("ham_sapma_pct"),
                             "u_sayisal_pct": x.get("u_sayisal_pct"),
                             "ayrilabilir_mi": x.get("ayrilabilir_mi"),
                             "referans": x["referans"]} for x in liste],
                # UC DURUM, IKI DEGIL: ayrilabilir / ayrilamaz / DEGERLENDIRILMEDI.
                # "Degerlendirilmedi"yi "ayrilamaz" saymak, olcmedigimiz bir
                # seyi olumsuz olcum gibi gostermek olurdu.
                "ayrilabilirlik_degerlendirilmedi":
                    sum(1 for x in liste if x.get("u_sayisal_pct") is None),
                # HUCRE ANCAK EN AZ BIR CAPA AYIRT EDEBILDIYSE "OLCUM"DUR.
                #
                # Onceki kosul su idi:
                #   all(u_sayisal is not None) and all(not ayrilabilir)
                # Ilk yan-kosul, DEGERLENDIRILMEMIS bir capa eklendiginde
                # bozuluyordu ve hucre "UST SINIR" olmaktan CIKIYORDU. Yani
                # EKSIK BILGI iddiayi YUKSELTIYORDU. Olculdu (2026-08-19):
                # Ahmed capasi yeniden kosuldu, sayisal bandi uretilemedi
                # (u_sayisal=None) ve bluff.wall_function hucresi
                # "UST SINIR — hicbir capa ayiramiyor" iken "olculen" oldu —
                # oysa ayrilabilir capa sayisi hala SIFIRDI.
                #
                # Dogrusu tek yonlu: en az bir capa farki kendi u_val'inden
                # ayirt ettiyse hucre olcumdur; aksi halde UST SINIRDIR.
                # "Degerlendirilmedi" ayri bir sayac olarak zaten raporlaniyor
                # ve hicbir kosulda iddiayi guclendirmez.
                "_ust_sinir_mi": not any(x.get("ayrilabilir_mi") for x in liste),
                "_anlam": (
                    (f"TEK ÇAPA (%{en_kotu:.2f}) öncülden (%{oncul}) KÜÇÜK — "
                     "band tek ölçümle DARALTILMADI; öncül korundu, ölçüm kayıtlı"
                     if oncul_korundu else
                     "TEK ÇAPA — dağılım değil, tek ölçüm; öncülü AŞTIĞI için "
                     "ölçüm kullanıldı") if len(liste) == 1
                    else f"{len(liste)} çapanın EN KÖTÜSÜ"),
            }

    # ESKI HUCRELER ARTIK KOSULSUZ TASINMIYOR. Onceki surum "bu betigin
    # kapsamadigi hucre silinmez" diyordu; kulaga muhafazakar geliyor ama iki
    # BOZUK hucreyi hayatta tutuyordu:
    #   - bluff.wall_resolved = %5.95 -> kaynagi DISK kosusu, ama o kosunun
    #     y+'i 31.3, yani duvar-FONKSIYONU. Hucre etiketi YANLISTI.
    #   - lifting.wall_function = %35.43 -> kaynagi NACA0012 kanat capasi, ama
    #     o capa bu betigin kurallariyla REDDEDILIYOR (sayisal band %17.4>%15).
    # Yani "silmeyelim" kurali, bu betigin KENDI olcutlerinin reddettigi
    # sayilari yayimda tutuyordu. Band artik BU KOSUNUN olcumlerinden kurulur;
    # dusen hucre sessizce kaybolmaz, gerekcesiyle kayda gecer ve oncule doner.
    onceki = json.loads(BAND_DOSYASI.read_text(encoding="utf-8")) \
        if BAND_DOSYASI.exists() else {}
    birlesik = {r: dict(v) for r, v in olculen.items()}
    dusurulen = []
    for r, h in onceki.items():
        for i, v in h.items():
            if birlesik.get(r, {}).get(i) is None:
                dusurulen.append({
                    "rejim": r, "duvar": i, "onceki_pct": v,
                    "neden": ("bu koşunun çapalarından hiçbiri bu hücreye "
                              "atanamadı — değer önceki bir kampanyadan "
                              "kalmıştı ve bu betiğin ölçütleriyle "
                              "desteklenmiyor; hücre ÖNCÜLE döndü")})

    oncul_kalan = []
    for rejim, cells in _MODEL_U_PCT.items():
        for islem, v in cells.items():
            if not birlesik.get(rejim, {}).get(islem):
                oncul_kalan.append({"rejim": rejim, "duvar": islem,
                                    "oncul_pct": v,
                                    "kapanmasi_icin": _NE_GEREKIYOR.get(
                                        f"{rejim}.{islem}",
                                        "deneysel referanslı, ayrılabilir bir çapa")})

    # BU BETIGIN HESAPLAMADIGI HUCRELER. Band dosyasinda duruyorlar ama baska
    # bir kampanyadan geldiler; kac capadan turedikleri ve tek-capa kuralinin
    # onlara uygulanip uygulanmadigi BURADAN bilinemez. Sessiz birakmak,
    # farkli kurallarla uretilmis sayilari ayni tabloda esitlemek olurdu.
    _bu_betik = {(r, i) for r, h in ayrinti.items() for i in h}
    dis_kaynakli = []
    for rejim, h in birlesik.items():
        for islem, v in h.items():
            if (rejim, islem) in _bu_betik:
                continue
            oncul = _MODEL_U_PCT.get(rejim, {}).get(islem)
            dis_kaynakli.append({
                "rejim": rejim, "duvar": islem, "u_pct": v, "oncul_pct": oncul,
                "_not": ("bu betik ÜRETMEDİ (başka kampanya); çapa sayısı ve "
                         "tek-çapa kuralının uygulanıp uygulanmadığı bilinmiyor"
                         + (f" — öncülden (%{oncul}) KÜÇÜK, gözden geçirilmeli"
                            if oncul is not None and v < oncul else ""))})

    rec = {
        "vaka": "Model-form belirsizliği — rejim × duvar işlemi, ÖLÇÜLEN çapalardan",
        "_neden": ("Deger LITERATUR-ONCULUYDU ve rejimden bagimsiz uygulaniyordu. "
                   "Bagli akis, ayrilmis akis ve kunt cisim ayni model-form "
                   "hatasini tasimaz."),
        "capalar": [{**x, "sapma_pct": (round(x["sapma_pct"], 2)
                                       if x.get("sapma_pct") is not None else None)}
                    for x in capalar],
        "olculen_hucreler": ayrinti,
        "atanamayan_capalar": atanamayan,
        "oncul_kalan_hucreler": oncul_kalan,
        "dis_kaynakli_hucreler": dis_kaynakli,
        "dusurulen_hucreler": dusurulen,
        "siralama_uyarilari": _siralama_uyarilari(birlesik, _MODEL_U_PCT),
        "yplus_kapsam_ozeti": _kapsam_ozeti(capalar),
        "_kisit": ("Bir capanin sapmasi, o rejimdeki model-form hatasinin BIR "
                   "ORNEGIDIR. N=1 olan hucrede dagilim IDDIA EDILMEZ. Duvar "
                   "islemi kayitli olmayan capa hucreye ATANMAZ — tahmin "
                   "edilmez. Ayrica sapma, referansin KENDI deneysel "
                   "belirsizligini de icerir ve o ayristirilmamistir."),
        "_uretim": "Üretim: python experiments/model_form_bandi.py",
    }
    _ust = [f"{r}.{i}" for r, h in ayrinti.items() for i, d in h.items()
            if d.get("_ust_sinir_mi")]
    rec["_ayrilabilirlik_notu"] = (
        "UST SINIR olan hucreler: " + (", ".join(_ust) or "yok") + ". Bu "
        "hucrelerde HICBIR capa, olculen farki kendi ayriklastirma bandindan "
        "ayirt edemiyor — deger olculmus bir model hatasi DEGIL, ust sinirdir. "
        "Ornek: disk capasinin farki %3.4 ama sayisal bandi %4.8."
        if _ust else "Her olculen hucrede en az bir capa model hatasini "
                     "sayisal hatadan ayirt edebiliyor.")
    rec["ozet"] = model_form_ozeti(rec)
    rec["verdikt"] = (
        f"{len(capalar)} capa toplandi; {sum(len(v) for v in ayrinti.values())} "
        f"hucre OLCULDU, {len(atanamayan)} capa atanamadi, "
        f"{len(oncul_kalan)} hucre ONCUL kaldi. "
        + "; ".join(f"{r}.{i}=%{d['u_pct']} (n={d['n_capa']})"
                    for r, h in ayrinti.items() for i, d in h.items()))
    rec["_yazilan"] = birlesik
    return rec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    BAND_DOSYASI.write_text(
        json.dumps(rec["_yazilan"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    # ORTAM DAMGASI URETIM ANINDA (bkz. ortam.damgala): sonradan eklenen
    # damga, sayinin hangi yiginda DOGDUGUNU degil en son ne zaman
    # bakildigini soyler.
    import ortam
    ortam.damgala(rec)
    (KOK / "model_form_bandi.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    for x in rec["capalar"]:
        _s = ("GEÇERSİZ" if x.get("_gecersiz")
              else "DÜŞTÜ" if x.get("_dustu")
              else f"%{x['sapma_pct']:>5.2f}")
        print(f"  {x['capa']:<34} {x['rejim']:<12} {_s:>8}"
              f"  y+={x.get('yplus_ort')}")
    if rec["atanamayan_capalar"]:
        print("\n  ATANAMAYAN:")
        for x in rec["atanamayan_capalar"]:
            # KAYITLI GEREKCEYI BAS. Ilk surum hepsine "tampon bolge" diyordu —
            # oysa nedenler farkli (tepe y+ disarida, sayisal band cok buyuk,
            # kayit yok) ve hangisinin gecerli oldugu okuyucu icin onemli.
            print(f"    {x['capa']} — %{x['sapma_pct']}: {x['neden'][:150]}")
    print("\n" + rec["verdikt"])
    print("-> model_form_bandi.json, validation_band.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
