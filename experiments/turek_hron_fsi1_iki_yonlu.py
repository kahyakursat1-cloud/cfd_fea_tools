"""Turek--Hron FSI1 --- İKİ YÖNLÜ: akış deforme bayrağı görüyor.

AÇIK KALAN KANAL BUYDU. Tek-yönlü koşu (`turek_hron_fsi1.py`) eksenel
kanalı ölçümle kapattı ama düşey sehimi %90 fazla verdi ve gerekçesi
biliniyordu: akış RİJİT bayrakla çözülüyordu. Kaynağın kendi taşıma
değerleri (rijit 1,119 / deforme 0,7638 N/m) geri beslemenin yükü %32
düşürdüğünü söylüyor ve o oranla ölçeklenince sapma %30'a iniyordu.
AMA O BİR HESAPTI. Bu betik onu koşar.

NASIL: Dirichlet--Neumann sabit-nokta turu.
    akış çöz -> yük taşı (basınç + viskoz) -> yapı çöz
      -> bayrak yüzey yer değiştirmesi -> CFD AĞINI DEFORME ET -> tekrar

AĞ HAREKETİ OpenFOAM'IN DEĞİL, DOĞRUDAN NOKTA DOSYASI ÜZERİNDEN. Sebebi
sadelik: hareket 0,8 mm, kanal 410 mm ve topoloji değişmiyor. Dinamik-ağ
çözücüsü, `dynamicMeshDict`, sınır koşulu ailesi --- hiçbiri gerekmiyor ve
her biri ayrı bir hata yüzeyi olurdu. Nokta yer değiştirmesi bayrak
yüzeyinde YAPININ değeridir ve akışkana doğru Gauss ağırlıkla söner;
diğer sınırlar sabit kalır.

SONUÇ: yayımlanan dört niceliğin dördü de %2,4 bandında üretildi ---
uy %2,34, ux %1,32, sürükleme %-0,08, taşıma %-1,83.

BU SONUCA İKİNCİ DENEMEDE ULAŞILDI VE BİRİNCİSİ SESSİZCE YANLIŞTI.
İlk koşu 7 turda ``sabit noktaya'' ulaşıp uy=1,4496 mm veriyordu, yani
referansın %77 üstünde. Sebep bu betiğin kendi döngüsündeydi: zaman
dizinleri turlar arasında BİRİKİYORDU. 1. tur 445'te yakınsadı, sonraki
turlar 439-441'de; OpenFOAM'ın `-latestTime`'ı sayıca en büyüğü seçtiği
için her tur 445'i, yani 1. TURUN RİJİT alanını okudu. Yapı hep aynı
rijit basıncı gördü ve ``sabit nokta'' da yük sabit olduğu için oluştu.

Yakalanması zordu çünkü İKİ KANAL AYRIŞMIŞTI ve ayrışma bir FİZİK BULGUSU
gibi okunabiliyordu: çözücünün kendi forces.dat'ı aynı dosyaya EKLENİYOR,
son satırı okunduğu için o kanal tazeydi. Yani taşıma her tur düşüyor,
aktarılan bayrak yükü sabit kalıyordu. Bunu ``taşıma silindir ile bayrak
arasında yeniden dağılıyor'' diye okudum ve üç ayrı eleme koşusu yazdım
(ağ ailesi, CSM1, dağılım ölçümü). Üçü de doğru sonuç verdi ve üçü de
kusuru bulamadı --- çünkü kusur onların hiçbirinde değil, BURADAYDI.

NE KAPATMAZ: ağ-bağımsızlığı (tek akış ağı, tek yapı ağı) ve zaman
bağımlılığı (FSI1 kararlıdır, FSI2/FSI3 değil). Yapısal model LİNEER;
sehim/uzunluk %0,24 olduğu için NLGEOM'un katkısı ikinci mertebedir ama
ÖLÇÜLMEDİ.

    python experiments/turek_hron_fsi1_iki_yonlu.py
Çıktı: turek_hron_fsi1_iki_yonlu.json
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

from turek_hron_ag import BAYRAK_SON_X, MERKEZ, Z_KALINLIK  # noqa: E402
from turek_hron_cfd1 import NU, RHO  # noqa: E402
from turek_hron_cfd1 import VAKA as CFD1_VAKA
from turek_hron_fsi1 import (  # noqa: E402
    REF,
    TASIMA_CFD1,
    TASIMA_FSI1,
    _bayrak_agi,
    _bayrak_stl,
    _fea_kos,
)

from analysis.backend import linux_run  # noqa: E402
from analysis.ccx_runner import windows_to_wsl_path  # noqa: E402

CIKTI = KOK / "turek_hron_fsi1_iki_yonlu.json"
VAKA = KOK / "turek_hron_fsi2y_case"
IS = KOK / "turek_hron_fsi2y_fea"

MAX_TUR = 12
TOL_MM = 1e-3          # uc sehiminde tur-arasi degisim [mm]
# SONUM YARICAPI: bayrak yuzeyinden uzaklastikca yer degistirme boyle soner.
# 0,03 m secildi cunku (i) bayrak kalinligi 0,02 m ile ayni mertebe, yani
# hareket birkac hucreye yayilir; (ii) en yakin sabit sinir (silindir yuzeyi
# ve kanal duvarlari) >=0,09 m uzakta ve exp(-(3)^2) ~ 1e-4, yani oralarda
# yer degistirme SIFIRA yakin --- sabit sinir kosuluyla catismaz.
SONUM_R = 0.03
# Sabit relaksasyon. FSI1'de kutle orani buyuk ve sehim kucuk oldugu icin
# eklenmis-kutle kararsizligi beklenmez; yine de 1,0 KULLANILMAZ cunku
# yakinsamayi tur-arasi degisimden OLCUYORUZ ve asiri adim onu maskeler.
OMEGA = 0.6


def _kur() -> np.ndarray:
    """CFD1 vakasını kopyala, ORİJİNAL nokta dizisini döndür."""
    if VAKA.exists():
        shutil.rmtree(VAKA)
    shutil.copytree(CFD1_VAKA, VAKA)
    for d in ("VTK", "postProcessing"):
        if (VAKA / d).exists():
            shutil.rmtree(VAKA / d)
    # Zaman dizinlerini temizle: her tur SIFIRDAN cozulur. Onceki cozumden
    # devam etmek hizli olurdu ama deforme agda eski alan kucuk bir tutarsizlik
    # tasir; bu vaka 15 saniyede yakinsadigi icin BEDELI ODEMEYE DEGMEZ.
    for t in VAKA.glob("[0-9]*"):
        if t.is_dir() and t.name != "0":
            shutil.rmtree(t)
    return _nokta_oku()


def _nokta_yolu() -> Path:
    return VAKA / "constant" / "polyMesh" / "points"


def _nokta_oku() -> np.ndarray:
    t = _nokta_yolu().read_text(encoding="utf-8", errors="replace")
    blok = t[t.index("("):t.rindex(")")]
    say = re.findall(r"\(\s*([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*\)",
                     blok)
    return np.array(say, dtype=float)


def _nokta_yaz(P: np.ndarray) -> None:
    yol = _nokta_yolu()
    t = yol.read_text(encoding="utf-8", errors="replace")
    bas = t.index("(", t.index("\n(", t.index("FoamFile")))
    son = t.rindex(")")
    govde = "\n".join(f"({x:.10g} {y:.10g} {z:.10g})" for x, y, z in P)
    yol.write_text(t[:bas] + "(\n" + govde + "\n" + t[son:], encoding="utf-8")


def _temizle() -> None:
    """Tur ARTIKLARINI sil --- `-latestTime` yalnız BU turu görsün.

    BU KUSUR ILK KOSUYU GECERSIZ KILDI ve sessizdi. Zaman dizinleri
    turlar arasi birikiyordu: 1. tur 445'te, sonraki turlar 439-441'de
    yakinsadi. OpenFOAM'in `-latestTime`'i SAYICA en buyugu secer, yani
    445'i --- 1. turun (RIJIT ag) alanini. Boylece yapi her turda ayni
    rijit basinci gordu, "sabit nokta" da yuk sabit oldugu icin olustu.

    Neden yakalanmasi zordu: cozucunun kendi forces.dat'i ayni dosyaya
    EKLENIYOR ve son satiri okundugu icin O KANAL TAZEYDI. Yani tasima her
    tur degisiyor, aktarilan bayrak yuku degismiyordu --- ve bu ikisinin
    ayrisması bir fizik bulgusu gibi okunabilirdi. Nitekim okunmustu.
    """
    for d in VAKA.glob("[0-9]*"):
        if d.is_dir() and d.name != "0":
            shutil.rmtree(d)
    for ad in ("VTK", "postProcessing"):
        if (VAKA / ad).exists():
            shutil.rmtree(VAKA / ad)


def _cfd_kos() -> dict:
    _temizle()
    yol = windows_to_wsl_path(VAKA)
    r = linux_run(
        f"cd '{yol}' && source /opt/openfoam11/etc/bashrc && "
        f"checkMesh -constant > log.checkMesh 2>&1; "
        f"simpleFoam > log.simpleFoam 2>&1; "
        f"foamPostProcess -solver incompressibleFluid -func gradU "
        f"-latestTime > log.gradU 2>&1; "
        f"foamToVTK -latestTime -ascii > log.foamToVTK 2>&1; echo BITTI",
        timeout=3600)
    log = (VAKA / "log.checkMesh")
    kotu = "***" in log.read_text(errors="replace") if log.exists() else None
    # DIZIN TEMIZLENDIGI ICIN TEK DOSYA OLMALI. Birden cok cikarsa
    # temizlik calismamistir ve SAYICA en buyugu secmek gerekir --- ad
    # siralamasi burada YANLIS cevap verir ("bayrak_98" > "bayrak_445").
    vtk = sorted(VAKA.glob("VTK/bayrak/bayrak_*.vtk"),
                 key=lambda p: int(p.stem.rsplit("_", 1)[1]))
    return {"kosdu": bool(vtk), "vtk": vtk[-1] if vtk else None,
            "vtk_aday": len(vtk),
            "checkMesh_hata": kotu, "cikti": (r.stdout or "")[-200:]}


def _kuvvet_oku() -> list | None:
    """Bu turda çözücünün KENDİ taşıma değeri (silindir+bayrak, N/m)."""
    dat = sorted(VAKA.glob("postProcessing/kuvvetler/*/force*.dat"))
    if not dat:
        return None
    son = [s for s in dat[-1].read_text(errors="replace").splitlines()
           if s.strip() and not s.startswith("#")]
    if not son:
        return None
    g = re.findall(r"\(([^()]*)\)", son[-1][son[-1].index("("):])
    if len(g) < 2:
        return None
    p = [float(x) for x in g[0].split()]
    v = [float(x) for x in g[1].split()]
    # 2B dilim -> birim derinlik (CFD1'deki ayni normalizasyon)
    return [(p[i] + v[i]) / Z_KALINLIK for i in range(3)]


def _deforme(P0: np.ndarray, dugum: np.ndarray, u: np.ndarray,
             sonum_r: float = SONUM_R) -> tuple[np.ndarray, dict]:
    """Yapı yer değiştirmesini ağa yay --- bayrakta birebir, uzakta sıfır."""
    from scipy.spatial import cKDTree
    # DEFORMASYON z'DEN BAGIMSIZ OLMAK ZORUNDA. Ilk surum 3B en-yakin-komsu
    # kullaniyordu ve on/arka duzlemdeki bir nokta cifti FARKLI FEA
    # dugumlerine dusuyordu; aralarindaki kenar z ekseninden sapiyordu.
    # `checkMesh` bunu yakaladi: "2349 edges not aligned with non-empty
    # directions". Oteki kalite olcutlerinin hepsi TEMIZDI (non-ortho 34,7;
    # carpiklik 0,82) --- yani kusur bir kalite kusuru degil, 2B VARSAYIMININ
    # kirilmasiydi ve `empty` yama isleminde sessizce baska bir problem
    # cozdurur. Cozum: sorguyu (x,y)'de yap, yer degistirmeyi z sutunu
    # boyunca ORTALA. Duzlem gerinimde bu zaten fiziksel olan.
    anahtar = np.round(dugum[:, :2], 9)
    tekil, ters = np.unique(anahtar, axis=0, return_inverse=True)
    u2 = np.zeros((len(tekil), 3))
    np.add.at(u2, ters, u)
    u2 /= np.bincount(ters, minlength=len(tekil))[:, None]
    d, i = cKDTree(tekil).query(P0[:, :2], k=1)
    agirlik = np.exp(-(d / sonum_r) ** 2)[:, None]
    yd = agirlik * u2[i]
    yd[:, 2] = 0.0
    # DIS SINIR KAPISI. Sonum yaricapinin "uzak sinirlara ulasmiyor" iddiasi
    # HESAPLANMIS bir iddiadir (exp(-9) ~ 1e-4); burada OLCULUR. Sinir
    # noktalari kayarsa problem sessizce baska bir problem olur --- kanal
    # daralir, giris egilir, ve cozucu bundan sikayet etmez.
    dis = ((P0[:, 0] < 1e-9) | (P0[:, 0] > 2.5 - 1e-9)
           | (P0[:, 1] < 1e-9) | (P0[:, 1] > 0.41 - 1e-9))
    return P0 + yd, {
        "max_yerdegistirme_mm": round(1000 * float(
            np.linalg.norm(yd, axis=1).max()), 6),
        "dis_sinir_max_mm": round(1000 * float(
            np.linalg.norm(yd[dis], axis=1).max()) if dis.any() else 0.0, 9),
        "dis_sinir_nokta": int(dis.sum()),
    }


def _dongu(sonum_r: float) -> tuple[list, str | None]:
    if not CFD1_VAKA.exists():
        return [], "CFD1 vakası yok — önce turek_hron_cfd1.py"
    P0 = _kur()
    mesh = _bayrak_agi()
    stl = IS / "bayrak_prep.stl"
    IS.mkdir(parents=True, exist_ok=True)
    _bayrak_stl(stl, 160)

    from scipy.spatial import cKDTree

    from coupling_fsi import cfd_pressure_to_fea_loads
    agac = cKDTree(mesh.points)

    u_yapi = np.zeros_like(mesh.points)      # yapisal yer degistirme alani
    tur_kayit, onceki = [], None
    for tur in range(1, MAX_TUR + 1):
        P, ag_bilgi = _deforme(P0, mesh.points, u_yapi, sonum_r)
        _nokta_yaz(P)
        cfd = _cfd_kos()
        if not cfd["kosdu"]:
            return tur_kayit, (f"tur {tur}: CFD düştü ({cfd['cikti']})")
        # KAPI DONGUYU GERCEKTEN DURDURUR. Ilk kosuda `checkMesh_hata` 2.
        # turdan itibaren True idi ve dongu ALDIRMADAN 7 tur kostu; sonuc
        # kendi kapisini gecmemis bir agdan geliyordu. Bu deponun en sik
        # kusuru: kapi VAR ama uretim yolu onu OKUMUYOR.
        if cfd["checkMesh_hata"]:
            return tur_kayit, (f"tur {tur}: checkMesh ag hatasi bildirdi "
                           f"(bkz {VAKA.name}/log.checkMesh); deforme ag "
                           f"kendi kapisini gecmeden sonuc alinmaz")
        # BAYAT VERI KAPISI. Ilk kosuyu gecersiz kilan kusur buydu ve
        # SESSIZDI: turlar arasi birikeen zaman dizinleri yuzunden
        # `-latestTime` onceki turun alanini seciyordu. Temizlik calisiyorsa
        # her turda TEK aday olur; birden cok cikarsa yuk hangi turdan
        # geldigi BILINMEZ ve dongu durmali.
        if cfd["vtk_aday"] != 1:
            return tur_kayit, (f"tur {tur}: {cfd['vtk_aday']} VTK adayi var; "
                           f"tur artiklari temizlenmemis ve yuk BAYAT "
                           f"olabilir")
        yuk = cfd_pressure_to_fea_loads(str(cfd["vtk"]), str(stl), rho=RHO,
                                        p_is_kinematic=True, kayma=True,
                                        mu_pa_s=RHO * NU)
        if yuk["status"] != "SUCCESS":
            return tur_kayit, (f"tur {tur}: aktarım düştü ({yuk})")
        stl_dugum = np.asarray(yuk["fea_nodes"], float)
        kuvvet = np.zeros_like(stl_dugum)
        for n, f in yuk["node_forces"].items():
            kuvvet[int(n) - 1] = f
        _, es = agac.query(stl_dugum, k=1)
        hk = np.zeros_like(mesh.points)
        np.add.at(hk, es, kuvvet)
        fea = _fea_kos(mesh, hk, IS)
        if not fea.get("kosdu"):
            return tur_kayit, (f"tur {tur}: FEA düştü ({fea['neden']})")

        yeni = _dugum_yerdegistirme(mesh, IS)
        if yeni is None:
            return tur_kayit, (f"tur {tur}: yer değiştirme alanı okunamadı")
        u_yapi = (1 - OMEGA) * u_yapi + OMEGA * yeni
        tasima = _kuvvet_oku()
        tur_kayit.append({
            "tur": tur,
            "uy_mm": round(fea["uy_mm"], 5), "ux_mm": round(fea["ux_mm"], 5),
            "degisim_mm": None if onceki is None
            else round(abs(fea["uy_mm"] - onceki), 6),
            "tasima_N_m": None if tasima is None else round(tasima[1], 4),
            "surukleme_N_m": None if tasima is None else round(tasima[0], 4),
            "checkMesh_hata": cfd["checkMesh_hata"],
            "vtk_aday": cfd["vtk_aday"],
            **ag_bilgi,
            "aktarilan_Fy_N": round(float(hk[:, 1].sum()), 8),
        })
        if onceki is not None and abs(fea["uy_mm"] - onceki) < TOL_MM:
            onceki = fea["uy_mm"]
            break
        onceki = fea["uy_mm"]
    return tur_kayit, None


# SONUM YARICAPI DUYARLILIGI. Ag hareketi bir Laplace cozumu degil, KINEMATIK
# bir secim --- ve secimin sonucu tasiyip tasimadigi kayitta "SINANMADI" diye
# duruyordu. Uc yaricap kosulur: yari, uretim, iki kat. Sonuc bunlar arasinda
# oynuyorsa "%2,34 sapma" bir fizik sonucu degil bir ayar sonucudur.
SONUM_SUPURME = (0.015, 0.03, 0.06)


def olc() -> dict:
    turlar, neden = _dongu(SONUM_R)
    r = _ozetle(turlar, neden)
    if neden is None:
        supurme = []
        for sr in SONUM_SUPURME:
            tl, nd = (turlar, None) if sr == SONUM_R else _dongu(sr)
            supurme.append({
                "sonum_r_m": sr, "tur": len(tl),
                "neden": nd,
                "uy_mm": None if nd or not tl else tl[-1]["uy_mm"],
                "tasima_N_m": None if nd or not tl else tl[-1]["tasima_N_m"],
            })
        r["sonum_duyarliligi"] = _supurme_ozeti(supurme)
    return r


def _supurme_ozeti(supurme: list) -> dict:
    iyi = [s for s in supurme if s["uy_mm"] is not None]
    d = {"kosular": supurme}
    if len(iyi) >= 2:
        v = [s["uy_mm"] for s in iyi]
        d["uy_yayilim_pct"] = round(100 * (max(v) - min(v)) / abs(v[0]), 3)
        d["_olcut"] = (
            "Yayilim, referanstan sapmayla (%2,3) KIYASLANIR: sapmadan "
            "kucukse ag-hareketi secimi sonucu tasimiyor demektir. Buyukse "
            "sonuc bir AYAR sonucudur ve oyle raporlanmalidir.")
    return d


def _dugum_yerdegistirme(mesh, work: Path):
    """FRD'den TÜM düğümlerin yer değiştirmesi (yapı yüzeyi dahil)."""
    from analysis.frd_parser import parse_frd
    frd = next(work.glob("*.frd"), None)
    if frd is None:
        return None
    r = parse_frd(frd)
    if "DISP" not in r.fields:
        return None
    u = np.zeros_like(mesh.points)
    for i, n in enumerate(r.node_ids):
        j = int(n) - 1
        if 0 <= j < len(u):
            u[j] = r.fields["DISP"][i]
    return u


def _ozetle(turlar: list, neden: str | None) -> dict:
    son = turlar[-1] if turlar else None
    sapma = None
    if son:
        sapma = {
            "uy_pct": round(100 * (son["uy_mm"] - REF["uy_mm"])
                            / REF["uy_mm"], 2),
            "ux_pct": round(100 * (son["ux_mm"] - REF["ux_mm"])
                            / abs(REF["ux_mm"]), 2),
        }
    return {
        "vaka": "Turek-Hron FSI1 — İKİ YÖNLÜ kuplaj",
        "_neden": ("Tek-yonlu kosuda dusey sehim %90 fazlaydi ve gerekcesi "
                   "biliniyordu: akis RIJIT bayrakla cozuluyordu. O gerekce "
                   "HESAPLANMISTI; bu betik onu KOSAR ve yayimlanan dort "
                   "nicelige karsi %2,4 bandinda kapatir."),
        "ayar": {"max_tur": MAX_TUR, "tol_mm": TOL_MM, "omega": OMEGA,
                 "sonum_r_m": SONUM_R,
                 "_ag_hareketi": "dogrudan points dosyasi, Gauss sonum"},
        "turlar": turlar,
        "referans": REF,
        "tasima_referans": {"rijit_cfd1": TASIMA_CFD1, "deforme_fsi1":
                            TASIMA_FSI1},
        "sapma": sapma,
        "surukleme_sapma_pct": (
            None if not turlar or turlar[-1].get("surukleme_N_m") is None
            else round(100 * (turlar[-1]["surukleme_N_m"] - 14.295) / 14.295, 2)),
        "tasima_sapma_pct": (
            None if not turlar or turlar[-1].get("tasima_N_m") is None
            else round(100 * (turlar[-1]["tasima_N_m"] - TASIMA_FSI1)
                       / TASIMA_FSI1, 2)),
        "verdikt": _hukum(turlar, sapma, neden),
        "_kisit": (
            "AG-BAGIMSIZLIGI SINANMADI: tek akis agi, tek yapi agi. "
            "Yapisal model LINEER; sehim/uzunluk %0,24 oldugu icin NLGEOM "
            "katkisi ikinci mertebedir ama OLCULMEDI. Ag hareketi Gauss "
            "sonumlu bir KINEMATIK secimdir, Laplace cozumu degil --- sonum "
            "yaricapi degisirse ag kalitesi degisir, cozum bundan ne kadar "
            "etkileniyor SINANMADI. FSI1 KARARLIDIR; bu tur zaman "
            "bagimliligi hakkinda hicbir sey soylemez."),
        "_uretim": "Üretim: python experiments/turek_hron_fsi1_iki_yonlu.py",
    }


def _hukum(turlar: list, sapma, neden) -> str:
    if neden:
        return f"KOŞULAMADI: {neden}"
    if not turlar:
        return "KOŞULAMADI: hiç tur tamamlanmadı."
    son = turlar[-1]
    ilk = turlar[0]
    yakinsadi = (son["degisim_mm"] is not None and son["degisim_mm"] < TOL_MM)
    s = (f"{len(turlar)} tur koşuldu. Uç sehimi ilk turda {ilk['uy_mm']} mm, "
         f"son turda {son['uy_mm']} mm; son tur-arası değişim "
         f"{son['degisim_mm']} mm. ")
    if son.get("tasima_N_m") is not None:
        s += (f"Deforme ağdaki taşıma {son['tasima_N_m']} N/m "
              f"(kaynak: rijit {TASIMA_CFD1}, deforme {TASIMA_FSI1}). ")
    s += (f"Yayımlanan FSI1 {REF['uy_mm']} mm --- sapma %{sapma['uy_pct']}. ")
    if not yakinsadi:
        return s + (f"SABİT NOKTAYA ULAŞILMADI ({MAX_TUR} tur tavanı): sonuç "
                    "bir yakınsama değeri DEĞİLDİR ve referansla "
                    "karşılaştırılamaz.")
    if abs(sapma["uy_pct"]) < 10.0:
        d_sur = 100 * (son["surukleme_N_m"] - 14.295) / 14.295
        d_tas = 100 * (son["tasima_N_m"] - TASIMA_FSI1) / TASIMA_FSI1
        return s + (
            f"Yayımlanan DÖRT niceliğin dördü de üretildi: uy "
            f"%{sapma['uy_pct']}, ux %{sapma['ux_pct']}, sürükleme "
            f"%{d_sur:.2f}, taşıma %{d_tas:.2f}. Geri besleme kanalı "
            f"HESAPLA değil KOŞUYLA kapandı ve bu, bu deponun FSI tarafında "
            f"tam bir kıyaslama vakasını uçtan uca ürettiği ilk sonuçtur. "
            f"BANT BİR GCI DEĞİLDİR: tek akış ağı, tek yapı ağı, lineer "
            f"yapı ve kinematik bir ağ-hareketi seçimi. Ayrıca bu sonuca "
            f"İKİNCİ denemede ulaşıldı --- birincisi tur artıklarını "
            f"temizlemediği için her turda bayat (rijit) basıncı okuyor ve "
            f"%77 sapan sahte bir 'sabit nokta' üretiyordu.")
    # KALAN FARKIN YERI DARALTILABILIYOR ve bu elemeyi kayit yapar.
    d_tasima = (100 * (son["tasima_N_m"] - ilk["tasima_N_m"])
                / ilk["tasima_N_m"]) if son.get("tasima_N_m") else None
    d_ref = 100 * (TASIMA_FSI1 - TASIMA_CFD1) / TASIMA_CFD1
    return s + (
        f"GERİ BESLEME ÇALIŞTI AMA AŞIRI: taşıma turlar boyunca "
        f"%{d_tasima:.1f} düştü, kaynağın kendi rijit/deforme çifti ise "
        f"%{d_ref:.1f} diyor. Sürükleme buna karşın {son['surukleme_N_m']} "
        f"N/m ile referansın (14,295) %0,1'inde. YAPISAL MODEL ELENİR: "
        f"tek-yönlü koşuda ux referansı %1,3 bandında tutturdu ve ux "
        f"doğrudan EA'ya bağlıdır --- E ya da kesit 1,8 kat yanlış olsaydı "
        f"ux da o kadar kayardı. Geriye AKIŞ tarafı kalıyor: taşıma "
        f"silindir ile bayrak arasında yeniden dağılıyor ve bu ayrışma "
        f"ağ-bağımsızlığı SINANMAMIŞ bir çözümden geliyor. Sıradaki soru "
        f"budur, ve bu betiğin cevabı DEĞİLDİR."
        if d_tasima is not None else
        "Sabit noktaya ulaşıldı ama sapma sürüyor ve taşıma okunamadı.")


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
