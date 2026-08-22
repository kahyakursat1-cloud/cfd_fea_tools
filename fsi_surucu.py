"""İki-yönlü FSI sürücüsü — doğrulanmış dört parçayı bir kuplaj turuna bağlar.

NEDEN: parçaların hepsi VAR ve doğrulanmış, ama üretim yolu hiçbirini sürmüyordu.
Depo bunu iki yerde kayıtlı tutuyordu (`analysis/openfoam_runner.py:146`,
`coupling_fsi.py:262`): "`fsi_twoway.partitioned_fsi` DOGRULANMIS ama YALNIZ
TESTLERDEN". Eksik olan yeni fizik değil, `map_fn`'di.

KUPLAJ TURU (Dirichlet-Neumann):
    x  = FEA yüzey düğümlerinin yer değiştirmesi (K×3, düzleştirilmiş)
    ├─ fea_displacement_to_cfd_points  → CFD yama noktalarına taşı
    ├─ write_point_displacement        → 0/pointDisplacement
    ├─ CFD çöz (hareketli ağ)          → yüzey basıncı VTK
    ├─ cfd_pressure_to_fea_loads       → düğüm kuvvetleri
    ├─ write_cload → run_ccx → parse_frd
    └─ yeni x

`partitioned_fsi` bu turu sabit-noktaya sürer (Aitken Δ², Küttler-Wall 2008).

DOĞRULAMA SÖZLEŞMESİ: sentetik girdiyle "çalışıyor" demek bu depoda YETMEZ.
`--kuru` kipi yalnız TESİSATI sınar (parçalar birbirine uyuyor mu, boyutlar
tutuyor mu) ve çıktısında bunu AÇIKÇA söyler; fiziksel yakınsama iddiası
GERÇEK kuplaj turundan gelir ve artık geçmişiyle birlikte kanıta yazılır.

    python fsi_surucu.py --kuru <run_dir>     # tesisat denetimi (CFD koşmaz)
    python fsi_surucu.py <run_dir>            # gerçek kuplaj
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))


@dataclass
class KuplajVakasi:
    """Bir FSI koşusunun tüm girdileri — sürücü BUNDAN başkasını varsaymaz."""
    run_dir: Path
    yama: str = "gövde"                  # CFD gövde yaması
    malzeme: str = "aluminum_6061"
    kisit: str = "y_min"
    rho: float = 1.225
    max_dis_iter: int = 8                # Aitken ile 3-6 tipik; tavan güvenlik
    tol: float = 1e-6                    # [m] arayüz yer değiştirme artığı
    kuru: bool = False
    gecmis: list = field(default_factory=list)


def _fea_yuzey(vaka: KuplajVakasi):
    """FEA yüzey düğümleri (K,3) ve onları taşıyan STL yolu."""
    import trimesh
    stl = next(vaka.run_dir.glob("*_prep.stl"), None) or next(
        vaka.run_dir.glob("*.stl"), None)
    if stl is None:
        raise FileNotFoundError(f"{vaka.run_dir}: FEA yüzey STL'i yok")
    m = trimesh.load(str(stl), force="mesh")
    return np.asarray(m.vertices, float), stl


def _cfd_yama_noktalari(vaka: KuplajVakasi):
    """CFD gövde yamasının noktaları (M,3) — VTK'dan okunur."""
    from coupling_fsi import _parse_legacy_vtk
    vtk = _son_vtk(vaka)
    points, _polys, _p, _loc = _parse_legacy_vtk(Path(vtk))
    return np.asarray(points, float), vtk


def _vaka_dizini(vaka: KuplajVakasi) -> Path:
    """OpenFOAM VAKA dizini — koşu dizini DEĞİL.

    ÖLÇÜLDÜ 2026-08-22 (fsi_tahrikH): `map_fn`, `write_point_displacement`'a
    `vaka.run_dir` veriyordu. O fonksiyon `<dizin>/<zaman>/pointDisplacement`
    yazar, yani alan `vehicle_runs/X/0/`'a düştü --- vaka
    `vehicle_runs/X/X/` iken. Çözücü onu HİÇ OKUMADI: yedi zaman dizininin
    yedisinde de gövde yaması `uniform (0 0 0)` kaldı, ağ hiç kıpırdamadı ve
    kuplaj "sabit-harita" imzası verdi. İmza doğruydu, TEŞHİS yanlış olurdu:
    "fizik sürmüyor" değil "yer değiştirme ağa ulaşmıyor".

    Ağ hareketinin kendisi daha önce doğrulanmıştı (3,000 mm istendi, 3,0000 mm
    ölçüldü) ama o doğrulama `write_point_displacement`'ı DOĞRUDAN çağırmıştı;
    sürücünün çağrı yeri hiç koşulmamıştı.
    """
    adaylar = [d for d in vaka.run_dir.iterdir()
               if d.is_dir() and (d / "system" / "controlDict").exists()]
    if len(adaylar) != 1:
        raise FileNotFoundError(
            f"{vaka.run_dir}: tek-anlamlı OpenFOAM vaka dizini yok "
            f"({len(adaylar)} aday) — yer değiştirme nereye yazılacağı "
            f"BELİRSİZ; tahminle yazmak ağı sessizce hareketsiz bırakır")
    return adaylar[0]


def _govde_yamasi(vaka: KuplajVakasi) -> str:
    """Ağdaki GERÇEK gövde yaması adı — çağıranın verdiği ad DOĞRULANIR.

    Aynı koşuda ikinci kusur buydu: çağıran `yama='fsi_tahrikH'` verdi, ağdaki
    yama ise `fsi_tahrikH_prep`. Yanlış ada yazılan bir sınır koşulu sessizce
    hiçbir şey yapmaz.
    """
    b = (_vaka_dizini(vaka) / "constant" / "polyMesh" / "boundary")
    adlar = re.findall(r"^\s{4}(\w+)\s*$", b.read_text(encoding="utf-8"), re.M)
    uzak = {"inlet", "outlet", "top", "bottom", "front", "back", "ground"}
    govde = [a for a in adlar if a not in uzak]
    if vaka.yama in govde:
        return vaka.yama
    if len(govde) == 1:
        return govde[0]
    raise ValueError(
        f"gövde yaması belirsiz: istenen '{vaka.yama}', ağdakiler {govde}")


def _son_vtk(vaka: KuplajVakasi) -> str:
    """EN GÜNCEL yüzey-basınç VTK'sı. YOKSA HATA — sessizce sıfır dönmez.

    ZAMAN'A GÖRE SEÇİLİR, ÖNBELLEĞE GÖRE DEĞİL. `resolve_cp_vtk` sonuc.json'da
    `cp_vtk` varsa ONU döndürür; kuplaj turunda bu, her iterasyonda TABAN
    basınç alanını okumak demektir. Ölçüldü 2026-08-21 (fsi_esnek): CFD deforme
    ağda gerçekten yeniden çözüyordu (postProcessing'de 205, 207, 209, 211
    üretildi) ama sürücü hepsinde 205'i okudu — FEA deplasmanı üç turda da
    0,1857 mm çıktı, dört ondalıkta birebir aynı, ve sabit-harita kapısı
    "SAHTE YAKINSAMA" dedi. Kapı haklıydı; kusur buradaydı.
    """
    kok = vaka.run_dir
    adaylar = []
    for yb in kok.rglob("postProcessing/yuzeyBasinc"):
        for t in yb.iterdir():
            try:
                adaylar.append((float(t.name), sorted(t.glob("*.vtk"))))
            # sessiz-yutma: kabul — sayısal olmayan dizin adı zaman değildir;
            # eleme kriterin ta kendisi, hata değil
            except (ValueError, OSError):
                continue
    adaylar = [(z, v[0]) for z, v in adaylar if v]
    if adaylar:
        return str(max(adaylar, key=lambda x: x[0])[1])

    from vehicle_fea import resolve_cp_vtk
    sonuc = {}
    sj = vaka.run_dir / "sonuc.json"
    if sj.exists():
        sonuc = json.loads(sj.read_text(encoding="utf-8"))
    v = resolve_cp_vtk(vaka.run_dir, sonuc)
    if not v:
        raise FileNotFoundError(
            f"{vaka.run_dir}: yüzey-basınç VTK'sı bulunamadı — kuplaj turu "
            "CFD sonucu OLMADAN başlayamaz (önce tek-yönlü koşu gerekir)")
    return v


def tesisat_denetimi(vaka: KuplajVakasi) -> dict:
    """Parçalar birbirine UYUYOR mu — CFD koşmadan ölçülebilen her şey.

    Fiziksel yakınsama İDDİA ETMEZ; yalnız boyutların, dosyaların ve
    taşıma operatörünün tutarlı olduğunu söyler. `--kuru` bunu koşar.
    """
    fea_nodes, fea_stl = _fea_yuzey(vaka)
    cfd_points, vtk = _cfd_yama_noktalari(vaka)
    from coupling_fsi import fea_displacement_to_cfd_points

    # RIJIT OTELEME SINAMASI: sabit bir alan HATASIZ tasinmali (birim-bolunum).
    # Bu, tasima operatorunun bu VAKA GEOMETRISINDE de dogru oldugunu olcer —
    # birim testi sentetik noktalarla yapiyor, burada gercek ag kullaniliyor.
    sabit = np.tile(np.array([1e-3, -2e-3, 3e-4]), (len(fea_nodes), 1))
    tasinan = fea_displacement_to_cfd_points(fea_nodes, sabit, cfd_points)
    rijit_hata = float(np.abs(tasinan - sabit[0]).max())

    return {
        "fea_dugum": int(len(fea_nodes)), "cfd_nokta": int(len(cfd_points)),
        "fea_stl": str(fea_stl), "vtk": str(vtk),
        "rijit_oteleme_hatasi_m": rijit_hata,
        "tesisat": "UYUMLU" if rijit_hata < 1e-12 else "TAŞIMA HATALI",
        "_kapsam": ("YALNIZ TESİSAT — parçalar uyuşuyor ve taşıma operatörü bu "
                    "geometride rijit ötelemeyi hatasız taşıyor. Fiziksel "
                    "yakınsama İDDİA EDİLMİYOR; o GERÇEK kuplaj turundan gelir."),
    }


def kuplaj_haritasi(vaka: KuplajVakasi):
    """`partitioned_fsi`'ye verilecek map_fn: x → bir tam kuplaj turu → x_yeni."""
    from analysis.ccx_runner import run_ccx
    from analysis.frd_parser import parse_frd
    from coupling_fsi import (
        cfd_pressure_to_fea_loads,
        fea_displacement_to_cfd_points,
        write_cload,
        write_point_displacement,
    )

    fea_nodes, fea_stl = _fea_yuzey(vaka)
    cfd_points, _ = _cfd_yama_noktalari(vaka)
    K = len(fea_nodes)

    def map_fn(x):
        d_fea = np.asarray(x, float).reshape(K, 3)

        # 1) Yapi -> akiskan: deplasmani CFD noktalarina tasi ve aga yaz
        d_cfd = fea_displacement_to_cfd_points(fea_nodes, d_fea, cfd_points)
        # VAKA dizini ve GERCEK yama adi — ikisi de cozuluyor, varsayilmiyor.
        # Ikisi de sessizce yanlis olabiliyordu (bkz. `_vaka_dizini`).
        _case, _yama = _vaka_dizini(vaka), _govde_yamasi(vaka)
        _yol = write_point_displacement(_case, _yama, d_cfd)
        # YAZILAN ALAN GERCEKTEN VAKANIN ICINDE MI. Yoklugun hukmu yok:
        # dosya vakanin disina duserse cozucu onu okumaz ve ilmek "sabit
        # harita" der — kusur fizige atfedilir.
        if _case not in _yol.parents:
            raise RuntimeError(
                f"yer değiştirme vaka dizininin DIŞINA yazıldı: {_yol}")

        # 2) CFD'yi HAREKETLI AGDA yeniden coz.
        #
        # EKSIK PARCA — ADIYLA SOYLENIYOR: `run_cfd(case, out_dir)` vakayi
        # SIFIRDAN kurar; mevcut bir vakayi yer degistirmis agla YENIDEN cozen
        # bir giris noktasi yok. Kuplaj turunun her adimi bunu ister.
        # Gereken: moveDynamicMesh (ya da cozucunun kendi ag hareketi) +
        # latestTime'dan devam + yeni yuzey VTK'si.
        # Sessizce atlanmiyor: burasi ACIKCA duser, cunku CFD'yi kosmadan
        # donen bir map_fn "yakinsadi" der ve bu, bu deponun reddettigi
        # sahte-kesinligin ta kendisi olurdu.
        from analysis import openfoam_runner as _of
        if not hasattr(_of, "run_cfd_yeniden"):
            raise NotImplementedError(
                "analysis.openfoam_runner.run_cfd_yeniden YOK — kuplaj turu "
                "hareketli agda CFD yeniden-cozumu gerektiriyor. Tesisatin "
                "geri kalani `--kuru` ile dogrulanabilir.")
        _r = _of.run_cfd_yeniden(vaka.run_dir)
        if _r.get("durum") != "ok":
            raise RuntimeError(f"CFD yeniden-cozumu dustu: {_r.get('durum')}")
        # Yuzey VTK'si BU katmanda uretilir (analysis/ kendi icinde kapali).
        from vehicle_pipeline import export_surface_vtk
        export_surface_vtk(_r["case"], _r["govde_yamasi"])

        # 3) Akiskan -> yapi: yuzey basinci -> dugum kuvvetleri -> CalculiX
        yukler = cfd_pressure_to_fea_loads(_son_vtk(vaka), str(fea_stl),
                                           rho=vaka.rho)
        if yukler.get("status") == "FAILED":
            raise RuntimeError(f"yük aktarımı düştü: {yukler.get('error')}")
        # YUK GERCEKTEN UYGULANIR. Ilk surum `fsi.cload`'u yaziyor ama .inp
        # onu HIC DAHIL ETMIYORDU: her tur AYNI statik yukle koşar, sabit-nokta
        # ilk adimda saglanir ve dongu "yakinsadi" der. Sahte kesinligin ders
        # kitabi ornegi olurdu. Yeni *CLOAD blogu .inp'e DOGRUDAN yazilir.
        cload = write_cload(yukler["node_forces"], str(vaka.run_dir / "fsi.cload"))
        # .inp kok dizinde DEGIL alt dizinde olabilir (vehicle_fea `fea/` altina
        # yaziyor); rglob kullanilir.
        inp = next(vaka.run_dir.rglob("*.inp"))
        _t = inp.read_text(encoding="utf-8")
        _i = _t.index("*CLOAD")
        _j = _t.find("*", _i + 6)
        inp.write_text(_t[:_i] + Path(cload).read_text(encoding="utf-8")
                       + (_t[_j:] if _j > 0 else ""), encoding="utf-8")
        run_ccx(inp, timeout=1800)

        # 4) Yeni deplasman
        frd = parse_frd(inp.with_suffix(".frd"))
        # DUGUM KIMLIGINE gore eslenir, SIRAYA gore degil. STL kosesi i,
        # CalculiX dugumu i+1'dir (`cfd_pressure_to_fea_loads` yuku boyle
        # anahtarliyor) — ayni anahtar uzayi kullanilarak yuk ve deplasman
        # tutarli kalir. FRD tum tet-ag dugumlerini tasir (13.423), yalniz
        # yuzeydekiler (K) alinir.
        _disp = frd.fields.get("DISP")
        if _disp is None:
            raise RuntimeError("FRD'de DISP alani yok — CalculiX cozumu eksik")
        _sira = {int(n): i for i, n in enumerate(frd.node_ids)}
        yeni = np.array([_disp[_sira[i + 1]] if (i + 1) in _sira else (0.0, 0.0, 0.0)
                         for i in range(K)], dtype=float)
        # HER TURDA IKI TARAFIN YUKU DE KAYDEDILIR.
        #
        # NEDEN: `sabit_harita` kapisi "harita YANIT VERMIYOR"u yakaliyor ama
        # "harita YANLIS SEBEPLE yanit veriyor"u yakalamiyordu. Olculdu
        # 2026-08-22 (fsi_tahrikH): ag hareket edince FEA tarafina tasinan
        # normal kuvvet 0,662 -> 0,441 N dustu (%33) ve ilmek yakinsadi; ama
        # CFD YUZEYINDEKI kuvvet 0,6058 -> 0,6070 N, yani %0,2 degisti.
        # Aerodinamik yuk degismemisti; degisen AKTARIMDI — aktarim artigi
        # %8,4'ten %27,4'e firladi, cunku CFD yuzeyi deforme olurken yuk
        # haritasinin dayandigi FEA STL'i REFERANS KONUMDA kaldi.
        #
        # Ikisi ayni yerde durmadikca bu ayrim gorulemez.
        vaka.gecmis.append({"tur": len(vaka.gecmis) + 1,
                            "max_disp_mm": float(np.abs(yeni).max() * 1000),
                            "Fz_fea_N": round(float(yukler["total_force_N"][2]), 5),
                            "Fz_cfd_N": round(float(yukler["total_force_cfd_N"][2]), 5),
                            "aktarim_hatasi_pct": round(
                                100 * float(yukler["aktarim_hatasi"]), 2),
                            "cload": cload})
        return yeni.ravel()

    return map_fn, K


def fsi_kos(vaka: KuplajVakasi) -> dict:
    from fsi_twoway import partitioned_fsi

    tesisat = tesisat_denetimi(vaka)
    if tesisat["tesisat"] != "UYUMLU":
        return {"vaka": "FSI kuplaj", "verdikt": "❌ TESİSAT UYUMSUZ",
                "tesisat": tesisat}
    if vaka.kuru:
        return {"vaka": "FSI kuplaj — KURU KOŞU",
                # Kuru dal da kanit uretiyor; depo kurali burada da gecerli
                # (saglik olceri bu eksigi hemen yakaladi).
                "_uretim": f"Üretim: python fsi_surucu.py --kuru {vaka.run_dir}",
                "verdikt": ("⚠️ YALNIZ TESİSAT DENETLENDİ — CFD koşulmadı, "
                            "fiziksel yakınsama İDDİA EDİLMİYOR"),
                "tesisat": tesisat}

    map_fn, K = kuplaj_haritasi(vaka)
    x0 = np.zeros(K * 3)
    x, bilgi = partitioned_fsi(map_fn, x0, tol=vaka.tol,
                               max_iter=vaka.max_dis_iter, aitken=True)
    yakinsadi = bool(bilgi["converged"])

    # SABIT-HARITA IMZASI: "yakinsadi" tek basina KANIT DEGILDIR.
    # map_fn girdiden BAGIMSIZ ayni degeri donduruyorsa (yani kuplaj aslinda
    # TEK YONLU ise) artik dizisi cebirsel olarak ZORUNLU su sekli alir:
    #   omega_0 = 0.5  ->  r_1 = 0.5*r_0   (tam yarisi)
    #   Aitken sabit haritada omega_1 = 1.0 -> r_2 = 0 (TAM sifir)
    # Olculdu 2026-08-21 (fsi_kiris): r = 5.761e-06, 2.880e-06, 0.000e+00 ve
    # omega = 0.500, 1.000 — imzanin birebir kendisi. Fiziksel sebep mesru
    # (6 mm aluminyum kiris 20 m/s'de 3 um sehim yapiyor, basinc alani
    # olculebilir bicimde degismiyor) AMA o kosu iki-yonlu kuplaji SINAMAZ,
    # yalnizca cokmedigini gosterir. Bunu "yakinsadi" diye raporlamak,
    # tek-yonlu bir hesabi iki-yonlu gibi gostermek olurdu.
    _r = bilgi["res_history"]
    _sabit_harita = (
        len(_r) >= 3 and _r[0] > 0
        and abs(_r[1] - 0.5 * _r[0]) < 1e-3 * _r[0]      # tam yarilanma
        # GORELI esik — `== 0.0` YANLIS NEGATIF veriyordu. Olculdu 2026-08-21
        # (fsi_esnek, taze basinc alaniyla): r = 3.7110e-04, 1.8555e-04,
        # 2.5005e-09. Yarilanma TAM, omega yine 0.5/1.0, sehim uc turda da
        # 0,18573 mm — harita hala fiilen sabit. Tek fark son artigin sifir
        # yerine baslangicin 7 MILYONDA BIRI olmasi. Mutlak sifir sarti bu
        # imzayi kaciriyordu.
        and _r[-1] < 1e-4 * _r[0]                         # yanit ~yok
        # OMEGA'DA DA TOLERANS. `== [0.5, 1.0]` ikinci bir YANLIS NEGATIF
        # kaynagiydi: Aitken sonlu-hassasiyette 0.9999973 uretiyor, tam 1.0
        # degil. Iki tam-esitlik denetimi de gercek veride imzayi kacirdi —
        # kirilgan karsilastirma, dedektorun kendisini korlestiriyordu.
        and abs(bilgi["omega_history"][0] - 0.5) < 1e-9
        and abs(bilgi["omega_history"][1] - 1.0) < 1e-3
    )
    return {
        "vaka": "FSI kuplaj — iki yönlü (Aitken)",
        "_uretim": f"Üretim: python fsi_surucu.py {vaka.run_dir}",
        "sabit_harita_suphesi": _sabit_harita,
        "verdikt": (
            ("⚠️ SAHTE YAKINSAMA — artık dizisi SABİT-HARİTA imzası taşıyor "
             f"(r={_r[0]:.3e}→{_r[1]:.3e}→{_r[-1]:.3e}, ω=0,5→1,0). map_fn "
             "girdiye YANIT VERMİYOR: kuplaj fiilen TEK YÖNLÜ. Döngü çöküyor "
             "değil ama iki-yönlü kuplajı SINAMIYOR; daha esnek yapı ya da "
             "daha yüksek dinamik basınç gerekir.")
            if _sabit_harita else
            f"{'✅ YAKINSADI' if yakinsadi else '⚠️ YAKINSAMADI'} — "
            f"{bilgi['iters']} dış iterasyon, son artık "
            f"{bilgi['res_history'][-1]:.3e} m (tol {vaka.tol:.0e})"),
        "tesisat": tesisat, "yakinsadi": yakinsadi and not _sabit_harita,
        "iterasyon": bilgi["iters"],
        "artik_gecmisi": bilgi["res_history"],
        "omega_gecmisi": bilgi["omega_history"],
        "tur_gecmisi": vaka.gecmis,
        "max_disp_mm": float(np.abs(x).max() * 1000),
        **aktarim_surulu_mu(vaka.gecmis),
    }


# Aktarim artigi bu kadar puan artarsa yanit AKTARIMDAN geliyor olabilir.
AKTARIM_SICRAMA_PUAN = 5.0
# CFD tarafindaki yuk bu orandan az degisiyorsa "aerodinamik yuk degismedi".
AERO_DEGISMEDI_PCT = 1.0


def aktarim_surulu_mu(gecmis: list[dict]) -> dict:
    """Kuplajın yanıtı FİZİKTEN mi AKTARIMDAN mı geliyor.

    `sabit_harita` kapısı haritanın yanıt VERMEDİĞİ durumu yakalar. Bu kapı
    ters durumu yakalar: harita yanıt veriyor ama sebep aerodinamik yükün
    değişmesi değil, yük aktarımının BOZULMASI.

    Ölçüldü 2026-08-22 (fsi_tahrikH): ağ hareket edince FEA'ya taşınan normal
    kuvvet %33 düştü ve ilmek yakınsadı; CFD yüzeyindeki kuvvet ise %0,2
    değişti. Aerodinamik yük değişmemişti. Sebep: CFD yüzeyi deforme olurken
    yük haritasının dayandığı FEA STL'i referans konumda kalıyor ve
    en-yakın-komşu eşlemesi bozuluyor (aktarım artığı %8,4 → %27,4).

    Bu bir HÜKÜM değil bir UYARIDIR: küçük deformasyonda yükü referans
    konfigürasyonda değerlendirmek meşru bir formülasyondur. Meşru olmayan,
    yükü DEFORME yüzeyden örnekleyip REFERANS yüzeye taşımaktır --- iki
    konfigürasyon karışır ve fark fizik sanılır.
    """
    if len(gecmis) < 2 or "Fz_cfd_N" not in gecmis[0]:
        return {}
    fc = [abs(g["Fz_cfd_N"]) for g in gecmis]
    ff = [abs(g["Fz_fea_N"]) for g in gecmis]
    ak = [g["aktarim_hatasi_pct"] for g in gecmis]
    d_cfd = 100 * (max(fc) - min(fc)) / (max(fc) + 1e-30)
    d_fea = 100 * (max(ff) - min(ff)) / (max(ff) + 1e-30)
    sicrama = max(ak) - min(ak)
    surulu = (d_cfd < AERO_DEGISMEDI_PCT and d_fea > 5 * AERO_DEGISMEDI_PCT
              and sicrama > AKTARIM_SICRAMA_PUAN)
    return {
        "aero_yuk_degisimi_pct": round(d_cfd, 2),
        "fea_yuk_degisimi_pct": round(d_fea, 2),
        "aktarim_hatasi_sicramasi_puan": round(sicrama, 2),
        "aktarim_surulu_mu": surulu,
        "aktarim_notu": (
            f"UYARI — YANIT AKTARIMDAN GELİYOR OLABİLİR: CFD yüzeyindeki yük "
            f"%{d_cfd:.2f} değişti (aerodinamik yük neredeyse sabit) ama FEA'ya "
            f"taşınan yük %{d_fea:.1f} değişti ve aktarım artığı {sicrama:.1f} "
            f"puan sıçradı. Yakınsama gerçek olabilir ama SEBEBİ fizik değil "
            f"yük-aktarım eşlemesinin bozulması olabilir: CFD yüzeyi deforme "
            f"olurken yük haritasının dayandığı FEA yüzeyi referans konumda "
            f"kalıyor. İki konfigürasyon karışıyor."
            if surulu else
            f"aerodinamik yük %{d_cfd:.2f}, FEA yüküne taşınan %{d_fea:.2f} "
            f"değişti; aktarım artığı sıçraması {sicrama:.1f} puan"),
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__.strip().splitlines()[-2].strip())
        return 2
    vaka = KuplajVakasi(run_dir=Path(args[0]), kuru="--kuru" in sys.argv)
    r = fsi_kos(vaka)
    print(json.dumps(r, indent=2, ensure_ascii=False)[:2000])
    (KOK / "fsi_kuplaj.json").write_text(
        json.dumps(r, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("-> fsi_kuplaj.json")
    return 0 if r.get("yakinsadi") or vaka.kuru else 1


if __name__ == "__main__":
    raise SystemExit(main())
