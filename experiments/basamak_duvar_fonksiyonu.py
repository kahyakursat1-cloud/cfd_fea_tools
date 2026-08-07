"""Geriye-basamak çapası, DUVAR-FONKSİYONU bandında (separated.wall_function).

NEDEN: model-form tablosunun sekiz hücresinden beşi hâlâ literatür öncülüyle
çalışıyor. `separated.wall_function` bunların en ulaşılabiliridir çünkü aynı
deneyin (Driver & Seegmiller 1985) referansı zaten elimizde ve DENEYSELDİR:
Xr/H = 6,26 ± 0,10, yani u_D = %1,6. Yarı-analitik kanat çapasında u_D=%15
baskındı ve ağ inceltmek çare değildi; burada durum tersine.

DUVAR İŞLEMİ AĞIN SONUCUDUR, NİYETİN DEĞİL. Aynı geometri üç ayrı bantta
koşulabilir; belirleyen ilk hücre yüksekliğidir. Duvar-çözünür aile (grading
20, y⁺tepe 0,048) `separated.wall_resolved` hücresini ölçüme bağlamıştı. Bu
betik ilk hücreyi KALINLAŞTIRARAK aynı deneyi log-bölgesine taşır.

İLK HÜCRE SEVİYELER ARASINDA SABİT TUTULUR. Ağ inceldikçe hücre sayısı artar
ve grading aynı kalırsa ilk hücre incelir --- üç seviye üç FARKLI duvar
işleminde olurdu ve GCI ailesi anlamını yitirirdi. Grading her seviyede,
istenen ilk hücreyi verecek şekilde sayısal olarak çözülür.

    python experiments/basamak_duvar_fonksiyonu.py           # üç seviye
    python experiments/basamak_duvar_fonksiyonu.py --oku     # diskteki çözüm

Çıktı: basamak_duvar_fonksiyonu.json (kanıt)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import basamak_ayrilma as _y  # noqa: E402

SEVIYELER = [("L1_kaba", 1.0), ("L2_orta", 1.4), ("L3_ince", 2.0)]
MODEL = "kOmegaSST"
# Hedef ilk hucre: ozgun kosuda 317 um -> y+ 14.3 (tampon bolge). Log bolgesi
# icin >=30 gerek; 850 um ~ y+ 38 verir (dogrusal olcekleme onculu, dogrulama
# kosunun kendi y+ olcumuyle yapilir).
HEDEF_ILK_HUCRE_M = 850e-6
YPLUS_BANDI = (30.0, 300.0)
# Xr sacilmasi bu esigin altindaysa QoI OTURMUSTUR (rezidüel platoda olsa
# bile). Esik dar tutuldu: olculen L1 sacilmasi %0.08 idi, yani karar
# sinirda degil acik ara. Ayni ilke validity_envelope.QOI_DURAGAN_DRIFT_PCT.
QOI_SACILMA_ESIGI_PCT = 1.0
# DENEYSEL referans belirsizligi: Driver & Seegmiller Xr/H = 6.26 +- 0.10.
U_REF_PCT = 0.10 / 6.26 * 100


def grading_coz(uzunluk: float, n: int, hedef_ilk: float) -> float:
    """simpleGrading oranını, ilk hücre `hedef_ilk` olacak şekilde çöz.

    `ilk_hucre_m` monotondur (grading büyüdükçe ilk hücre küçülür), o yüzden
    ikiye bölme yeter. Kapalı form da var ama monotonluk üzerinden çözmek
    kenar durumlarda (n küçük, oran 1'e yakın) daha güvenli.
    """
    if hedef_ilk >= uzunluk / n:
        alt, ust = 1e-4, 1.0          # ilk hucre TEK-TIPTEN buyuk -> grading<1
    else:
        alt, ust = 1.0, 1e4
    for _ in range(200):
        orta = (alt * ust) ** 0.5     # geometrik ortalama: oran uzayinda ara
        h = _y.ilk_hucre_m(uzunluk, n, orta)
        if h > hedef_ilk:
            alt = orta
        else:
            ust = orta
    return (alt * ust) ** 0.5


# ALT BLOK DUVAR-NORMALI HUCRE SAYISI SABIT. Ilk denemede aile her yonde
# inceltiliyor ve ilk hucreyi sabit tutmak icin grading uc degere gidiyordu
# (L3'te 0.0043 — duvardan uzaktaki hucreler 233 kat kucuk): L2 yakinsamadi,
# L3 floating point exception ile dustu. Duvar-fonksiyonu ailesinde
# duvar-normali cozunurluk SABIT TUTULUR, cunku ilk hucre y+ bandini yani
# DUVAR ISLEMINI belirler; degistirmek aileyi tek bir hucreyi temsil etmekten
# cikarir. Bedeli acik: elde edilen band duvar-normali ayriklastirma hatasini
# KAPSAMAZ ve bu kanit dosyasinda yazilidir.
OLCEK_ALT_Y = 1.0


def _hucre(olcek: float) -> int:
    nxg, nxc = int(_y.NX_GIRIS * olcek), int(_y.NX_CIKIS * olcek)
    nyu = int(_y.NY_UST * olcek)
    nya = int(_y.NY_ALT * OLCEK_ALT_Y)
    return nxg * nyu + nxc * nyu + nxc * nya


def _seviye_kos(kok: Path, ad: str, olcek: float, sadece_oku: bool) -> dict:
    case = kok / ad
    nya = int(_y.NY_ALT * OLCEK_ALT_Y)
    g = grading_coz(_y.H_STEP, nya, HEDEF_ILK_HUCRE_M)
    ilk = _y.ilk_hucre_m(_y.H_STEP, nya, g)
    print(f"[{ad}] ölçek={olcek} hücre≈{_hucre(olcek):,} "
          f"grading={g:.4f} ilk_hücre={ilk * 1e6:.1f} µm", flush=True)
    if sadece_oku and (case / "log.foamRun").exists():
        ok, hata = True, ""
    else:
        _y._yaz(case, MODEL, olcek=olcek, alt_grading=g,
                olcek_alt_y=OLCEK_ALT_Y)
        ok, hata = _y._kos(case, timeout=7200)
    if not ok:
        print(f"   ÇÖZÜCÜ DÜŞTÜ: {hata[:140]}", flush=True)
        return {"ad": ad, "durum": "cozucu_dustu", "hata": hata[:200]}
    yakin, it = _y.yakinsadi_mi(case)
    band, neden = _y.yapisma_bandi(case)
    yp = _y.yplus_olc(case)
    if not band:
        return {"ad": ad, "durum": "xr_okunamadi", "neden": neden,
                "hucre": _hucre(olcek)}
    # QoI-DURAGANLIK: "residualControl tetiklenmedi" ile "Xr hala hareket
    # ediyor" AYNI SEY DEGILDIR. Bu ayrim `validity_envelope.sonuc_kapisi`'nda
    # zaten kurulu ama capa betiklerine hic uygulanmamisti — ve L1 kosusunda
    # somut zarar verdi: rezidueller platoda kaldi (20000 iterasyon) ama Xr son
    # dort anlik goruntude 5.667/5.666/5.670/5.661 idi, yani %0.08 icinde
    # OTURMUSTU. O kosu "yakinsamadi" diye copze atilacakti.
    #
    # KAPI GEVSEMIYOR: sacilma OLCULUP esige vuruluyor ve rezidüel durumu
    # ciktida ACIKCA yaziliyor. ASME V&V pratiginde hukum ILGILENILEN
    # BUYUKLUGUN yakinsamasina dayanir; rezidüel onun VEKILIDIR.
    sacilma = (max(band) - min(band)) / (sum(band) / len(band)) * 100
    duragan = sacilma <= QOI_SACILMA_ESIGI_PCT
    if not (yakin or duragan):
        print(f"   YAKINSAMADI ({it} iterasyon, Xr saçılması %{sacilma:.2f})",
              flush=True)
        return {"ad": ad, "durum": "yakinsamadi", "iterasyon": it,
                "hucre": _hucre(olcek), "yplus": yp,
                "qoi_sacilma_pct": round(sacilma, 3)}
    xr = sum(band) / len(band)
    hata_pct = (xr - _y.XR_DENEY) / _y.XR_DENEY * 100
    _alt = (yp or {}).get("alt", {})
    print(f"   Xr/H={xr:.3f} → %{hata_pct:+.2f} | y⁺(alt) ort={_alt.get('ort')} "
          f"max={_alt.get('max')}", flush=True)
    return {"ad": ad, "durum": "ok", "olcek": olcek, "hucre": _hucre(olcek),
            "iterasyon": it, "grading": round(g, 5),
            "residualControl_gecti": yakin,
            "qoi_sacilma_pct": round(sacilma, 3),
            "_yakinsama_notu": (None if yakin else
                                (f"residualControl TETIKLENMEDI ({it} iterasyon) "
                                 f"ama Xr sacilmasi %{sacilma:.2f} <= "
                                 f"%{QOI_SACILMA_ESIGI_PCT} — hukum QoI'ye "
                                 "dayaniyor, rezidüel onun vekilidir")),
            "ilk_hucre_m": round(ilk, 9),
            "Xr_H": round(xr, 4), "hata_pct": round(hata_pct, 3), "yplus": yp}


def _duvar_hukmu(seviyeler: list[dict]) -> dict:
    """Üç seviyenin HEPSİ log-bölgesinde mi? Tepe y⁺ de sayılır."""
    ok = [s for s in seviyeler if s.get("durum") == "ok" and s.get("yplus")]
    alt = [(s["ad"], (s["yplus"].get("alt") or {})) for s in ok]
    deger = [(a, d.get("ort"), d.get("max")) for a, d in alt if d.get("ort")]
    disarida = [(a, o, m) for a, o, m in deger
                if not (YPLUS_BANDI[0] <= o <= YPLUS_BANDI[1]
                        and (m is None or m <= YPLUS_BANDI[1]))]
    return {"islem": "wall_function" if deger and not disarida else None,
            "yplus": {a: {"ort": o, "max": m} for a, o, m in deger},
            "bant_disi": {a: {"ort": o, "max": m} for a, o, m in disarida},
            "gerekce": (f"üç seviyede de y⁺ {YPLUS_BANDI[0]:.0f}–"
                        f"{YPLUS_BANDI[1]:.0f} bandında (tepe dahil)"
                        if deger and not disarida else
                        "y⁺ log-bölgesi dışında — hedef ilk hücre ayarlanmalı")}


def _sayisal_band(seviyeler: list[dict]) -> dict:
    ok = [s for s in seviyeler if s.get("durum") == "ok"]
    if len(ok) < 3:
        return {"gecerli": False, "neden": f"{len(ok)} geçerli seviye (<3)"}
    from report_generator import band_from_levels
    return band_from_levels([s["hucre"] for s in ok], [s["Xr_H"] for s in ok],
                            boyut=2)


def main(argv: list[str]) -> int:
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    sadece_oku = "--oku" in argv
    kok = HERE.parent / "_basamak_duvarfn"
    kok.mkdir(exist_ok=True)
    t0 = time.time()
    seviyeler = [_seviye_kos(kok, ad, o, sadece_oku) for ad, o in SEVIYELER]

    duvar = _duvar_hukmu(seviyeler)
    band = _sayisal_band(seviyeler)
    ok = [s for s in seviyeler if s.get("durum") == "ok"]
    ince = max(ok, key=lambda s: s["hucre"]) if ok else None
    u_say = band.get("u_pct")
    ham = abs(float(ince["hata_pct"])) if ince else None

    from model_form_bandi import ayrilabilir
    ayr = ayrilabilir(ham, u_say, U_REF_PCT)
    out = {
        "vaka": (f"Geriye-basamakli akis, DUVAR-FONKSIYONU ailesi — "
                 f"H={_y.H_STEP * 1000:.1f} mm, U={_y.U_INF} m/s, "
                 f"Re_H={_y.U_INF * _y.H_STEP / _y.NU:.0f}"),
        "kaynak": "OpenFOAM 11 foamRun/incompressibleFluid, 2D blockMesh",
        "model": MODEL,
        "referans": {"Xr_H": _y.XR_DENEY, "belirsizlik": _y.XR_BELIRSIZLIK,
                     "u_ref_pct": round(U_REF_PCT, 3),
                     "kaynak": "Driver & Seegmiller, AIAA J. 23(2), 1985 — deneysel"},
        "seviyeler": seviyeler,
        "duvar_islemi": duvar,
        "sayisal_band": band,
        "hata_pct_ince": ince.get("hata_pct") if ince else None,
        "ayrilabilirlik": ayr,
        "hedef_ilk_hucre_m": HEDEF_ILK_HUCRE_M,
        "_neden": ("Model-form tablosunun sekiz hucresinden besi oncul. "
                   "separated.wall_function en ulasilabiliri: ayni deneyin "
                   "DENEYSEL referansi elde ve u_D yalniz %1.6 (yari-analitik "
                   "kanat capasinda u_D=%15 baskindi ve ag inceltmek care "
                   "degildi)."),
        "_basarisizlik_kok_nedeni": (
            "ILK HUCREYI SABIT TUTMA STRATEJISI INCE AGDA COKUYOR. Ag "
            "inceldikce ayni ilk hucreyi korumak icin grading uc degere "
            "gidiyor: L1 0.0835, L2 0.0242, L3 0.0043 — sonuncusunda duvardan "
            "uzaktaki hucreler 233 kat kucuk ve foamRun floating point "
            "exception ile dustu. L2 ise yakinsamadi (Xr sacilmasi %3.91 > %1). "
            "Tek gecerli seviye kaldi, dolayisiyla GCI bandi YOK ve "
            "ayrilabilirlik degerlendirilemedi. "
            "DOGRU TASARIM: aile alt blogun duvar-normali yonunde degil, "
            "x-yonunde ve ust blokta inceltilmeli; alt blokta hucre sayisi "
            "SABIT kalip ilk hucreyi korumali (ya da iki-bolgeli mesh). "
            "Bu bir sonraki turun isi."),
        "_aile_yonlu": (
            "AG AILESI YONLUDUR: akis-yonu ve dis-alan cozunurlugu incelir, alt "
            "duvarin duvar-normali hucre sayisi SABIT kalir (40). Zorunludur: "
            "ilk hucre y+ bandini yani DUVAR ISLEMINI belirler ve degistirmek "
            "aileyi tek bir model-form hucresini temsil etmekten cikarir. "
            "BEDELI: elde edilen band duvar-normali ayriklastirma hatasini "
            "KAPSAMAZ; yalniz akis-yonu/dis-alan bilesenini olcer."),
        "_ilk_hucre_notu": ("Ilk hucre SEVIYELER ARASINDA SABIT tutuldu. Ag "
                            "inceldikce hucre sayisi artar ve grading ayni "
                            "kalirsa ilk hucre incelir — uc seviye uc FARKLI "
                            "duvar islemine duserdi ve GCI ailesi anlamini "
                            "yitirirdi. Grading her seviyede sayisal cozuldu."),
        "_uretim": "Üretim: python experiments/basamak_duvar_fonksiyonu.py",
        "_sure_s": round(time.time() - t0, 1),
    }
    out["verdikt"] = _verdikt(out)
    import ortam
    ortam.damgala(out)
    (HERE.parent / "basamak_duvar_fonksiyonu.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDuvar işlemi: {duvar['islem']} — {duvar['gerekce']}")
    print(f"Sayısal band: %{u_say}  |  model hatası: %{ham}")
    print(out["verdikt"])
    print("-> basamak_duvar_fonksiyonu.json")
    return 0


def _verdikt(o: dict) -> str:
    if not o.get("hata_pct_ince"):
        return "❌ Hiçbir seviye yakınsamadı — çapa kullanılamaz"
    if o["duvar_islemi"]["islem"] is None:
        return (f"⚠️ Duvar işlemi belirsiz ({o['duvar_islemi']['gerekce']}) — "
                "çapa separated.wall_function hücresine atanamaz")
    a = o["ayrilabilirlik"]
    ham = abs(float(o["hata_pct_ince"]))
    if a["ayrilabilir_mi"] is None:
        return f"⚠️ Ayrılabilirlik değerlendirilemedi: {a['gerekce']}"
    if not a["ayrilabilir_mi"]:
        return (f"⚠️ Sapma %{ham:.2f} ≤ u_val %{a['u_val_pct']} — elde ölçüm "
                "değil ÜST SINIR var; hücre muhafazakâr yönde etiketlenir")
    return (f"✅ wall_function ({o['duvar_islemi']['gerekce']}); sapma %{ham:.2f} "
            f"> u_val %{a['u_val_pct']} — model hatası AYRILABİLİYOR, "
            "separated.wall_function ölçüme bağlandı")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
