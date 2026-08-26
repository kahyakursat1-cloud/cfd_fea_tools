"""`lifting.wall_function` hücresi neden boş — engel gerçekten donanım mı?

VAKA. Model-form tablosunun bu hücresi öncülle çalışıyor ve kayıtlı gerekçesi
şuydu: ``referans belirsizliği (%15) baskın''. O gerekçe ARTIK GEÇERLİ DEĞİL.
AR6 çapasının referansı 2026-08-19'da yarı-analitikten Ladson TM-4074
ölçümüne taşındı ve `u_ref_pct` %15'ten %1,0'a indi --- yani ``ağ ne kadar
inceltilirse inceltilsin u_val %15'in altına inemez'' cümlesi bugün yanlıştır.
Metin elle yazılmıştı ve veriyle birlikte güncellenmedi; bu depoda avlanan
kusur sınıfının ta kendisi.

O HÂLDE GERÇEK ENGEL NE? Ölçülen tek şey şu: AR6 çapası `snappyHexMesh`te
1319 s sonra rc 137 ile düştü ve süre iç zaman aşımının (1780 s) ALTINDA
olduğu için arıza belleğe bağlandı (bkz. `_asama_arizasi` sınıflandırması).
Ama o koşu KATMAN örüyordu --- yani duvar-ÇÖZÜNÜR bir ağ hedefliyordu.

BU HÜCRE DUVAR-FONKSİYONU HÜCRESİ. y⁺ 30--300 bandı, y⁺≈1'e göre ilk hücreyi
mertebelerce büyütür ve katman yığınını kısaltır. Yani düşen koşunun bütçesi
bu hücrenin bütçesi DEĞİLDİR. Betik ikisini de aynı modelle kestirir ve
farkı sayıya çevirir: engel donanım mı, yoksa yanlış ağ hedefi mi?

KESTİRİM KESTİRİMDİR. Hücre sayısı 1/7-kuvvet yasası + geometrik katman
modeliyle bulunur; snappy'nin gerçek çıktısı bundan sapar. Sonuç bir MERTEBE
hükmüdür ("sığar / sığmaz / sınırda"), bir taahhüt değil.

    python experiments/lifting_wf_fizibilite.py
Çıktı: lifting_wf_fizibilite.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "lifting_wf_fizibilite.json"
NU = 1.5e-5
BUYUME = 1.2
# AR6 capasinin GERCEK gecmesi (sonuc.json geometry): kiris 3,0 m, aciklik
# 18,0 m, 30 m/s. Sabit yazilmaz, kayittan okunur.
KOSU = KOK / "validation_anchors_runs" / "_anchor_naca0012_wing_ar6" / "sonuc.json"
# Duvar-fonksiyonu bandinin ALT ucu secilir: en ince, yani en PAHALI hal.
# Bandin ustunu secmek fizibiliteyi kendi lehine cevirmek olurdu.
YPLUS_WF = 30.0
YPLUS_WR = 1.0


def _kosu_gecmisi() -> dict:
    """Geometri ve hız çapanın KENDİ kaydından; burada yeniden yazılmaz."""
    if not KOSU.exists():
        return {"_kaynak": "kayıt yok — öncül geometri", "kord_m": 3.0,
                "aciklik_m": 18.0, "u_ms": 30.0}
    d = json.loads(KOSU.read_text(encoding="utf-8"))
    g = d.get("geometry") or {}
    b = g.get("boyutlar_m") or [3.0, 18.0, 0.36]
    return {"_kaynak": str(KOSU.relative_to(KOK)),
            "kord_m": float(b[0]), "aciklik_m": float(b[1]),
            "u_ms": float(d.get("velocity") or 30.0),
            "islak_alan_m2": float(g.get("yuzey_alani_m2") or 2 * b[0] * b[1]),
            "dusme_gerekcesi": (d.get("error") or "").splitlines()[:1]}


def ilk_hucre(u_inf: float, l_ref: float, yplus: float) -> tuple[float, float]:
    """Hedef y⁺ için ilk hücre yüksekliği (m) ve u_tau.

    1/7-kuvvet yasası (Schlichting). y⁺ hücre MERKEZİNDE tanımlı olduğundan
    ilk hücre yüksekliği iki katıdır --- bu çarpan düz levha çapasında
    ölçülerek doğrulandı, varsayılmadı.
    """
    re_l = u_inf * l_ref / NU
    cf = 0.0592 * re_l ** -0.2
    u_tau = u_inf * math.sqrt(cf / 2.0)
    return 2.0 * yplus * NU / u_tau, u_tau


def _butce(g: dict, yplus: float, katman_sonu_m: float) -> dict:
    ilk, u_tau = ilk_hucre(g["u_ms"], g["kord_m"], yplus)
    n_katman = max(1, math.ceil(math.log(max(katman_sonu_m / ilk, 1.0001))
                                / math.log(BUYUME)))
    yuzey_hucre = katman_sonu_m
    n_yuzey = g["islak_alan_m2"] / yuzey_hucre ** 2
    n_toplam = n_yuzey * n_katman * 3.0      # dis alan ~ prizmanin 3 kati

    import bellek_kapisi
    bel = bellek_kapisi.tahmini_gb(int(n_toplam))
    bos = bellek_kapisi.bos_bellek_gb()
    # Sure: ayni referans olcum (3B URANS 403.200 hucre / 3300 adim / 2 saat)
    saat = 2.0 * (n_toplam / 403_200) * (2000 / 3300)
    return {
        "yplus_hedef": yplus,
        "ilk_hucre_um": round(ilk * 1e6, 2),
        "u_tau_ms": round(u_tau, 4),
        "katman_sayisi": n_katman,
        "yuzey_hucre_mm": round(katman_sonu_m * 1e3, 2),
        "hucre_kestirimi": int(n_toplam),
        "bellek_gb": round(bel["gereken_gb"], 2),
        "bellek_kaynagi": bel["kaynak"],
        "bos_bellek_gb": round(bos, 2) if bos else None,
        "bellege_sigar_mi": bool(bos is not None and bel["gereken_gb"] < bos),
        "sure_saat_kestirim": round(saat, 1),
    }


# TARANAN YUZEY COZUNURLUKLERI (kirisin katlari). Tek bir deger SECMEK
# olcumu ona baglar; ilk surum 0,005c aldi ve butceyi 4-16 kat sisirdi ---
# ustelik "sigmaz" yonunde, yani KOLAY yonde. Gercek capalarin kullandigi
# bant OLCULDU (h/L: disk 0,0158, kup 0,0234, Ahmed 0,0114, kure 0,0204),
# o yuzden burada bir EGRI verilir ve hukum egriden okunur.
COZUNURLUKLER = (0.005, 0.0075, 0.01, 0.015, 0.02, 0.03)


def olc() -> dict:
    g = _kosu_gecmisi()
    egri = []
    for oran in COZUNURLUKLER:
        b = _butce(g, YPLUS_WF, oran * g["kord_m"])
        b["h_bolu_kiris"] = oran
        b["kiris_basina_hucre"] = int(round(1.0 / oran))
        egri.append(b)
    sigan = [b for b in egri if b["bellege_sigar_mi"]]
    wf = min(egri, key=lambda b: abs(b["h_bolu_kiris"] - 0.01))
    wr = _butce(g, YPLUS_WR, 0.01 * g["kord_m"])
    wr["h_bolu_kiris"] = 0.01
    return _ozetle(g, wf, wr, egri, sigan)


def _ozetle(g: dict, wf: dict, wr: dict, egri: list, sigan: list) -> dict:
    import validation_anchors as va
    spec = va.ANCHORS.get("naca0012_wing_ar6", {})
    u_ref = spec.get("u_ref_pct")
    en_ince_sigan = min(sigan, key=lambda b: b["h_bolu_kiris"]) if sigan else None
    return {
        "vaka": "lifting.wall_function — engel donanım mı, ağ hedefi mi?",
        "_neden": ("Hucrenin kayitli engeli 'referans belirsizligi %15' idi ve "
                   "BAYAT: AR6 referansi Ladson olcumune tasindi, u_ref %1,0. "
                   "Olculen tek engel kosunun BELLEKTEN dusmesi --- ama o kosu "
                   "duvar-COZUNUR ag oruyordu; bu hucre duvar-FONKSIYONU."),
        "capa_gecmisi": g,
        "referans_belirsizligi_pct": u_ref,
        "referans_belirsizligi_sinifi": spec.get("u_ref_sinif"),
        "eski_gerekce_gecerli_mi": bool(u_ref is not None and u_ref >= 15.0),
        "cozunurluk_egrisi": egri,
        "_capalarin_kullandigi_bant": {
            "disk": 0.0158, "kup": 0.0234, "ahmed": 0.0114, "kure": 0.0204,
            "_not": ("h/L olculdu (L = en buyuk boyut). Kanatta ilgili uzunluk "
                     "KIRIS'tir, kunt gövdede en buyuk boyut --- yani bu bant "
                     "birebir tasinamaz, yalniz MERTEBE verir."),
        },
        "bellege_sigan_en_ince": en_ince_sigan,
        "duvar_fonksiyonu_butcesi": wf,
        "duvar_cozunur_butcesi": wr,
        "ucuzlama_carpani": (round(wr["hucre_kestirimi"] / wf["hucre_kestirimi"], 1)
                             if wf["hucre_kestirimi"] else None),
        "verdikt": _hukum(g, wf, wr, u_ref, en_ince_sigan),
        "_kisit": ("KESTIRIM: hucre sayisi 1/7-kuvvet yasasi + geometrik katman "
                   "modeliyle bulunur; snappy'nin gercek ciktisi bundan SAPAR. "
                   "Sonuc bir MERTEBE hukmudur, taahhut degil. Ayrica bellege "
                   "sigmak KOSMAK demek degildir: snappy'nin tepe kullanimi "
                   "cozucununkinden yuksek olabilir ve dusen kosu tam orada "
                   "dustu. y+ bandinin ALT ucu (30) secildi, yani en pahali "
                   "hal. GCI icin UC seviye gerekir; asagidaki butce TEK "
                   "seviyenindir ve en ince seviye butceyi belirler."),
        "_uretim": "Üretim: python experiments/lifting_wf_fizibilite.py",
    }


def _hukum(g: dict, wf: dict, wr: dict, u_ref, en_ince) -> str:
    s = ""
    if u_ref is not None and u_ref < 15.0:
        s += (f"ESKI GEREKCE CURUDU: kayitli engel 'referans belirsizligi %15' "
              f"diyordu, bugunku deger %{u_ref} --- o cumle elle yazilmis ve "
              f"veriyle guncellenmemis. ")
    kat = (wr["hucre_kestirimi"] / wf["hucre_kestirimi"]
           if wf["hucre_kestirimi"] else 0)
    s += (f"Kiris basina 100 hucrede (h/c=0,01): duvar-fonksiyonu "
          f"{wf['hucre_kestirimi']:,} hucre / {wf['bellek_gb']} GB, "
          f"duvar-cozunur {wr['hucre_kestirimi']:,} hucre / {wr['bellek_gb']} "
          f"GB --- {kat:.1f} kat fark. ")
    if en_ince is None:
        return s + (f"TARANAN HICBIR COZUNURLUK bos bellege "
                    f"({wf['bos_bellek_gb']} GB) SIGMIYOR (en kaba deneme "
                    f"h/c={max(COZUNURLUKLER)}). Engel gercekten DONANIM.")
    return s + (
        f"Bos bellege ({en_ince['bos_bellek_gb']} GB) sigan EN INCE cozunurluk "
        f"h/c={en_ince['h_bolu_kiris']} yani kiris basina "
        f"{en_ince['kiris_basina_hucre']} hucre "
        f"({en_ince['hucre_kestirimi']:,} hucre, {en_ince['bellek_gb']} GB, "
        f"~{en_ince['sure_saat_kestirim']} saat). HUKUM BU SAYIYA BAKAN "
        f"KISININDIR: kiris basina {en_ince['kiris_basina_hucre']} hucre bir "
        f"tasima capasi icin yeterli mi? Ustelik GCI UC seviye ister ve en "
        f"ince seviye budur --- yani gercek butce daha buyuk.")


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
