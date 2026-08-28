"""Lineer statik NE ZAMAN yetmez --- eşiği ALINTIYLA değil ÖLÇÜMLE kur.

NEDEN. NLGEOM arayüze taşınacak ve kullanıcıya "ne zaman açmalıyım"
sorusunun bir cevabı gerekiyor. Literatürden bir sayı ("δ/L > %5") almak
kolaydı; ama bu depo o cümleyi kendi ağıyla, kendi çözücüsüyle ve kendi
eleman tipiyle sınamadan yazmamalı --- aynı eşik C3D10 ile C3D4'te ya da
farklı kesit oranında aynı yerde durmayabilir.

CSM1 bu ölçümü ucuza verir: yapı, yerçekimi, akış yok, yayımlanmış NLGEOM
cevabı elde. Yerçekimini süpürünce δ/L bir bant tarar ve her noktada
lineer çözüm NLGEOM'a karşı ölçülür. Bir çift 10 saniye sürer.

ÖLÇÜLEN ŞEY İKİ AYRI NİCELİK VE İKİSİ AYNI CEVABI VERMİYOR:

  uy (enine sehim)   --- lineer teori BURADA ŞAŞIRTICI ÖLÇÜDE AFFEDİCİ.
  ux (eksenel kısalma) --- lineer teoride MERTEBE OLARAK YOK: enine yüklü
                           bir konsolun ucu ikinci mertebeden kısalır
                           (0,6 uy^2/L) ve lineer kinematik bu terimi
                           tanımlamaz. Sapma δ/L'den bağımsız olarak ~%100.

Yani "δ/L şu eşiği aşarsa NLGEOM aç" tek başına YANLIŞ bir kuraldır:
sehim küçükken bile eksenel yol tümüyle yanlıştır. Doğru kural niceliğe
bağlıdır ve kapı bunu söylemek zorunda.

KAPSAM SINIRI --- BU EĞRİ ELVERİŞLİ (İYİMSER) TARAFTIR. CSM1 konsolu
eksenel SERBEST uçludur; kısalma serbestçe gerçekleşir ve zar (membran)
sertleşmesi doğmaz. İki ucu eksenel tutulu bir yapıda aynı kısalma
engellenir, eksenel çekme doğar ve yapı belirgin biçimde sertleşir ---
orada lineer çözüm bu banttan ÇOK ÖNCE bozulur. Buradan çıkan eşik bir
ALT SINIRDIR, güvenli taraf değil.

    python experiments/buyuk_yer_degistirme_esigi.py
Çıktı: buyuk_yer_degistirme_esigi.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

from turek_hron_ag import BAYRAK_SON_X, bayrak_bas_x  # noqa: E402
from turek_hron_csm1 import _kos  # noqa: E402

CIKTI = KOK / "buyuk_yer_degistirme_esigi.json"

# Yercekimi supurmesi: CSM1'in kendi degeri (2,0) bandin ust ucunda kalsin
# ki yayimlanmis capa supurmenin ICINDE olsun ve egri ona baglanabilsin.
G_MERDIVEN = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0)


def _sapma_pct(lineer: float, nl: float) -> float | None:
    """Lineerin NLGEOM'a gore BAGIL sapmasi. Payda NLGEOM (dogru kabul
    edilen); NLGEOM sifira giderse oran anlamsizlasir, o yuzden None.

    YUVARLAMA 6 ONDALIK, 3 DEGIL. Ilk surumde 3 ondaliktaydi ve bandin alt
    ucunda sapma -0,002 cikiyordu: IKI kuantum. Kare-yasasinin artigi orada
    %6,9 olcuLdu ve yasa "tutmuyor" hukmu aldi --- oysa olculen sey fizik
    degil KENDI CIKTI COZUNURLUGUMDU. Yuvarlama bir olcum aletidir; band
    genisledikce onunla birlikte genisletilmeli.
    """
    if abs(nl) < 1e-9:
        return None
    return round(100.0 * (lineer - nl) / abs(nl), 6)


def olc() -> dict:
    L_mm = (BAYRAK_SON_X - bayrak_bas_x()) * 1000.0
    noktalar = []
    for g in G_MERDIVEN:
        lin = _kos(nlgeom=False, g=g)
        nl = _kos(nlgeom=True, g=g)
        if not (lin.get("kosdu") and nl.get("kosdu")):
            noktalar.append({"g_m_s2": g, "kosdu": False,
                             "neden": lin.get("neden") or nl.get("neden")})
            continue
        noktalar.append({
            "g_m_s2": g, "kosdu": True,
            "uy_lineer_mm": round(lin["uy_mm"], 5),
            "uy_nlgeom_mm": round(nl["uy_mm"], 5),
            "ux_lineer_mm": round(lin["ux_mm"], 6),
            "ux_nlgeom_mm": round(nl["ux_mm"], 6),
            # delta/L NLGEOM'dan olculur --- lineer sehim kendisi sapmali,
            # onu eksen yapmak egriyi kendi hatasiyla carpitirdi.
            "delta_L_pct": round(100.0 * abs(nl["uy_mm"]) / L_mm, 4),
            "uy_sapma_pct": _sapma_pct(lin["uy_mm"], nl["uy_mm"]),
            "ux_sapma_pct": _sapma_pct(lin["ux_mm"], nl["ux_mm"]),
        })
    return _ozetle(L_mm, noktalar)


def _esik_ara(noktalar: list[dict], anahtar: str, tavan_pct: float):
    """En buyuk delta/L ki sapma HALA tavanin altinda. Merdiven kabaysa
    bu bir ARALIK'tir; tek sayi gibi sunmak cozunurlugun ustunde bir
    kesinlik iddia ederdi."""
    iyi = [n for n in noktalar if n.get("kosdu")
           and n.get(anahtar) is not None and abs(n[anahtar]) <= tavan_pct]
    kotu = [n for n in noktalar if n.get("kosdu")
            and n.get(anahtar) is not None and abs(n[anahtar]) > tavan_pct]
    if not iyi:
        return {"durum": "hicbir nokta tavanin altinda degil",
                "tavan_pct": tavan_pct}
    if not kotu:
        return {"durum": "supurmenin TAMAMI tavanin altinda — esik bandin "
                         "USTUNDE, bu merdivenle olculemez",
                "tavan_pct": tavan_pct,
                "en_buyuk_sinanan_delta_L_pct": max(n["delta_L_pct"]
                                                    for n in iyi)}
    return {"durum": "olculdu", "tavan_pct": tavan_pct,
            "son_gecen_delta_L_pct": max(n["delta_L_pct"] for n in iyi),
            "ilk_kalan_delta_L_pct": min(n["delta_L_pct"] for n in kotu)}


def _hukum_metni(yasa: dict, eksenel: dict, noktalar: list[dict]) -> str:
    """HUKUM SAYILARDAN KURULUR, ELLE YAZILMAZ. Bu depoda rapor gerekcesi
    bir kez kanittan koparilmis ve kanit yenilendiginde sessizce eskimisti;
    burada cumle her kosuda olculen degerlerden yeniden dogar."""
    kosan = [n for n in noktalar if n.get("kosdu")]
    if not kosan:
        return "❌ KALDI: süpürmenin hiçbir noktası koşmadı."
    band = (f"δ/L %{min(n['delta_L_pct'] for n in kosan):.2g}–"
            f"%{max(n['delta_L_pct'] for n in kosan):.3g}")
    if not yasa.get("tutuyor"):
        return (f"⚠️ Güç yasası {band} bandında TUTMADI (en kötü artık "
                f"%{100 * yasa.get('en_kotu_bagil_artik', 0):.1f}); eşik "
                "uydurmadan türetilemez, merdiven aralığı kullanılmalı.")
    parcalar = [
        f"✅ {band} bandında enine sehim sapması "
        f"{yasa['katsayi']:.4g}·(δ/L)^{yasa['us']:.3g} yasasını izliyor "
        f"(en kötü artık %{100 * yasa['en_kotu_bagil_artik']:.1f}); üstel "
        "ölçüldü, varsayılmadı. %1 hata için eşik "
        f"δ/L = %{yasa['delta_L_esik_1pct']:.3g}."]
    if eksenel.get("olculdu") and eksenel.get("esikten_bagimsiz"):
        parcalar.append(
            f"Eksenel kısalma ise bandın TAMAMINDA %"
            f"{eksenel['ux_sapma_min_pct']:.4g}–"
            f"%{eksenel['ux_sapma_maks_pct']:.4g} yanlış ve eşikten bağımsız: "
            "lineer kinematikte ikinci-mertebe kısalma terimi yoktur.")
    parcalar.append(
        "Konsol ekseninde SERBEST uçludur (zar sertleşmesi yok); eksenel "
        "tutulu yapıda bu eşik geçmez, ALT SINIRDIR.")
    return " ".join(parcalar)


def _ozetle(L_mm: float, noktalar: list[dict]) -> dict:
    yasa = _uy_yasasi(noktalar)
    eksenel = _eksenel_hukum(noktalar)
    return {
        "vaka": "CSM1 konsolu — yerçekimi süpürmesi, lineer vs NLGEOM",
        "uretim": ("Üretim: python experiments/buyuk_yer_degistirme_esigi.py"),
        "sonuc": _hukum_metni(yasa, eksenel, noktalar),
        "_neden": ("NLGEOM arayuze tasiniyor; 'ne zaman ac' sorusunun "
                   "cevabi bu depoda ALINTI degil OLCUM olmali."),
        "_kapsam_siniri": ("Konsol ekseninde SERBEST uctur — zar sertlesmesi "
                           "yok. Eksenel TUTULU bir yapida lineer cozum bu "
                           "banttan cok once bozulur; buradaki esik bir ALT "
                           "SINIRDIR."),
        "L_mm": round(L_mm, 3),
        "noktalar": noktalar,
        "esik_uy_1pct": _esik_ara(noktalar, "uy_sapma_pct", 1.0),
        "esik_uy_5pct": _esik_ara(noktalar, "uy_sapma_pct", 5.0),
        "eksenel_hukum": eksenel,
        "uy_yasasi": yasa,
    }


def _uy_yasasi(noktalar: list[dict]) -> dict:
    """Sapma-delta/L iliskisinin USTELI OLCULUR, varsayilmaz.

    Ikinci mertebe kinematik us=2 bekletir; ama bekleyis kanit degildir ve
    ag/eleman tipi bunu bozabilirdi. log-log egimi olculur, ardindan
    ARTIK da raporlanir --- yasa tutmuyorsa esigi ondan turetmek yanlis
    olur ve kapi bu durumda merdiven araligina duser.
    """
    import math

    d = [n for n in noktalar if n.get("kosdu") and n.get("uy_sapma_pct")
         and abs(n["uy_sapma_pct"]) > 1e-9]
    if len(d) < 3:
        return {"olculdu": False, "neden": "yeterli nokta yok"}
    x = [math.log(n["delta_L_pct"]) for n in d]
    y = [math.log(abs(n["uy_sapma_pct"])) for n in d]
    n_ = len(d)
    xm, ym = sum(x) / n_, sum(y) / n_
    sxx = sum((a - xm) ** 2 for a in x)
    us = sum((a - xm) * (b - ym) for a, b in zip(x, y)) / sxx
    lnc = ym - us * xm
    c = math.exp(lnc)
    artik = max(abs(math.exp(lnc + us * a) - math.exp(b)) / math.exp(b)
                for a, b in zip(x, y))
    tutuyor = artik < 0.05
    out = {"olculdu": True, "n": n_, "us": round(us, 4),
           "katsayi": round(c, 6), "en_kotu_bagil_artik": round(artik, 4),
           "tutuyor": tutuyor,
           "_bicim": "uy_sapma_pct = katsayi * (delta_L_pct ** us)"}
    if tutuyor:
        for tavan in (1.0, 5.0):
            out[f"delta_L_esik_{tavan:g}pct"] = round(
                (tavan / c) ** (1.0 / us), 3)
    return out


def _eksenel_hukum(noktalar: list[dict]) -> dict:
    """ux'in esikten BAGIMSIZ oldugu iddiasinin sinavi. Iddia dogruysa
    sapma butun bantta ~%100 kalir ve delta/L ile ANLAMLI bicimde
    degismez."""
    d = [n for n in noktalar if n.get("kosdu") and n.get("ux_sapma_pct")
         is not None]
    if len(d) < 3:
        return {"olculdu": False, "neden": "yeterli nokta yok"}
    s = [abs(n["ux_sapma_pct"]) for n in d]
    return {"olculdu": True, "n": len(d),
            "ux_sapma_min_pct": round(min(s), 3),
            "ux_sapma_maks_pct": round(max(s), 3),
            "delta_L_bandi_pct": [min(n["delta_L_pct"] for n in d),
                                  max(n["delta_L_pct"] for n in d)],
            "esikten_bagimsiz": bool(min(s) > 90.0)}


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    ozet = olc()
    CIKTI.write_text(json.dumps(ozet, indent=2, ensure_ascii=False),
                     encoding="utf-8")
    for n in ozet["noktalar"]:
        if not n.get("kosdu"):
            print(f"  g={n['g_m_s2']:<5g} KOŞMADI — {n.get('neden')}")
            continue
        print(f"  g={n['g_m_s2']:<5g} δ/L={n['delta_L_pct']:6.2f}%   "
              f"uy sapma {n['uy_sapma_pct']:+7.3f}%   "
              f"ux sapma {n['ux_sapma_pct']:+8.2f}%")
    print(f"\nuy %1 tavani : {ozet['esik_uy_1pct']}")
    print(f"uy %5 tavani : {ozet['esik_uy_5pct']}")
    print(f"eksenel      : {ozet['eksenel_hukum']}")
    print(f"\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
