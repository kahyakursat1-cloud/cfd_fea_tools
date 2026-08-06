"""Analiz mentoru — ML katmanının 'nasıl mesh atılır / nasıl analiz yapılır' öğrenmesi
+ acemi-kullanıcı öğretici katmanı (BİLSEM BYF/ÖYG/PROJE seviyeleri).

Dört iş:
1. harvest_mesh(): geçmiş koşulardan mesh/ayar→sonuç kayıtları toplar (mesh_memory.jsonl).
   BAŞARISIZ koşular da kaydedilir — negatif ders ("bu geometri sınıfı + bu kalite çöküyor")
   öğrenmenin yarısıdır. FEA sonuçları (fea_sonuc.json) kardeş sonuc.json geometrisiyle eşlenir.
2. advise_mesh(metrik, tip): kNN → kalite önerisi (komşu başarı oranına göre), ölçülmüş
   y⁺ hedef-düzeltmesi, beklenen hücre sayısı, risk notları.
3. advise_fea(metrik): model (dolu/kabuk) + tekillik beklentisi önerisi.
4. egitim_notu(baglam, seviye): otomatik kararların 'NEDEN'ini BYF (analoji) / ÖYG
   (pratik+temel formül) / PROJE (mühendislik) dilinde anlatır — analiz yaparken öğretir.

DÜRÜSTLÜK: 2-3 çıktıları ÖĞRENİLEN-ÖNCÜL'dür; ayarı kural+kullanıcı onayı belirler
(öner+onayla). Veri ince (n<MIN_SUPPORT) ise şeffaf None. Öğretici metinler şablondur,
sayı uydurmaz — sayılar yalnız koşunun kendi sonuçlarından gelir.

CLI: python mentor.py harvest | advise <stl> [--tip roket] | ogret <stl> [--seviye byf]
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MESH_MEMORY = HERE / "mesh_memory.jsonl"
_SCAN_ROOTS = ("vehicle_runs", "validation_anchors_runs", "_doe_runs")
MIN_SUPPORT = 4
SEVIYELER = ("byf", "oyg", "proje")


# ───────────────────────── 1. Hasat ─────────────────────────

def _cfd_record(path: Path) -> dict | None:
    try:
        s = json.loads(path.read_text(encoding="utf-8"))
    # sessiz-yutma: kabul — öğrenme kaydı; düşerse vaka kütüphaneye girmez — hüküm üretmez, öneri zayıflar
    except Exception:
        return None
    geo = s.get("geometry") or {}
    if not geo.get("boyutlar_m"):
        return None
    import auto_pilot as ap
    try:
        cls = ap.classify_vehicle(geo)
    # sessiz-yutma: kabul — öğrenme kaydı; düşerse vaka kütüphaneye girmez — hüküm üretmez, öneri zayıflar
    except Exception:
        return None
    metrik = cls["metrik"]
    bl = s.get("sinir_tabaka") or {}
    yp = bl.get("yplus") or {}
    md = s.get("mesh_duyarlilik") or {}
    conv = s.get("convergence") or {}
    return {"tur": "cfd", "ts": time.strftime("%Y-%m-%d %H:%M"), "kaynak": str(path),
            "dosya": geo.get("dosya", ""), "metrik": metrik, **_tip_alanlari(s, cls),
            "kalite": s.get("kalite", ""), **_basari_etiketi(s),
            "cells": (s.get("mesh") or {}).get("cells"),
            "non_ortho": (s.get("mesh") or {}).get("non_ortho_max"),
            "n_layers": bl.get("katman_sayisi", 0),
            "yplus_hedef": bl.get("yplus_hedef"), "yplus_ort": yp.get("ort"),
            # AYAR→SONUÇ öğrenmesinin asıl değişkeni. Kayıtta YOKTU: havuz
            # `kalite`yi tutuyordu ama ölçülmüş tek kaldıraç ref_bump'tı, yani
            # öğrenme değişkeni hiç kaydedilmiyordu. Fizik önerisi ile GERÇEKTEN
            # kullanılan kademe ayrı ayrı durur — ikisi ayrıştığında sebebi
            # görünsün.
            **{k: (bl.get("ref_bump_onerisi") or {}).get(v)
               for k, v in (("ref_bump", "kullanilan"), ("ref_bump_oneri", "bump"),
                            ("beklenen_yplus", "beklenen_yplus"))},
            "drift_ok": conv.get("drift_ok"),
            "gci_asimptotik": str(md.get("verdikt", "")).startswith("✅"),
            "n_uyari": len(s.get("uyarilar") or []),
            # ÖĞRENİLEBİLİR Mİ? Kayıt TARİHİNE göre değil, GÖVDENİN GERÇEKTEN
            # ÇÖZÜLÜP ÇÖZÜLMEDİĞİNE göre. 2026-07-29'a kadarki tüm araç koşularında
            # arka plan mesh'i hücre bütçesini tek başına yiyordu; snappy hiç yüzey
            # iyileştirmesi yapamıyor ve gövde 74 yüzle temsil ediliyordu (ölçüldü).
            # O koşulardan öğrenilen her örüntü, çözülmemiş bir geometrinin
            # örüntüsüdür. Ama tarihe göre kesmek yanlış olurdu: eski bir koşuda
            # geometri tesadüfen çözülmüş olabilir, yeni bir koşuda çözülmemiş
            # olabilir. Ölçüm ayraçtır.
            #
            # `yuzey_cozunurlugu` alanı düzeltmeyle geldi; yoksa ölçüm YOK demektir
            # ve "ölçemedim" ≠ "iyi" (bu oturumun tekrarlayan dersi).
            **_yuzey_gecerlilik(bl)}


def _basari_etiketi(s: dict) -> dict:
    """Öğrenmenin BAŞARI etiketi = KAPININ HÜKMÜ, çözücünün çıkış kodu değil.

    Eski etiket `status == "ok"` idi, yani "çözücü temiz çıktı". ÖLÇÜLDÜ (sabit
    ref_bump=0 taraması, 12 geometri): kapı 6 koşuyu savunulamaz saydı
    (gondol_dort y⁺=1222, su57 y⁺=3239, çiftkuyruk 426, kapsül 370, a320, …)
    ama ONİKİSİNİN DE status'ü "ok" idi — havuz 27 kayda çıktı, hepsi hâlâ
    "başarılı" göründü. Havuz bu etiketle hiçbir zaman ayırt edici olamazdı:
    kayıt sayısı artıyor, bilgi artmıyordu.

    Tanım çoğaltılmıyor: validity_envelope.savunulabilir TEK KAYNAK.
    """
    from validity_envelope import savunulabilir
    h = savunulabilir(s)
    return {"ok": bool(h["savunulabilir"]),
            "cozucu_bitti": s.get("status") == "ok",   # provenans: eski etiket
            "basarisizlik": "; ".join(h["gerekce"])[:200] or None}


def _tip_alanlari(s: dict, cls: dict) -> dict:
    """Havuz anahtarı olarak SINIFLANDIRILAN tip kullanılır, koşuya GEÇİLEN değil.

    NEDEN: `vehicle_type` çoğu zaman çağıranın dokunmadığı VARSAYILAN argümandır,
    bir gözlem değil. ÖLÇÜLDÜ (165 kayıt): kaydedilen tip ile geometriden
    sınıflandırılan tip yalnız 78'inde uyuşuyor — %47. Güvenilirlik taraması
    hiç `vehicle_type` geçirmediği için öğrenilebilir 16 kaydın 16'sı da "ucak"
    yazıyordu; içlerinde 800 mm'lik bir KÜP ve bir multikopter var.

    Sorgu tarafı (auto_pilot) zaten sınıflandırılmış tiple çağırıyor; kayıt
    tarafının da aynı yordamdan gelmesi karşılaştırmayı elma-elma yapar.
    Kaydedilen değer `tip_kayitli`de saklanır — çelişki gizlenmez, sayılır.

    UYARI: sınıflandırıcı da mutlak değil ve güveni kalibre DEĞİL (ölçüldü:
    A320 gövdesi → "genel" güven 1.0). Bu yüzden tip yalnız ÖN-FİLTREdir ve
    havuz eşiği tutmazsa kNN tüm havuza düşer; asıl iş metrik uzayındadır.
    """
    kayitli = s.get("vehicle_type", "genel")
    return {"tip": cls["tip"], "tip_kayitli": kayitli,
            "tip_guven": round(float(cls.get("guven", 0.0)), 2),
            "tip_celiskisi": kayitli != cls["tip"]}


def _yuzey_gecerlilik(bl: dict) -> dict:
    """Bu koşudan öğrenilebilir mi? Ölçüm yoksa 'bilinmiyor' — 'iyi' DEĞİL."""
    yc = bl.get("yuzey_cozunurlugu")
    if not isinstance(yc, dict):
        return {"yuzey_cozuldu": None,
                "ogrenilebilir": False,
                "gecersizlik": "yuzey cozunurlugu OLCULMEMIS (duzeltme oncesi kosu)"}
    ok = bool(yc.get("cozuldu"))
    # EN KUCUK OZELLIK ayri bir bilgidir ve engelleyici DEGILDIR: kapiyi gecen
    # bir kosuda bile ince firar kenari temsil edilmemis olabilir (arsivde 3/12).
    # Havuz bunu tasimazsa, iki kosu "ayni ayar, ayni geometri" gorunup farkli
    # Cd verir ve komsuluk yaniltir.
    gr = yc.get("geometri_goreli") or {}
    return {"yuzey_cozuldu": ok, "ogrenilebilir": ok,
            "ozellik_basina_hucre": gr.get("ozellik_basina_hucre"),
            "ozellik_cozuldu": gr.get("ozellik_cozuldu"),
            **({} if ok else
               {"gecersizlik": "; ".join(yc.get("gerekce", []))[:160]})}


def _fea_record(path: Path) -> dict | None:
    try:
        f = json.loads(path.read_text(encoding="utf-8"))
        s = json.loads((path.parent / "sonuc.json").read_text(encoding="utf-8"))
    # sessiz-yutma: kabul — öğrenme kaydı; düşerse vaka kütüphaneye girmez — hüküm üretmez, öneri zayıflar
    except Exception:
        return None
    geo = s.get("geometry") or {}
    if not geo.get("boyutlar_m"):
        return None
    import auto_pilot as ap
    try:
        cls = ap.classify_vehicle(geo)
    # sessiz-yutma: kabul — öğrenme kaydı; düşerse vaka kütüphaneye girmez — hüküm üretmez, öneri zayıflar
    except Exception:
        return None
    metrik = cls["metrik"]
    return {"tur": "fea", "ts": time.strftime("%Y-%m-%d %H:%M"), "kaynak": str(path),
            "metrik": metrik, **_tip_alanlari(s, cls),
            "ok": f.get("status") == "ok", "model": f.get("model", ""),
            "mesnet": f.get("mesnet", ""), "dugum": f.get("dugum"),
            "eleman_tipi": f.get("eleman_tipi", ""),
            "tekillik": bool(f.get("tekillik_suphesi")),
            "mekanizma": bool(f.get("gecersiz"))}


def harvest_mesh(roots=_SCAN_ROOTS) -> dict:
    """Koşu dizinlerini tara → MESH_MEMORY'yi yeniden yaz (idempotent, kendiliğinden büyür)."""
    recs = []
    for root in roots:
        base = HERE / root
        for p in sorted(base.rglob("sonuc.json")):
            r = _cfd_record(p)
            if r:
                recs.append(r)
        for p in sorted(base.rglob("fea_sonuc.json")):
            r = _fea_record(p)
            if r:
                recs.append(r)
    MESH_MEMORY.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs),
                           encoding="utf-8")
    n_cfd = sum(1 for r in recs if r["tur"] == "cfd")
    cfd = [r for r in recs if r["tur"] == "cfd"]
    ogr = sum(1 for r in cfd if r.get("ogrenilebilir"))
    olculmemis = sum(1 for r in cfd if r.get("yuzey_cozuldu") is None)
    # SESSİZ DARALTMA YOK: kaç kaydın öğrenmeye girmediği ve NEDEN girmediği
    # raporlanır. Havuz sessizce küçülürse "modelim neden kötü öneriyor"
    # sorusunun cevabı görünmez olur.
    return {"n_kayit": len(recs), "n_cfd": n_cfd, "n_fea": len(recs) - n_cfd,
            "n_basarisiz": sum(1 for r in recs if not r["ok"]),
            "n_ogrenilebilir": ogr, "n_dislanan": n_cfd - ogr,
            "n_yuzey_olculmemis": olculmemis,
            "n_tip_celiskisi": sum(1 for r in recs if r.get("tip_celiskisi")),
            "dosya": str(MESH_MEMORY)}


def _load(tur: str, sadece_gecerli: bool = True) -> list[dict]:
    """Öğrenme havuzu. `sadece_gecerli`: gövdesi ÇÖZÜLMEMİŞ koşular havuza GİRMEZ.

    Bu filtre olmadan kNN, çözülmemiş geometrilerin örüntüsünü öğrenir ve onu
    güvenle önerir — nitekim öğrenmişti: mentor "katman-çökmesi imzası, katmansız
    'hassas_nl' düşünün" diyordu; ÖLÇÜLDÜ ki `hassas_nl` ile `hassas` BİREBİR aynı
    mesh'i veriyor (660862 hücre, iki preset de ref_bump=+1). Yani bozuk veriden
    tutarlı ama YANLIŞ bir kural çıkmıştı.

    Sessizce daraltmıyoruz: `harvest_mesh` kaç kaydın dışlandığını raporlar.
    """
    if not MESH_MEMORY.exists():
        return []
    out = []
    for line in MESH_MEMORY.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if sadece_gecerli and r.get("tur") == "cfd" and not r.get("ogrenilebilir"):
                continue
            if r.get("tur") == tur and r.get("metrik"):
                out.append(r)
        # sessiz-yutma: kabul — bozuk satır atlanır; kütüphane kısmi yüklenir, hüküm üretmez
        except Exception:
            pass
    return out


# ───────────────────────── 2-3. Öğrenilen öneriler ─────────────────────────

def _knn(pool: list[dict], metrik: dict, k: int) -> list[tuple[float, dict]]:
    import auto_pilot as ap
    fv = ap._features(metrik)

    def d2(c):
        return sum((a - b) ** 2 for a, b in zip(fv, ap._features(c["metrik"])))
    return sorted(((d2(c), c) for c in pool), key=lambda t: t[0])[:k]


def _geometri_anahtari(c: dict) -> str:
    return str(c.get("dosya") or c.get("kaynak") or id(c))


def _ayrik_geometriler(pool: list[dict]) -> list[dict]:
    """Geometri başına TEK kayıt — mesafe istatistiği için.

    ÖLÇÜLDÜ: havuz 31 kayıt ama yalnız 17 AYRIK geometri; aynı gövdenin farklı
    ayarlarla tekrar koşuları ayrı kayıt olarak duruyor ve öznitelik vektörleri
    BİREBİR AYNI. Sonuç: 31 kaydın 26'sının en-yakın-komşu mesafesi TAM SIFIR.
    Eşiği bu dağılımdan türetmek, yarısı sıfır olan bir dağılımdan türetmektir.

    Sonuç istatistiği (ayar→başarı) için tekrarlar DEĞERLİDİR ve korunur;
    burada yalnız GEOMETRİ UZAYI yoğunluğu ölçülür.
    """
    gorulen: dict[str, dict] = {}
    for c in pool:
        gorulen.setdefault(_geometri_anahtari(c), c)
    return list(gorulen.values())


def _havuz_en_yakin_mesafeler(pool: list[dict]) -> list[float]:
    """AYRIK geometrilerin en-yakın-komşu mesafeleri (leave-one-out).

    OOD eşiği UYDURULMAZ: havuzun kendi yoğunluğundan türetilir. Bir sorgu,
    havuz üyelerinin birbirine olan tipik uzaklığından belirgin daha uzaksa
    o sorgu havuzun KAPSAMADIĞI bir bölgededir.
    """
    import auto_pilot as ap
    fv = [ap._features(c["metrik"]) for c in _ayrik_geometriler(pool)]
    out = []
    for i, a in enumerate(fv):
        d = [sum((x - y) ** 2 for x, y in zip(a, b))
             for j, b in enumerate(fv) if j != i]
        if d:
            out.append(min(d) ** 0.5)
    return sorted(out)


# Sorgunun en yakın komşusu, havuzun kendi en-yakın-mesafelerinin bu yüzdeliğini
# aşarsa DAĞILIM DIŞI sayılır. %90: havuz üyelerinin onda dokuzu birbirine bundan
# daha yakın; sorgu daha uzaksa havuzun örneklemediği bir bölgededir.
OOD_YUZDELIK = 0.90


def _ood_hukmu(pool: list[dict], knn: list) -> dict:
    """Sorgu havuzun kapsadığı bölgede mi? Öneri güvenilirliği buradan gelir.

    NEDEN: `_knn` uzaklık NE OLURSA OLSUN k komşu döndürüyordu. Hiçbir şeye
    benzemeyen bir geometri de kendinden emin görünen bir öneri alıyordu;
    öneriyle birlikte MESAFE gösterilmediği için kullanıcı bunu göremiyordu.
    """
    if not knn:
        return {"durum": "komşu yok", "guvenilir": False}
    d_sorgu = knn[0][0] ** 0.5
    havuz = _havuz_en_yakin_mesafeler(pool)
    if len(havuz) < 3:
        return {"durum": "havuz çok küçük — eşik türetilemedi",
                "en_yakin_mesafe": round(d_sorgu, 4), "guvenilir": False}
    esik = havuz[min(int(len(havuz) * OOD_YUZDELIK), len(havuz) - 1)]
    disarida = d_sorgu > esik
    # KOMŞULAR KAÇ AYRI GÖVDEDEN? k=8 komşu, 2 gövdenin 8 koşusu olabilir.
    # "8 komşu" iyi desteklenmiş görünür ama aslında iki geometridir.
    komsu_ayrik = len({_geometri_anahtari(c) for _, c in knn})
    return {
        "en_yakin_mesafe": round(d_sorgu, 4),
        "havuz_esigi": round(esik, 4),
        "havuz_medyan_mesafe": round(havuz[len(havuz) // 2], 4),
        "havuz_ayrik_geometri": len(havuz) + 1,
        "komsu_ayrik_geometri": komsu_ayrik,
        "komsu_kayit": len(knn),
        "yuzdelik": OOD_YUZDELIK,
        "dagilim_disi": disarida,
        "guvenilir": not disarida and komsu_ayrik >= 2,
        "durum": (f"DAĞILIM DIŞI: en yakın komşu {d_sorgu:.3f} uzaklıkta, havuzun kendi "
                  f"%{OOD_YUZDELIK * 100:.0f} yüzdeliği {esik:.3f}. Bu geometri havuzun örneklemediği "
                  "bir bölgede; öneri YALNIZ BAŞLANGIÇ AYARIDIR ve otomatik "
                  "karara GİRMEZ")
        if disarida else
        (f"havuz kapsamında: en yakın komşu {d_sorgu:.3f}, eşik {esik:.3f}"
         ),
    }


def _ref_bump_dersi(knn: list) -> dict:
    """Komşuların ref_bump→sonuç geçmişi ve FİZİK KURALIYLA ÇELİŞKİSİ.

    NEDEN AYRI: mentor `kalite` sıralıyordu, ama ölçülmüş tek kaldıraç ref_bump
    (MiniHawk: +1/+2/+3 → y⁺ 340/112/61). Yani öğrenme, sonucu belirlemeyen
    değişkeni sıralıyordu.

    BU BİR ÖNERİ DEĞİL, BİR DENETİMDİR. Kademeyi `onerilen_ref_bump` fizikten
    seçer (beklenen y⁺ bandı + hücre bütçesi); öğrenilen havuz onu EZMEZ. Havuzun
    işi, fiziğin seçtiği kademenin gerçekte tutup tutmadığını söylemektir —
    kural ile ölçüm ayrışırsa bu görünmelidir.
    """
    kayitli = [c for _, c in knn if c.get("ref_bump") is not None]
    if not kayitli:
        return {"ref_bump_basari": None, "ref_bump_notu":
                "komşularda ref_bump kaydı YOK (düzeltme öncesi kayıtlar) — "
                "ayar→sonuç dersi çıkarılamaz"}
    ist: dict[int, list[bool]] = {}
    for c in kayitli:
        ist.setdefault(int(c["ref_bump"]), []).append(bool(c["ok"]))
    basari = {b: round(sum(v) / len(v), 2) for b, v in sorted(ist.items())}
    # Fizik önerisi ile KULLANILAN kademenin ayrıştığı ve sonucun BAŞARISIZ
    # olduğu vakalar: kuralı doğrulayan en güçlü kanıt budur.
    ayrisan = [c for c in kayitli
               if c.get("ref_bump_oneri") is not None
               and c["ref_bump_oneri"] != c["ref_bump"]]
    ayrisan_basarisiz = sum(1 for c in ayrisan if not c["ok"])
    not_ = None
    if len(set(basari.values())) <= 1:
        not_ = (f"ref_bump→sonuç AYIRT EDİCİ değil: {len(kayitli)} komşunun hepsi "
                "aynı sonucu verdi; kademe seçimi hakkında bilgi taşımıyor")
    elif ayrisan:
        not_ = (f"fizik önerisinden SAPILAN {len(ayrisan)} komşunun "
                f"{ayrisan_basarisiz} tanesi başarısız — kademeyi kural seçsin, "
                "havuz yalnız denetlesin")
    return {"ref_bump_basari": basari, "ref_bump_notu": not_,
            "ref_bump_kayitli_komsu": len(kayitli)}


def advise_mesh(metrik: dict, tip: str = "", k: int = 8,
                min_support: int = MIN_SUPPORT) -> dict | None:
    """Benzer geometrilerin mesh/ayar SONUÇLARINDAN öneri: kalite (başarı oranıyla),
    y⁺ hedef-düzeltmesi, beklenen hücre, riskler. ÖĞRENİLEN-ÖNCÜL — kuralı ezmez."""
    cases = _load("cfd")
    same = [c for c in cases if c.get("tip") == tip]
    pool = same if len(same) >= min_support else cases
    if len(pool) < min_support:
        return None
    knn = _knn(pool, metrik, k)

    kalite_ist: dict[str, list[bool]] = {}
    for _, c in knn:
        if c.get("kalite"):
            kalite_ist.setdefault(c["kalite"], []).append(bool(c["ok"]))
    basari = {q: round(sum(v) / len(v), 2) for q, v in kalite_ist.items()}
    riskler = []
    onerilen = None
    # AYIRT EDİCİ KANIT YOKSA SIRALAMA YAPILMAZ. Havuzdaki TÜM sonuçlar aynıysa
    # (hepsi başarılı ya da hepsi başarısız) başarı oranı hangi seçeneğin daha iyi
    # olduğu hakkında SIFIR bilgi taşır; sıralama tamamen beraberlik-bozucuya kalır.
    #
    # ÖLÇÜLDÜ: havuz 16 kayıt, 16'sı da ok=True. Mentor `kalite_basari
    # {"hassas_nl": 1.0, "hassas": 1.0}` deyip beraberliği `hassas` lehine bozuyor
    # ve onu öneriyordu — oysa `hassas`ın bu geometride katmanları ÇÖKERTTİĞİ ve
    # `hassas_nl` ile BİREBİR aynı mesh'i verdiği (660862 hücre) ölçülmüştü.
    # Yani bilgi taşımayan bir orandan kendinden emin ve YANLIŞ bir öneri çıkıyordu.
    _sonuclar = {bool(c["ok"]) for _, c in knn}
    _ayirt_edici = len(_sonuclar) > 1
    if basari and _ayirt_edici:
        guvenli = {q: r for q, r in basari.items() if r >= 0.5}
        sira = {"hassas": 3, "hassas_nl": 2, "standart": 1, "hizli": 0}
        if guvenli:
            onerilen = max(guvenli, key=lambda q: (guvenli[q], sira.get(q, -1)))
    elif basari:
        riskler.append(
            f"KALİTE ÖNERİSİ YOK: komşu {len(knn)} vakanın hepsi aynı sonucu verdi "
            f"({'tümü başarılı' if all(_sonuclar) else 'tümü başarısız'}) — başarı "
            "oranı seçenekler arasında AYIRT EDİCİ değil. Öneri üretmek için havuzda "
            "hem başarılı hem başarısız örnek gerekir")
    # Kalite-bazlı RİSK uyarıları sıralamadan BAĞIMSIZDIR: "bu preset komşularda
    # düşük başarılı" bilgisi, sıralama yapılabilsin ya da yapılmasın geçerlidir.
    if basari:
        for q, r in basari.items():
            if r < 0.5:
                katmanli = any(c.get("n_layers", 0) > 0 for _, c in knn
                               if c.get("kalite") == q and not c["ok"])
                # ESKİ ÖNERİ 'hassas_nl' İDİ ve ÖLÇÜMLE YANLIŞ ÇIKTI: `hassas_nl` ile
                # `hassas` BİREBİR aynı mesh'i veriyor (660862 hücre) — ikisinin de
                # ref_bump'ı +1, bg_div'i 9, hücre tavanı aynı. Tek fark n_layers, o da
                # zaten çöküyor. Yani "katmansıza geç" hiçbir şeyi değiştirmiyordu.
                # ÖLÇÜLEN gerçek kaldıraç yüzey iyileştirmesi: y⁺ 340 → 112 → 61
                # (ref_bump +1/+2/+3, MiniHawk, katmansız).
                riskler.append(f"'{q}' bu geometri sınıfında komşularda %{r*100:.0f} başarılı"
                               + (" (katman-çökmesi imzası — 'hassas_nl' AYNI mesh'i "
                                  "verir, çare --ref-bump ile YÜZEY İYİLEŞTİRMESİ)"
                                  if katmanli and q == "hassas" else ""))

    oranlar = [c["yplus_ort"] / c["yplus_hedef"] for _, c in knn
               if c.get("yplus_ort") and c.get("yplus_hedef")]
    yplus_duzeltme = None
    if len(oranlar) >= 2:
        oranlar.sort()
        med = oranlar[len(oranlar) // 2]
        if med > 5.0 or med < 0.2:
            # Uç oran ≠ korelasyon sapması: katmanlar örülememiş/etkisiz (layer-collapse
            # imzası) — hedef-ölçekleme burada yanlış reçete olur.
            # ÇARE ÖLÇÜLDÜ. 'hassas_nl' YANLIŞ reçeteydi (hassas ile birebir aynı
            # mesh). Katman çökmesinin sebebi de ölçüldü: ilk katman 0.048 mm iken
            # yüzey hücresi 10.4 mm — en-boy 215:1, snappy determinant<0.001 ile
            # 34023 yüzü reddedip TÜM ekstrüzyonu geri alıyor. Ayrıca ince firar
            # kenarı (1.19 mm) y⁺=30 için gereken tek katmanı (1.45 mm) bile
            # barındıramıyor. İkisinin de çaresi aynı: YÜZEY HÜCRESİNİ küçültmek.
            _kat = math.ceil(math.log2(max(med / 150.0, 1.0))) if med > 150 else 1
            yplus_duzeltme = {"olculen_hedef_orani": round(med, 2),
                              "onerilen_ref_bump": _kat,
                              "oneri": f"ölçülen y⁺ hedefin ~{med:.0f} katı — prizma "
                                       "katmanları örülememiş (layer-collapse imzası). "
                                       "'hassas_nl' AYNI mesh'i verir, çare değildir; "
                                       f"YÜZEY İYİLEŞTİRMESİ gerekir (--ref-bump {_kat}: "
                                       "her kademe y⁺'ı yarıya indirir, hücreyi ~8× artırır)"}
        elif not 0.5 <= med <= 2.0:
            yplus_duzeltme = {"olculen_hedef_orani": round(med, 2),
                              "oneri": f"düz-plaka korelasyonu bu sınıfta ~{med:.1f}× sapıyor; "
                                       f"hedef y⁺'ı {1/med:.2f}× ile ölçekleyin"}

    cells = sorted(c["cells"] for _, c in knn
                   if c.get("cells") and (not onerilen or c.get("kalite") == onerilen))
    return {"onerilen_kalite": onerilen, "kalite_basari": basari,
            **_ref_bump_dersi(knn),
            "beklenen_hucre": cells[len(cells) // 2] if cells else None,
            "yplus_duzeltme": yplus_duzeltme, "riskler": riskler,
            # n_destek KAYIT sayısı; bağımsız vaka sayısı DEĞİL. Ölçüldü: 16 kaydın
            # 5'i aynı gövde (minihawk, farklı ayarlarla). Ayar→sonuç için tekrarlar
            # sinyaldir, ama "16 farklı geometri gördüm" demek değildir. Ayraç
            # koşu DİZİNİ değil GEOMETRİ DOSYASI: beş minihawk koşusu beş ayrı
            # dizinde ama aynı gövde (mh_katman/mh_nl/mh_rb2/mh_rb3/duzeltme).
            "n_destek": len(pool),
            "n_ayrik_geometri": len({c.get("dosya") or c.get("kaynak") for c in pool}),
            "komsu": len(knn), "ayni_tip": pool is same,
            # OOD HÜKMÜ ÖNERİYLE BİRLİKTE GİDER. Mesafe gösterilmezse kullanıcı
            # "hiçbir şeye benzemeyen geometri" ile "havuzun tam ortasındaki
            # geometri" arasındaki farkı göremez; ikisi de aynı özgüvenle
            # sunulurdu.
            "ood": _ood_hukmu(pool, knn),
            "etiket": "ÖĞRENİLEN-ÖNCÜL — ayarı kural+onay belirler"}


def advise_fea(metrik: dict, k: int = 6, min_support: int = MIN_SUPPORT) -> dict | None:
    """Benzer geometrilerin FEA sonuçlarından: model önerisi + tekillik/mekanizma beklentisi."""
    pool = _load("fea")
    if len(pool) < min_support:
        return None
    knn = _knn(pool, metrik, k)
    ok = [c for _, c in knn if c["ok"] and not c["mekanizma"]]
    tekillik_orani = sum(1 for _, c in knn if c.get("tekillik")) / len(knn)
    mekanizma_orani = sum(1 for _, c in knn if c.get("mekanizma")) / len(knn)
    model_say: dict[str, int] = {}
    for c in ok:
        key = "kabuk" if "kabuk" in c.get("model", "") else "dolu"
        model_say[key] = model_say.get(key, 0) + 1
    notlar = []
    if tekillik_orani >= 0.5:
        notlar.append("Benzer geometrilerde sivri-köşe TEKİLLİĞİ sık — temsili (%99) gerilmeyi "
                      "esas alın, tepe-SF'yi fillet/mesh-yakınsamayla teyit edin.")
    if mekanizma_orani >= 0.3:
        notlar.append("Mesnet-mekanizma riski gözlenmiş — mesnet düzlemini/oryantasyonu kontrol edin.")
    return {"onerilen_model": max(model_say, key=model_say.get) if model_say else None,
            "tekillik_beklentisi": round(tekillik_orani, 2),
            "mekanizma_riski": round(mekanizma_orani, 2), "notlar": notlar,
            "n_destek": len(pool), "komsu": len(knn),
            "ood": _ood_hukmu(pool, knn),
            "etiket": "ÖĞRENİLEN-ÖNCÜL — ayarı kural+onay belirler"}


# ───────────────────────── 4. Öğretici katman ─────────────────────────

_DERS = {
    "mesh": {
        "byf": "Mesh, havayı küçük kutulara bölmek demek — fotoğrafın pikselleri gibi. "
               "Kutular ne kadar küçükse resim o kadar net, ama bilgisayar o kadar yavaş.",
        "oyg": "Mesh = akış alanının hücrelere bölünmesi; cismin yakınında küçük hücre "
               "(değişim hızlı), uzakta büyük hücre kullanılır. Kalite ayarı bu dengeyi seçer.",
        "proje": "snappyHexMesh yüzey-uyarlamalı hex mesh üretir; refinement seviyesi ve "
                 "prizma katmanları sınır tabakasını (y⁺ hedefi) çözer. Mesh yakınsaması "
                 "gösterilmeden mutlak katsayı savunulamaz (GCI).",
    },
    "yakinsama": {
        "byf": "Bilgisayar cevabı deneye deneye bulur. Cevap artık değişmiyorsa 'yakınsadı' "
               "deriz — terazinin ibresinin durması gibi.",
        "oyg": "Her iterasyonda hata (rezidüel) küçülür; Cd eğrisi düzleşince sonuç kararlıdır. "
               "Eğri hâlâ kayıyorsa koşuyu uzatmak gerekir.",
        "proje": "Yakınsama çift kriterlidir: rezidüel < 1e-4 VE kuvvet-katsayısı driftinin "
                 "pencere içinde <%2 kalması. Rezidüel tek başına yanıltır (residual≠force).",
    },
    "belirsizlik": {
        "byf": "Her ölçümün bir hata payı vardır — boyunu ölçerken cetvelin kayması gibi. "
               "Bu yüzden sonucu tek sayı değil, aralık olarak söyleriz.",
        "oyg": "Aynı analizi kaba/orta/ince mesh'le koşup sonucun ne kadar değiştiğine bakarız; "
               "değişim küçükse sayıya güvenilir (mesh-bağımsızlık).",
        "proje": "ASME V&V 20: U_toplam = √(U_sayısal² + U_model²). U_sayısal 3-mesh GCI/LSR'den, "
                 "U_model validasyon çapalarından gelir. Bandsız mutlak sayı rapor edilmez.",
    },
    "aoa": {
        "byf": "Kanadın rüzgâra bakış açısı (hücum açısı) arttıkça kaldırma artar — ama çok "
               "kaldırırsan hava kanattan kopar (perdövites/stall), uçak düşer gibi olur.",
        "oyg": "Cl, α ile yaklaşık doğrusal artar (~0.11/° ince kanat); stall yaklaşınca eğri "
               "kırılır. Polar taraması bu eğriyi çıkarır.",
        "proje": "Doğrulanmış zarf |α|≤8° (bağlı akış, Ladson'a ≤%8). Üstünde steady-RANS "
                 "taşımayı ~%45 düşük verir — o bölgede sayı değil, yalnız stall-onset sinyali.",
    },
    "zemin": {
        "byf": "Araba yerde gider — altındaki hava serbestçe akamaz, yere sürtünür. "
               "Bu yüzden arabayı havada asılıymış gibi hesaplarsak yanlış çıkar; "
               "bilgisayara 'altta yol var' deriz.",
        "oyg": "Zemin, aracın altındaki akışı sıkıştırır ve arkadaki iz bölgesini değiştirir; "
               "rüzgâr tünellerinde de bu yüzden zemin tablası kullanılır. Clearance "
               "(şasi-yer boşluğu) sonucu belirgin etkiler.",
        "proje": "Zemin-etkili kurulum: taban patch'i noSlip duvar, clearance deney "
                 "kurulumuyla eşleşmeli (Ahmed: h/H≈0.17, sabit zemin). Serbest-akış Cd'si "
                 "zemin-etkili referansla kıyaslanamaz — setup-uyumu validasyonun önkoşulu.",
    },
    "fea_sf": {
        "byf": "Emniyet faktörü = malzemenin dayandığı yük / bindirdiğimiz yük. 2 demek "
               "'iki kat garanti' demek — köprüleri de böyle yaparlar.",
        "oyg": "SF = akma gerilmesi / en büyük von Mises gerilmesi. SF≥1.5 hedefleriz; "
               "sivri köşelerdeki tepe değer aldatıcı olabilir (tekillik).",
        "proje": "Tepe-SF muhafazakâr karardır; tekillik şüphesinde temsili (%99-persentil) "
                 "gerilme raporlanır ama karar tepede kalır — gerçek konsantrasyon ile sahte "
                 "tekilliği tek mesh ayıramaz.",
    },
}


def egitim_notu(baglam: dict, seviye: str = "oyg") -> str:
    """Analiz bağlamına göre seviyeli öğretici blok (Markdown). baglam anahtarları:
    tip, analiz ('polar'|'cd_mach'|'tekil'), fea (bool). Şablon-tabanlı — sayı uydurmaz."""
    seviye = seviye.lower()
    if seviye not in SEVIYELER:
        seviye = "oyg"
    konular = ["mesh", "yakinsama", "belirsizlik"]
    if baglam.get("analiz") == "polar" or baglam.get("tip") in ("ucak", "tilt_rotor", "kanatli_vtol"):
        konular.append("aoa")
    if baglam.get("tip") == "araba":
        konular.append("zemin")
    if baglam.get("fea"):
        konular.append("fea_sf")
    baslik = {"byf": "🎓 Merak Kutusu", "oyg": "🎓 Öğrenme Kutusu",
              "proje": "🎓 Yöntem Notları"}[seviye]
    md = [f"### {baslik} (seviye: {seviye.upper()})\n"]
    ad = {"mesh": "Mesh nedir?", "yakinsama": "Yakınsama ne demek?",
          "belirsizlik": "Sonuca ne kadar güvenebilirim?",
          "aoa": "Hücum açısı ve stall", "zemin": "Zemin etkisi",
          "fea_sf": "Emniyet faktörü"}
    for kon in konular:
        md.append(f"- **{ad[kon]}** {_DERS[kon][seviye]}")
    md.append("")
    return "\n".join(md)


if __name__ == "__main__":
    import argparse
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cli = argparse.ArgumentParser()
    cli.add_argument("komut", choices=["harvest", "advise", "ogret"])
    cli.add_argument("stl", nargs="?")
    cli.add_argument("--tip", default="")
    cli.add_argument("--seviye", default="oyg", choices=list(SEVIYELER))
    args = cli.parse_args()
    if args.komut == "harvest":
        print(json.dumps(harvest_mesh(), indent=2, ensure_ascii=False))
    elif args.komut == "advise":
        if not args.stl:
            sys.exit("advise için STL yolu gerekli")
        import auto_pilot as ap
        from vehicle_pipeline import inspect_geometry
        cls = ap.classify_vehicle(inspect_geometry(args.stl))
        out = {"mesh": advise_mesh(cls["metrik"], args.tip or cls["tip"]),
               "fea": advise_fea(cls["metrik"])}
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        tip = args.tip or "genel"
        if args.stl:
            import auto_pilot as ap
            from vehicle_pipeline import inspect_geometry
            tip = args.tip or ap.classify_vehicle(inspect_geometry(args.stl))["tip"]
        print(egitim_notu({"tip": tip, "analiz": "tekil", "fea": True}, args.seviye))
