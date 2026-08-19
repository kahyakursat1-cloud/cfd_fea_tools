"""Pipeline validasyon koşusu: bilinen-doğru çapaları (validation_anchors.ANCHORS)
run_vehicle_analysis'ten geçirip ÖLÇÜLEN hata bandını üretir → validation_band.json.
Bu dosya yazıldığında model_uncertainty_pct literatür-öncülü bırakıp ölçülen bandı kullanır.

CFD GEREKTİRİR (her çapa 3-mesh GCI ile dakikalar). Koşu meşgulken çalıştırma.
Kullanım: python validate_pipeline.py [--hiz 30] [--anchor sphere]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from validation_anchors import ANCHORS  # noqa: E402
from vehicle_pipeline import GCI_MIN_ORAN, run_vehicle_analysis  # noqa: E402


def ahmed_body() -> trimesh.Trimesh:
    """Ahmed gövdesi, SAE standart ölçüler (Ahmed 1984): L=1.044 m, W=0.389, H=0.288,
    ön yuvarlatma R=0.100, arka slant 0.222 m @ 25°. Gövde konvekstir → yoğun kenar/
    yuvarlatma örneklemesinin konveks zarfı geçerli yüzeydir. Ayaklar (stilts) CFD
    konvansiyonu gereği ihmal. Burun x=0'da (akış +x), taban z=0 (zemin clearance
    run_vehicle_analysis(ground_clearance=0.05) ile verilir)."""
    L, W, H, R = 1.044, 0.389, 0.288, 0.100
    ang = math.radians(25.0)
    sx, sz = 0.222 * math.cos(ang), 0.222 * math.sin(ang)
    pts: list[tuple[float, float, float]] = []
    for t in np.linspace(0.0, math.pi / 2, 16):
        x, d = R * (1 - math.cos(t)), R * math.sin(t)
        w = W / 2 - R + d
        for z in (R, H - R):                       # dikey ön kenar yuvarlatması
            pts += [(x, -w, z), (x, w, z)]
        for y in (-(W / 2 - R), W / 2 - R):        # yatay ön kenar yuvarlatması
            pts += [(x, y, R - d), (x, y, H - R + d)]
    for cy in (-(W / 2 - R), W / 2 - R):           # ön köşe küre-oktantları
        for cz, sgn in ((R, -1.0), (H - R, 1.0)):
            for t in np.linspace(0.0, math.pi / 2, 8):
                for u in np.linspace(0.0, math.pi / 2, 8):
                    pts.append((R - R * math.cos(t),
                                cy + math.copysign(R * math.sin(t) * math.cos(u), cy),
                                cz + sgn * R * math.sin(t) * math.sin(u)))
    for x in (R, L - sx):                          # ana gövde + slant başlangıcı
        for y in (-W / 2, W / 2):
            pts += [(x, y, 0.0), (x, y, H)]
    for y in (-W / 2, W / 2):                      # taban (base) köşeleri
        pts += [(L, y, 0.0), (L, y, H - sz)]
    return trimesh.convex.convex_hull(np.asarray(pts, float)).subdivide()


def disk_body() -> trimesh.Trimesh:
    """Akışa dik dairesel disk (t/D=0.1): keskin-kenar ayrılması → Re-duyarsız ve
    türbülans-modeli-toleranslı bluff çapa (Hoerner Cd≈1.17). Silindir ekseni +x'e döndürülür."""
    m = trimesh.creation.cylinder(radius=0.05, height=0.01, sections=64)
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    return m


def naca0012_wing(ar: float = 6.0, chord: float = 0.15, n: int = 80) -> trimesh.Trimesh:
    """Dikdörtgen NACA0012 kanat (AR=6): LIFTING-rejim çapası. Kesit analitik kalınlık
    formülünden (kapalı-TE katsayısı -0.1036), açıklık boyunca ekstrüzyon + uçlarda
    merkez-fan kapak (kesit yıldız-şekilli → geçerli). Kiriş x, açıklık y, kalınlık z
    (akış-çerçevesi); Re_c = 3e5 @ 30 m/s."""
    xs = 0.5 * (1 - np.cos(np.linspace(0.0, math.pi, n)))
    t = 5 * 0.12 * (0.2969 * np.sqrt(xs) - 0.1260 * xs - 0.3516 * xs ** 2
                    + 0.2843 * xs ** 3 - 0.1036 * xs ** 4)
    ust = np.column_stack([xs, t])
    alt = np.column_stack([xs, -t])[::-1]
    prof = np.vstack([ust, alt[1:-1]]) * chord
    N = len(prof)
    span = ar * chord
    v0 = np.column_stack([prof[:, 0], np.full(N, -span / 2), prof[:, 1]])
    v1 = np.column_stack([prof[:, 0], np.full(N, +span / 2), prof[:, 1]])
    verts = np.vstack([v0, v1, v0.mean(0), v1.mean(0)])
    faces = []
    for i in range(N):
        j = (i + 1) % N
        faces += [[i, j, N + i], [j, N + j, N + i]]      # yan yüzeyler
        faces += [[2 * N, j, i], [2 * N + 1, N + i, N + j]]  # uç kapakları (fan)
    m = trimesh.Trimesh(vertices=verts, faces=np.asarray(faces), process=True)
    m.fix_normals()
    return m


# çapa → (geometri üreteci, pipeline araç-tipi, koşu-parametreleri).
# Hız seçimi çapanın Re bandına oturur: Ahmed 40 m/s → Re_L≈2.8e6 (Meile 2011);
# küp/disk keskin-kenarlı, Re-duyarsız → varsayılan hız.
_GEOM = {
    # cube v6 bulgusu (v5 dizisi 0.961→1.018→1.053→0.916): orta seviye Hoerner'a OTURDU;
    # ince seviye 2.14M hücreyle 2.5M TAVANINA çarpıp bütçe-kesilmişti → mesh ailesinin
    # sistematik üyesi değil (GCI/LSR varsayımı kırılır). Tavan 4M'e çıkarıldı.
    "cube": (lambda: trimesh.creation.box(extents=(0.1, 0.1, 0.1)), "genel",
             {"quality": "hassas_nl", "max_cells": 4_000_000,
              "refinement_regions": [
                  {"ad": "izBolgesi", "min": (0.05, -0.07, -0.07),
                   "max": (0.25, 0.07, 0.07), "level": 2}]}),
    "disk": (disk_body, "genel", {}),
    # ahmed v6 bulgusu: bölge kutuları HACMİ inceltti ama YÜZEY seviyesine dokunmuyor —
    # y⁺ 5237'de sabit kaldı, katmanlar yine örülmedi; kaba seviyeler platoda (p=0.05).
    # ref_bump +1 → yüzey (3,4): hücre 7.3→3.6mm, ilk-katman oranı 0.02→0.04 (örülebilir
    # kenar); tavan 3M (yüzey-kabuk + bölgeler için bütçe payı).
    "ahmed_25": (ahmed_body, "genel", {"velocity": 40.0, "ground_clearance": 0.05,
                                       "n_layers": 8, "yplus_target": 30.0,
                                       "ref_bump": 1, "max_cells": 3_000_000,
                                       "refinement_regions": [
                                           {"ad": "altBosluk", "min": (-0.05, -0.22, -0.051),
                                            "max": (1.10, 0.22, 0.07), "level": 4},
                                           {"ad": "yakinIz", "min": (1.04, -0.30, -0.051),
                                            "max": (2.10, 0.30, 0.35), "level": 3}]}),
    # LIFTING çapası: ince-kanat katman güvenle örülmez (hq dersi) → hassas_nl;
    # yüzey-Cd yakınsamazsa wake yolu (iz-momentum) kanıt verebilir (_accept hiyerarşisi).
    # ref_bump="oto": ÖLÇÜLDÜ ki bump=0'da kanat HİÇ ÇÖZÜLMÜYOR (2026-08-02).
    #   yüzey hücresi 11.4 mm → 150 mm kiriş boyunca yalnız 13 hücre
    #   firar kenarı 3.75 mm → hücrenin 0.33 katı (hedef ≥6)
    #   CL = 0.018, ince-kanat + sonlu-kanat teorisi 0.329 bekler → 18.2 KAT düşük
    #   Cd = 0.050, beklenen ~0.020
    #   y⁺ = 407, duvar-fonksiyonu bandının (30-300) dışında
    # Boru hattının kendi fizik önerisi zaten bump=2 diyordu (y⁺≈105, 33.959 yüz);
    # çapa kurulumu onu kullanmıyordu.
    #
    # DÜZELTME SONRASI ÖLÇÜLDÜ: y⁺ 407→134 (bant içi), yüzey yüzü 2.142→30.321,
    # Cd 0.050→0.0236 ve Richardson ekstrapolasyonu 0.0211 (beklenen 0.0204, %3).
    # Yani SÜRÜKLEME çapası artık sağlıklı.
    #
    # TAŞIMA İSE BU YOLLA ÇÖZÜLEMİYOR ve sebebi ölçüldü:
    #   seviye     hücre      Cl      Cd     L/D
    #    cokkaba    38.903  0.0572  0.0346   1.65
    #    kaba       97.075  0.0599  0.0278   2.15
    #    orta      290.382  0.0656  0.0251   2.61
    #    ince      802.880  0.0705  0.0236   2.98      beklenen L/D ≈ 16.1
    # Hücre 20.6 KAT artarken Cl yalnız %23 arttı; beklenen 0.329 için 4.7 kat daha
    # gerekiyor. Sebep firar kenarı: kalınlık 3.6 mm, yüzey hücresi 2.8 mm — TE
    # 1.3 HÜCRE. Kutta koşulu bir hücrelik firar kenarında kurulamaz, dolayısıyla
    # sirkülasyon (ve taşıma) doğmaz. Projenin kendi hedefi olan ≥6 hücre için
    # 0.60 mm hücre, yani YALNIZ YÜZEYDE ~775.000 yüz gerekir (şu anki TÜM mesh
    # 803 bin hücre) — bu donanımda çözülemez.
    #
    # Bu, 2B kanat profilinde zaten ölçülmüş dersin 3B karşılığıdır: taşıyıcı
    # kesitlerde snappyHexMesh kesme-hücre yaklaşımı yerine gövde-uyumlu yapısal
    # grid gerekir (TMR/C-grid yolu %1.7 GCI verdi). ÇAPA YALNIZ Cd DOĞRULAR;
    # ANCHORS["naca0012_wing_ar6"] zaten yalnız Cd referansı taşıyor, yani yanlış
    # bir iddia YOK — burada kayda geçen, aramanın tekrarlanmaması için ölçümdür.
    "naca0012_wing_ar6": (naca0012_wing, "ucak",
                          {"alpha_deg": 4.0, "quality": "hassas_nl",
                           "ref_bump": "oto"}),
}

# Koşulamayan çapalar — gerekçesiyle (dürüst V&V: setup-uyumsuz koşu validasyon değildir).
_SKIP_REASON = {
    "sphere": ("subkritik küre GEÇİŞ-BASKIN (laminer sınır tabakası + türbülanslı iz); "
               "tam-türbülanslı kOmegaSST ile setup-uyumsuz — 2026-07-06 kampanyası "
               "Cd=0.349 (türbülanslı-BL davranışı) ölçtü, ref 0.47 laminer-BL. "
               "LM geçiş-modeli yolu gerekir (TMR/standalone)."),
    "naca0012_a0": "2B airfoil → TMR yolu kapsar (tmr_cfd/), 3B pipeline değil.",
}

# LSR-kabul eşiği: sayısal band model-öncül bandından (bluff %10-20) küçük olmalı ki
# çapa model hatasını AYIRT EDEBİLSİN; daha geniş sayısal band validasyon yapamaz.
LSR_U_MAX_PCT = 15.0


def _gci_asimptotik(gci: dict | None) -> bool:
    if not gci:
        return False
    asy = gci.get("asymptotic")
    return bool(gci.get("monotonic") and gci.get("p_in_range")
                and gci.get("gci_fine_pct", 1e9) < 5.0
                and asy is not None and 0.5 <= asy <= 2.0)


def _sinirlayan_band(levels: list | None) -> dict | None:
    """Salınımlı 3-seviye dizisi için EKSTRAPOLASYONSUZ bant: U = 3·Δ_M (E&H 2014).

    NEDEN GEREKLİ: kabul hiyerarşisi yalnız EKSTRAPOLE EDEN yolları tanıyordu
    (asimptotik GCI, ≥4-seviye LSR). Salınımlı üçlü hiçbirine girmiyor ve
    "mesh-bağımsızlığı gösterilemedi" oluyordu — hatta değerler birbirine ÇOK
    yakınken bile.

    ÖLÇÜLDÜ (disk çapası): 66.858 / 203.798 / 648.569 hücrede Cd = 1.2049 /
    1.19256 / 1.20956. On kat hücre aralığında saçılma %1.4; h oranları 1.450 ve
    1.471 (Celik r≥1.3 SAĞLANIYOR). Bant U = 3·Δ_M = %4.22, Hoerner'a sapma
    %3.38 — yani sapma bandın İÇİNDE. Bu, "yakınsamış değer" kanıtı değildir ama
    SINIRLAMA kanıtıdır ve çapanın işi tam olarak budur.

    KAPI GEVŞEMİYOR — üç şart birlikte aranır:
      (a) en az 3 seviye (hepsi zaten fizik/yakınsama/yüzey kapılarından geçmiş),
      (b) ardışık h oranlarının HEPSİ ≥ 1.3; yoksa küçük Δ sahte-dar bant üretir
          (küpte ölçülmüştü: r=1.076'da p=-2.338 ve GCI=-%3.2),
      (c) bant < LSR_U_MAX_PCT, yani model-öncülünden dar.
    Ekstrapolasyon YOK: kestirim f_ince'dir, "Richardson değeri" DEĞİL.
    """
    if not levels or len(levels) < 3:
        return None
    c = [lv.get("cells") for lv in levels]
    f = [lv.get("Cd") for lv in levels]
    if any(x in (None, 0) for x in c) or any(x is None for x in f):
        return None
    r = [(c[i + 1] / c[i]) ** (1.0 / 3.0) for i in range(len(c) - 1)]
    if min(r) < GCI_MIN_ORAN:
        return None
    dm = max(abs(f[i + 1] - f[i]) for i in range(len(f) - 1))
    u = 3.0 * dm / max(abs(f[-1]), 1e-12) * 100
    return {"u_pct": round(u, 2), "f": f[-1], "n": len(f),
            "r_min": round(min(r), 3)}


def _accept(gci: dict, lsr: dict | None, cd_richardson, cd_fine, wake: dict | None = None,
            levels: list | None = None):
    """Çapa kabul kararı: (kabul_mü, cd_pred, yontem). Hiyerarşi: yüzey-GCI asimptotik >
    wake-GCI asimptotik (iz-momentum 2. mertebe — yüzey entegrasyonu çökerken drag kanıtı
    verebilir) > yüzey-LSR dar (U<%15) > wake-LSR dar > SINIRLAYAN band (salınımlı ≥3
    seviye, ekstrapolasyonsuz); hiçbiri yoksa RED."""
    if _gci_asimptotik(gci) and cd_richardson and cd_richardson > 0:
        return True, cd_richardson, "GCI (3-mesh, asimptotik)"
    wgci = (wake or {}).get("gci") or {}
    if _gci_asimptotik(wgci) and wgci.get("f_exact", 0) > 0:
        return True, wgci["f_exact"], "wake-GCI (iz-momentum, asimptotik)"
    if lsr and lsr.get("u_pct", 1e9) < LSR_U_MAX_PCT and lsr.get("f_exact", 0) > 0:
        return True, lsr["f_exact"], f"LSR ({lsr['n']}-seviye, U=%{lsr['u_pct']})"
    wlsr = (wake or {}).get("lsr")
    if wlsr and wlsr.get("u_pct", 1e9) < LSR_U_MAX_PCT and wlsr.get("f_exact", 0) > 0:
        return True, wlsr["f_exact"], f"wake-LSR ({wlsr['n']}-seviye, U=%{wlsr['u_pct']})"
    sb = _sinirlayan_band(levels)
    if sb and sb["u_pct"] < LSR_U_MAX_PCT and sb["f"] > 0:
        return True, sb["f"], (f"SINIRLAYAN band ({sb['n']}-seviye salınımlı, "
                               f"U=3·Δ=%{sb['u_pct']}, r_min={sb['r_min']}) — "
                               "ekstrapolasyon YOK, kestirim en ince seviyedir")
    return False, cd_fine, None


def _run_anchor(name: str, velocity: float, out_root: str) -> dict | None:
    spec = ANCHORS[name]
    if name not in _GEOM:
        return {"atlandi": _SKIP_REASON.get(name, "geometri üreteci yok")}
    gen, vtype, kw = _GEOM[name]
    v = kw.get("velocity", velocity)
    stl = HERE / out_root / f"_anchor_{name}.stl"
    stl.parent.mkdir(parents=True, exist_ok=True)
    gen().export(stl)
    r = run_vehicle_analysis(str(stl), vehicle_type=vtype, velocity=v,
                             alpha_deg=kw.get("alpha_deg", 0.0),
                             quality=kw.get("quality", "hassas"),
                             n_layers=kw.get("n_layers", 0),
                             yplus_target=kw.get("yplus_target", 30.0),
                             mesh_sensitivity=True, mesh_levels=4,
                             out_root=out_root, ground_clearance=kw.get("ground_clearance"),
                             refinement_regions=kw.get("refinement_regions"),
                             max_cells=kw.get("max_cells"), ref_bump=kw.get("ref_bump", 0))
    if r.status != "ok" or r.cd is None:
        return {"durum": "koşu başarısız", "hata": r.error[-400:]}   # kuyruk: asıl hata sonda
    # GUARD (dürüst V&V): mesh-bağımsızlık kanıtı olmadan banda yazılmaz. Kanıt yolu iki:
    # asimptotik 3-mesh GCI YA DA 4-seviye LSR dar-bandı (U<%15 — model-öncülünden küçük,
    # yoksa çapa model hatasını ayırt edemez).
    md = r.mesh_duyarlilik or {}
    converged, cd_pred, yontem = _accept(md.get("gci") or {}, md.get("lsr"),
                                         r.cd_richardson, r.cd, md.get("wake"),
                                         md.get("seviyeler"))
    if not converged or cd_pred is None or cd_pred <= 0:
        return {"durum": "REDDEDİLDİ — mesh-bağımsızlığı gösterilemedi (banda yazılmaz)",
                "regime": spec["regime"], "Cd_ref": spec["Cd"], "Cd_ince": r.cd,
                "hiz_ms": v, "verdikt": md.get("verdikt"), "lsr": md.get("lsr"),
                "kaynak_ref": spec["ref"]}
    # DUVAR KAPISI ÜRETİM ANINDA. Bu kapı YOKTU: y⁺'ı hiçbir duvar işlemine
    # ait olmayan bir koşu (Ahmed 25°: ort=46 ama tepe=1237) çapa olarak
    # yazılıyor ve geçersizliği ancak AŞAĞI AKIŞTA (`model_form_bandi`)
    # fark ediliyordu. Kanıtı üreten yerin, ürettiği şeyin geçerli olup
    # olmadığını bilmesi gerekir --- tüketicinin fark etmesine bırakılmaz.
    #
    # Ölçüt `validity_envelope.duvar_hukmu`: TEK kaynak. Depoda bu ölçütün
    # ikinci bir kopyası vardı ve docstring'i bunu kendisi söylüyordu.
    from validity_envelope import duvar_hukmu
    _duvar_ok, _duvar_neden = duvar_hukmu(getattr(r, "sinir_tabaka", None))
    if not _duvar_ok:
        return {"durum": "REDDEDİLDİ — duvar işlemi savunulabilir değil "
                         "(çapa olarak yazılmaz)",
                "duvar_gerekce": _duvar_neden,
                "regime": spec["regime"], "Cd_ref": spec["Cd"], "Cd_ince": r.cd,
                "hiz_ms": v, "kaynak_ref": spec["ref"]}

    err = abs(cd_pred - spec["Cd"]) / spec["Cd"] * 100
    return {"regime": spec["regime"], "Cd_ref": spec["Cd"], "Cd_pipeline": round(cd_pred, 5),
            "hata_pct": round(err, 2), "hiz_ms": v, "yontem": yontem,
            "u_sayisal_pct": (r.belirsizlik or {}).get("u_sayisal_pct"),
            "duvar_gerekce": _duvar_neden,
            "kaynak_ref": spec["ref"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hiz", type=float, default=30.0)
    ap.add_argument("--anchor", default="all")
    ap.add_argument("--out", default="validation_anchors_runs")
    args = ap.parse_args()
    names = list(ANCHORS) if args.anchor == "all" else [args.anchor]
    results = {n: _run_anchor(n, args.hiz, args.out) for n in names}

    # BANDI BU BETIK ARTIK YAZMIYOR. Neden: her olculen hatayi kosulsuz
    # "wall_resolved" hucresine yaziyordu — duvar islemini OLCMEDEN, VARSAYARAK.
    # Olculdu: disk kosusunun y+'i 31.3, kup capasinin 37.3; ikisi de
    # duvar-FONKSIYONU. Yani `bluff.wall_resolved = %5.95` hucresi YANLIS
    # ETIKETLIYDI ve o etiketle yayimlanmisti.
    #
    # Hucre atamasi tek bir yerde olmali: `experiments/model_form_bandi.py`
    # olculen y+'a bakar, tepe y+ bant disindaysa reddeder, sayisal bandi
    # olcmek istedigi model hatasindan buyuk olan capayi da reddeder. Bu betik
    # kosuyu URETIR; hukmu o verir.
    print(json.dumps({"sonuclar": results,
                      "_band": ("Band BU BETIK tarafindan YAZILMAZ. Kosular "
                                "uretildi; hucre atamasi ve band icin: "
                                "python experiments/model_form_bandi.py"),
                      "_neden": ("onceki surum her hatayi kosulsuz "
                                 "'wall_resolved' hucresine yaziyordu — duvar "
                                 "islemini olcmeden. disk y+=31.3, kup y+=37.3: "
                                 "ikisi de duvar-FONKSIYONU idi.")},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
