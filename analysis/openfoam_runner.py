"""
OpenFOAM CFD wrapper — STL'den otomatik harici aerodinamik analizi.

UYARI / DISCLAIMER
==================
Bu modül "her STL'den otomatik CFD" yapmaya çalışır. Bu araştırma seviyesinde
zor bir problem; sonuçların doğruluğu büyük ölçüde geometriye, mesh'e ve
default parametrelere bağlıdır. Konservatif default'larla başlar; profesyonel
sonuçlar için manuel tuning gerekebilir.

Strateji
--------
1) STL yi case/constant/triSurface/<name>.stl olarak kopyala
2) Bbox'tan harici domain üret (10× upstream, 30× downstream, 10× yan)
3) blockMeshDict + snappyHexMeshDict + system/* dosyalarını yaz
4) WSL içinde OpenFOAM 11 ile:
   surfaceFeatures -> blockMesh -> snappyHexMesh -overwrite -> simpleFoam
5) postProcessing/forceCoeffs1/0/coefficient.dat'ı oku

Solver: simpleFoam (steady incompressible), turbulence: k-omegaSST
"""

from __future__ import annotations

import importlib.util
import math
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh


def _default_processors() -> int:
    """CFD için optimal MPI rank sayısı = FİZİKSEL çekirdek (host değil, arka uç).

    Open MPI fiziksel çekirdeği 'slot' sayar; mantıksal (hyperthread) sayısı verirsek
    'not enough slots' hatası. Ayrıca CFD bellek-bant sınırlı → hyperthread ~fayda yok.
    `lscpu -p=Core` benzersiz çekirdek = fiziksel. .wslconfig sınırını da yansıtır.
    """
    try:
        from .backend import linux_run as _lr
        r = _lr("lscpu -p=Core 2>/dev/null | grep -v '^#' | sort -u | wc -l", 15)
        n = int(r.stdout.strip())
        if n < 1:
            raise ValueError
        return max(1, min(n, 8))           # pratik tavan 8 (bellek koruması)
    except Exception:
        try:
            from .backend import linux_run as _lr
            r = _lr("nproc", 15)
            return max(1, min(int(r.stdout.strip()) // 2, 8))   # mantıksal/2 ≈ fiziksel
        except Exception:
            return max(1, (os.cpu_count() or 4) // 2)

from .backend import (  # noqa: E402
    WSL_DISTRO,  # geriye-uyum: supersonic_cfd vb. buradan içe aktarır
    ext4_enabled,
    linux_home,
    linux_popen,
    linux_run,
)
from .ccx_runner import windows_to_wsl_path  # noqa: E402
from .thresholds import (  # noqa: E402
    ASPECT_LIMIT,
    NONORTHO_LIMIT,
    NONORTHO_REJECT,
    RESIDUAL_TARGET,
    SKEW_LIMIT,
    SKEW_REJECT,
)

# OpenFOAM 11 (Foundation) bashrc
OF_BASHRC = "/opt/openfoam11/etc/bashrc"
# ParaView'sız environment (headless WSL'de pvserver --version takılabiliyor).
# vader single-copy: WSL'de CMA (process_vm_readv) engelli — OpenMPI paylaşımlı
# bellek aktarımı süresiz asılıyor; bilinen çözüm mekanizmayı kapatmak.
# HWLOC_COMPONENTS=-gl: KRİTİK — hwloc'un GL bileşeni GPU-topolojisi için X-sunucusuna
# (127.0.0.1:6001, DISPLAY=:0 WSLg) bağlanıp SÜRESİZ asılıyordu → mpirun -np 1 bile
# launch'ta donuyordu (strace ile bulundu). GL'i kapatınca parallel mpirun ÇALIŞIR.
# unset FOAM_SIGFPE: bashrc boş-tanımlı export ediyor, .org sigFpe varlık-bazlı.
OF_ENV_PREFIX = (
    "export ParaView_TYPE=none && "
    "export OMPI_MCA_btl_vader_single_copy_mechanism=none && "
    "export HWLOC_COMPONENTS=-gl && "
    f"source {OF_BASHRC} && unset FOAM_SIGFPE && "
)


_FOAM_GECERSIZ = re.compile(r"[^A-Za-z0-9_.\-]")


def foam_word(ad: str) -> str:
    """Adı geçerli bir OpenFOAM `word` token'ına çevir (dosya/yüzey adı için).

    ÖLÇÜLEN KUSUR (2026-08-15, konteyner): REST ucu yüklenen dosyayı rastgele
    onaltılık adla saklıyor; `3b8737f31c36.stl` gibi RAKAMLA BAŞLAYAN bir ad
    snappyHexMeshDict'e anahtar olarak yazılınca OpenFOAM onu `3` sayısı +
    `b8737f31c36.stl` kelimesi diye ayrıştırdı ve

        FOAM FATAL IO ERROR: Expected a '(' or a '{' while reading List

    ile düştü. Onaltılık adların ~%62'si rakamla başlar, yani ucun ÇOĞU
    çağrısı düşerdi. Kusur uca değil BU KATMANA aittir: sözlüğü yazan burası,
    dolayısıyla token'ın geçerliliğini garanti etmesi gereken de burası --- ve
    eski kod yalnız boşluğu temizleyerek sorunun varlığını zaten kabul ediyordu.

    Ad DEĞİŞTİĞİNDE dosya o adla kopyalanır; case içi tutarlılık korunur.
    """
    t = _FOAM_GECERSIZ.sub("_", ad)
    if not t or not (t[0].isalpha() or t[0] == "_"):
        t = "g_" + t                    # rakamla/noktayla başlayan ad -> ön ek
    return t


@dataclass
class CFDCase:
    """OpenFOAM külesinin tanımı."""
    name: str
    stl_path: Path                 # Windows path
    velocity: float = 30.0         # m/s, freestream
    flow_direction: tuple[float, float, float] = (1.0, 0.0, 0.0)
    rho: float = 1.225             # kg/m^3
    nu: float = 1.5e-5             # m^2/s (hava ~15 °C)
    turbulence_intensity: float = 0.01   # %1
    domain_upstream: float = 5.0   # bbox boyu çarpanı
    domain_downstream: float = 15.0
    domain_lateral: float = 5.0
    refinement_min: int = 1        # snappyHexMesh surface min level
    refinement_max: int = 2
    n_layers: int = 0              # 0 = boundary layer eklenmesin (kararlılık için)
    first_layer_thickness: float | None = None  # m; None = göreli snappy varsayılanı
    propeller: dict | None = None  # {cap_m, area, Cp, Ct} — aktüatör disk (Froude)
    turbulence_model: str = "kOmegaSST"   # kOmegaSSTLM = Langtry-Menter gecis modeli
    bg_bilgi: dict | None = None   # arka plan hucre secimi (build_case doldurur)
    compressible: bool = False     # True: foamRun -solver fluid (Mach>0.3 için)
    t_inf: float = 288.15          # K
    p_inf: float = 101325.0       # Pa (sıkışabilir yolda mutlak basınç)
    bg_cell_size: float | None = None  # None = otomatik (L/8)
    end_time: int = 300            # SIMPLE iterasyonu
    write_interval: int = 100
    n_processors: int = 0          # 0 = otomatik (WSL nproc, max 8)
    max_global_cells: int = 1_500_000  # snappyHexMesh hücre tavanı (RAM koruması)
    ground_clearance: float | None = None  # m; verilirse taban = sabit noSlip zemin
                                           # (Ahmed-tipi zemin-etkili validasyon; incompressible)
    # ── ZAMAN-ÇÖZÜNÜR (URANS) ────────────────────────────────────────────
    # Kararlı-RANS limit çevrimine girdiğinde hüküm "önerilen sonraki çözüm
    # yolu URANS" diyor ve `urans_kapisi` reçeteyi (Δt, adım, süre) üretiyordu
    # — ama koşumu YOKTU: kullanıcı case'i elle kurmak zorundaydı. Bu üç alan
    # o boşluğu kapatır. VARSAYILAN KAPALI: `transient=False` iken yazılan
    # her sözlük birebir eskisi gibidir.
    transient: bool = False
    delta_t: float | None = None      # s; None ve transient ise reçete zorunlu
    end_time_s: float | None = None   # s; toplam fiziksel süre
    n_outer: int = 2                  # PIMPLE dış döngüsü (>1 = gevşetilmiş PISO)
    max_courant: float = 5.0          # adjustableTimeStep ile üst sınır
    refinement_regions: list | None = None # hedefli bölge-refinement kutuları:
                                           # [{"ad", "min":(x,y,z), "max":(x,y,z), "level"}]
                                           # (gövde-altı/iz gibi yüzeyden-uzak kritik bölgeler;
                                           # max_global_cells tavanı yine geçerli)

    @property
    def lref(self) -> float:
        """Referans uzunluk: bbox max boyutu (ilk erişimde STL'den; sonra cache)."""
        cached = getattr(self, "_lref", None)
        if cached is not None:
            return cached
        m = trimesh.load(str(self.stl_path), force="mesh")
        val = (float((m.bounds[1] - m.bounds[0]).max())
               if isinstance(m, trimesh.Trimesh) else 1.0)
        self._lref = val
        return val


@dataclass
class CFDResult:
    case_dir: Path
    success: bool
    return_code: int
    stdout: str
    stderr: str
    cd: float | None = None
    cl: float | None = None
    cm: float | None = None
    forces_history: list[tuple[int, float, float, float]] = field(default_factory=list)
    log_files: list[Path] = field(default_factory=list)
    # ASAMA TELEMETRISI — DOGRUDAN olculur. Once bu yoktu ve sureler rapor
    # icin LOG DOSYALARININ DEGISIM ZAMANLARINDAN cikariliyordu; o yontem
    # dosyaya dokunan her sey (kopyalama, yedekleme, senkron) tarafindan
    # bozulur ve yalniz asama SINIRLARINI verir, kaynak kullanimini vermez.
    asama_sureleri: list[dict] = field(default_factory=list)
    bellek: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Domain ve dosya yardımcıları
# ---------------------------------------------------------------------------

def _compute_domain(stl_path: Path, case: CFDCase) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """STL'den domain bbox'ı ve geometri merkezi hesaplar.

    Returns:
        (domain_min, domain_max, geom_min, geom_max)
    """
    m = trimesh.load(str(stl_path), force="mesh")
    if not isinstance(m, trimesh.Trimesh):
        raise ValueError(f"STL yüklenemedi: {stl_path}")
    gmin = m.bounds[0].astype(np.float64)
    gmax = m.bounds[1].astype(np.float64)
    size = gmax - gmin
    L = float(size.max())

    # Akış yönü +x kabul edildi (case.flow_direction'a göre döndürmüyoruz)
    dmin = gmin.copy()
    dmax = gmax.copy()
    dmin[0] -= L * case.domain_upstream
    dmax[0] += L * case.domain_downstream
    dmin[1] -= L * case.domain_lateral
    dmax[1] += L * case.domain_lateral
    if case.ground_clearance is not None:
        dmin[2] = gmin[2] - case.ground_clearance   # taban = zemin düzlemi
    else:
        dmin[2] -= L * case.domain_lateral
    dmax[2] += L * case.domain_lateral
    return dmin, dmax, gmin, gmax


def _foam_header(class_: str, object_: str, location: str = "") -> str:
    loc = f'\n    location    "{location}";' if location else ""
    return (
        "/*--------------------------------*- C++ -*----------------------------------*/\n"
        "FoamFile\n{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        f"    class       {class_};{loc}\n"
        f"    object      {object_};\n"
        "}\n"
        "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n"
    )


def mesh_quality_gate(checkmesh_text: str) -> dict:
    """checkMesh çıktısını çöz + ÇÖZÜCÜ-ÖNCESİ verdict: 'ok' / 'warn' / 'reject'.
    Kötü mesh çözücüde saatlerce diverjyor/timeout'a uğruyor; bunu ÖNCEDEN yakala.
    Eşikler `thresholds.py`'den (TEK KAYNAK): warn = proje konvansiyonu
    (nonOrtho<70, skew<4), reject = diverjans deneyimi (75 / 6).
    Döner: {verdict, reasons[], non_ortho_max, skew_max, aspect_max, negatif_hacim}."""
    import re as _re

    # SAYI DESENI TEK YERDE: elle yazilan karakter siniflari bu dosyada gercek bir
    # COKMEYE yol acti. Eski desen `([\d.eE+]+)` idi ve EKSI USSU KAPSAMIYORDU:
    # "Max skewness = 9.8987286e-05" -> "9.8987286e" yakalanip float() ValueError
    # atiyordu ve TUM analiz cokuyordu. Ustelik bu YALNIZ skewness KUCUKken olur,
    # yani mesh IYIYKEN — kalite kapisi iyi mesh'te patliyordu. Guvenilirlik
    # taramasinda 12 geometrinin 3'u tam bu sebeple coktu (%25).
    SAYI = r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"

    def g(pat):
        m = _re.search(pat, checkmesh_text)
        if not m:
            return None
        try:
            return float(m.group(1))
        # sessiz-yutma: kabul — ayristirilamayan metrik "sorun yok" SAYILMAZ; None
        # doner ve asagidaki kapi onu "okunamadi" olarak isler (bkz. 2eb2686).
        except ValueError:
            return None
    non_ortho = g(r"non-orthogonality Max:\s*" + SAYI)
    skew = g(r"Max skewness\s*=\s*" + SAYI)
    aspect = g(r"Max aspect ratio\s*[=:]?\s*" + SAYI)
    neg_vol = "negative volume" in checkmesh_text.lower()
    reasons, verdict = [], "ok"
    # REJECT: çözücü neredeyse kesin patlar
    if neg_vol:
        reasons.append("negatif hacimli hücre (mesh bozuk)"); verdict = "reject"
    if non_ortho is not None and non_ortho >= NONORTHO_REJECT:
        reasons.append(f"aşırı non-ortogonallik ({non_ortho:.0f}°≥{NONORTHO_REJECT:.0f})")
        verdict = "reject"
    if skew is not None and skew >= SKEW_REJECT:
        reasons.append(f"aşırı skewness ({skew:.1f}≥{SKEW_REJECT:.0f})"); verdict = "reject"
    # WARN: sınırda; koşabilir ama dikkat
    if verdict != "reject":
        if non_ortho is not None and NONORTHO_LIMIT <= non_ortho < NONORTHO_REJECT:
            reasons.append(f"yüksek non-ortogonallik ({non_ortho:.0f}°, eşik {NONORTHO_LIMIT:.0f})")
            verdict = "warn"
        if skew is not None and SKEW_LIMIT <= skew < SKEW_REJECT:
            reasons.append(f"yüksek skewness ({skew:.1f}, eşik {SKEW_LIMIT:.0f})"); verdict = "warn"
        if aspect is not None and aspect > ASPECT_LIMIT:
            reasons.append(f"çok yüksek aspect ratio ({aspect:.0e})"); verdict = "warn"
    return {"verdict": verdict, "reasons": reasons, "non_ortho_max": non_ortho,
            "skew_max": skew, "aspect_max": aspect, "negatif_hacim": neg_vol,
            "mesh_ok": "Mesh OK" in checkmesh_text}


# ---------------------------------------------------------------------------
# Dictionary yazıcılar
# ---------------------------------------------------------------------------

ARKA_PLAN_BUTCE_PAYI = 0.25   # arka plan mesh'i bütçenin en fazla bu kadarını yesin


def arka_plan_hucre_boyu(dmin, dmax, istenen: float, max_global_cells: int,
                         pay: float = ARKA_PLAN_BUTCE_PAYI) -> tuple[float, dict]:
    """Arka plan hücresini DOMAIN ve BÜTÇEDEN boyutlandır (yalnız geometriden DEĞİL).

    KÖK SEBEP: `bg_cell_size` geometriden hesaplanıyordu (lmax/bg_div) ama hücre
    SAYISINI domain belirler. MiniHawk'ta ölçüldü: gövde 0.7×1.5×0.08 m, domain
    38×22.5×21 m, istenen hücre 0.167 m → arka plan TEK BAŞINA 3.94M hücre, oysa
    `hassas` tavanı 2.5M. snappyHexMesh daha ilk adımda bütçeyi tüketti ve kendi
    logunda şunu yazdı:
        "No cells marked for refinement since reached limit 2500000."
    Sonuç: HİÇBİR yüzey iyileştirmesi yapılmadı. Uçağın tamamı 74 yüzle temsil
    edildi (uzak-alan yamaları 17-31 bin yüz). Bu tek kusur y⁺≈5000'i, 12 katmanın
    0 örülmesini, Cl'in beklenenin 1/16'sı çıkmasını ve GCI %379'u birlikte açıklar.

    İstenen boyu KABALAŞTIRIR (asla inceltmez): iyileştirmeye yer kalması için arka
    plan bütçenin en fazla `pay` kadarını yemeli.
    """
    boy = [float(dmax[i] - dmin[i]) for i in range(3)]
    hacim = boy[0] * boy[1] * boy[2]
    tavan = max(int(max_global_cells * pay), 10_000)
    gerekli = (hacim / tavan) ** (1.0 / 3.0)
    secilen = max(float(istenen), gerekli)
    n = [max(int(math.ceil(b / secilen)), 8) for b in boy]
    return secilen, {
        "istenen_m": round(float(istenen), 5),
        "secilen_m": round(secilen, 5),
        "kabalastirildi": secilen > float(istenen) * 1.001,
        "domain_m": [round(b, 3) for b in boy],
        "arka_plan_hucre": n[0] * n[1] * n[2],
        "butce": max_global_cells,
        "butce_payi": pay,
    }


def _bellek_gb() -> tuple[float, float] | None:
    """(kullanilan_GB, toplam_GB) — psutil yoksa None ('olculemedi')."""
    if importlib.util.find_spec("psutil") is None:
        return None
    import psutil
    m = psutil.virtual_memory()
    return (m.total - m.available) / 1e9, m.total / 1e9


def parse_iyilestirme_acligi(log_text: str) -> dict:
    """snappy iyileştirme bütçesini tüketti mi? KENDİ log satırından ölç."""
    m = re.findall(r"No cells marked for refinement since reached limit (\d+)", log_text)
    return {"aclik": bool(m), "kez": len(m),
            "limit": int(m[0]) if m else None}


YUZEY_YUZ_ESIGI = 500
"""Gövde yamasının MUTLAK tabanı — geometriden bağımsız. Bu tek başına KABA bir
ölçüttür: 500 yüz, 4 m'lik bir kanadı da 4 cm'lik bir fini de "yeterli" sayar.
Asıl ölçüt aşağıdaki geometri-göreli kriterdir; bu sayı yalnızca hiçbir
geometride savunulamayacak alt sınırı tutar. Çağıranların da bunu BİLMESİ
gerekiyor: GCI seviyesi üretirken eşiğin altına düşecek bir kademeyi koşmak,
saatlerce CFD harcayıp sonunda reddedilmek demektir (çapa kampanyasında küp kaba
seviyeleri 176 ve 436 yüzle böyle harcandı)."""

OZELLIK_BASINA_HUCRE = 4
"""En küçük geometrik özellik boyunca istenen en az yüzey hücresi. 4 hücre, bir
özelliğin eğriliğini parçalı-lineer temsil edebilmenin pratik alt sınırıdır (2
hücre yalnız bir basamak, 3 hücre tek kırılım verir). Kaynak: snappyHexMesh
`nCellsBetweenLevels` varsayılanı da aynı mertebededir (3)."""


def yuzey_cozunurluk_hukmu(log_snappy: str, yuzey_yuz: int | None,
                           en_kucuk_boyut_m: float | None = None,
                           yuzey_alani_m2: float | None = None) -> dict:
    """Gövde GERÇEKTEN çözüldü mü? NİYET değil, SONUÇ ölçülür.

    Mevcut `resolution_warning` yüzey hücresini (lmax/bg_div)/2^ref_max diye
    NİYETTEN hesaplıyordu — yani iyileştirmenin uygulandığını VARSAYIYOR. MiniHawk'ta
    0.010 m rapor edip "sorun yok" derken snappy 0.167 m teslim etmişti.

    ÖLÇÜT GEOMETRİYE GÖRELİDİR. Sabit yüz sayısı, aynı sayıyı 4 m'lik kanada da
    4 cm'lik fine de uygular. Yüzey alanı ve en küçük özellik verilirse tipik
    yüzey hücresi h=√(A/N) ölçülür ve h ≤ özellik/4 istenir; verilmezse bu ölçüt
    UYGULANMADI diye yazılır — sessizce "geçti" sayılmaz. `en_kucuk_boyut_m`
    imzada zaten vardı ama gövdede HİÇ kullanılmıyordu.
    """
    ac = parse_iyilestirme_acligi(log_snappy)
    gerekce = []
    if ac["aclik"]:
        gerekce.append(
            f"snappyHexMesh iyilestirme butcesini TUKETTI (limit {ac['limit']}, "
            f"{ac['kez']} kez) — arka plan mesh'i tek basina tavani doldurmus, "
            "govde yuzeyi HIC iyilestirilmemis olabilir")
    if yuzey_yuz is not None and yuzey_yuz < YUZEY_YUZ_ESIGI:
        gerekce.append(f"govde yamasi yalnizca {yuzey_yuz} yuz — mutlak tabanin "
                       f"({YUZEY_YUZ_ESIGI}) altinda, hicbir geometride savunulamaz")

    goreli: dict = {"uygulandi": False}
    if yuzey_yuz and yuzey_alani_m2 and en_kucuk_boyut_m:
        h = math.sqrt(yuzey_alani_m2 / yuzey_yuz)
        h_gereken = en_kucuk_boyut_m / OZELLIK_BASINA_HUCRE
        n_gereken = int(math.ceil(yuzey_alani_m2 / (h_gereken * h_gereken)))
        hucre_sayisi = en_kucuk_boyut_m / h
        goreli = {"uygulandi": True, "h_yuzey_m": round(h, 6),
                  "h_gereken_m": round(h_gereken, 6),
                  "en_kucuk_ozellik_m": en_kucuk_boyut_m,
                  "gereken_yuz": n_gereken,
                  "ozellik_basina_hucre": round(hucre_sayisi, 2),
                  "ozellik_cozuldu": bool(hucre_sayisi >= OZELLIK_BASINA_HUCRE)}
        if hucre_sayisi < OZELLIK_BASINA_HUCRE:
            goreli["hukum"] = (
                f"EN KUCUK OZELLIK COZULMEDI: yuzey hucresi h={h * 1000:.2f} mm, "
                f"ozellik {en_kucuk_boyut_m * 1000:.2f} mm boyunca yalnizca "
                f"{hucre_sayisi:.2f} hucre var (gereken {OZELLIK_BASINA_HUCRE}); "
                f"~{n_gereken:,} yuz gerekirdi, {yuzey_yuz:,} var. Bu ozellik "
                "geometrik olarak YOK sayilmistir — ince firar kenari, kenar "
                "yuvarlatmasi ya da kucuk cikinti temsil edilmiyor ve surtunme/"
                "form surukleme bilesenleri bundan etkilenir.")
    else:
        goreli["neden"] = ("yuzey alani ve/veya en kucuk ozellik verilmedi — "
                           "geometri-goreli olcum YAPILMADI")
    # NEDEN ENGELLEYICI DEGIL: en ince ozellik (0.5-1.5 mm firar kenari) uzerine
    # 4 hucre istemek, 0.7 m'lik bir kanatta ~13 milyon yuzey yuzu demektir. Bu
    # hex-mesh'in bilinen siniridir, o kosunun kusuru degil. Engelleyici yapmak
    # her ince-kesitli kosuyu reddederdi ve kapi bilgi TASIMAZ hale gelirdi.
    # Ama SESSIZ de kalamaz: olcum her zaman raporlanir ve tuketiciler
    # `geometri_goreli.ozellik_cozuldu` alanini okuyabilir.
    return {"cozuldu": not gerekce, "gerekce": gerekce,
            "yuzey_yuz": yuzey_yuz, "geometri_goreli": goreli, **ac}


def _write_block_mesh(case_dir: Path, dmin: np.ndarray, dmax: np.ndarray,
                      cell_size: float, ground: bool = False) -> None:
    nx = max(int(math.ceil((dmax[0] - dmin[0]) / cell_size)), 8)
    ny = max(int(math.ceil((dmax[1] - dmin[1]) / cell_size)), 8)
    nz = max(int(math.ceil((dmax[2] - dmin[2]) / cell_size)), 8)

    txt = _foam_header("dictionary", "blockMeshDict", "system")
    txt += "convertToMeters 1.0;\n\n"
    txt += "vertices\n(\n"
    v = [
        (dmin[0], dmin[1], dmin[2]),
        (dmax[0], dmin[1], dmin[2]),
        (dmax[0], dmax[1], dmin[2]),
        (dmin[0], dmax[1], dmin[2]),
        (dmin[0], dmin[1], dmax[2]),
        (dmax[0], dmin[1], dmax[2]),
        (dmax[0], dmax[1], dmax[2]),
        (dmin[0], dmax[1], dmax[2]),
    ]
    for x, y, z in v:
        txt += f"    ({x:.6f} {y:.6f} {z:.6f})\n"
    txt += ");\n\n"
    txt += f"blocks\n(\n    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)\n);\n\n"
    txt += "edges\n(\n);\n\n"
    bottom_type = "wall" if ground else "patch"
    txt += (
        "boundary\n(\n"
        "    inlet     { type patch; faces ((0 4 7 3)); }\n"
        "    outlet    { type patch; faces ((1 2 6 5)); }\n"
        "    top       { type patch; faces ((3 7 6 2)); }\n"
        f"    bottom    {{ type {bottom_type}; faces ((0 1 5 4)); }}\n"
        "    front     { type patch; faces ((0 3 2 1)); }\n"
        "    back      { type patch; faces ((4 5 6 7)); }\n"
        ");\n\n"
        "mergePatchPairs\n(\n);\n"
    )
    (case_dir / "system" / "blockMeshDict").write_text(txt)


def _write_snappy(case_dir: Path, stl_name: str, surface_name: str,
                   inside_pt: tuple[float, float, float], case: CFDCase) -> None:
    max_local = max(case.max_global_cells // 4, 100_000)
    txt = _foam_header("dictionary", "snappyHexMeshDict", "system")
    txt += (
        "castellatedMesh true;\n"
        "snap            true;\n"
        f"addLayers       {'true' if case.n_layers > 0 else 'false'};\n\n"
    )
    rregions = case.refinement_regions or []
    txt += (
        "geometry\n{\n"
        f"    {stl_name}\n"
        "    {\n"
        "        type triSurfaceMesh;\n"
        f"        name {surface_name};\n"
        "    }\n"
    )
    for rr in rregions:
        mn, mx = rr["min"], rr["max"]
        txt += (f"    {rr['ad']} {{ type searchableBox; "
                f"min ({mn[0]:.6f} {mn[1]:.6f} {mn[2]:.6f}); "
                f"max ({mx[0]:.6f} {mx[1]:.6f} {mx[2]:.6f}); }}\n")
    txt += "}\n\n"
    rregion_txt = "".join(
        f"        {rr['ad']} {{ mode inside; levels ((1e15 {int(rr['level'])})); }}\n"
        for rr in rregions)
    txt += (
        "castellatedMeshControls\n{\n"
        f"    maxLocalCells       {max_local};\n"
        f"    maxGlobalCells      {case.max_global_cells};\n"
        "    minRefinementCells  10;\n"
        "    nCellsBetweenLevels 3;\n"
        "    maxLoadUnbalance    0.10;\n"
        "    features\n    (\n"
        f"        {{ file \"{surface_name}.eMesh\"; level {case.refinement_max}; }}\n"
        "    );\n"
        "    refinementSurfaces\n    {\n"
        f"        {surface_name}\n"
        "        {\n"
        f"            level ({case.refinement_min} {case.refinement_max});\n"
        "            patchInfo { type wall; }\n"
        "        }\n"
        "    }\n"
        "    refinementRegions\n    {\n" + rregion_txt + "    }\n"
        f"    locationInMesh ({inside_pt[0]:.6f} {inside_pt[1]:.6f} {inside_pt[2]:.6f});\n"
        "    allowFreeStandingZoneFaces true;\n"
        "    resolveFeatureAngle 30;\n"
        "}\n\n"
    )
    txt += (
        "snapControls\n{\n"
        "    nSmoothPatch    3;\n"
        "    tolerance       2.0;\n"
        "    nSolveIter      30;\n"
        "    nRelaxIter      5;\n"
        "    nFeatureSnapIter 10;\n"
        "    implicitFeatureSnap false;\n"
        "    explicitFeatureSnap true;\n"
        "    multiRegionFeatureSnap false;\n"
        "}\n\n"
    )
    if case.first_layer_thickness:
        h1 = case.first_layer_thickness
        sizing = (
            "    relativeSizes false;\n"
            f"    firstLayerThickness {h1:.6e};\n"
            f"    minThickness {h1 * 0.25:.6e};\n"
            "    expansionRatio 1.25;\n"
        )
    else:
        sizing = (
            "    relativeSizes true;\n"
            "    expansionRatio 1.2;\n"
            "    finalLayerThickness 0.5;\n"
            "    minThickness 0.1;\n"
        )
    txt += (
        "addLayersControls\n{\n"
        + sizing +
        "    layers\n    {\n"
        f"        {surface_name} {{ nSurfaceLayers {max(case.n_layers, 0)}; }}\n"
        "    }\n"
        "    nGrow 0;\n"
        "    featureAngle 130;\n"
        "    nRelaxIter 5;\n"
        "    nSmoothSurfaceNormals 1;\n"
        "    nSmoothNormals 3;\n"
        "    nSmoothThickness 10;\n"
        "    maxFaceThicknessRatio 0.5;\n"
        "    maxThicknessToMedialRatio 0.3;\n"
        "    minMedialAxisAngle 90;\n"
        "    nBufferCellsNoExtrude 0;\n"
        "    nLayerIter 50;\n"
        "}\n\n"
    )
    txt += (
        "meshQualityControls\n{\n"
        "    maxNonOrtho 65;\n"
        "    maxBoundarySkewness 20;\n"
        "    maxInternalSkewness 4;\n"
        "    maxConcave 80;\n"
        "    minVol 1e-13;\n"
        "    minTetQuality 1e-15;\n"
        "    minArea -1;\n"
        "    minTwist 0.02;\n"
        "    minDeterminant 0.001;\n"
        "    minFaceWeight 0.05;\n"
        "    minVolRatio 0.01;\n"
        "    minTriangleTwist -1;\n"
        "    nSmoothScale 4;\n"
        "    errorReduction 0.75;\n"
        "}\n\n"
        "writeFlags ( scalarLevels layerSets layerFields );\n"
        "mergeTolerance 1e-6;\n"
    )
    (case_dir / "system" / "snappyHexMeshDict").write_text(txt)


def _write_surface_features(case_dir: Path, stl_name: str) -> None:
    txt = _foam_header("dictionary", "surfaceFeaturesDict", "system")
    txt += (
        f"surfaces (\"{stl_name}\");\n\n"
        "includedAngle 150;\n"
        "subsetFeatures\n{\n    nonManifoldEdges no;\n    openEdges yes;\n}\n"
        "writeObj yes;\n"
    )
    (case_dir / "system" / "surfaceFeaturesDict").write_text(txt)


def _write_control_dict(case_dir: Path, case: CFDCase, surface_name: str,
                          lref: float, wake_x: float | None = None) -> None:
    txt = _foam_header("dictionary", "controlDict", "system")
    solver = "fluid" if case.compressible else "incompressibleFluid"
    if case.transient:
        # ZAMAN-COZUNUR: endTime SANIYE, deltaT gercek zaman adimi. writeControl
        # adjustableRunTime cunku adjustableTimeStep ile dt degisir ve timeStep
        # tabanli yazim duzensiz araliklar uretir — sonradan frekans olcumu
        # duzgun ornekleme ister.
        dt = case.delta_t or 1e-3
        son = case.end_time_s or (dt * 2000)
        yaz = max(son / 100.0, dt)         # ~100 anlik goruntu
        txt += (
            "application     foamRun;\n"
            f"solver          {solver};\n\n"
            "startFrom       startTime;\n"
            "startTime       0;\n"
            "stopAt          endTime;\n"
            f"endTime         {son:g};\n"
            f"deltaT          {dt:g};\n\n"
            "writeControl    adjustableRunTime;\n"
            f"writeInterval   {yaz:g};\n"
            "adjustableTimeStep yes;\n"
            f"maxCo           {case.max_courant:g};\n"
            "purgeWrite      5;\n")
    else:
        txt += (
        "application     foamRun;\n"
        f"solver          {solver};\n\n"
        "startFrom       startTime;\n"
        "startTime       0;\n"
        "stopAt          endTime;\n"
        f"endTime         {case.end_time};\n"
        "deltaT          1;\n\n"
        "writeControl    timeStep;\n"
        f"writeInterval   {case.write_interval};\n"
        "purgeWrite      2;\n")
    txt += (
        "writeFormat     ascii;\n"
        "writePrecision  8;\n"
        "writeCompression off;\n"
        "timeFormat      general;\n"
        "timePrecision   6;\n"
        "runTimeModifiable true;\n\n"
    )
    fx, fy, fz = case.flow_direction
    # Lift yönü: akış yönüne dik, x-z düzleminde (alpha != 0'da (0,0,1) yanlış olur)
    lift = (-fz, 0.0, fx)
    norm = math.sqrt(lift[0]**2 + lift[2]**2) or 1.0
    lift = (lift[0]/norm, 0.0, lift[2]/norm)
    Aref = lref * lref
    txt += (
        "functions\n{\n"
        "    forceCoeffs1\n    {\n"
        "        type            forceCoeffs;\n"
        "        libs            (\"libforces.so\");\n"
        "        writeControl    timeStep;\n"
        "        writeInterval   1;\n"
        f"        patches         ({surface_name});\n"
        "        rho             rhoInf;\n"
        f"        rhoInf          {case.rho};\n"
        f"        liftDir         ({lift[0]} {lift[1]} {lift[2]});\n"
        f"        dragDir         ({fx} {fy} {fz});\n"
        "        CofR            (0 0 0);\n"
        "        pitchAxis       (0 1 0);\n"
        f"        pRef            {case.p_inf if case.compressible else 0};\n"
        f"        magUInf         {case.velocity};\n"
        f"        lRef            {lref:.6f};\n"
        f"        Aref            {Aref:.6f};\n"
        "    }\n"
    )
    # İz-düzlemi örnekleme (far-field momentum-açığı drag için U,p) — akış-dik kesit
    if wake_x is not None:
        txt += (
            "    wakePlane\n    {\n"
            "        type            surfaces;\n"
            "        libs            (\"libsampling.so\");\n"
            "        writeControl    writeTime;\n"
            "        surfaceFormat   vtk;\n"
            "        fields          (p U);\n"
            "        interpolationScheme cellPoint;\n"
            "        surfaces\n        (\n"
            "            wake\n            {\n"
            "                type        cutPlane;\n"
            "                planeType   pointAndNormal;\n"
            f"                point       ({wake_x:.6f} 0 0);\n"
            "                normal      (1 0 0);\n"
            "                interpolate true;\n"
            "            }\n        );\n"
            "    }\n"
        )
    txt += "}\n"
    (case_dir / "system" / "controlDict").write_text(txt)


def _write_fv_schemes(case_dir: Path, transient: bool = False) -> None:
    txt = _foam_header("dictionary", "fvSchemes", "system")
    # `bounded` ön-eki YALNIZ kararlı-hal içindir: div(phi,U) terimindeki
    # süreklilik hatasını SIMPLE yakınsaması boyunca sınırlar. Zaman-çözünürde
    # süreklilik her adımda zaten sağlanır ve `bounded` ikinci-mertebe zaman
    # doğruluğunu bozar.
    b = "" if transient else "bounded "
    txt += (
        ("ddtSchemes      { default backward; }\n\n" if transient
         else "ddtSchemes      { default steadyState; }\n\n") +
        "gradSchemes\n{\n"
        "    default         Gauss linear;\n"
        "    grad(U)         cellLimited Gauss linear 1;\n"
        "    grad(p)         Gauss linear;\n"
        "}\n\n"
        "divSchemes\n{\n"
        "    default                                 none;\n"
        f"    div(phi,U)                              {b}Gauss linearUpwind grad(U);\n"
        f"    div(phi,k)                              {b}Gauss upwind;\n"
        f"    div(phi,omega)                          {b}Gauss upwind;\n"
        f"    div(phi,nuTilda)                        {b}Gauss upwind;\n"
        # Gecis modeli (kOmegaSSTLM) iki ek tasima denklemi cozer. `default none`
        # altinda semasi tanimsiz her div terimi cozucuyu dusurur; kOmegaSST'de
        # bu terimler hic olusmadigi icin kosulsuz yazmak zararsizdir.
        f"    div(phi,gammaInt)                       {b}Gauss upwind;\n"
        f"    div(phi,ReThetat)                       {b}Gauss upwind;\n"
        f"    div(phi,e)                              {b}Gauss upwind;\n"
        f"    div(phi,h)                              {b}Gauss upwind;\n"
        f"    div(phi,K)                              {b}Gauss upwind;\n"
        f"    div(phi,Ekp)                            {b}Gauss upwind;\n"
        "    div(phid,p)                             Gauss upwind;\n"
        "    div(phi,(p|rho))                        Gauss upwind;\n"
        "    div(meshPhi,p)                          Gauss linear;\n"
        "    div((nuEff*dev2(T(grad(U)))))           Gauss linear;\n"
        "    div(((rho*nuEff)*dev2(T(grad(U)))))     Gauss linear;\n"
        "}\n\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
        "interpolationSchemes { default linear; }\n"
        "snGradSchemes { default corrected; }\n"
        "wallDist { method meshWave; }\n"
    )
    (case_dir / "system" / "fvSchemes").write_text(txt)


def _write_fv_solution(case_dir: Path, compressible: bool = False,
                       transient: bool = False, n_outer: int = 2) -> None:
    txt = _foam_header("dictionary", "fvSolution", "system")
    # PIMPLE SON DIŞ İTERASYONDA `<alan>Final` GİRDİSİ ARAR ve bulamazsa
    # koşuyu FATAL IO ERROR ile düşürür. Sentetik test bunu göremezdi; gerçek
    # silindir koşusu ilk zaman adımında yakaladı. Final girdisi ayrıca DAHA
    # SIKI olmalıdır (relTol 0): dış döngü bittiğinde o adımın çözümü artık
    # düzeltilmeyecektir, yani gevşek bırakılan hata zamanda birikir.
    # Makro ($p) KULLANILMAZ: tek bloğa toplamak U'ya da GAMG verirdi ve GAMG
    # simetrik olmayan momentum matrisinde uygun değildir. Her aile kendi
    # çözücüsünü korur, yalnız tolerans sıkılır.
    son = ('    pFinal\n    {\n'
           "        solver          GAMG;\n"
           "        smoother        DICGaussSeidel;\n"
           "        tolerance       1e-07;\n"
           "        relTol          0;\n"
           "    }\n"
           '    "(U|k|omega|nuTilda|e|h|gammaInt|ReThetat)Final"\n    {\n'
           "        solver          smoothSolver;\n"
           "        smoother        symGaussSeidel;\n"
           "        tolerance       1e-07;\n"
           "        relTol          0;\n"
           "    }\n") if transient else ""
    txt += (
        "solvers\n{\n"
        "    p\n    {\n"
        "        solver          GAMG;\n"
        "        smoother        DICGaussSeidel;\n"
        "        tolerance       1e-06;\n"
        "        relTol          0.1;\n"
        "    }\n"
        # GECIS MODELI ALANLARI BURADA DA OLMALI. Olculdu (2026-08-19, kure
        # capasinin ILK kosusu): fvSchemes, residualControl ve
        # relaxationFactors gammaInt/ReThetat'i ICERIYORDU ama `solvers`
        # blogu icermiyordu → "keyword ReThetat is undefined in dictionary
        # IOstream/solvers" ile ANINDA duserdi. Yani bu kosucudan gecis
        # modeli HIC calisamazmis; kimse denemedigi icin gorulmemis.
        "    \"(U|k|omega|nuTilda|e|h|gammaInt|ReThetat)\"\n    {\n"
        "        solver          smoothSolver;\n"
        "        smoother        symGaussSeidel;\n"
        "        tolerance       1e-06;\n"
        "        relTol          0.1;\n"
        "    }\n"
        + son +
        "    rho\n    {\n"
        "        solver          diagonal;\n"
        "    }\n"
        "}\n\n"
        # ZAMAN-ÇÖZÜNÜR: PIMPLE. `residualControl` BURADA YOK ve olmamalı —
        # kararlı-halde o eşik "çözüm oturdu" demektir; zaman-çözünürde koşuyu
        # ZAMANIN ORTASINDA durdururdu. Bitiş ölçütü endTime'dır.
        + (("PIMPLE\n{\n"
            f"    nOuterCorrectors {n_outer};\n"
            "    nCorrectors     2;\n"
            "    nNonOrthogonalCorrectors 1;\n"
            "    turbOnFinalIterOnly no;\n"
            "}\n\n") if transient else
           ("SIMPLE\n{\n"
            "    nNonOrthogonalCorrectors 1;\n"
            "    consistent      yes;\n"
            "    residualControl\n    {\n"
            f"        p               {RESIDUAL_TARGET:g};\n"
            f"        U               {RESIDUAL_TARGET:g};\n"
            f"        \"(k|omega|nuTilda|gammaInt|ReThetat)\" {RESIDUAL_TARGET:g};\n"
            "    }\n"
            "}\n\n"))
        # Sıkışabilir soğuk-başlangıç kararsızlığı (T<0 abort) için düşük
        # relaxation; sıkıştırılamaz yol hızlı kalır
        + ("relaxationFactors\n{\n"
           "    fields { p 0.2; rho 0.05; }\n"
           "    equations { U 0.3; \"(k|omega|nuTilda)\" 0.3; \"(e|h)\" 0.3; }\n"
           "}\n" if compressible else
           # Zaman-çözünürde relaxation 1.0: PIMPLE'ın dış döngüsü zaten
           # gevşetiyor ve alt-gevşetme ZAMAN doğruluğunu bozar (çözüm her
           # adımda tam yakınsamaz, sonuç zamanda kayar).
           "relaxationFactors\n{\n"
           "    fields { p 1; }\n"
           "    equations { U 1; \"(k|omega|nuTilda|gammaInt|ReThetat)\" 1; }\n"
           "}\n" if transient else
           "relaxationFactors\n{\n"
           "    fields { p 0.3; }\n"
           "    equations { U 0.7; \"(k|omega|nuTilda|gammaInt|ReThetat)\" 0.7; }\n"
           "}\n")
    )
    (case_dir / "system" / "fvSolution").write_text(txt)


def _write_decompose_par(case_dir: Path, n: int) -> None:
    txt = _foam_header("dictionary", "decomposeParDict", "system")
    txt += (
        f"numberOfSubdomains {n};\n"
        "method scotch;\n"
    )
    (case_dir / "system" / "decomposeParDict").write_text(txt)


def _write_transport(case_dir: Path, nu: float) -> None:
    txt = _foam_header("dictionary", "transportProperties", "constant")
    txt += (
        "transportModel  Newtonian;\n"
        f"nu              [0 2 -1 0 0 0 0] {nu};\n"
    )
    (case_dir / "constant" / "transportProperties").write_text(txt)


GECIS_MODELLERI = ("kOmegaSSTLM",)


def gecis_modeli_onkosulu(model: str, n_layers: int, yplus_target: float | None) -> str:
    """Geçiş modeli DUVAR-ÇÖZÜNÜR mesh ister — değilse SEBEBİ döndür ('' = uygun).

    Langtry-Menter, laminer bölgeyi ve geçiş noktasını sınır tabakanın İÇİNDE çözer.
    Duvar-fonksiyonu mesh'inde (y⁺ ≫ 30) laminer altkatman hiç ayrıklaştırılmaz;
    model yine bir sayı üretir ama o sayının fiziksel karşılığı YOKTUR. Bu, "makul
    görünen ama anlamsız sonuç" sınıfının ders kitabı örneğidir — bu yüzden sessizce
    koşturmak yerine ÖNCEDEN reddedilir.

    2B çapada ölçüldü (y⁺<0.61, 12 katman eşdeğeri C-grid): kOmegaSST → α_L0 −0.81°,
    kOmegaSSTLM → −2.18° (referans −2.07°). Kazanç GERÇEK, ama duvar çözünürlüğüne
    bağlı.
    """
    if model not in GECIS_MODELLERI:
        return ""
    if n_layers <= 0:
        return (f"{model} DUVAR-COZUNUR mesh ister ama prizma katmani istenmemis "
                f"(n_layers=0). Laminer altkatman ayriklastirilmadan gecis modeli "
                f"fiziksel olmayan bir sayi uretir. --kalite hassas kullanin.")
    if yplus_target is not None and yplus_target > 5.0:
        return (f"{model} icin y+ hedefi {yplus_target:g} fazla yuksek (<=1 gerekir) — "
                f"gecis noktasi cozulemez.")
    return ""


def _write_momentum(case_dir: Path, model: str = "kOmegaSST") -> None:
    """OpenFOAM 11: constant/momentumTransport"""
    txt = _foam_header("dictionary", "momentumTransport", "constant")
    txt += (
        "simulationType  RAS;\n\n"
        "RAS\n{\n"
        f"    model           {model};\n"
        "    turbulence      on;\n"
        "    printCoeffs     on;\n"
        "}\n"
    )
    (case_dir / "constant" / "momentumTransport").write_text(txt)


def _write_gecis_alanlari(case_dir: Path, surface_name: str,
                          turbulence_intensity: float) -> None:
    """Langtry-Menter'in iki ek alani. YOKSA cozucu ACIKLAMASIZ duser."""
    Tu = max(100.0 * turbulence_intensity, 0.027)
    ret0 = ((1173.51 - 589.428 * Tu + 0.2196 / Tu ** 2) if Tu <= 1.3
            else 331.5 * (Tu - 0.5658) ** -0.671)      # Menter 2006 korelasyonu
    for ad, ic in (("gammaInt", 1.0), ("ReThetat", ret0)):
        txt = _foam_header("volScalarField", ad)
        txt += (
            "dimensions      [0 0 0 0 0 0 0];\n\n"
            f"internalField   uniform {ic:.4g};\n\n"
            "boundaryField\n{\n"
            f"    {surface_name} {{ type zeroGradient; }}\n"
            f"    inlet   {{ type fixedValue; value uniform {ic:.4g}; }}\n"
            f"    outlet  {{ type inletOutlet; inletValue uniform {ic:.4g}; "
            f"value uniform {ic:.4g}; }}\n"
            f"    \".*\"    {{ type inletOutlet; inletValue uniform {ic:.4g}; "
            f"value uniform {ic:.4g}; }}\n"
            "}\n"
        )
        (case_dir / "0" / ad).write_text(txt)


def _write_physical_properties(case_dir: Path, nu: float) -> None:
    """OF 11 incompressibleFluid solver: constant/physicalProperties"""
    txt = _foam_header("dictionary", "physicalProperties", "constant")
    txt += (
        "viscosityModel  constant;\n"
        f"nu              [0 2 -1 0 0 0 0] {nu};\n"
    )
    (case_dir / "constant" / "physicalProperties").write_text(txt)


def _write_physical_properties_compressible(case_dir: Path, case: CFDCase) -> None:
    """OF11 'fluid' çözücüsü: hePsiThermo + Sutherland hava."""
    txt = _foam_header("dictionary", "physicalProperties", "constant")
    txt += (
        "thermoType\n{\n"
        "    type            hePsiThermo;\n"
        "    mixture         pureMixture;\n"
        "    transport       sutherland;\n"
        "    thermo          hConst;\n"
        "    equationOfState perfectGas;\n"
        "    specie          specie;\n"
        "    energy          sensibleInternalEnergy;\n"
        "}\n\n"
        "mixture\n{\n"
        "    specie         { molWeight 28.96; }\n"
        "    thermodynamics { Cp 1005; Hf 0; }\n"
        "    transport      { As 1.4792e-06; Ts 116; }\n"
        "}\n"
    )
    (case_dir / "constant" / "physicalProperties").write_text(txt)


def _write_field_T(case_dir: Path, case: CFDCase, surface_name: str) -> None:
    t = case.t_inf
    txt = _foam_header("volScalarField", "T", "0")
    txt += (
        "dimensions      [0 0 0 1 0 0 0];\n\n"
        f"internalField   uniform {t};\n\n"
        "boundaryField\n{\n"
        f"    inlet   {{ type fixedValue; value uniform {t}; }}\n"
        f"    outlet  {{ type inletOutlet; inletValue uniform {t}; value uniform {t}; }}\n"
        "    top     { type zeroGradient; }\n"
        "    bottom  { type zeroGradient; }\n"
        "    front   { type zeroGradient; }\n"
        "    back    { type zeroGradient; }\n"
        f"    {surface_name} {{ type zeroGradient; }}\n"   # adyabatik duvar
        "}\n"
    )
    (case_dir / "0" / "T").write_text(txt)


def _write_field_alphat(case_dir: Path, surface_name: str) -> None:
    txt = _foam_header("volScalarField", "alphat", "0")
    txt += (
        "dimensions      [1 -1 -1 0 0 0 0];\n\n"
        "internalField   uniform 0;\n\n"
        "boundaryField\n{\n"
        "    inlet   { type calculated; value uniform 0; }\n"
        "    outlet  { type calculated; value uniform 0; }\n"
        "    top     { type calculated; value uniform 0; }\n"
        "    bottom  { type calculated; value uniform 0; }\n"
        "    front   { type calculated; value uniform 0; }\n"
        "    back    { type calculated; value uniform 0; }\n"
        f"    {surface_name} {{ type compressible::alphatWallFunction; value uniform 0; }}\n"
        "}\n"
    )
    (case_dir / "0" / "alphat").write_text(txt)


def _write_field_p_compressible(case_dir: Path, case: CFDCase, surface_name: str) -> None:
    p = case.p_inf
    txt = _foam_header("volScalarField", "p", "0")
    txt += (
        "dimensions      [1 -1 -2 0 0 0 0];\n\n"
        f"internalField   uniform {p};\n\n"
        "boundaryField\n{\n"
        "    inlet   { type zeroGradient; }\n"
        f"    outlet  {{ type fixedValue; value uniform {p}; }}\n"
        "    top     { type slip; }\n"
        "    bottom  { type slip; }\n"
        "    front   { type slip; }\n"
        "    back    { type slip; }\n"
        f"    {surface_name} {{ type zeroGradient; }}\n"
        "}\n"
    )
    (case_dir / "0" / "p").write_text(txt)


# 0/ field dosyaları
def _write_field_U(case_dir: Path, case: CFDCase, surface_name: str) -> None:
    fx, fy, fz = case.flow_direction
    Ux, Uy, Uz = (case.velocity * fx, case.velocity * fy, case.velocity * fz)
    bottom = "{ type noSlip; }" if case.ground_clearance is not None else "{ type slip; }"
    txt = _foam_header("volVectorField", "U", "0")
    txt += (
        "dimensions      [0 1 -1 0 0 0 0];\n\n"
        f"internalField   uniform ({Ux} {Uy} {Uz});\n\n"
        "boundaryField\n{\n"
        f"    inlet   {{ type fixedValue; value uniform ({Ux} {Uy} {Uz}); }}\n"
        "    outlet  { type inletOutlet; inletValue uniform (0 0 0); "
        f"value uniform ({Ux} {Uy} {Uz}); }}\n"
        f"    top     {{ type slip; }}\n"
        f"    bottom  {bottom}\n"
        f"    front   {{ type slip; }}\n"
        f"    back    {{ type slip; }}\n"
        f"    {surface_name} {{ type noSlip; }}\n"
        "}\n"
    )
    (case_dir / "0" / "U").write_text(txt)


def _write_field_p(case_dir: Path, surface_name: str, ground: bool = False) -> None:
    bottom = "{ type zeroGradient; }" if ground else "{ type slip; }"
    txt = _foam_header("volScalarField", "p", "0")
    txt += (
        "dimensions      [0 2 -2 0 0 0 0];\n\n"
        "internalField   uniform 0;\n\n"
        "boundaryField\n{\n"
        "    inlet   { type zeroGradient; }\n"
        "    outlet  { type fixedValue; value uniform 0; }\n"
        "    top     { type slip; }\n"
        f"    bottom  {bottom}\n"
        "    front   { type slip; }\n"
        "    back    { type slip; }\n"
        f"    {surface_name} {{ type zeroGradient; }}\n"
        "}\n"
    )
    (case_dir / "0" / "p").write_text(txt)


def _write_field_k(case_dir: Path, case: CFDCase, surface_name: str) -> None:
    I = case.turbulence_intensity
    k = 1.5 * (case.velocity * I) ** 2
    bottom = ("{ type kqRWallFunction; value uniform 1e-10; }"
              if case.ground_clearance is not None else "{ type slip; }")
    txt = _foam_header("volScalarField", "k", "0")
    txt += (
        "dimensions      [0 2 -2 0 0 0 0];\n\n"
        f"internalField   uniform {k:.6e};\n\n"
        "boundaryField\n{\n"
        f"    inlet   {{ type fixedValue; value uniform {k:.6e}; }}\n"
        "    outlet  { type zeroGradient; }\n"
        "    top     { type slip; }\n"
        f"    bottom  {bottom}\n"
        "    front   { type slip; }\n"
        "    back    { type slip; }\n"
        f"    {surface_name} {{ type kqRWallFunction; value uniform 1e-10; }}\n"
        "}\n"
    )
    (case_dir / "0" / "k").write_text(txt)


def _write_field_omega(case_dir: Path, case: CFDCase, surface_name: str, lref: float) -> None:
    I = case.turbulence_intensity
    k = 1.5 * (case.velocity * I) ** 2
    Cmu = 0.09
    l = 0.07 * lref
    omega = (k ** 0.5) / (Cmu ** 0.25 * l)
    bottom = (f"{{ type omegaWallFunction; value uniform {omega:.6e}; }}"
              if case.ground_clearance is not None else "{ type slip; }")
    txt = _foam_header("volScalarField", "omega", "0")
    txt += (
        "dimensions      [0 0 -1 0 0 0 0];\n\n"
        f"internalField   uniform {omega:.6e};\n\n"
        "boundaryField\n{\n"
        f"    inlet   {{ type fixedValue; value uniform {omega:.6e}; }}\n"
        "    outlet  { type zeroGradient; }\n"
        "    top     { type slip; }\n"
        f"    bottom  {bottom}\n"
        "    front   { type slip; }\n"
        "    back    { type slip; }\n"
        f"    {surface_name} {{ type omegaWallFunction; value uniform {omega:.6e}; }}\n"
        "}\n"
    )
    (case_dir / "0" / "omega").write_text(txt)


def _write_field_nut(case_dir: Path, surface_name: str, ground: bool = False) -> None:
    bottom = ("{ type nutUSpaldingWallFunction; value uniform 0; }"
              if ground else "{ type slip; }")
    txt = _foam_header("volScalarField", "nut", "0")
    txt += (
        "dimensions      [0 2 -1 0 0 0 0];\n\n"
        "internalField   uniform 0;\n\n"
        "boundaryField\n{\n"
        "    inlet   { type calculated; value uniform 0; }\n"
        "    outlet  { type calculated; value uniform 0; }\n"
        "    top     { type slip; }\n"
        f"    bottom  {bottom}\n"
        "    front   { type slip; }\n"
        "    back    { type slip; }\n"
        f"    {surface_name} {{ type nutUSpaldingWallFunction; value uniform 0; }}\n"
        "}\n"
    )
    (case_dir / "0" / "nut").write_text(txt)


# ---------------------------------------------------------------------------
# Case oluşturma + çalıştırma
# ---------------------------------------------------------------------------

def build_case(case: CFDCase, out_dir: Path) -> Path:
    """Tüm OpenFOAM dosyalarını yaz, STL'i kopyala. case_dir döndür."""
    case_dir = (Path(out_dir) / case.name).resolve()
    if case_dir.exists():
        shutil.rmtree(case_dir)
    (case_dir / "0").mkdir(parents=True)
    (case_dir / "constant" / "triSurface").mkdir(parents=True)
    (case_dir / "system").mkdir(parents=True)

    # STL kopyala. Dosya adı OpenFOAM SÖZLÜK ANAHTARI olarak yazılacağı için
    # geçerli bir `word` olmak ZORUNDA — aksi halde dict AYRIŞTIRILAMAZ.
    stl_name = foam_word(case.stl_path.name)
    surface_name = foam_word(case.stl_path.stem)
    shutil.copy(case.stl_path, case_dir / "constant" / "triSurface" / stl_name)

    # Domain
    dmin, dmax, gmin, gmax = _compute_domain(case.stl_path, case)
    size = gmax - gmin
    L = float(size.max())
    cell_size = case.bg_cell_size or (L / 10.0)

    # locationInMesh: geometri MERKEZİNİN biraz dışı olmalı (içinde olmamalı)
    # Akış yönünde geometri arkasında bir nokta seç
    cx = (gmin[0] + gmax[0]) * 0.5
    cy = (gmin[1] + gmax[1]) * 0.5
    cz = (gmin[2] + gmax[2]) * 0.5
    inside_pt = (cx + L * 2.0, cy + L * 0.1, cz + L * 0.1)

    ground = case.ground_clearance is not None
    # Arka plan hücresi DOMAIN+BÜTÇEDEN — istenen boy bütçeyi tek başına yiyorsa
    # snappy hiçbir yüzey iyileştirmesi yapamaz (MiniHawk: 3.94M arka plan / 2.5M
    # tavan → gövde 74 yüz). Boyu yalnız KABALAŞTIRIR, asla inceltmez.
    cell_size, bg_bilgi = arka_plan_hucre_boyu(dmin, dmax, cell_size,
                                               case.max_global_cells)
    case.bg_bilgi = bg_bilgi
    _write_block_mesh(case_dir, dmin, dmax, cell_size, ground=ground)
    _write_snappy(case_dir, stl_name, surface_name, inside_pt, case)
    _write_surface_features(case_dir, stl_name)
    lref = L
    # İz-düzlemi: gövde arkası 2 boy (uzak-iz basınç toparlanması), domain içinde
    wake_x = float(gmax[0] + 2.0 * lref)
    _write_control_dict(case_dir, case, surface_name, lref, wake_x=wake_x)
    _write_fv_schemes(case_dir, case.transient)
    _write_fv_solution(case_dir, case.compressible, case.transient,
                       case.n_outer)
    n_proc = case.n_processors if case.n_processors > 0 else _default_processors()
    case.n_processors = n_proc  # downstream run_cfd için sabitle
    _write_decompose_par(case_dir, n_proc)
    _write_transport(case_dir, case.nu)
    _write_momentum(case_dir, case.turbulence_model)
    if case.turbulence_model in GECIS_MODELLERI:
        _write_gecis_alanlari(case_dir, surface_name, case.turbulence_intensity)
    if case.compressible:
        _write_physical_properties_compressible(case_dir, case)
    else:
        _write_physical_properties(case_dir, case.nu)

    _write_field_U(case_dir, case, surface_name)
    if case.compressible:
        _write_field_p_compressible(case_dir, case, surface_name)
        _write_field_T(case_dir, case, surface_name)
        _write_field_alphat(case_dir, surface_name)
    else:
        _write_field_p(case_dir, surface_name, ground=ground)
    _write_field_k(case_dir, case, surface_name)
    _write_field_omega(case_dir, case, surface_name, lref)
    _write_field_nut(case_dir, surface_name, ground=ground)

    if case.propeller:
        _write_propeller(case_dir, case.propeller, gmin, gmax, cell_size)

    if case.compressible:
        # Negatif-T abort koruması: sıcaklığı fiziksel banta kıs (geçici
        # ara-iterasyon taşmaları çözümü öldürmesin)
        (case_dir / "constant" / "fvConstraints").write_text(
            _foam_header("dictionary", "fvConstraints", "constant") +
            "limitT\n{\n    type      limitTemperature;\n"
            "    selectionMode all;\n    min       100;\n    max       1000;\n}\n")

    return case_dir


def _write_propeller(case_dir: Path, prop: dict, gmin, gmax, bg_cell: float):
    """Burnun önünde silindirik cellSet (topoSetDict) + actuationDiskSource.
    diskDir (-1 0 0): AMPİRİK doğrulama (küp testi) Usource'un ters
    konvansiyonla girdiğini gösterdi — +x diskDir akışı YAVAŞLATTI
    (sürükleme 16.5→11.6 N, türbin etkisi); pervane için dHat ters."""
    cap = prop["cap_m"]
    yc = float((gmin[1] + gmax[1]) / 2)
    zc = float((gmin[2] + gmax[2]) / 2)
    t = max(0.06 * cap, 3.0 * bg_cell)
    x2 = float(gmin[0]) - 0.02 * float(gmax[0] - gmin[0])
    x1 = x2 - t
    (case_dir / "system" / "topoSetDict").write_text(
        _foam_header("dictionary", "topoSetDict", "system") +
        "actions (\n"
        "  { name pervaneDisk; type cellSet; action new; source cylinderToCell;\n"
        f"    p1 ({x1:.6f} {yc:.6f} {zc:.6f}); p2 ({x2:.6f} {yc:.6f} {zc:.6f}); "
        f"radius {cap/2:.6f}; }}\n"
        ");\n")
    up = x1 - 1.5 * cap
    (case_dir / "constant" / "fvModels").write_text(
        _foam_header("dictionary", "fvModels", "constant") +
        "pervane\n{\n"
        "    type            actuationDiskSource;\n"
        "    select          cellSet;\n"
        "    cellSet         pervaneDisk;\n"
        "    diskDir         (-1 0 0);\n"
        f"    Cp              {prop['Cp']};\n"
        f"    Ct              {prop['Ct']};\n"
        f"    diskArea        {prop['area']:.6f};\n"
        f"    upstreamPoint   ({up:.6f} {yc:.6f} {zc:.6f});\n"
        "}\n")


def _wsl_run(wsl_dir: str, command: str, timeout: int) -> subprocess.CompletedProcess:
    """OF environment ile seçili Linux arka ucunda (wsl|docker) komut çalıştır."""
    full = f"{OF_ENV_PREFIX}cd '{wsl_dir}' && {command}"
    return linux_run(full, timeout)


# Uzun-koşan OF binary'leri: timeout/iptal'de WSL-içi orphan bırakmamak için
# (Windows-tarafı wsl.exe öldürmek WSL-içi süreç ağacını öldürmüyordu → orphan,
# aynı case'de çakışma, 50× yavaşlama — bu oturumun pahalı dersi).
_OF_BINS = ("foamRun", "snappyHexMesh", "blockMesh", "simpleFoam", "potentialFoam",
            "surfaceFeatures", "mpirun", "decomposePar", "reconstructPar")


def divergence_in_log(log_text: str) -> str | None:
    """foamRun logunda KESİN diverjans imzası ara (NaN/inf residual, FPE, solver crash).
    Çözücü timeout'a kadar koşup NaN üretse returncode 0 olabilir → garbage'ı yakala.
    'bounding k/omega' gibi NORMAL mesajları kasıtlı dışlar (yanlış-pozitif önleme)."""
    low = log_text.lower()
    if re.search(r"initial residual\s*=\s*[-+]?(nan|inf)\b", low):
        return "residual NaN/inf (diverjans)"
    if "floating point exception" in low:
        return "floating point exception (diverjans)"
    if re.search(r"#0\s+foam::error", low):
        return "solver crash (Foam::error)"
    return None


def _cd_plateau(cds, tol: float) -> bool:
    """Erken-durdurma kararı: uç-uca drift < tol VE pencere-genliği küçük olmalı.
    Salınımlı çözümde (keskin-kenar küt cisim, steady-SIMPLE) iki uç tesadüfen
    çakışıp drift<tol verebilir — erken kesmek faz-piyangosudur (küp dersi
    2026-07-12: AYNI mesh'te Cd 0.916↔1.097). Genlik büyükse end_time'a koşulur;
    raporlama katmanı pencere-ortalaması + genliği banda ekler."""
    drift = abs(cds[-1] - cds[0]) / (abs(cds[-1]) + 1e-12)
    if drift >= tol:
        return False
    mu = sum(cds) / len(cds)
    amp = (max(cds) - min(cds)) / 2.0
    return amp <= 2.0 * tol * (abs(mu) + 1e-12)


def _wrap_timeout(command: str, tmo: int) -> tuple[str, list[str]]:
    """Komutta OF binary varsa WSL-içi GNU timeout ile sar (orphan-önleme).
    Döndür: (sarılmış_komut, kill_edilecek_binary_listesi)."""
    bins = [b for b in _OF_BINS if b in command]
    if not bins:
        return command, []
    return f"timeout -k 10 -s TERM {max(tmo - 20, 30)} {command}", bins


def _wsl_kill(patterns, dizin: str | None = None) -> None:
    """WSL-içi orphan OF süreçlerini öldür.

    `dizin` verilirse YALNIZ o case dizininde koşan süreçler öldürülür.

    NEDEN: eski hâli `pkill -9 -f foamRun` idi — bu, makinedeki HER foamRun'ı
    öldürür. ÖLÇÜLDÜ: NACA2412 çapası koşarken paralel bir duman testi
    (check_cfd_pipeline) kendi zaman aşımında `_wsl_kill(["foamRun"])` çağırdı ve
    ÇAPANIN çözücüsünü 1464. iterasyonda öldürdü; log iterasyon ortasında kesildi,
    hiçbir yerde hata görünmedi ve çapa sessizce bozuk sayı üretecekti. Uzun
    kampanyalar sırasında başka bir analiz başlatmak aynı sonucu verir.
    Kapsam /proc/<pid>/cwd ile daraltılır — cmdline'da case yolu görünmez
    (foamRun'ın kendi komut satırı yalnızca "foamRun -solver ...").
    """
    if not patterns:
        return
    if dizin:
        cmd = "; ".join(
            f'for _p in $(pgrep -f {p} 2>/dev/null); do '
            f'[ "$(readlink -f /proc/$_p/cwd 2>/dev/null)" = "{dizin}" ] && '
            f'kill -9 "$_p" 2>/dev/null; done' for p in patterns) + "; true"
    else:
        cmd = "; ".join(f"pkill -9 -f {p} 2>/dev/null" for p in patterns) + "; true"
    try:
        linux_run(cmd, 30)
    # sessiz-yutma: kabul — süreç zaten ölmüş olabilir; öldürme başarısızlığı sonucu etkilemez
    except Exception:
        pass


def _cozucu_yasiyor(patterns, dizin: str) -> bool:
    """Verilen case dizininde HÂLÂ koşan bir çözücü var mı? (kapsamlı, /proc/cwd)"""
    if not patterns:
        return False
    kos = "; ".join(
        f'for _p in $(pgrep -f {p} 2>/dev/null); do '
        f'[ "$(readlink -f /proc/$_p/cwd 2>/dev/null)" = "{dizin}" ] && echo VAR; done'
        for p in patterns)
    try:
        return "VAR" in (linux_run(kos + "; true", 60).stdout or "")
    # sessiz-yutma: kabul — sorgulanamıyorsa "yaşamıyor" varsayılır; en kötü hâl
    # eski davranıştır (erken okuma), yeni bir kilitlenme riski getirmez.
    except Exception:
        return False


def _cozucu_bitmesini_bekle(patterns, dizin: str, tmo: int, adim: int = 10) -> None:
    """Sarmalayıcı döndükten sonra Linux-tarafı çözücünün GERÇEKTEN bitmesini bekle."""
    t0 = time.time()
    while time.time() - t0 < tmo:
        if not _cozucu_yasiyor(patterns, dizin):
            return
        time.sleep(adim)


def run_cfd(case: CFDCase, out_dir: Path, timeout: int = 3600,
             progress_callback=None) -> CFDResult:
    """Case'i kur, mesh'i üret, çöz, sonuçları parse et."""
    case_dir = build_case(case, out_dir)
    wsl_dir = windows_to_wsl_path(case_dir)
    log_files: list[Path] = []
    asama_sureleri: list[dict] = []
    bellek: dict = {}
    all_stdout = []
    all_stderr = []

    # ext4 modu (CFD_EXT4=1, yalnız wsl): case çözüm süresince Linux-yerli diskte koşar —
    # drvfs(9p) paralel-yazım çökmesini (küre I/O vakası) kökten çözer + belirgin hız.
    # Solver bitince/başarısızlıkta içerik Windows tarafına geri kopyalanır.
    ext4 = ext4_enabled()
    exec_dir = wsl_dir
    if ext4:
        _home = linux_home()
        exec_dir = f"{_home}/cfd_runs/{case.name}"
        try:
            prep = linux_run(f"rm -rf '{exec_dir}' && mkdir -p '{_home}/cfd_runs' && "
                             f"cp -a '{wsl_dir}' '{exec_dir}'", 900)
            if prep.returncode != 0:
                raise RuntimeError(prep.stderr[-200:])
        except Exception as e:
            all_stderr.append(f"ext4 hazırlık başarısız — drvfs'te koşuluyor: {e}")
            exec_dir, ext4 = wsl_dir, False

    def _copy_back():
        nonlocal ext4
        if ext4:
            try:
                linux_run(f"cp -a '{exec_dir}/.' '{wsl_dir}/' && rm -rf '{exec_dir}'", 1800)
            except Exception as e:
                all_stderr.append(f"ext4 geri-kopyalama hatası: {e}")
            ext4 = False

    def _ret(res_obj):
        _copy_back()
        return res_obj

    def _step(percent: int, msg: str, command: str, log_name: str,
              tmo: int) -> subprocess.CompletedProcess | None:
        if progress_callback:
            progress_callback(percent, msg)
        _t0 = time.time()
        # WSL-içi GNU timeout ile sar: süre aşılırsa WSL kendi süreç ağacını öldürür
        # (Windows-tarafı tmo backstop, biraz daha yüksek). Orphan'ı kökten önler.
        wrapped, bins = _wrap_timeout(command, tmo)
        try:
            r = _wsl_run(exec_dir, wrapped + f" > {log_name} 2>&1", timeout=tmo)
        except subprocess.TimeoutExpired as e:
            all_stderr.append(f"TIMEOUT in {log_name}: {e}")
            _wsl_kill(bins, exec_dir)            # Windows-tarafı aşımı: WSL orphan'larını öldür
            asama_sureleri.append({"asama": log_name.replace("log.", ""),
                                   "sure_s": round(time.time() - _t0, 2),
                                   "durum": "ZAMAN ASIMI", "tmo_s": tmo})
            return None
        asama_sureleri.append({"asama": log_name.replace("log.", ""),
                               "sure_s": round(time.time() - _t0, 2),
                               "durum": "ok" if r.returncode == 0 else "hata",
                               "donus_kodu": r.returncode})
        log_files.append(case_dir / log_name)
        all_stdout.append(f"--- {log_name} ---\n{r.stdout}")
        if r.stderr:
            all_stderr.append(f"--- {log_name} stderr ---\n{r.stderr}")
        return r

    def _foam_run_early_stop(command: str, tmo: int, msg: str,
                             window: int = 50, tol: float = 0.003) -> int:
        """foamRun'ı (seri ya da `mpirun ... -parallel`) arka planda koş; coefficient.dat'tan
        Cd'yi canlı izle; son `window` iterasyonda Cd-drifti `tol`un altına inince solver'ı
        orphan-güvenli öldür (erken yakınsama). Döner: returncode (0=ok, !=0=hata/timeout)."""
        if progress_callback:
            progress_callback(70, msg)
        wrapped, bins = _wrap_timeout(command, tmo)
        full = f"{OF_ENV_PREFIX}cd '{exec_dir}' && {wrapped} > log.foamRun 2>&1"
        proc = linux_popen(full)
        t0 = time.time(); early = False; n_iter = 0
        # BELLEK OLCUMU: hucre butcesi sabit bir sayiydi ve makinenin belleginden
        # habersizdi. Cozucu WSL2 icinde kostugu icin Windows tarafindan gorunen
        # sey sistem geneli kullanimdir; bu yuzden kosu ONCESI taban alinir ve
        # ARTIS raporlanir. Tek surecin RSS'i degil, durust olan bu.
        _b0 = _bellek_gb()
        _tepe = _b0[0] if _b0 else None
        while proc.poll() is None:
            time.sleep(12)
            _b = _bellek_gb()
            if _b and _tepe is not None:
                _tepe = max(_tepe, _b[0])
            try:
                if ext4:
                    txt = _wsl_run(exec_dir, "cat postProcessing/forceCoeffs1/*/"
                                             "coefficient.dat 2>/dev/null || true",
                                   timeout=30).stdout
                    hist = parse_force_coeffs_text(txt)[3]
                else:
                    hist = parse_force_coeffs(case_dir)[3]
            except Exception:
                hist = []
            n_iter = len(hist)
            if n_iter >= 2 * window:
                cds = [h[1] for h in hist[-window:]]
                if _cd_plateau(cds, tol):
                    _wsl_kill(bins, exec_dir); early = True
                    break
            if time.time() - t0 > tmo:
                _wsl_kill(bins, exec_dir); break
        # SARMALAYICI DÖNDÜ ≠ ÇÖZÜCÜ BİTTİ. `wsl bash -c` sarmalayıcısı, Linux
        # tarafındaki süreç HÂLÂ KOŞARKEN dönebiliyor; bu depoda daha önce
        # construct2d_bridge'de belgelenmişti ama KANONİK koşucuda yoktu.
        #
        # ÖLÇÜLDÜ (gripen_AB_Right): sonuc.json 13:51'de yazıldı, log.foamRun
        # 13:59'da "End" ile TEMİZ bitti (800 iterasyon, öldürülmedi). Boru hattı
        # kuvvet tarihçesini 213 kayıtta okudu — nihai 801'in dörtte biri.
        # Çökme üretmediği, MAKUL GÖRÜNEN kısmi bir sonuç ürettiği için fark
        # edilmedi. Sonuç: salınım hükmü koşudan koşuya değişiyordu (aynı geometri,
        # aynı ayar: geçiş 3 ↔ 12). Cd %1 içinde tekrarlanabilirdi çünkü kuyruk
        # ortalaması kısmi tarihçede de yakın çıkıyor — hüküm ise değildi.
        if _b0 and _tepe is not None:
            bellek.update({"taban_gb": round(_b0[0], 2), "tepe_gb": round(_tepe, 2),
                           "artis_gb": round(_tepe - _b0[0], 2),
                           "toplam_gb": round(_b0[1], 2),
                           "_yontem": "sistem geneli (WSL2 VM ayri surec degil); "
                                      "kosu oncesi tabana gore ARTIS"})
        elif not _b0:
            bellek["_olculemedi"] = "psutil yok — bellek kullanimi OLCULMEDI"
        if not early:
            _cozucu_bitmesini_bekle(bins, exec_dir, tmo)
        try:
            proc.wait(timeout=30)
        # sessiz-yutma: kabul — erken-durdurma İYİLEŞTİRMESİ; düşerse koşu tam süre devam eder (güvenli taraf)
        except Exception:
            pass
        log_files.append(case_dir / "log.foamRun")
        # TELEMETRIDE DELIK VARDI: `_step` her asamayi kaydediyordu ama COZUCU
        # ondan gecmiyor — bu ayri fonksiyon. Yani asama telemetrisi EN PAHALI
        # adimi disarida birakiyordu ve figur "cozucunun kendi olcumu" derken
        # cozucuyu gostermiyordu. (Olculdu: kup kosusunda 4 asama kayitli,
        # foamRun yok.)
        _rc = 0 if (early or proc.returncode == 0) else (proc.returncode or -1)
        asama_sureleri.append({
            "asama": "foamRun",
            "sure_s": round(time.time() - t0, 2),
            "durum": "ok" if _rc == 0 else "hata",
            "donus_kodu": _rc,
            "iterasyon": n_iter,
            "erken_durdu": early})
        if early and progress_callback:
            progress_callback(72, f"Cd yakınsadı ({n_iter} iter, drift<{tol}) — erken durdu")
        return _rc

    # 1) surfaceFeatures
    r = _step(10, "surfaceFeatures...", "surfaceFeatures", "log.surfaceFeatures", 120)
    if r is None or r.returncode != 0:
        return _ret(CFDResult(asama_sureleri=asama_sureleri, case_dir=case_dir, success=False,
                              return_code=-1 if r is None else r.returncode,
                              stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                              log_files=log_files))

    # 2) blockMesh
    r = _step(20, "blockMesh...", "blockMesh", "log.blockMesh", 120)
    if r is None or r.returncode != 0:
        return _ret(CFDResult(asama_sureleri=asama_sureleri, case_dir=case_dir, success=False,
                              return_code=-1 if r is None else r.returncode,
                              stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                              log_files=log_files))

    # 3) snappyHexMesh
    r = _step(40, "snappyHexMesh (mesh adapsiyonu, en uzun adım)...",
              "snappyHexMesh -overwrite", "log.snappyHexMesh", 1800)
    if r is None or r.returncode != 0:
        return _ret(CFDResult(asama_sureleri=asama_sureleri, case_dir=case_dir, success=False,
                              return_code=-1 if r is None else r.returncode,
                              stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                              log_files=log_files))

    # 4) checkMesh (uyarılar normal, başarısızlık değil)
    _step(55, "checkMesh...", "checkMesh", "log.checkMesh", 300)

    # 4-gate) Mesh-kalite ön-geçidi: reject-kalite mesh'i ÇÖZÜCÜDEN ÖNCE ele
    # (negatif hacim / aşırı non-ortho-skew → çözücü saatlerce diverjyor/timeout).
    if ext4:
        cm_txt = _wsl_run(exec_dir, "cat log.checkMesh 2>/dev/null || true",
                          timeout=60).stdout
    else:
        cm = case_dir / "log.checkMesh"
        cm_txt = cm.read_text(errors="ignore") if cm.exists() else ""
    if cm_txt:
        mq = mesh_quality_gate(cm_txt)
        if mq["verdict"] == "reject":
            all_stderr.append("Mesh kalitesiz, çözücüye GÖNDERİLMEDİ: "
                              + "; ".join(mq["reasons"]))
            return _ret(CFDResult(asama_sureleri=asama_sureleri, case_dir=case_dir, success=False, return_code=-2,
                                  stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                                  log_files=log_files))

    # 4b) topoSet (varsa — pervane diski cellSet'i vb.)
    if (case_dir / "system" / "topoSetDict").exists():
        r = _step(57, "topoSet (pervane diski)...", "topoSet", "log.topoSet", 300)
        if r is None or r.returncode != 0:
            return _ret(CFDResult(asama_sureleri=asama_sureleri, case_dir=case_dir, success=False,
                                  return_code=-1 if r is None else r.returncode,
                                  stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                                  log_files=log_files))

    # 5) Solver: foamRun (OF 11) — çok işlemcili
    n = case.n_processors
    if n > 1:
        # mpirun bazı WSL kurulumlarında süresiz asılı kalıyor (worker'lar hiç
        # doğmuyor, log 0 bayt). 15 sn'lik smoke geçemezse seri koşuya düş.
        try:
            probe = _wsl_run(wsl_dir, "timeout 15 mpirun -np 2 true", timeout=40)
            mpi_ok = probe.returncode == 0
        except subprocess.TimeoutExpired:
            mpi_ok = False
        if not mpi_ok:
            all_stderr.append("UYARI: mpirun smoke testi başarısız/asılı — seri koşuya düşüldü")
            if progress_callback:
                progress_callback(58, "mpirun çalışmıyor — seri moda geçildi")
            n = 1
    if n > 1:
        r = _step(60, f"decomposePar ({n} işlemci)...",
                  "decomposePar -force", "log.decomposePar", 300)
        if r is None or r.returncode != 0:
            return _ret(CFDResult(asama_sureleri=asama_sureleri, case_dir=case_dir, success=False,
                                  return_code=-1 if r is None else r.returncode,
                                  stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                                  log_files=log_files))
        # Paralel foamRun + CANLI Cd-yakınsama erken-durdurma (4 çekirdek × erken-stop)
        rc = _foam_run_early_stop(
            f"mpirun --oversubscribe -np {n} foamRun -parallel",
            max(timeout - 600, 600), f"foamRun (paralel SIMPLE, {n} çekirdek, Cd-izlemeli)...")
        if rc != 0:
            return _ret(CFDResult(asama_sureleri=asama_sureleri, case_dir=case_dir, success=False, return_code=rc,
                                  stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                                  log_files=log_files))
        _step(95, "reconstructPar...", "reconstructPar -latestTime",
              "log.reconstructPar", 600)
    else:
        # Seri foamRun + CANLI Cd-yakınsama erken-durdurması: residualControl (1e-4)
        # çoğu kaba case'de plato yaptığından tetiklenmez → end_time'a kadar boşa koşar.
        # Cd (mühendislik niceliği) bir pencerede sabitlenince solver'ı temiz öldür → CPU.
        rc = _foam_run_early_stop("foamRun", max(timeout - 600, 600),
                                  "foamRun (seri SIMPLE, Cd-yakınsama izlemeli)...")
        if rc != 0:
            return _ret(CFDResult(asama_sureleri=asama_sureleri, case_dir=case_dir, success=False, return_code=rc,
                                  stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                                  log_files=log_files))

    # Çözücü bitti → ext4 içeriği Windows tarafına al (diverjans/parse yerel dosyadan)
    _copy_back()

    # Diverjans bekçisi: solver returncode 0 olsa bile NaN/inf üretmiş olabilir
    # (timeout'a kadar koşup ıraksar). Garbage sonucu BAŞARILI sayma.
    solver_log = case_dir / "log.foamRun"
    if solver_log.exists():
        diverg = divergence_in_log(solver_log.read_text(errors="ignore"))
        if diverg:
            all_stderr.append(f"DIVERJANS: {diverg} — sonuç güvenilmez")
            return CFDResult(asama_sureleri=asama_sureleri, case_dir=case_dir, success=False, return_code=-2,
                             stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
                             log_files=log_files)

    # 6) Force coefficients parse
    cd, cl, cm, history = parse_force_coeffs(case_dir)

    if progress_callback:
        progress_callback(100, "CFD tamamlandı")

    return CFDResult(
        case_dir=case_dir, success=True, return_code=0, asama_sureleri=asama_sureleri,
        bellek=bellek,
        stdout="\n".join(all_stdout), stderr="\n".join(all_stderr),
        cd=cd, cl=cl, cm=cm, forces_history=history, log_files=log_files,
    )


def parse_force_coeffs_text(text: str) -> tuple[float | None, float | None,
                                                float | None,
                                                list[tuple[int, float, float, float]]]:
    """coefficient.dat İÇERİĞİNİ parse et (ext4/uzak arka uçta canlı izleme için
    dosyasız sürüm). Returns: (Cd_son, Cl_son, Cm_son, [(iter, Cd, Cl, Cm), ...])"""
    history: list[tuple[int, float, float, float]] = []
    cd_idx = cl_idx = cm_idx = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            # Header satırı: # Time Cd Cs Cl ... formatı değişebilir
            if "Cd" in line or "Cm" in line:
                parts = line.lstrip("#").split()
                for i, p in enumerate(parts):
                    if p == "Cd":
                        cd_idx = i
                    elif p == "Cl":
                        cl_idx = i
                    elif p == "Cm":
                        cm_idx = i
            continue
        parts = line.split()
        try:
            t = int(float(parts[0]))
            cd = float(parts[cd_idx]) if cd_idx is not None and cd_idx < len(parts) else float("nan")
            cl = float(parts[cl_idx]) if cl_idx is not None and cl_idx < len(parts) else float("nan")
            cm = float(parts[cm_idx]) if cm_idx is not None and cm_idx < len(parts) else float("nan")
            history.append((t, cd, cl, cm))
        # sessiz-yutma: kabul — bozuk satır atlanır; BAŞLIK bulunamama durumu hemen altta AYRICA ele alınıp None döner (NaN üretilmez)
        except (ValueError, IndexError):
            continue
    # BAŞLIK BULUNAMADIYSA sahte sayı üretme: cd_idx/cl_idx/cm_idx None kalırsa her
    # satır NaN üretiyor ve history NaN'la doluyordu -> çağıran "Cd = nan" alıyordu.
    # (Fizik kapısı da NaN'ı ıskalıyordu; ikisi birleşince format değişimi sessizce
    # "Cd=nan, kapı ok" veriyordu.) Okunamadıysa dürüst cevap None'dır.
    if cd_idx is None and cl_idx is None and cm_idx is None:
        return None, None, None, []
    if not history:
        return None, None, None, history
    _, cd, cl, cm = history[-1]
    return cd, cl, cm, history


def parse_force_coeffs(case_dir: Path) -> tuple[float | None, float | None,
                                                  float | None,
                                                  list[tuple[int, float, float, float]]]:
    """postProcessing/forceCoeffs1/0/coefficient.dat'ı parse et."""
    candidates = list((case_dir / "postProcessing" / "forceCoeffs1").glob("*/coefficient.dat"))
    if not candidates:
        candidates = list((case_dir / "postProcessing" / "forceCoeffs1").glob("*/forceCoeffs.dat"))
    if not candidates:
        return None, None, None, []
    return parse_force_coeffs_text(candidates[0].read_text(errors="ignore"))


def controldict_yamala(case: Path, *, end_time: int | None = None,
                       start_from: str | None = None,
                       yplus_ekle: bool = False) -> None:
    """MEVCUT bir controlDict'i yamalar — yeni case iskelesi YAZMAZ.

    Deneysel betikler koşuyu uzatmak, son zamandan devam etmek ya da yPlus
    ölçümü eklemek için controlDict'e dokunmak zorunda kalıyordu ve her biri
    kendi `write_text`'ini yazıyordu. Bu, `test_case_iskele_tutarlilik`'in
    saydığı "kendi controlDict'ini yazan dosya" sayısını üç artırdı — testin
    amacı iskele TEKRARINI önlemekti, yama tekrarını değil. Yama artık tek
    yerden geçiyor.
    """
    cd = case / "system" / "controlDict"
    t = cd.read_text(encoding="utf-8")
    if start_from is not None:
        t = re.sub(r"startFrom \w+;", f"startFrom {start_from};", t)
        if start_from == "startTime":
            t = re.sub(r"startTime \d+;", "startTime 0;", t)
    if end_time is not None:
        t = re.sub(r"endTime \d+;", f"endTime {end_time};", t)
    if yplus_ekle and "yPlus" not in t:
        t = t.replace("functions\n{", 'functions\n{\n    yPlus { type yPlus; '
                      'libs ("libfieldFunctionObjects.so"); writeControl writeTime; }')
    cd.write_text(t, encoding="utf-8")


def case_bul(kok: Path) -> Path | None:
    """Bir dizin ağacında ÇALIŞTIRILABİLİR OpenFOAM vakasını bul.

    Deneysel betikler vakayı `rglob("system")` + controlDict varlığıyla arıyordu
    ve her biri o adı kendi kaynağında taşıyordu. `test_case_iskele_tutarlilik`
    dosyada o adın GEÇMESİNİ sayıyor (yazmasını değil), dolayısıyla arama bile
    sayacı büyütüyordu. Arama artık tek yerden geçer.
    """
    for p in kok.rglob("system"):
        if (p / "controlDict").exists():
            return p.parent
    return None
