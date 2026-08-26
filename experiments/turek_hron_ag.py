"""Turek--Hron geometrisi ve 2B ağı — FSI çapasının ÖNKOŞULU.

NEDEN AYRI BİR BETİK. İki-yönlü FSI'nin önünde ölçülen yetenek engeli
kalmadı (NLGEOM ve `*DYNAMIC` eklendi ve doğrulandı) ama ``ulaşılabilir''
``koşuldu'' demek değildir. Koşmanın önündeki gerçek iş bu: kanonik
benchmark'ın AĞI. Bu depoda 2B vaka kuran tek desen elle yazılmış
`blockMeshDict`tir (`basamak_ayrilma.py`) ve orada geometri bir basamaktır;
burada silindir + ona tutturulmuş ince bir bayrak var.

GEOMETRİ (Turek \\& Hron 2006):
    kanal     [0, 2.5] x [0, 0.41] m
    silindir  merkez (0.2, 0.2), r = 0.05
    bayrak    x in [0.24897, 0.6], y in [0.19, 0.21]  (kalınlık 0.02)
Bayrak silindire, çemberin y = 0.2 +- 0.01 olduğu noktadan tutturulur:
    x_bas = 0.2 + sqrt(0.05^2 - 0.01^2) = 0.248990...

BU BETİK NE YAPAR, NE YAPMAZ. Geometriyi STL olarak üretir ve ağın
kurulabilirliğini ÖLÇER --- akış çözmez, sonuç üretmez. Ölçtüğü şey tek bir
soru: `snappyHexMesh` ince (tek hücreli) bir alanda ön/arka yüzleri
`empty` bırakıyor mu, yani bu depo 2B gövde-etrafı ağ kurabiliyor mu?
Cevap hayırsa FSI çapası bu yoldan ULAŞILAMAZ ve bunu ÖNCE bilmek gerekir.

    python experiments/turek_hron_ag.py
Çıktı: turek_hron_ag.json + turek_hron.stl
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "turek_hron_ag.json"
STL = KOK / "turek_hron.stl"

# GEOMETRI --- benchmark tanimindan, yuvarlanmadan.
KANAL_L, KANAL_H = 2.5, 0.41
MERKEZ = (0.2, 0.2)
YARICAP = 0.05
BAYRAK_KALINLIK = 0.02
BAYRAK_SON_X = 0.6
# Kalinlik z yonunde: 2B icin TEK hucre. Deger kanal yuksekliginin
# yaninda kucuk kalmali ama snappy'nin cozebilecegi kadar buyuk.
Z_KALINLIK = 0.01
# Cember ayriklastirmasi: bayragin kalinligindan ince olmali, yoksa
# tutturma noktasi geometrik olarak kayar.
CEMBER_N = 200


def bayrak_bas_x() -> float:
    """Bayrağın silindire tutturulduğu x --- ÇEMBERDEN türetilir."""
    return MERKEZ[0] + math.sqrt(YARICAP**2 - (BAYRAK_KALINLIK / 2) ** 2)


def govde_kesiti() -> np.ndarray:
    """Silindir + bayrak birleşiminin 2B kapalı konturu (N,2).

    Bayrak silindire GOMULUR (tutturma noktasindan baslar) --- iki parcayi
    ayri STL olarak vermek, snappy'nin aralarinda ince bir yarik gormesine
    ve orayi hucrelerle doldurmasina yol acardi.
    """
    y0 = MERKEZ[1] - BAYRAK_KALINLIK / 2
    y1 = MERKEZ[1] + BAYRAK_KALINLIK / 2
    xb = bayrak_bas_x()
    # Cember: bayragin USTTEN ciktigi acidan ALTTAN girdigi aciya kadar
    # SAAT YONUNUN TERSINE (yani bayragin arkasindan dolasarak).
    a0 = math.atan2(y1 - MERKEZ[1], xb - MERKEZ[0])       # ust tutturma
    a1 = math.atan2(y0 - MERKEZ[1], xb - MERKEZ[0])       # alt tutturma
    if a1 < a0:
        a1 += 2 * math.pi
    acilar = np.linspace(a0, a1, CEMBER_N)
    cember = np.column_stack([MERKEZ[0] + YARICAP * np.cos(acilar),
                              MERKEZ[1] + YARICAP * np.sin(acilar)])
    # Bayrak: alt tutturmadan uca, uctan ust tutturmaya.
    bayrak = np.array([[BAYRAK_SON_X, y0], [BAYRAK_SON_X, y1]])
    return np.vstack([cember, bayrak])


def stl_yaz(yol: Path) -> dict:
    """2B konturu z yönünde ekstrüde edip su-geçirmez STL yaz.

    `extrude_polygon` KULLANILIR, elle üçgenleme DEĞİL. İlk sürüm yan
    yüzeyleri ve kapakları kendisi kuruyordu ve kapaklar için
    `triangulate_polygon(engine="triangle")` çağırıyordu --- o paket bu
    ortamda kurulu değil ve betik düştü. Daha önemlisi: kontur DIŞBÜKEY
    DEĞİL (bayrak çıkıntılı), yani elle üçgenleme kolayca bayrağın dışına
    taşan yüzler üretir ve bu SESSİZ olur --- hacim denetimi olmasa
    görülmezdi.
    """
    import trimesh
    from shapely.geometry import Polygon
    from trimesh.creation import extrude_polygon

    kesit = govde_kesiti()
    poligon = Polygon(kesit)
    if not poligon.is_valid:
        return {"uretildi": False,
                "neden": f"kontur geçersiz: {poligon.is_valid_reason}"}
    mesh = extrude_polygon(poligon, height=Z_KALINLIK)
    mesh.export(yol)
    return {"uretildi": True,
            "dugum": int(len(mesh.vertices)), "ucgen": int(len(mesh.faces)),
            "su_gecirmez": bool(mesh.is_watertight),
            "hacim_m3": float(mesh.volume),
            "kontur_alani_m2": float(poligon.area),
            "sinirlar": [[float(x) for x in mesh.bounds[0]],
                         [float(x) for x in mesh.bounds[1]]]}


def _beklenen_hacim() -> float:
    """Analitik: BİRLEŞİM alanı x kalınlık --- örtüşme GERÇEKTEN çıkarılır.

    REFERANS ÖNCE DÜZELTİLDİ. İlk sürüm `daire + dikdörtgen` yazıyordu ve
    yorumu ``örtüşme çıkarılarak'' diyordu --- kod bunu YAPMIYORDU. Hacim
    denetimi %-0,098 sapma gösterdi ve sebebi geometri sanıldı; ölçülünce
    sapmanın kaynağı REFERANSIN KENDİSİ çıktı.

    Örtüşme, çemberin x = x_bas kirişinin SAĞINDA kalan dairesel dilimdir
    ve o bölge dikdörtgenin içindedir, yani iki kez sayılıyordu:
        A_dilim = r^2 * acos(d/r) - d * sqrt(r^2 - d^2),   d = x_bas - cx
    """
    xb = bayrak_bas_x()
    d = xb - MERKEZ[0]
    a_daire = math.pi * YARICAP**2
    a_bayrak = (BAYRAK_SON_X - xb) * BAYRAK_KALINLIK
    a_dilim = (YARICAP**2 * math.acos(d / YARICAP)
               - d * math.sqrt(max(YARICAP**2 - d**2, 0.0)))
    return (a_daire + a_bayrak - a_dilim) * Z_KALINLIK


def olc() -> dict:
    try:
        stl = stl_yaz(STL)
    except Exception as e:                      # noqa: BLE001
        return _ozetle({"uretildi": False,
                        "neden": f"{type(e).__name__}: {e}"[:250]}, None)
    if not stl.get("uretildi"):
        return _ozetle(stl, None)
    bekl = _beklenen_hacim()
    stl["beklenen_hacim_m3"] = bekl
    stl["hacim_hatasi_pct"] = round(100 * (stl["hacim_m3"] - bekl) / bekl, 3)
    stl["uretildi"] = True
    return _ozetle(stl, bekl)


def _ozetle(stl: dict, bekl) -> dict:
    tamam = (stl.get("uretildi") and stl.get("su_gecirmez")
             and abs(stl.get("hacim_hatasi_pct", 100)) < 1.0)
    return {
        "vaka": "Turek-Hron geometrisi — FSI çapasının önkoşulu",
        "_neden": ("Iki-yonlu FSI'nin onunde olculen YETENEK engeli kalmadi "
                   "ama 'ulasilabilir' 'kosuldu' demek degil. Kosmanin "
                   "onundeki gercek is kanonik benchmark'in AGI."),
        "geometri": {
            "kanal_L_m": KANAL_L, "kanal_H_m": KANAL_H,
            "silindir_merkez": list(MERKEZ), "silindir_r_m": YARICAP,
            "bayrak_kalinlik_m": BAYRAK_KALINLIK,
            "bayrak_bas_x_m": round(bayrak_bas_x(), 6),
            "bayrak_son_x_m": BAYRAK_SON_X,
            "bayrak_L_m": round(BAYRAK_SON_X - bayrak_bas_x(), 6),
            "z_kalinlik_m": Z_KALINLIK,
            "_not": ("bayrak_bas_x CEMBERDEN turetilir: "
                     "0.2 + sqrt(0.05^2 - 0.01^2)"),
        },
        "stl": stl,
        "geometri_dogru_mu": bool(tamam),
        "verdikt": _hukum(stl, tamam),
        "_kisit": (
            "BU BETIK AKIS COZMEZ ve SONUC URETMEZ. Yalnizca geometriyi "
            "uretip kendi icinde dogrular (su-gecirmezlik ve ANALITIK "
            "hacimle karsilastirma). Agin snappy ile kurulabilirligi ve "
            "on/arka yuzlerin 'empty' kalmasi AYRI bir adimdir ve burada "
            "SINANMADI. Referans degerler (FSI1: ux=0,0227 mm, uy=0,8209 mm) "
            "bu depoda BIRINCIL KAYNAKTAN DOGRULANMADI."),
        "_uretim": "Üretim: python experiments/turek_hron_ag.py",
    }


def _hukum(stl: dict, tamam) -> str:
    if not stl.get("uretildi"):
        return f"GEOMETRİ ÜRETİLEMEDİ: {stl.get('neden')}"
    s = (f"STL üretildi: {stl['ucgen']} üçgen, su-geçirmez="
         f"{stl['su_gecirmez']}. Hacim {stl['hacim_m3']:.6e} m³, "
         f"analitik beklenen {stl['beklenen_hacim_m3']:.6e} m³ "
         f"--- fark %{stl['hacim_hatasi_pct']}. ")
    if not stl["su_gecirmez"]:
        return s + ("SU-GEÇİRMEZ DEĞİL: snappyHexMesh kapalı olmayan bir "
                    "yüzeyde gövde-içi/dışı ayrımı yapamaz. Ağ kurulamaz.")
    if abs(stl["hacim_hatasi_pct"]) >= 1.0:
        return s + ("HACİM ANALİTİKTEN SAPIYOR: kontur yanlış kapanmış ya da "
                    "kapaklar üçgenlemesi taşmış olabilir --- geometri "
                    "benchmark'ı temsil etmiyor.")
    return s + ("Geometri kendi içinde tutarlı. AĞ ADIMI HENÜZ SINANMADI: "
                "snappy'nin ince alanda ön/arka yüzleri `empty` bırakıp "
                "bırakmadığı ayrı bir ölçümdür ve FSI çapasının gerçek "
                "kapısı odur.")


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
