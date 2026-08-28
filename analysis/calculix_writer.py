"""
CalculiX .inp dosya yazıcısı.

TetMesh + malzeme + sınır koşulları + yükler -> .inp
Sonra ccx.exe ile çalıştırılabilir.

Birim sistemi: SI (m, kg, s, N, Pa)
  - E, sigma_y: Pa (kullanıcı GPa girerse 1e9 ile çarpılmalı)
  - rho: kg/m³
  - kuvvet: N
  - basınç: Pa

Bu modül analiz adımları olarak STATIC, FREQUENCY, BUCKLE ve DYNAMIC
(zaman-çözünür, doğrudan integrasyon) destekler. STATIC ayrıca büyük
yer-değiştirme (NLGEOM) ile koşulabilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .birim_kapisi import pa_dogrula
from .tet_mesher import TetMesh


@dataclass
class FEAMaterial:
    """Lineer elastik malzeme (SI). Varsayılan izotropik; engineering_constants
    verilirse ORTOTROPİK yazılır (*ELASTIC, TYPE=ENGINEERING CONSTANTS —
    9'lu: E1,E2,E3,nu12,nu13,nu23,G12,G13,G23; eksenler GLOBAL çerçevede,
    kanat konvansiyonu: 1=kiriş/x, 2=açıklık/y, 3=kalınlık/z; bkz. laminat.py)."""
    name: str
    youngs_modulus_pa: float   # Pa (örn: 70e9 = 70 GPa)
    poisson_ratio: float
    density_kg_m3: float
    yield_strength_pa: float = 0.0  # post-process için
    thermal_expansion_per_k: float = 0.0   # α (1/K); >0 ise termal genleşme etkin
    engineering_constants: tuple | None = None  # 9'lu ortotropik takım (Pa)

    def __post_init__(self):
        # BİRİM KAPISI. Bu depoda `youngs_modulus` adı üç katmanda üç birim
        # taşıyor: material_database GPa, fea_runner MPa, burası Pa. Yanlış
        # katmandan gelen bir sayı CalculiX'i rahatsız etmez — sehimi 10³ ya da
        # 10⁹ kat kaydırıp "geçerli görünen" bir sonuç üretir. Kapı sayının
        # BÜYÜKLÜĞÜNE bakar; sessiz düzeltme YAPMAZ, reddeder.
        pa_dogrula(self.name, self.youngs_modulus_pa, self.density_kg_m3,
                   self.yield_strength_pa or None)

    @classmethod
    def from_gpa(cls, name: str, e_gpa: float, nu: float, rho: float,
                 yield_mpa: float = 0.0, alpha_per_k: float = 0.0) -> FEAMaterial:
        return cls(
            name=name,
            youngs_modulus_pa=e_gpa * 1e9,
            poisson_ratio=nu,
            density_kg_m3=rho,
            yield_strength_pa=yield_mpa * 1e6,
            thermal_expansion_per_k=alpha_per_k,
        )


@dataclass
class FixedBC:
    """Sabit (encastre) sınır koşulu — verilen düğümlerde tüm DOF'lar sıfır."""
    node_ids: np.ndarray   # 1-indexed (CalculiX)
    name: str = "FIXED"
    dof_start: int = 1
    dof_end: int = 3       # 1-3 = ux, uy, uz (sadece 3D solid)


@dataclass
class PressureLoad:
    """Yüzey üçgenlerine uygulanan üniform basınç."""
    face_node_ids: np.ndarray  # (K, 3 veya 6) yüzey üçgenleri (1-indexed düğümler)
    pressure_pa: float          # pozitif = yüzeye doğru bastırır
    name: str = "PRESSURE"


@dataclass
class ForceLoad:
    """Düğümlere dağıtılmış konsantre kuvvet (toplam F, /N node ile bölünür)."""
    node_ids: np.ndarray   # 1-indexed
    direction: tuple       # (fx, fy, fz) birim vektör
    total_force_n: float
    name: str = "FORCE"


@dataclass
class GravityLoad:
    """Tüm yapıya eylemsizlik gövde-kuvveti (CalculiX *DLOAD, GRAV).
    Manevra g-yükü için accel = n·9.81 (n = yük faktörü). Yoğunluk *DENSITY'den."""
    accel_m_s2: float                       # ivme büyüklüğü (örn. 3.8*9.81)
    direction: tuple = (0.0, 0.0, -1.0)     # yön (birim vektör; yer-çekimi -z)
    name: str = "GRAV"


@dataclass
class FEACase:
    """Tam bir FEA çalışması."""
    name: str
    mesh: TetMesh
    material: FEAMaterial
    fixed_bcs: list[FixedBC] = field(default_factory=list)
    pressure_loads: list[PressureLoad] = field(default_factory=list)
    force_loads: list[ForceLoad] = field(default_factory=list)
    # DUGUM-BASINA SERBEST KUVVET: {dugum_no (1-tabanli): (Fx, Fy, Fz)}.
    # FSI aktariminin urettigi yuk boyledir --- her dugumde ayri ve 3
    # bilesenli. `ForceLoad` bunu ifade edemez (tek yonde TOPLAM dagitir),
    # ve bu eksik uc cagiraninin .inp metnini ELLE duzenlemesine yol
    # aciyordu. Bkz. write_inp icindeki gerekce.
    dugum_kuvvetleri: dict[int, tuple] = field(default_factory=dict)
    gravity_loads: list[GravityLoad] = field(default_factory=list)
    analysis_type: str = "STATIC"   # STATIC, FREQUENCY, BUCKLE, DYNAMIC
    num_modes: int = 10              # FREQUENCY/BUCKLE için
    # ZAMAN-ÇÖZÜNÜR (DYNAMIC) parametreleri.
    #
    # NEDEN EKLENDİ: iki-yönlü FSI'nin kanonik çapaları (Turek-Hron FSI2/FSI3)
    # zamana bağlıdır --- girdap dökülmesi bayrağı salındırır ve cevap bir
    # denge değil bir HAREKETTİR. Ölçüldü (fsi_capa_ulasilabilirlik.json):
    # NLGEOM eklendikten sonra o vakaları bekleten TEK yetenek buydu.
    dinamik_dt: float = 1e-3         # zaman adımı (s)
    dinamik_sure: float = 1.0        # toplam süre (s)
    # CalculiX varsayilani alpha=-0.05 (HHT sayisal sonumu). SIFIR yapmak
    # yuksek-frekans gurultusunu birakir; varsayilan birakildi ve DEGERI
    # kayda yazilir ki bir cozumdeki genlik dususu "fizik" sanilmasin.
    dinamik_alpha: float = -0.05
    # SABIT ZAMAN ADIMI. Varsayilan KAPALI --- CalculiX'in kendi varsayilani
    # adimi otomatik buyutur ve bu DOGRULUK icin iyidir (sonda kosusunda
    # 2e-4'ten 1,16e-3'e cikti). Ama KUPLAJDA dt'yi akis dayatir: yapisal
    # taraf kendi adimini secerse iki cozucu ayri zamanlarda olur. FSI
    # cagiranlari bunu ACIKCA acar.
    dinamik_direct: bool = False
    delta_t: float = 0.0             # üniform sıcaklık değişimi (K); termal gerilme için
    # BÜYÜK YER-DEĞİŞTİRME. Varsayılan KAPALI --- açmak yalnız daha "genel"
    # olmaz, ÇÖZÜMÜ DEĞİŞTİRİR ve yayımlanmış sonuçları yeniden üretilemez
    # kılardı. Lineer statik, sehim/boy oranı küçükken doğrudur ve bu deponun
    # bütün yapısal çapaları o rejimde ölçüldü.
    #
    # NEDEN EKLENDİ: iki-yönlü FSI'nin kanonik çapası (Turek-Hron FSI2/FSI3)
    # uç sehimi bayrak boyunun %10--%23'ü olan bir rejimde tanımlı; orada
    # lineer statik GEÇERSİZDİR. Ölçüldü (fsi_capa_ulasilabilirlik.json):
    # o vakaları bekleten şey donanım değil TAM OLARAK bu yetenekti.
    nlgeom: bool = False
    # Yük artımı: NLGEOM'da denge iteratif çözülür ve tek adımda yakınsamak
    # zorunda değildir. CalculiX ilk artımı `ilk_artim`, toplamı 1,0 alır.
    ilk_artim: float = 0.1
    max_artim_sayisi: int = 100


def write_inp(case: FEACase, output_dir: Path) -> Path:
    """Verilen case için CalculiX .inp dosyası yaz.

    Returns:
        Yazılan .inp dosyasının Path'i.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    inp_path = output_dir / f"{case.name}.inp"

    mesh = case.mesh
    mat = case.material
    elem_type = mesh.element_type  # C3D4 veya C3D10

    lines: list[str] = []
    lines.append("*HEADING")
    lines.append(f"Case: {case.name} (auto-generated by bilsem_beyin)")
    lines.append("**")

    # ─── DÜĞÜMLER ───
    lines.append("*NODE, NSET=NALL")
    # CalculiX 1-indexed; bizim points 0-indexed
    pts = mesh.points
    for i, (x, y, z) in enumerate(pts, start=1):
        lines.append(f"{i:8d}, {x: .9e}, {y: .9e}, {z: .9e}")
    lines.append("**")

    # ─── ELEMENTLER ───
    lines.append(f"*ELEMENT, TYPE={elem_type}, ELSET=EALL")
    tets = mesh.tets + 1  # 1-indexed'e çevir
    if elem_type == "C3D4":
        for i, conn in enumerate(tets, start=1):
            lines.append(f"{i:8d}, " + ", ".join(f"{n:d}" for n in conn))
    else:
        # C3D10: gmsh node ordering ile CalculiX/Abaqus aynı
        # (1-4 köşe, 5-10 kenar orta noktaları, sıralama eşleşir)
        for i, conn in enumerate(tets, start=1):
            lines.append(f"{i:8d}, " + ", ".join(f"{n:d}" for n in conn[:8]))
            lines.append("        " + ", ".join(f"{n:d}" for n in conn[8:]))
    lines.append("**")

    # ─── MALZEME ───
    lines.append(f"*MATERIAL, NAME={mat.name}")
    if mat.engineering_constants:
        ec = mat.engineering_constants
        lines.append("*ELASTIC, TYPE=ENGINEERING CONSTANTS")
        lines.append(", ".join(f"{v:.6e}" for v in ec[:8]))   # ilk 8 değer 1. satır
        lines.append(f"{ec[8]:.6e}")                          # G23 (+ opsiyonel T) 2. satır
    else:
        lines.append("*ELASTIC")
        lines.append(f"{mat.youngs_modulus_pa:.6e}, {mat.poisson_ratio:.4f}")
    lines.append("*DENSITY")
    lines.append(f"{mat.density_kg_m3:.6e}")
    thermal = mat.thermal_expansion_per_k > 0 and abs(case.delta_t) > 0
    if thermal:
        lines.append("*EXPANSION, ZERO=0")
        lines.append(f"{mat.thermal_expansion_per_k:.6e}")
    lines.append("**")
    lines.append(f"*SOLID SECTION, ELSET=EALL, MATERIAL={mat.name}")
    if thermal:                                   # referans sıcaklık 0 → ΔT uygulanacak
        lines.append("*INITIAL CONDITIONS, TYPE=TEMPERATURE")
        lines.append("NALL, 0.0")
    lines.append("**")

    # ─── BC NODE SETLERİ ───
    # NSET adlarını yerel sözlükte tut (dataclass'a attribute enjekte etme — case
    # yeniden kullanılır/deepcopy edilirse kaybolur ve frozen dataclass'ta patlar).
    bc_nset: dict[int, str] = {}
    for i, bc in enumerate(case.fixed_bcs, start=1):
        nset_name = f"{bc.name}_{i}"
        lines.append(f"*NSET, NSET={nset_name}")
        _write_id_list(lines, bc.node_ids)
        bc_nset[id(bc)] = nset_name
    lines.append("**")

    # ─── PRESSURE: yüzey üçgenlerini element + face olarak yazmamız gerek.
    # En basit & taşınabilir yol: her üçgen için 1 boyutlu *DLOAD yerine,
    # eşdeğer nodal kuvvetlere dönüştürmek. Üçgen alanı * basınç / 3 = her köşeye F.
    nodal_force_accumulator = {}  # (node_id, axis) -> force
    for pl in case.pressure_loads:
        tris = pl.face_node_ids
        if tris.shape[1] >= 3:
            # Tutarlı (consistent) nodal yük ∫N·p dA:
            #   T3 (3 düğüm): her köşe A/3.
            #   T6 (6 düğüm, C3D10 yüzeyi): üniform basınçta KÖŞELER 0, kenar-orta
            #   düğümler A/3 (kuadratik şekil-fonksiyonu integrali). Yükü köşeye
            #   koymak quadratic'i 1. mertebeye düşürür (cyl V&V'deki %7.2 hatanın kaynağı).
            quadratic = tris.shape[1] >= 6
            for tri in tris:
                p1 = mesh.points[tri[0] - 1]
                p2 = mesh.points[tri[1] - 1]
                p3 = mesh.points[tri[2] - 1]
                v1 = p2 - p1
                v2 = p3 - p1
                normal = np.cross(v1, v2)
                area2 = np.linalg.norm(normal)
                if area2 < 1e-20:
                    continue
                area = 0.5 * area2
                n_unit = normal / area2  # outward normal yönü
                # Pressure: yüzeye doğru = -normal yönünde kuvvet
                f_total = -pl.pressure_pa * area * n_unit  # (3,) Newton
                f_per_node = f_total / 3.0
                load_nodes = tri[3:6] if quadratic else tri[:3]  # T6→kenar-orta, T3→köşe
                for n in load_nodes:
                    for axis in (0, 1, 2):
                        key = (int(n), axis + 1)  # CalculiX DOF: 1=x,2=y,3=z
                        nodal_force_accumulator[key] = (
                            nodal_force_accumulator.get(key, 0.0) + f_per_node[axis]
                        )

    # Force loads -> nodal kuvvetlere ekle
    for fl in case.force_loads:
        if len(fl.node_ids) == 0:
            continue
        f_per_node = np.array(fl.direction, dtype=np.float64)
        norm = np.linalg.norm(f_per_node)
        if norm < 1e-12:
            continue
        f_per_node = f_per_node / norm * (fl.total_force_n / len(fl.node_ids))
        for n in fl.node_ids:
            for axis in (0, 1, 2):
                key = (int(n), axis + 1)
                nodal_force_accumulator[key] = (
                    nodal_force_accumulator.get(key, 0.0) + f_per_node[axis]
                )

    # Dugum-basina SERBEST kuvvet -> ayni birikece
    #
    # NEDEN GEREKLI. `ForceLoad` bir TOPLAM kuvveti tek yonde dugumlere esit
    # dagitir; FSI aktariminin urettigi yuk ise dugum basina AYRI ve 3
    # bilesenlidir, yani o siniftan ifade EDILEMEZ. Bu eksik yuzunden uc
    # cagiran (vehicle_fea, turek_hron_fsi1 x2) uretilen .inp METNINI elle
    # duzenliyordu: `txt.replace("*STATIC", "*STATIC\n" + cload, 1)`.
    #
    # O DESEN KIRILGAN VE BEDELI OLCULDU. NLGEOM acildiginda `*STATIC` bir
    # artim satiri tasir ("0.1, 1.0") ve enjeksiyon onu CLOAD blogunun
    # icine iter; CalculiX girdiyi reddeder. CSM1'de tam bu oldu. Lineer
    # adimda o satir olmadigi icin kusur SESSIZDI --- yani vehicle_fea'da
    # NLGEOM'un acildigi gun patlayacak gizli bir kusurdu.
    for _n, _f in (case.dugum_kuvvetleri or {}).items():
        for axis in (0, 1, 2):
            if abs(float(_f[axis])) > 1e-14:
                key = (int(_n), axis + 1)
                nodal_force_accumulator[key] = (
                    nodal_force_accumulator.get(key, 0.0) + float(_f[axis])
                )

    # ─── ANALİZ ADIMI ───
    #
    # NLGEOM YALNIZ STATIC'TE ANLAMLIDIR ve bu SESSİZCE geçilmez.
    # FREQUENCY/BUCKLE kendi doğrusallaştırılmış problemlerini çözer; oraya
    # NLGEOM koymak CalculiX'i düşürmez ama okuyucuya yapılmayan bir şey
    # yapılmış gibi görünür. İstenmişse ve uygulanamıyorsa DOSYAYA yazılır.
    _nlgeom = bool(getattr(case, "nlgeom", False))
    _tip = case.analysis_type.upper()
    _statik = _tip not in ("FREQUENCY", "BUCKLE")
    if _nlgeom and not _statik:
        lines.append(f"** NLGEOM İSTENDİ ama {case.analysis_type.upper()} "
                     f"adımında UYGULANMAZ — bu adım doğrusallaştırılmış "
                     f"problemi çözer.")
    # ARTIM TAVANI. CalculiX varsayilani 100'dur ve zaman-cozunur bir kosu
    # bunu kolayca asar: OLCULDU --- 6 periyot x 40 adim = 240 artim isteyen
    # bir kosu "*ERROR: max. # of increments reached" ile dustu. Tavan
    # ISTENEN ADIM SAYISINDAN TURETILIR, sabit yazilmaz; %20 pay birakilir
    # cunku CalculiX yakinsamada adim kucultebilir.
    #
    # `*CONTROLS` bilerek YAZILMIYOR (parametre sirasi bu depoda
    # dogrulanmadi) ama `INC` tek bir belgeli anahtardir ve gereksinimi
    # ARIZA MESAJININ KENDISI soyledi.
    _inc = ""
    if _tip == "DYNAMIC" and case.dinamik_dt > 0:
        _gerekli = int(case.dinamik_sure / case.dinamik_dt * 1.2) + 10
        _inc = f", INC={max(case.max_artim_sayisi, _gerekli)}"
    elif _nlgeom and _statik:
        _inc = f", INC={case.max_artim_sayisi}"
    lines.append(("*STEP, NLGEOM" if (_nlgeom and _statik) else "*STEP") + _inc)
    if _tip == "FREQUENCY":
        lines.append("*FREQUENCY")
        lines.append(f"{case.num_modes}")
    elif _tip == "BUCKLE":
        lines.append("*BUCKLE")
        lines.append(f"{case.num_modes}")
    elif _tip == "DYNAMIC":
        # ZAMAN-COZUNUR: dogrudan integrasyon (implicit, HHT-alpha).
        # Satir: dt, toplam_sure. `alpha` sayisal sonumdur ve KAYDA yazilir
        # --- birakilan sonum bir cozumdeki genlik dususunu "fizik" gibi
        # gosterir ve o hata sessizdir.
        lines.append(f"** dinamik: dt={case.dinamik_dt:g} s, "
                     f"sure={case.dinamik_sure:g} s, "
                     f"HHT alpha={case.dinamik_alpha:g} (sayısal sönüm)")
        lines.append(f"*DYNAMIC, ALPHA={case.dinamik_alpha:g}"
                     + (", DIRECT" if case.dinamik_direct else ""))
        lines.append(f"{case.dinamik_dt:g}, {case.dinamik_sure:g}")
    elif _nlgeom:
        # YUK ARTIMLI UYGULANIR. Buyuk yer-degistirmede denge Newton ile
        # cozulur ve tek adimda yakinsamak zorunda degildir; CalculiX'e ilk
        # artim ve toplam "sure" verilir (statikte sure yalnizca yuk
        # olceginin parametresidir).
        #
        # `*CONTROLS` YAZILMIYOR ve bu bir tercih: o karti dogru yazmak
        # TIME INCREMENTATION parametrelerinin sirasini bilmeyi gerektirir
        # ve bu depoda dogrulanmadi. Dogrulanmamis bir kontrol karti,
        # varsayilanlardan daha kotu davranabilir ve sebebi gorunmez olur.
        # Varsayilanlar birakildi; yakinsamama log'da gorunur.
        lines.append("*STATIC")
        lines.append(f"{case.ilk_artim:g}, 1.0")
    else:
        lines.append("*STATIC")

    # BC'ler
    for bc in case.fixed_bcs:
        nset = bc_nset.get(id(bc), bc.name)
        lines.append("*BOUNDARY")
        lines.append(f"{nset}, {bc.dof_start}, {bc.dof_end}, 0.0")

    # Konsantre yükler (tüm pressure + force toplamları)
    # BUCKLE: referans yük adımın içinde verilir; özdeğer × bu yük = kritik yük.
    if nodal_force_accumulator and _tip in ("STATIC", "BUCKLE", "DYNAMIC"):
        lines.append("*CLOAD")
        for (node_id, dof), val in sorted(nodal_force_accumulator.items()):
            if abs(val) < 1e-12:
                continue
            lines.append(f"{node_id}, {dof}, {val:.6e}")

    # Eylemsizlik gövde-kuvveti (g-yükü) — *DLOAD GRAV (yoğunluk *DENSITY'den)
    if case.gravity_loads and _tip in ("STATIC", "DYNAMIC"):
        lines.append("*DLOAD")
        for gl in case.gravity_loads:
            d = np.asarray(gl.direction, dtype=np.float64)
            d = d / (np.linalg.norm(d) + 1e-30)
            lines.append(f"EALL, GRAV, {gl.accel_m_s2:.6e}, "
                         f"{d[0]:.6f}, {d[1]:.6f}, {d[2]:.6f}")

    # Termal yük: üniform ΔT → α·ΔT termal strain (engellenirse termal gerilme)
    if thermal and case.analysis_type.upper() == "STATIC":
        lines.append("*TEMPERATURE")
        lines.append(f"NALL, {case.delta_t:.6e}")

    # Çıktı talepleri
    lines.append("*NODE FILE")
    if case.analysis_type.upper() == "STATIC":
        lines.append("U, RF")
        lines.append("*EL FILE")
        lines.append("S, E")
    else:
        lines.append("U")
    lines.append("*END STEP")

    inp_path.write_text("\n".join(lines), encoding="utf-8")
    return inp_path


def _write_id_list(lines: list[str], ids, per_line: int = 8) -> None:
    """ID listesini per_line ID/satır olarak ekle."""
    ids = np.asarray(ids).flatten().astype(np.int64)
    for i in range(0, len(ids), per_line):
        chunk = ids[i:i + per_line]
        lines.append(", ".join(f"{n:d}" for n in chunk))


# ─────────────────────────────────────────────────────────────────────────────
# Yüzey üçgeninden node ID çıkarma yardımcısı
# ─────────────────────────────────────────────────────────────────────────────

def surface_face_nodes(mesh: TetMesh, face_indices: np.ndarray) -> np.ndarray:
    """Verilen yüzey üçgen index'lerinden 1-indexed CalculiX node ID array'i (kümesi).

    Args:
        mesh: TetMesh
        face_indices: surface_tris içindeki üçgenlerin index'leri

    Returns:
        np.ndarray (M,) — benzersiz, sıralı, 1-indexed
    """
    if len(face_indices) == 0 or len(mesh.surface_tris) == 0:
        return np.array([], dtype=np.int64)
    selected = mesh.surface_tris[face_indices]  # (K, 3 veya 6)
    unique = np.unique(selected.flatten())
    return (unique + 1).astype(np.int64)
