"""Alıcı (FEA) yüzey CFD yükünü taşıyabiliyor mu --- ÜRETİM YOLUNDA ölçülür.

NEDEN BU BETIK. Dış hakem "FSI Receiver Mesh Adequacy" istedi ve gerekçe
olarak iş-ayrışımındaki yüzey payını (en kötü %78,6) gösterdi. Depodaki
kayıt ise yüzey payının "eski şemadan gelen, üretim yolunda BULUNMAYAN"
bir fark olduğunu söylüyordu. İkisi birden doğru olamaz.

Bakınca ortaya ÜÇÜNCÜ bir şey çıktı: depoda İKİ ayrı üretim yolu var ve
farklı eşleme şemaları kullanıyorlar.

  `coupling_fsi`   (FSI sürücüsü)  --- korunumlu: CFD yüzünde hesaplanan
                                       KUVVET baryzentrik ağırlıklarla FEA
                                       düğümlerine dağıtılır. Toplam kuvvet
                                       kimlik olarak korunur.
  `vehicle_fea`    (araç akışı)    --- en yakın CFD hücresinin BASINCINI
                                       alır ve kuvveti FEA yüzeyinin KENDİ
                                       alanı ve normaliyle YENIDEN INTEGRE
                                       eder.

İkincisi tam olarak "eski/tutarlı" şemadır; deponun kendi ölçümü
(`fsi_esleme_kiyasi`) onu 24/24 vakada momentte daha kötü bulmuş ve
kuvvet hatasının ALAN FARKINI izlediğini söylemişti. Yani yüzey payı
araç yolunda GERÇEK bir üretim hatasıdır --- "üretim yolunda yoktur"
cümlesi yalnız FSI sürücüsü için doğru.

BU BETİK ÇIKARIM YAPMAZ, ÖLÇER. Her koşuda aynı basınç alanından iki
kuvvet hesaplanır:

    F_cfd = sum_f  (-p_f) n_f A_f          CFD yüzeyi üzerinde
    F_fea = sum_g  (-p_{en yakin}) n_g A_g  ALICI yüzey üzerinde

İkisi arasındaki fark, ESKİ şemanın FEA'ya uyguladığı yükün aerodinamik
yükten sapmasıdır.

SONUÇ VE SONRASI. Medyan %9,5, 23 koşunun 9'unda %10'un üstünde. Bu ölçüm
üretim yolunun korunumlu şemaya taşınmasının GEREKÇESİDİR; taşındıktan
sonra sapma tanımı gereği sıfırdır (ağırlıklar 1'e toplanır) ve
`_map_pressure_to_tet` her koşuda `korunum_artigi` döndürür. Betik
TARİHSEL kaydı üretmeye devam eder --- silmek, taşınmanın gerekçesini
silmek olurdu.

    python experiments/alici_yuzey_yeterliligi.py
Çıktı: alici_yuzey_yeterliligi.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "alici_yuzey_yeterliligi.json"
KOSULAR = KOK / "vehicle_runs"

# Uretimde kullanilan hava yogunlugu varsayilani (vehicle_fea ile ayni).
RHO = 1.225


def _cfd_yuzey(vtk: Path):
    from vehicle_fea import _parse_legacy_vtk
    noktalar, poly, p, p_loc = _parse_legacy_vtk(vtk)
    if len(poly) == 0 or len(p) == 0:
        return None
    if p_loc == "POINT" or len(p) == len(noktalar):
        p_yuz = np.array([p[list(q)].mean() for q in poly])
    else:
        p_yuz = np.asarray(p)
    merkez = np.array([noktalar[list(q)].mean(axis=0) for q in poly])
    # Alan ve normal: poligonlar ucgen degilse ucgen yelpazesiyle toplanir.
    alan_vek = np.zeros((len(poly), 3))
    for i, q in enumerate(poly):
        v = noktalar[list(q)]
        for j in range(1, len(v) - 1):
            alan_vek[i] += 0.5 * np.cross(v[j] - v[0], v[j + 1] - v[0])
    alan = np.linalg.norm(alan_vek, axis=1)
    normal = alan_vek / (alan[:, None] + 1e-30)
    # YONLENDIRME KURESELDIR, YUZ BASINA DEGIL. Ilk surumde burada da
    # "normal, govde merkezinden disari baksin" olcutu vardi ve A320'de
    # 335.156 yuzun 176.031'ini TERS CEVIRDI; F_cfd cozucunun bildirdigi
    # kuvvetle hic tutmadi (-39,4 N z, oysa tasima +6,77 N). Ayni kusur
    # `vehicle_fea`'da da duruyordu ve orada URETIM yukunu bozuyordu.
    normal = _kuresel_yonlendir(merkez, normal, alan)
    return {"merkez": merkez, "normal": normal, "alan": alan,
            "p_pa": p_yuz * RHO}


def _kuresel_yonlendir(merkez, normal, alan):
    """Sarim tutarliysa geriye TEK bir soru kalir: ice mi disa mi.

    Diverjans teoremi cevabi verir --- kapali yuzeyin cevreledigi hacim
    pozitifse sarim disadir. Tek tek yuze DOKUNULMAZ; dokunmak ince/uzun
    govdelerde yuzeyin tutarliligini bozar.
    """
    hacim = float((np.einsum("ij,ij->i", merkez, normal) * alan).sum() / 3.0)
    return -normal if hacim < 0 else normal


def _alici_yuzey(stl: Path):
    import trimesh
    m = trimesh.load(stl, force="mesh")
    if not isinstance(m, trimesh.Trimesh) or len(m.faces) == 0:
        return None
    return {"merkez": np.asarray(m.triangles_center),
            "normal": np.asarray(m.face_normals),
            "alan": np.asarray(m.area_faces)}


def olc_vaka(vtk: Path, stl: Path) -> dict | None:
    c = _cfd_yuzey(vtk)
    a = _alici_yuzey(stl)
    if c is None or a is None:
        return None
    # CFD yuzeyi uzerindeki GERCEK aerodinamik kuvvet
    F_cfd = (-c["p_pa"][:, None] * c["normal"] * c["alan"][:, None]).sum(axis=0)
    # ESKI SEMA (2026-08-28'e kadar uretimdeydi): en yakin CFD hucresinin
    # basinci, ALICI yuzeyin KENDI alani ve normaliyle yeniden integre
    # edilir. Alanlar farkliysa toplam kuvvet de farkli cikar.
    #
    # BU OLCUM ARTIK TARIHSELDIR ve oyle etiketlenir. Uretim korunumlu
    # semaya tasindi: kuvvet CFD yuzunde kurulup baryzentrik agirliklarla
    # dagitiliyor ve toplam KIMLIK olarak korunuyor, yani bugunku sapma
    # TANIMI GEREGI sifirdir. Betigi eski sayilari uretmeye devam eder
    # halde birakmak, kanitin bayatlamasi olurdu.
    _, en_yakin = cKDTree(c["merkez"]).query(a["merkez"], k=1)
    F_fea = (-c["p_pa"][en_yakin][:, None] * a["normal"]
             * a["alan"][:, None]).sum(axis=0)
    n_cfd = float(np.linalg.norm(F_cfd))
    fark = float(np.linalg.norm(F_fea - F_cfd))
    # KAPALILIK OLCULUR VE HUKME GIRER. OpenFOAM'in kinematik basinci bir
    # SABITE KADAR tanimlidir; kapali bir yuzeyde o sabit ∮n dA = 0 ile
    # sifirlanir, ACIK yuzeyde SIFIRLANMAZ ve iki yuzeyde FARKLI bir yapay
    # kuvvet birakir. Yani acik yuzeyde bu kiyas kirlidir. Gripen'de
    # |Σn·A|/ΣA = 0,68 --- yarim model, simetri duzlemi acik.
    def _kap(y):
        return float(np.linalg.norm((y["normal"] * y["alan"][:, None]).sum(
            axis=0)) / (y["alan"].sum() + 1e-30))

    # ONEMLI OLAN ALICININ KAPALILIGI. Ilk surumde CFD yuzeyini olcuyordum
    # ve hepsi 0,00000 cikti --- OpenFOAM duvar yamasini KAPALI yazar, yani
    # olcut hicbir vakayi elemedi ve bir sey sinamiyordu. Sabitin
    # sifirlanmadigi yer ALICI yuzeydir: gripen'in STL'i yarim model,
    # |Σn·A|/ΣA = 0,68.
    kap_cfd, kap_alici = _kap(c), _kap(a)
    return {
        "kapalilik_cfd": round(kap_cfd, 5),
        "kapalilik_alici": round(kap_alici, 5),
        "hukum_verilebilir": bool(max(kap_cfd, kap_alici) < 0.05),
        "n_cfd_yuz": int(len(c["alan"])),
        "n_alici_yuz": int(len(a["alan"])),
        "cfd_alan_m2": round(float(c["alan"].sum()), 6),
        "alici_alan_m2": round(float(a["alan"].sum()), 6),
        "alan_farki_pct": round(
            100.0 * abs(float(a["alan"].sum() - c["alan"].sum()))
            / (float(c["alan"].sum()) + 1e-30), 4),
        "F_cfd_N": [round(float(x), 5) for x in F_cfd],
        "F_fea_N": [round(float(x), 5) for x in F_fea],
        "kuvvet_farki_eski_sema_pct": (round(100.0 * fark / n_cfd, 4)
                             if n_cfd > 1e-12 else None),
        "kuvvet_buyuklugu_N": round(n_cfd, 6),
    }


def _vakalar():
    for sj in sorted(KOSULAR.glob("*/sonuc.json")):
        try:
            d = json.loads(sj.read_text(encoding="utf-8"))
        # sessiz-yutma: kabul — bozuk kayit ADIYLA `dusen` listesine gecer
        except (OSError, json.JSONDecodeError) as e:
            yield sj.parent.name, None, None, f"sonuc.json: {e}"
            continue
        vtk = d.get("cp_vtk")
        stl = d.get("stl")
        if not vtk or not stl:
            continue
        vtk_y, stl_y = Path(vtk), Path(stl)
        if not stl_y.is_absolute():
            stl_y = KOK / stl_y
        if not (vtk_y.exists() and stl_y.exists()):
            yield sj.parent.name, None, None, "vtk ya da stl diskte yok"
            continue
        yield sj.parent.name, vtk_y, stl_y, None


def olc() -> dict:
    kayit, dusen = [], []
    for ad, vtk, stl, neden in _vakalar():
        if neden:
            dusen.append({"vaka": ad, "neden": neden})
            continue
        try:
            r = olc_vaka(vtk, stl)
        except Exception as e:                          # noqa: BLE001
            dusen.append({"vaka": ad,
                          "neden": f"{type(e).__name__}: {e}"[:140]})
            continue
        if r is None:
            dusen.append({"vaka": ad, "neden": "yüzey ayrıştırılamadı"})
            continue
        kayit.append({"vaka": ad, **r})
    return _ozetle(kayit, dusen)


def _ozetle(kayit: list[dict], dusen: list[dict]) -> dict:
    # HUKUM YALNIZ KAPALI YUZEYLERDEN. Acik yuzeyde basinc sabiti
    # sifirlanmaz ve kiyasa yapay bir kuvvet katar; onlari ayni tabloda
    # hukumlemek olculemeyeni olculmus gostermek olurdu.
    olculen = [k for k in kayit if k["kuvvet_farki_eski_sema_pct"] is not None
               and k["hukum_verilebilir"]]
    acik = [k for k in kayit if k["kuvvet_farki_eski_sema_pct"] is not None
            and not k["hukum_verilebilir"]]
    sirali = sorted(olculen, key=lambda k: -k["kuvvet_farki_eski_sema_pct"])
    return {
        "vaka": ("Alıcı (FEA) yüzey yeterliliği — ESKİ şemanın uyguladığı "
                 "yük (TARİHSEL; üretim korunumlu şemaya taşındı)"),
        "_neden": ("Arac yolu (vehicle_fea) basinci tasiyip kuvveti ALICI "
                   "yuzeyde yeniden integre eder; FSI surucusu ise korunumlu "
                   "semayi kullanir. Yuzey payinin 'uretim yolunda yoktur' "
                   "hukmu yalniz IKINCISI icin dogru. Bu betik birincisinin "
                   "hatasini dogrudan olcer."),
        "olculen_vaka": len(olculen),
        "acik_yuzey_hukumsuz": [
            {"vaka": k["vaka"], "kapalilik_alici": k["kapalilik_alici"],
             "kuvvet_farki_eski_sema_pct": k["kuvvet_farki_eski_sema_pct"]} for k in acik],
        "dusen": dusen,
        "vakalar": sirali,
        "ozet": _istatistik(olculen),
        "verdikt": _hukum(olculen),
        "_kisit": (
            "ACIK yuzeyler hukumsuz birakilir: kinematik basinc bir sabite "
            "kadar tanimlidir ve o sabit yalniz KAPALI yuzeyde sifirlanir. "
            "Olculen sey TOPLAM KUVVET farkidir; moment ve yerel dagilim "
            "ayrica bozulabilir ve bu betik onlari olcmez. Alici yuzey "
            "olarak kosunun STL'i alinir --- tet agi ondan uretildigi icin "
            "yuzey ucgenlemesi ayni ailededir, ama birebir ayni ag DEGILDIR."),
        "_uretim": "Üretim: python experiments/alici_yuzey_yeterliligi.py",
    }


def _istatistik(k: list[dict]) -> dict:
    if not k:
        return {"olculdu": False}
    v = sorted(x["kuvvet_farki_eski_sema_pct"] for x in k)
    return {
        "olculdu": True, "n": len(v),
        "medyan_pct": v[len(v) // 2],
        "en_kotu_pct": v[-1],
        "bir_pct_altinda": sum(1 for x in v if x < 1.0),
        "on_pct_ustunde": sum(1 for x in v if x > 10.0),
    }


def _hukum(k: list[dict]) -> str:
    if not k:
        return "ÖLÇÜLEMEDİ: hiçbir vakada yüzey ve STL birlikte bulunamadı."
    s = _istatistik(k)
    en = max(k, key=lambda x: x["kuvvet_farki_eski_sema_pct"])
    return (
        f"{s['n']} koşuda ölçüldü. Araç yolunun FEA'ya uyguladığı toplam "
        f"kuvvet, aerodinamik kuvvetten medyan %{s['medyan_pct']:.2f}, en "
        f"kötü %{s['en_kotu_pct']:.2f} sapıyordu ({en['vaka']}; alan farkı "
        f"%{en['alan_farki_pct']:.2f}). %1'in altında {s['bir_pct_altinda']}"
        f"/{s['n']}, %10'un üstünde {s['on_pct_ustunde']}/{s['n']}. Bu fark "
        f"ŞEMADAN gelir: basınç taşınıp kuvvet alıcı yüzeyde yeniden "
        f"integre ediliyordu, dolayısıyla alanlar farklıysa kuvvet de "
        f"farklı çıkıyordu. BU ÖLÇÜM TARİHSELDİR: üretim 2026-08-28'de "
        f"korunumlu şemaya taşındı (kuvvet CFD yüzünde kurulup baryzentrik "
        f"ağırlıklarla dağıtılıyor), yani bugünkü sapma TANIMI GEREĞİ "
        f"sıfırdır ve `korunum_artigi` her koşuda ölçülüyor.")


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    o = olc()
    CIKTI.write_text(json.dumps(o, indent=2, ensure_ascii=False),
                     encoding="utf-8")
    for k in o["vakalar"][:12]:
        print(f"  {k['vaka'][:28]:<28} kuvvet farkı "
              f"{k['kuvvet_farki_eski_sema_pct']:8.3f}%   alan farkı "
              f"{k['alan_farki_pct']:7.3f}%   "
              f"{k['n_cfd_yuz']:>7}→{k['n_alici_yuz']:<7}")
    print()
    print(o["verdikt"])
    if o["dusen"]:
        print(f"\ndüşen: {len(o['dusen'])}")
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
