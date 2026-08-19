"""BAĞIMSIZ FEA çapaları — özgüllüğü ölçebilmek için "doğru çıkması beklenen" hücre.

NEDEN. `dis_korpus` guard'ı dış vakalarda ölçtü ve özgüllüğü YAYINLAYAMADI:
güvenilir bir NEGATİF etiket (|E| küçük VE bunu söyleyebilecek kadar dar band)
kuracak hücre yoktu. Depodaki dış-referanslı koşuların hemen tamamı bir
tutarsızlığı soruşturmak için yapılmış, yani hata-ağırlıklı; iki aday çapa da
|E| ≤ u_val olduğu için ETİKETLENEMEDİ.

Kapalı-form FEA tam da eksik olan rejimdir: gerçek değer analitik (u_D≈0) ve
koşu saniyeler sürer. Buradaki iki vaka, FEA_KABUL_SINIRI'nı belirleyen ALTI
benchmark'ın DIŞINDADIR --- eşik sabitken yeni bir vaka geçerli bir
dışarıda-bırakma testidir.

İKİ FARKLI NİCELİK SINIFI seçildi, çünkü eşik sınıfa göre değişiyor
(yer_degistirme 0,05 · ozdeger 0,05):
  1) Basit mesnetli kiriş, yayılı yük  → yer değiştirme   δ=5wL⁴/(384EI)
  2) Ankastre kiriş, 1. doğal frekans  → özdeğer          f₁=(1,875²/2π)√(EI/ρAL⁴)

KAPALI FORMUN KENDİ HATASI YOK SAYILMAZ. İkisi de Euler-Bernoulli kirişidir ve
3B elastisiteye göre ~(h/L)² mertebesinde kayma-deformasyonu hatası taşır.
Bu, referansın u_D'sidir ve raporlanır; "analitik" demek "hatasız" demek değildir.

    python experiments/fea_capa_bagimsiz.py
Çıktı: fea_capa_bagimsiz.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import gmsh
import meshio
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
for _a in (sys.stdout, sys.stderr):
    if hasattr(_a, "reconfigure"):
        _a.reconfigure(encoding="utf-8", errors="replace")

from analysis.calculix_writer import (  # noqa: E402
    FEACase,
    FEAMaterial,
    FixedBC,
    ForceLoad,
    PressureLoad,
    write_inp,
)
from analysis.ccx_runner import run_ccx  # noqa: E402
from analysis.frd_parser import parse_frd  # noqa: E402
from analysis.tet_mesher import TetMesh  # noqa: E402

E, NU, RHO = 210e9, 0.30, 7850.0        # çelik
B = H = 0.05                            # kare kesit kenarı (m)
L = 1.5                                 # açıklık (m) → L/h = 30, ince kiriş
W_PRESSURE = 2.0e5                      # üst yüzeye yayılı basınç (Pa)

I_KESIT = B * H ** 3 / 12.0
A_KESIT = B * H
# Basınç → birim boyda çizgisel yük: w = p·b [N/m]
W_LINE = W_PRESSURE * B
DELTA_AN = 5.0 * W_LINE * L ** 4 / (384.0 * E * I_KESIT)
F1_AN = (1.875104 ** 2 / (2.0 * math.pi)) * math.sqrt(
    E * I_KESIT / (RHO * A_KESIT * L ** 4))
# Euler-Bernoulli'nin 3B elastisiteye göre kayma-deformasyonu hatası ~ (h/L)²
U_D_PCT = round((H / L) ** 2 * 100.0, 3)


TEK_AG_YOK = (
    "Tek ağ, ölçülmemiş bir sayısal belirsizlik demektir. Bu çapaların amacı "
    "GÜVENİLİR NEGATİF etiket üretmek; |E| küçük olsa bile u_num bilinmiyorsa "
    "etiket kurulamaz ve hücre yine BELİRSİZ'e düşerdi.")
SEVIYELER = (1.0, 1.4, 2.0)     # ağ inceltme çarpanı (h bölen)
# Küre AYRI: kiriş çapaları üç seviyede yakınsadı (u_num≈%0,01) ama küre
# yüzey gerilmesi yavaş yakınsıyor --- eğri yüzeyde C3D10 gerilmesi böyledir.
# Ağı yalnız İHTİYAÇ DUYAN vakada artırmak, yakınsamış olanları boşuna
# yeniden koşmaktan ucuzdur (küre ağları 8k eleman mertebesinde).
SEVIYELER_KURE = (1.4, 2.0, 2.8, 4.0)


def _mesh(work: Path, ad: str, boy: float, incelik: float = 1.0) -> TetMesh:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.addBox(0, 0, 0, boy, B, H)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMin", H / 3 / incelik)
        gmsh.option.setNumber("Mesh.MeshSizeMax", H / 2 / incelik)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        msh = work / f"{ad}.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    m = meshio.read(str(msh))
    tet = next(c for c in m.cells if c.type == "tetra10")
    tri = next((c for c in m.cells if c.type == "triangle6"), None)
    return TetMesh(points=m.points.astype(np.float64),
                   tets=tet.data.astype(np.int64),
                   surface_tris=(tri.data.astype(np.int64) if tri is not None
                                 else np.zeros((0, 6), np.int64)),
                   msh_path=msh, element_type="C3D10")


def kiris_sehim(work: Path, incelik: float = 1.0) -> dict:
    """Basit mesnetli kiriş + yayılı basınç → orta açıklık sehimi."""
    mesh = _mesh(work, f"kiris{incelik}", L, incelik)
    p = mesh.points
    tol = 1e-7
    # Basit mesnet: iki uçta ALT kenar çizgisi. Tüm uç yüzeyi tutmak ANKASTRE
    # olurdu ve kapalı-form artık geçerli olmazdı --- mesnet tipini yanlış
    # kurmak, referansı değil kurulumu sınamak demektir.
    sol = np.where((np.abs(p[:, 0]) < tol) & (np.abs(p[:, 2]) < tol))[0] + 1
    sag = np.where((np.abs(p[:, 0] - L) < tol) & (np.abs(p[:, 2]) < tol))[0] + 1
    # PressureLoad ÜÇGEN indeksi ister, düğüm değil: üst yüzeyde KÖŞE
    # düğümlerinin üçü de z=H olan yüzey üçgenleri.
    kose = mesh.surface_tris[:, :3]
    idx = np.where(np.all(np.abs(p[kose][:, :, 2] - H) < tol, axis=1))[0]
    if len(idx) == 0:
        raise AssertionError("üst yüzeyde basınç üçgeni bulunamadı")
    # T6'nın ALTI düğümü de geçer: yazıcı kuadratik tutarlı-yükü (köşe 0,
    # kenar-orta A/3) ancak böyle uygulayabilir. Köşeye yüklemek elemanı
    # 1. mertebeye düşürür --- silindir V&V'sindeki %7,2 hatanın kaynağı buydu.
    ust_tri = (mesh.surface_tris[idx] + 1).astype(np.int64)

    case = FEACase(
        name=f"kiris{incelik}".replace(".", "_"), mesh=mesh, material=FEAMaterial("CELIK", E, NU, RHO),
        # Sol uç: düşey + yanal tutulur (dz, dy); sağ uç yalnız düşey →
        # eksenel uzamaya izin verilir, aksi halde membran kilitlenmesi
        # sehimi YAPAY olarak azaltır.
        fixed_bcs=[FixedBC(sol, "MESNET_SOL", 2, 3), FixedBC(sol, "SOLX", 1, 1),
                   FixedBC(sag, "MESNET_SAG", 2, 3)],
        pressure_loads=[PressureLoad(ust_tri, W_PRESSURE, "PUST")],
        analysis_type="STATIC")
    inp = write_inp(case, work)
    r = run_ccx(inp, timeout=900)
    if not r.success:
        return {"durum": "hata", "mesaj": (r.stderr or r.stdout or "")[-300:]}
    frd = parse_frd(inp.with_suffix(".frd"))
    if "DISP" not in frd.fields:
        return {"durum": "hata", "mesaj": "frd yer değiştirme taşımıyor"}
    u = frd.fields["DISP"]
    # frd düğüm SIRASI giriş sırasıyla aynı olmak zorunda değil: seçim
    # node_ids üzerinden yapılır, indeks varsayımıyla değil.
    kimlik = frd.node_ids
    hedef = set(np.where(np.abs(p[:, 0] - L / 2.0) < H / 3.0)[0] + 1)
    maske = np.array([int(k) in hedef for k in kimlik])
    if not maske.any():
        return {"durum": "hata", "mesaj": "orta açıklık düğümü bulunamadı"}
    sehim = float(np.abs(u[maske, 2]).max())
    return {"durum": "ok", "nicelik": "yer_degistirme",
            "analitik_m": DELTA_AN, "fem_m": sehim,
            "hata_pct": abs(sehim - DELTA_AN) / DELTA_AN * 100.0,
            "dugum": int(mesh.num_nodes), "eleman": int(mesh.num_tets)}


R_IC, R_DIS, P_IC = 0.05, 0.10, 50e6     # kalın küre: iç/dış yarıçap, iç basınç
# Lamé (KÜRE, silindir DEĞİL). Genel çözüm:
#   σ_t(r) = p·r_ic³/(r_dış³−r_ic³) · (1 + r_dış³/(2r³))
# İç yüzeyde (r=r_ic) sadeleşir:
#   σ_t(r_ic) = p·(2r_ic³ + r_dış³) / (2(r_dış³ − r_ic³))
#
# İLK SÜRÜM KATSAYILARI TERS YAZDI (r_ic³+2r_dış³) ve referansı 60,7 MPa
# gösterdi; doğrusu 35,7 MPa. FEM %43 "sapıyor" görünüyordu, oysa sapan
# referanstı. DOĞRULAMA: r=r_ic'de σ_r = p·r_ic³/(r_dış³−r_ic³)·(1−r_dış³/r_ic³)
# = −p çıkmalı; bu özdeşlik formülü tutuyor. Gerçek değer denetlenmeden
# hiçbir hüküm kurulamaz --- çapanın kendisi de bir kanıttır.
SIG_KURE_AN = P_IC * (2 * R_IC ** 3 + R_DIS ** 3) / (2 * (R_DIS ** 3 - R_IC ** 3))
_SIG_R_KONTROL = (P_IC * R_IC ** 3 / (R_DIS ** 3 - R_IC ** 3)
                  * (1 - R_DIS ** 3 / R_IC ** 3))
assert abs(_SIG_R_KONTROL + P_IC) < 1e-6 * P_IC, "Lamé özdeşliği tutmuyor"
# Küre kapalı-formu TAM elastisite çözümüdür (kiriş teorisi gibi bir yaklaşım
# değil): referansın model hatası yok, u_D yalnız ayrıklaştırmadan gelir.
U_D_KURE_PCT = 0.0


def kure_lame(work: Path, incelik: float = 1.0) -> dict:
    """Kalın küre + iç basınç → iç yüzey teğetsel gerilmesi (Lamé).

    Kiriş kümesinden AYRI bir geometri: özgüllük tek geometrinin kurulumlarından
    kestirilirse küme yapısı sayıyı olduğundan güvenli gösterir.
    """
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        dis = gmsh.model.occ.addSphere(0, 0, 0, R_DIS)
        ic = gmsh.model.occ.addSphere(0, 0, 0, R_IC)
        kabuk, _ = gmsh.model.occ.cut([(3, dis)], [(3, ic)])
        # SEKİZDE BİR: üç simetri düzlemi → aynı çözüm, sekizde bir maliyet.
        kutu = gmsh.model.occ.addBox(0, 0, 0, R_DIS * 1.2, R_DIS * 1.2, R_DIS * 1.2)
        parca, _ = gmsh.model.occ.intersect(kabuk, [(3, kutu)])
        gmsh.model.occ.synchronize()
        hh = (R_DIS - R_IC) / 6.0 / incelik
        gmsh.option.setNumber("Mesh.MeshSizeMin", hh)
        gmsh.option.setNumber("Mesh.MeshSizeMax", hh * 1.6)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        msh = work / f"kure{incelik}.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    m = meshio.read(str(msh))
    tet = next(c for c in m.cells if c.type == "tetra10")
    tri = next((c for c in m.cells if c.type == "triangle6"), None)
    mesh = TetMesh(points=m.points.astype(np.float64),
                   tets=tet.data.astype(np.int64),
                   surface_tris=(tri.data.astype(np.int64) if tri is not None
                                 else np.zeros((0, 6), np.int64)),
                   msh_path=msh, element_type="C3D10")

    p = mesh.points
    tol = 1e-7
    duz = [np.where(np.abs(p[:, i]) < tol)[0] + 1 for i in range(3)]
    kose = mesh.surface_tris[:, :3]
    rr = np.linalg.norm(p[kose], axis=2).mean(axis=1)
    ic_tri = np.where(np.abs(rr - R_IC) < (R_DIS - R_IC) * 0.25)[0]
    if len(ic_tri) == 0:
        return {"durum": "hata", "mesaj": "iç yüzey üçgeni bulunamadı"}

    case = FEACase(
        name=f"kure{incelik}".replace(".", "_"), mesh=mesh,
        material=FEAMaterial("CELIK", E, NU, RHO),
        fixed_bcs=[FixedBC(duz[0], "SYMX", 1, 1), FixedBC(duz[1], "SYMY", 2, 2),
                   FixedBC(duz[2], "SYMZ", 3, 3)],
        pressure_loads=[PressureLoad((mesh.surface_tris[ic_tri] + 1).astype(np.int64),
                                     P_IC, "PIC")],
        analysis_type="STATIC")
    inp = write_inp(case, work)
    r = run_ccx(inp, timeout=1800)
    if not r.success:
        return {"durum": "hata", "mesaj": (r.stderr or r.stdout or "")[-300:]}
    frd = parse_frd(inp.with_suffix(".frd"))
    vm = frd.von_mises()
    if vm is None:
        return {"durum": "hata", "mesaj": "frd gerilme taşımıyor"}
    # İÇ YÜZEYDEKİ düğümler: tepe değeri tüm gövdeden almak, mesnet
    # köşesindeki tekilliği ölçmek olurdu.
    rn = np.linalg.norm(p, axis=1)
    # SEÇİM BANDI GEOMETRİK OLMALI, duvar kalınlığının yüzdesi DEĞİL.
    # İlk sürüm bandı 0,06·(r_dış−r_iç) = 3 mm alıyordu; oysa σ_t yüzeyden
    # 3 mm içeride %12,8 düşüyor (kapalı-formdan hesaplanabilir). Medyan o
    # bandın içine yayılınca ÖLÇÜM sistematik olarak düşük çıkıyordu ve bu
    # ayrıklaştırma hatası gibi görünüyordu. gmsh düğümleri CAD yüzeyine
    # oturtur (kuadratik kenar-orta düğümler de eğrilir), dolayısıyla
    # yüzey düğümleri için mikron mertebesinde bir tolerans yeterlidir.
    ic_dugum = set(np.where(np.abs(rn - R_IC) < R_IC * 1e-4)[0] + 1)
    maske = np.array([int(k) in ic_dugum for k in frd.node_ids])
    if not maske.any():
        return {"durum": "hata", "mesaj": "iç yüzey düğümü bulunamadı"}
    # Küresel simetride asal gerilmeler (σ_t, σ_t, σ_r) → vM = |σ_t − σ_r|.
    # İç yüzeyde σ_r = −p olduğundan σ_t = vM + σ_r = vM − p. İlk sürüm
    # ARTI yazıyordu ve %121 sapma veriyordu; ağ yakınsamıştı (u_num=%0,4),
    # yani sapma ayrıklaştırmadan değil bu işaretten geliyordu.
    sig = float(np.median(vm[maske])) - P_IC
    return {"durum": "ok", "nicelik": "gerilme",
            "analitik_Pa": SIG_KURE_AN, "fem_Pa": sig,
            "hata_pct": abs(sig - SIG_KURE_AN) / SIG_KURE_AN * 100.0,
            "dugum": int(mesh.num_nodes), "eleman": int(mesh.num_tets)}


def _dat_frekanslari(dat_path) -> list[float]:
    """CalculiX .dat'tan öz-frekansları (Hz) çıkar.

    Blok başlığı 'EIGENVALUE OUTPUT' ve satırlar:
      mod  özdeğer  ω(rad/s)  f(cycles/time)  ...
    Frekans SÜTUNU alınır; özdeğerden kök alıp 2π'ye bölmek aynı sayıyı verir
    ama sütun zaten oradadır ve iki yoldan hesaplamak ayrışma riskidir.
    """
    p = Path(dat_path) if dat_path else None
    if not p or not p.exists():
        return []
    out, icinde = [], False
    for ln in p.read_text(errors="ignore").splitlines():
        yassi = ln.upper().replace(" ", "")
        if "EIGENVALUEOUTPUT" in yassi or "EIGENVALUENUMBER" in yassi:
            icinde = True
            continue
        if not icinde:
            continue
        alan = ln.split()
        if len(alan) >= 4:
            try:
                out.append(float(alan[3].replace("D", "E").replace("d", "e")))
                continue
            # sessiz-yutma: kabul — .dat bloğu başlık/boş satırlar da içerir ve
            # sayıya çevrilemeyen satır BURADA beklenen durumdur, hata değil.
            # Sebebin yutulması bilgi kaybetmiyor: blok bittiğinde `out` doluysa
            # döngü kırılır, boşsa çağıran "dat frekans taşımıyor" HATASI alır.
            except ValueError:
                pass
        if out:
            break
    return out


def kiris_frekans(work: Path, incelik: float = 1.0) -> dict:
    """Ankastre kiriş → 1. eğilme doğal frekansı."""
    mesh = _mesh(work, f"modal{incelik}", L, incelik)
    p = mesh.points
    kok = np.where(np.abs(p[:, 0]) < 1e-7)[0] + 1
    case = FEACase(name=f"modal{incelik}".replace(".", "_"), mesh=mesh,
                   material=FEAMaterial("CELIK", E, NU, RHO),
                   fixed_bcs=[FixedBC(kok, "ANKASTRE", 1, 3)],
                   analysis_type="FREQUENCY", num_modes=6)
    inp = write_inp(case, work)
    r = run_ccx(inp, timeout=900)
    if not r.success:
        return {"durum": "hata", "mesaj": (r.stderr or r.stdout or "")[-300:]}
    # `parse_frd` YALNIZ ilk adımı okur; frekanslar .dat'tadır. Burkulma
    # çapasının kullandığı desen (özdeğer bloğunu .dat'tan ayıkla) burada
    # tekrarlanır --- iki yerde iki ayrı okuyucu tutmak ayrışma demek olurdu.
    f = _dat_frekanslari(r.dat_path)
    if not f:
        return {"durum": "hata", "mesaj": f"dat frekans taşımıyor: {r.dat_path}"}
    # Kare kesitte 1. mod iki yönde ÇİFT KATLIdır; en küçüğü al.
    f1 = float(min(x for x in f if x > 1e-6))
    return {"durum": "ok", "nicelik": "ozdeger",
            "analitik_hz": F1_AN, "fem_hz": f1,
            "hata_pct": abs(f1 - F1_AN) / F1_AN * 100.0,
            "modlar_hz": [round(float(x), 3) for x in f[:6]],
            "dugum": int(mesh.num_nodes), "eleman": int(mesh.num_tets)}


def main() -> int:
    work = HERE.parent / "_fea_capa_bagimsiz"
    work.mkdir(exist_ok=True)
    print(f"  Analitik: sehim={DELTA_AN * 1e6:.3f} um · f1={F1_AN:.3f} Hz "
          f"· referans u_D≈%{U_D_PCT} (kayma-deformasyonu, (h/L)²)\n", flush=True)

    out = {
        "vaka": "Bağımsız FEA çapaları — FEA_KABUL_SINIRI'nı belirleyen altı "
                "benchmark'ın DIŞINDA",
        "_neden": "dis_korpus özgüllüğü yayınlayamadı: güvenilir NEGATİF etiket "
                  "kuracak (|E| küçük ve band dar) hücre yoktu.",
        "geometri": {"b_m": B, "h_m": H, "L_m": L, "L_over_h": L / H,
                     "E_Pa": E, "nu": NU, "rho": RHO},
        "referans_u_D_pct": U_D_PCT,
        "referans_kaynak": "Euler-Bernoulli kiriş teorisi (kapalı-form); "
                           "u_D = (h/L)² kayma-deformasyonu mertebesi",
        "ag_ailesi": {"incelikler": list(SEVIYELER),
                      "incelikler_kure": list(SEVIYELER_KURE),
                      "_neden": TEK_AG_YOK},
    }

    for ad, fn, alan, u_d in (("sehim", kiris_sehim, "fem_m", U_D_PCT),
                              ("frekans", kiris_frekans, "fem_hz", U_D_PCT),
                              ("kure", kure_lame, "fem_Pa", U_D_KURE_PCT),
                              # ÜÇÜNCÜ bağımsız geometri: özgüllük küme sayısına
                              # duyarlı ve negatifler iki kümeden geliyordu.
                              ("mil", mil_burulma, "fem_rad_m", U_D_KURE_PCT)):
        seviyeler = []
        for inc in (SEVIYELER_KURE if ad == "kure" else SEVIYELER):
            d = fn(work, inc)
            d["incelik"] = inc
            seviyeler.append(d)
            durum = (f"hata=%{d['hata_pct']:.3f}" if d["durum"] == "ok"
                     else f"HATA: {d['mesaj'][:60]}")
            print(f"  {ad:8s} h/{inc:<4} {durum}", flush=True)
        iyi = [x for x in seviyeler if x["durum"] == "ok"]
        band = None
        if len(iyi) >= 2:
            a, b = iyi[-2][alan], iyi[-1][alan]
            band = abs(b - a) / abs(b) * 100.0     # en ince iki seviye bağıl fark
        son = iyi[-1] if iyi else {}
        u_val = (math.hypot(band, u_d) if band is not None else None)
        out[ad] = {
            "seviyeler": seviyeler,
            "en_ince": son,
            "u_num_pct": (round(band, 4) if band is not None else None),
            "u_num_yontem": "en ince iki seviye bağıl farkı",
            "u_D_pct": u_d,
            "u_val_pct": (round(u_val, 4) if u_val is not None else None),
            "hata_pct": son.get("hata_pct"),
        }
        if u_val is not None and son:
            print(f"    → u_num=%{band:.4f} ⊕ u_D=%{u_d} → u_val=%{u_val:.4f}"
                  f"  |E|=%{son['hata_pct']:.3f}", flush=True)
    # HÜKÜM ZORUNLU: sayıyı hükümsüz yayınlamak bu deponun kapattığı kusur.
    # Her çapa, negatif etiket kurmaya yetip yetmediğiyle birlikte özetlenir.
    esik = 5.0
    satir = []
    for ad in ("sehim", "frekans", "kure", "mil"):
        b = out.get(ad) or {}
        if b.get("hata_pct") is None or b.get("u_val_pct") is None:
            satir.append(f"{ad}: ÖLÇÜLEMEDİ")
            continue
        pay = esik - (b["hata_pct"] + b["u_val_pct"])
        satir.append(f"{ad}: |E|=%{b['hata_pct']:.3f} ⊕ u_val=%{b['u_val_pct']:.3f}"
                     f" → eşiğe {pay:.2f} puan"
                     + (" (NEGATİF ETİKET KURULABİLİR)" if pay > 0 else
                        " (KURULAMAZ)")
                     + (" ⚠ SINIRDA" if 0 < pay < 1.0 else ""))
    out["verdikt"] = ("✅ Üç çapa da negatif etiket kurabiliyor — " + " · ".join(satir)
                      if all("KURULABİLİR" in s for s in satir)
                      else "⚠️ " + " · ".join(satir))
    (HERE.parent / "fea_capa_bagimsiz.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n  YAZILDI fea_capa_bagimsiz.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ── Burulma çapası: ÜÇÜNCÜ bağımsız geometri ──────────────────────────────
# Korpusun negatif etiketleri iki kümeden geliyordu (kiriş, küre). Özgüllük
# küme sayısına duyarlıdır; üçüncü BAĞIMSIZ geometri onu güçlendirir.
#
# Neden burulma: kapalı-form TAM (St. Venant, dairesel kesitte kesin), yükleme
# kirişten ve küreden farklı, ve FEA_KABUL_SINIRI'nı belirleyen altı
# benchmark'ın hiçbiri burulma değil.
R_MIL, L_MIL, T_TORK = 0.02, 0.30, 500.0      # yarıçap, boy (m), tork (N·m)
J_KESIT = math.pi * R_MIL ** 4 / 2.0
G_MODUL = E / (2.0 * (1.0 + NU))
# Birim boyda burulma açısı — uçlardan UZAKTA (St. Venant bölgesi) geçerli.
BURULMA_ORANI_AN = T_TORK / (G_MODUL * J_KESIT)      # rad/m


def mil_burulma(work: Path, incelik: float = 1.0) -> dict:
    """Ankastre dairesel mil + uç torku → BİRİM BOYDA burulma açısı.

    UÇ ETKİSİ DIŞLANIR: toplam açı yerine iki ARA kesit arasındaki açı farkı
    ölçülür (z=0,25L ve z=0,75L). Uçta yükün nasıl dağıtıldığı St. Venant'a
    göre yalnız yerel etki yapar; ortadaki oran kapalı-formun geçerli olduğu
    bölgedir. Toplam açıyı ölçmek, ölçtüğü şeyi yük dağıtımına bağlardı.
    """
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, L_MIL, R_MIL)
        gmsh.model.occ.synchronize()
        hh = R_MIL / 2.5 / incelik
        gmsh.option.setNumber("Mesh.MeshSizeMin", hh)
        gmsh.option.setNumber("Mesh.MeshSizeMax", hh * 1.5)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        msh = work / f"mil{incelik}.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    m = meshio.read(str(msh))
    tet = next(c for c in m.cells if c.type == "tetra10")
    tri = next((c for c in m.cells if c.type == "triangle6"), None)
    mesh = TetMesh(points=m.points.astype(np.float64), tets=tet.data.astype(np.int64),
                   surface_tris=(tri.data.astype(np.int64) if tri is not None
                                 else np.zeros((0, 6), np.int64)),
                   msh_path=msh, element_type="C3D10")

    p = mesh.points
    kok = np.where(np.abs(p[:, 2]) < 1e-7)[0]
    uc = np.where(np.abs(p[:, 2] - L_MIL) < 1e-7)[0]
    if len(uc) == 0:
        return {"durum": "hata", "mesaj": "uç yüzey düğümü yok"}

    # TORK = teğetsel kuvvetler. Düğüm i'ye F_i = k·r_i (teğet yön) verilirse
    # moment Σ r_i·F_i = k·Σ r_i² olur; k = T/Σr_i² ile toplam tam T eder.
    rr = np.linalg.norm(p[uc, :2], axis=1)
    kats = rr > 1e-9
    uc, rr = uc[kats], rr[kats]
    k = T_TORK / float((rr ** 2).sum())
    yukler = []
    for dugum, r_i in zip(uc, rr):
        x, y = p[dugum, 0], p[dugum, 1]
        yukler.append(ForceLoad(np.array([dugum + 1], dtype=np.int64),
                                (-y / r_i, x / r_i, 0.0), k * r_i,
                                f"T{dugum}"))

    case = FEACase(name=f"mil{incelik}".replace(".", "_"), mesh=mesh,
                   material=FEAMaterial("CELIK", E, NU, RHO),
                   fixed_bcs=[FixedBC(kok + 1, "ANKASTRE", 1, 3)],
                   force_loads=yukler, analysis_type="STATIC")
    inp = write_inp(case, work)
    r = run_ccx(inp, timeout=1800)
    if not r.success:
        return {"durum": "hata", "mesaj": (r.stderr or r.stdout or "")[-300:]}
    frd = parse_frd(inp.with_suffix(".frd"))
    if "DISP" not in frd.fields:
        return {"durum": "hata", "mesaj": "frd yer değiştirme taşımıyor"}
    u = frd.fields["DISP"]
    kimlik = np.asarray(frd.node_ids, dtype=np.int64)

    def _aci(z_hedef):
        """Kesitteki ortalama burulma açısı: u_teğet / r."""
        sec = np.where(np.abs(p[:, 2] - z_hedef) < L_MIL * 0.03)[0]
        hedef = set((sec + 1).tolist())
        maske = np.array([int(x) in hedef for x in kimlik])
        if not maske.any():
            return None
        idx = kimlik[maske] - 1
        x, y = p[idx, 0], p[idx, 1]
        rad = np.hypot(x, y)
        iyi = rad > R_MIL * 0.3          # eksene yakın düğümde açı gürültülü
        if not iyi.any():
            return None
        ut = (-y[iyi] * u[maske][iyi, 0] + x[iyi] * u[maske][iyi, 1]) / rad[iyi]
        return float(np.median(ut / rad[iyi]))

    a1, a2 = _aci(0.25 * L_MIL), _aci(0.75 * L_MIL)
    if a1 is None or a2 is None:
        return {"durum": "hata", "mesaj": "ara kesit düğümü bulunamadı"}
    oran = (a2 - a1) / (0.5 * L_MIL)
    return {"durum": "ok", "nicelik": "yer_degistirme",
            "analitik_rad_m": BURULMA_ORANI_AN, "fem_rad_m": oran,
            "hata_pct": abs(oran - BURULMA_ORANI_AN) / BURULMA_ORANI_AN * 100.0,
            "dugum": int(mesh.num_nodes), "eleman": int(mesh.num_tets)}
