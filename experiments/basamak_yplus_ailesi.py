"""Geriye-basamak çapasını DUVAR-ÇÖZÜNÜR banda taşıyan ağ ailesi.

NEDEN: `model_form_bandi` tablosunda `separated` rejimi hiç ölçülmemişti. Tek
çapa (Driver & Seegmiller, kOmegaSST) vardı ve hiçbir duvar-işlemi hücresine
atanamıyordu: hüküm yaması `alt` üzerinde y⁺ ortalaması 14{,}3, tepesi 16{,}8 —
tampon bölge. Orada log-yasası geçerli değildir, duvar-çözünürlük de yoktur;
yani ölçüm bir hücreye ait DEĞİLDİR.

Kusur mesh dağılımındaydı, çözünürlükte değil: alt blok duvar-normali yönde
tek-tipti (grading 1). Duvara doğru sıkıştırma, hücre sayısını artırmadan ilk
hücreyi inceltir. Bu betik aynı çapayı üç ağ seviyesinde duvar-çözünür
kurulumla koşar; üç seviye hem y⁺ bandını hem de Richardson/LSR ayrıklaştırma
bandını verir --- çapanın atanabilmesi için ikisi de gerekir (model hatası
sayısal banttan büyük olmalı, yoksa elde ölçüm değil üst sınır vardır).

ÖZGÜN ÇAPA KORUNUR: `basamak_ayrilma.json` bu betikçe hiç yazılmaz. Çıktı ayrı
dosyadır ve iki kayıt yan yana durur --- aynı vaka, iki duvar işlemi.

    python experiments/basamak_yplus_ailesi.py           # üç seviye
    python experiments/basamak_yplus_ailesi.py --oku     # diskteki çözümü oku

Çıktı: basamak_yplus_ailesi.json (kanıt)
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

# Seviye: (ad, olcek). Hucre ~ olcek^2 ile buyur; r ~ 1.4 GCI icin yeterli.
SEVIYELER = [("L1_kaba", 1.0), ("L2_orta", 1.4), ("L3_ince", 2.0)]
ALT_GRADING = 20.0          # alt duvarda son/ilk hucre orani
MODEL = "kOmegaSST"
Y_DUVAR_COZUNUR = 5.0


def _hucre_sayisi(olcek: float) -> int:
    nxg, nxc = int(_y.NX_GIRIS * olcek), int(_y.NX_CIKIS * olcek)
    nyu, nya = int(_y.NY_UST * olcek), int(_y.NY_ALT * olcek)
    return nxg * nyu + nxc * nyu + nxc * nya


def _seviye_kos(kok: Path, ad: str, olcek: float, sadece_oku: bool) -> dict:
    case = kok / ad
    print(f"[{ad}] ölçek={olcek} hücre≈{_hucre_sayisi(olcek):,}", flush=True)
    if sadece_oku and (case / "log.foamRun").exists():
        ok, hata = True, ""
    else:
        _y._yaz(case, MODEL, olcek=olcek, alt_grading=ALT_GRADING)
        ok, hata = _y._kos(case, timeout=7200)
    if not ok:
        print(f"   ÇÖZÜCÜ DÜŞTÜ: {hata[:140]}", flush=True)
        return {"ad": ad, "durum": "cozucu_dustu", "hata": hata[:200]}
    yakin, it = _y.yakinsadi_mi(case)
    band, neden = _y.yapisma_bandi(case)
    yp = _y.yplus_olc(case)
    nya = int(_y.NY_ALT * olcek)
    ilk = _y.ilk_hucre_m(_y.H_STEP, nya, ALT_GRADING)
    if not yakin:
        print(f"   YAKINSAMADI ({it} iterasyon) — veri sayılmıyor", flush=True)
        return {"ad": ad, "durum": "yakinsamadi", "iterasyon": it,
                "hucre": _hucre_sayisi(olcek), "yplus": yp,
                "_not": "residualControl saglanmadi — HUKME GIRMEZ"}
    if not band:
        return {"ad": ad, "durum": "xr_okunamadi", "neden": neden,
                "iterasyon": it, "hucre": _hucre_sayisi(olcek)}
    xr = sum(band) / len(band)
    hata_pct = (xr - _y.XR_DENEY) / _y.XR_DENEY * 100
    print(f"   Xr/H = {xr:.3f} (deney {_y.XR_DENEY}) → hata %{hata_pct:+.2f}"
          f"  | y⁺(alt) ort={(yp or {}).get('alt', {}).get('ort')} "
          f"max={(yp or {}).get('alt', {}).get('max')}", flush=True)
    return {"ad": ad, "durum": "ok", "olcek": olcek,
            "hucre": _hucre_sayisi(olcek), "iterasyon": it,
            "ilk_hucre_m": round(ilk, 9), "alt_grading": ALT_GRADING,
            "Xr_H": round(xr, 4), "Xr_H_anliklar": [round(v, 4) for v in band],
            "hata_pct": round(hata_pct, 3), "yplus": yp}


def _duvar_hukmu(seviyeler: list[dict]) -> dict:
    """Üç seviyenin HEPSİ duvar-çözünür bantta mı? Tepe y⁺ de sayılır.

    Ortalama bantta olup tepesi dışarıda kalan koşu, duvarın bir bölümünde
    hiçbir zaman çözünür değildir — Ahmed 25° çapası tam bu yüzden elendi.
    """
    ok = [s for s in seviyeler if s.get("durum") == "ok" and s.get("yplus")]
    alt = [(s["ad"], s["yplus"].get("alt", {})) for s in ok]
    tepe = [(a, d.get("max")) for a, d in alt if d.get("max") is not None]
    disarida = [(a, m) for a, m in tepe if m > Y_DUVAR_COZUNUR]
    return {"islem": "wall_resolved" if tepe and not disarida else None,
            "tepe_yplus": dict(tepe),
            "bant_disi": dict(disarida),
            "gerekce": ("üç seviyede de tepe y⁺ ≤ %.1f — duvar-çözünür"
                        % Y_DUVAR_COZUNUR if tepe and not disarida else
                        "tepe y⁺ bandı aşıyor: duvarın bir bölümü çözünür değil")}


def _sayisal_band(seviyeler: list[dict]) -> dict:
    """Xr üzerinden ayrıklaştırma bandı (Richardson + LSR).

    2B ağ: h ~ N^(-1/2). Band, model hatasıyla KARŞILAŞTIRILMAK için gerekli;
    model hatası bandın altındaysa elde ölçüm değil ÜST SINIR vardır.
    """
    ok = [s for s in seviyeler if s.get("durum") == "ok"]
    if len(ok) < 3:
        return {"gecerli": False, "neden": f"{len(ok)} geçerli seviye (<3)"}
    from report_generator import band_from_levels
    cells = [s["hucre"] for s in ok]
    xr = [s["Xr_H"] for s in ok]
    return band_from_levels(cells, xr, boyut=2)


def _verdikt(ince: dict | None, duvar: dict, band: dict) -> str:
    """Kanıtın hükmü. Ölçülen model hatası büyük olabilir ve bu bir BAŞARISIZLIK
    değildir --- ölçülmek istenen zaten odur. Hükmün sınadığı şey vakanın
    ATANABİLİR olup olmadığıdır: duvar işlemi belirli mi, ve sapma kendi
    ayrıklaştırma bandından ayırt edilebiliyor mu."""
    if not ince:
        return "❌ Hiçbir seviye yakınsamadı — çapa kullanılamaz"
    if duvar.get("islem") is None:
        return (f"⚠️ Duvar işlemi belirsiz ({duvar.get('gerekce')}) — çapa hâlâ "
                "hiçbir model-form hücresine atanamaz")
    u = band.get("u_pct")
    h = abs(float(ince["hata_pct"]))
    if u is None:
        return (f"⚠️ Ayrıklaştırma bandı hesaplanamadı ({band.get('neden')}) — "
                f"sapma %{h:.2f} ölçüm mü sayısal gürültü mü AYIRT EDİLEMEZ")
    if h <= u:
        return (f"⚠️ Sapma %{h:.2f} ≤ ayrıklaştırma bandı %{u} — elde ölçüm değil "
                "ÜST SINIR var; model hatası sayısaldan ayrılamıyor")
    return (f"✅ {duvar['islem']} ({duvar['gerekce']}); sapma %{h:.2f} > "
            f"ayrıklaştırma bandı %{u} — model hatası sayısal hatadan AYRILABİLİYOR, "
            f"separated rejimi ölçüme bağlandı (Xr/H={ince['Xr_H']}, deney 6.26)")


def main(argv: list[str]) -> int:
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    sadece_oku = "--oku" in argv
    kok = HERE.parent / "_basamak_yplus"
    kok.mkdir(exist_ok=True)
    t0 = time.time()
    seviyeler = [_seviye_kos(kok, ad, o, sadece_oku) for ad, o in SEVIYELER]

    duvar = _duvar_hukmu(seviyeler)
    band = _sayisal_band(seviyeler)
    ok = [s for s in seviyeler if s.get("durum") == "ok"]
    ince = ok[-1] if ok else None
    out = {
        "vaka": (f"Geriye-basamakli akis (DUVAR-COZUNUR aile) — H={_y.H_STEP * 1000:.1f} mm, "
                 f"U={_y.U_INF} m/s, Re_H={_y.U_INF * _y.H_STEP / _y.NU:.0f}"),
        "kaynak": "OpenFOAM 11 foamRun/incompressibleFluid, 2D blockMesh",
        "model": MODEL,
        "referans": {"Xr_H": _y.XR_DENEY, "belirsizlik": _y.XR_BELIRSIZLIK,
                     "kaynak": "Driver & Seegmiller, AIAA J. 23(2), 1985 — deneysel"},
        "seviyeler": seviyeler,
        "duvar_islemi": duvar,
        "sayisal_band": band,
        "hata_pct_ince": ince.get("hata_pct") if ince else None,
        "verdikt": _verdikt(ince, duvar, band),
        "_neden": ("Ozgun capa (basamak_ayrilma.json) alt duvarda y+ 14.3 ile TAMPON "
                   "bolgedeydi ve hicbir duvar-islemi hucresine atanamiyordu. Kusur "
                   "cozunurlukte degil DAGILIMDA idi: alt blok duvar-normali yonde "
                   "tek-tipti. Duvara sikistirma (grading 20) hucre sayisini "
                   "artirmadan ilk hucreyi inceltir."),
        "_ozgun_capa": "basamak_ayrilma.json — DEGISTIRILMEDI; iki kayit yan yana durur",
        "_uretim": "Üretim: python experiments/basamak_yplus_ailesi.py",
        "_sure_s": round(time.time() - t0, 1),
    }
    (HERE.parent / "basamak_yplus_ailesi.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDuvar işlemi: {duvar['islem']} — {duvar['gerekce']}")
    print(f"Sayısal band: {band}")
    print(f"İnce seviye model hatası: %{out['hata_pct_ince']}")
    print("-> basamak_yplus_ailesi.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
