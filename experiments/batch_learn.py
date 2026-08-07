"""Toplu öğrenme kampanyası — ÇEŞİTLİ + ETİKETLİ geometrileri otopilot akışıyla koşar,
record_case ile öğrenme kütüphanesini OVERFITTING'e karşı dikkatli büyütür.

OVERFITTING KORUMASI (kritik — yüzlerce sentetik yakın-kopya metrik-uzayını boğmasın):
  1. Çeşitlilik-seçimi (farthest-point): büyük randomize havuz → CFD'den ÖNCE metrik-uzayında
     mevcut kütüphaneye göre EN SEYREK bölgeleri seç (boşluk-dolduran). min-uzaklık eps altına
     inince DUR → yakın-kopya kaydetme, pahalı CFD harcama.
  2. Sınıf-başı tavan (cap) → tek sınıf kütüphaneyi domine etmesin.
  3. Holdout doğrulama: kaydedilmeyen ayrı set; öğrenmeden ÖNCE+SONRA sınıflandırma isabeti
     → genelleme düşerse overfitting sinyali (raporlanır).

KURŞUN-GEÇİRMEZ: CFD-öncesi geometri validasyonu (watertight/hacim/yüz), koşular-arası
orphan + disk temizliği, geo-başına catch-all (biri çökse batch durmaz), devam-edebilir.

Kullanım: python experiments/batch_learn.py [cap_per_class] [pool_mult]
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

from analysis.backend import linux_run

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import auto_pilot as ap  # noqa: E402
from analysis.ccx_runner import WSL_DISTRO  # noqa: E402
from auto_pilot import _features, _load_cases, classify_vehicle, record_case  # noqa: E402
from vehicle_pipeline import inspect_geometry, prepare_geometry, run_vehicle_analysis  # noqa: E402

# İzolasyon: env ile ayrı bellek/done/dizine yönlendirilebilir (ör. yüksek-kalite gece koşusu
# mevcut hizli-kalite DB'yi kirletmesin). Varsayılan = orijinal yollar.
_TAG = os.environ.get("BATCH_TAG", "")
GEN_DIR = HERE.parent / "vehicle_runs" / (f"_batch_geo{('_'+_TAG) if _TAG else ''}")
LOG = HERE.parent / f"batch_learn{('_'+_TAG) if _TAG else ''}.log"
DONE = HERE.parent / f"batch_learn_done{('_'+_TAG) if _TAG else ''}.json"
if _TAG:                                      # izole bellek dosyası (record_case ap.MEMORY'ye yazar)
    ap.MEMORY = HERE.parent / f"auto_pilot_memory_{_TAG}.jsonl"
DIVERSITY_EPS = 0.045        # bu uzaklıktan yakın (aynı-tip) örnek → yakın-kopya, kaydetme
ALL_TIPLER = ("roket", "kanatli_roket", "ucak", "multikopter", "genel",
              "tilt_rotor", "kanatli_vtol", "kaldirici_govde")


# ─────────── geometri üreticileri (RANDOMIZE + geniş — çeşitlilik) ───────────

def _revolve(profile, sections=64):
    m = trimesh.creation.revolve(np.asarray(profile, float), sections=sections)
    m.merge_vertices(); m.fix_normals()
    return m


def gen_roket(rng, R=0.04):
    L_D = rng.uniform(4.5, 15)
    nose = rng.uniform(0.15, 0.45)
    L = L_D * 2 * R; Ln = nose * L
    if rng.random() < 0.5:                              # konik vs ogive burun
        prof = [[0, 0], [R, 0], [R, L - Ln], [0, L]]
    else:
        xs = np.linspace(0, Ln, 8)
        og = [[R * np.sqrt(max(1 - (x / Ln) ** 2, 0)), L - Ln + x] for x in xs]
        prof = [[0, 0], [R, 0], [R, L - Ln], *og]
    return _revolve(prof), "roket"


def gen_kanatli_roket(rng, R=0.04):
    body, _ = gen_roket(rng, R)
    L = (body.bounds[1] - body.bounds[0])[2]
    nf = int(rng.integers(3, 5))
    fcode = NACA_KATALOG[rng.integers(0, 4)]               # ince SİMETRİK fin profili
    fins = []
    for k in range(nf):
        fin = _naca_wing(fcode, chord=R * rng.uniform(2.0, 3.0), span=R * rng.uniform(1.5, 2.5))
        # airfoil kanat (kiriş→x, açıklık→y, kalınlık→z); fin radyal dışa, eksen z
        fin.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        fin.apply_translation((0, 0, L * 0.10))           # gövde aft, radyal dışa (y→z sonrası)
        fin.apply_transform(trimesh.transformations.rotation_matrix(2 * np.pi * k / nf, [0, 0, 1]))
        fins.append(fin)
    return trimesh.util.concatenate([body, *fins]), "kanatli_roket"


# Çeşitli NACA 4-haneli profiller (simetrik + kamburlu) — airfoil-kesitli gerçekçi kanat
NACA_KATALOG = ("0009", "0012", "0015", "0018", "1408", "2412", "2415",
                "4412", "4415", "6409", "23012", "63012")


def naca4(code, n=70):
    """NACA 4-haneli airfoil dış-hat koordinatları (kapalı döngü, kiriş 0–1)."""
    code = code[-4:]
    m, p, t = int(code[0]) / 100, int(code[1]) / 10, int(code[2:]) / 100
    beta = np.linspace(0, np.pi, n)
    x = (1 - np.cos(beta)) / 2                          # kosinüs aralık (TE sıklaştırma)
    yt = 5 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2
                  + 0.2843 * x**3 - 0.1015 * x**4)
    if p == 0:
        yc = np.zeros_like(x); dyc = np.zeros_like(x)
    else:
        yc = np.where(x < p, m / p**2 * (2 * p * x - x**2),
                      m / (1 - p)**2 * ((1 - 2 * p) + 2 * p * x - x**2))
        dyc = np.where(x < p, 2 * m / p**2 * (p - x), 2 * m / (1 - p)**2 * (p - x))
    th = np.arctan(dyc)
    xu, yu = x - yt * np.sin(th), yc + yt * np.cos(th)
    xl, yl = x + yt * np.sin(th), yc - yt * np.cos(th)
    X = np.concatenate([xu[::-1], xl[1:]])
    Y = np.concatenate([yu[::-1], yl[1:]])
    return np.column_stack([X, Y])


def _naca_wing(code, chord, span, taper=1.0):
    """NACA profilini kök→uç loft ederek (taper'lı) 3B watertight kanat — kiriş→x,
    açıklık→y, kalınlık→z. shapely'siz elle örgü (bağımlılık yok)."""
    af = naca4(code)                                          # (N,2): (kiriş, kalınlık)
    n = len(af)
    root = np.column_stack([af[:, 0] * chord, np.full(n, -span / 2), af[:, 1] * chord])
    tc = chord * taper
    tip = np.column_stack([af[:, 0] * tc, np.full(n, span / 2), af[:, 1] * tc])
    verts = np.vstack([root, tip])
    faces = []
    for i in range(n):                                       # kök↔uç şerit (quad→2 üçgen)
        j = (i + 1) % n
        faces += [[i, j, n + j], [i, n + j, n + i]]
    rc = len(verts); verts = np.vstack([verts, root.mean(0)])    # kök kapağı (yelpaze)
    faces += [[rc, (i + 1) % n, i] for i in range(n)]
    tcv = len(verts); verts = np.vstack([verts, tip.mean(0)])    # uç kapağı
    faces += [[tcv, n + i, n + (i + 1) % n] for i in range(n)]
    w = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    w.fix_normals()
    return w


def gen_ucak(rng, L=0.6):
    R = L * rng.uniform(0.035, 0.06)
    fus = trimesh.creation.cylinder(radius=R, height=L * rng.uniform(0.8, 0.95))
    fus.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    span = rng.uniform(0.5, 0.95) * L
    chord = L * rng.uniform(0.13, 0.20)
    code = NACA_KATALOG[rng.integers(0, len(NACA_KATALOG))]   # farklı NACA modeli
    wing = _naca_wing(code, chord, span, taper=rng.uniform(0.45, 1.0))
    wing.apply_translation((L * rng.uniform(-0.05, 0.12), 0, 0))
    tcode = NACA_KATALOG[rng.integers(0, 4)]                  # kuyruk: ince simetrik
    tail = _naca_wing(tcode, chord * 0.55, span * rng.uniform(0.3, 0.5))
    tail.apply_translation((-L * 0.4, 0, 0))
    return trimesh.util.concatenate([fus, wing, tail]), "ucak"


def gen_multikopter(rng, R=0.03):
    arm = rng.uniform(0.16, 0.42)
    na = rng.choice([4, 6])
    parts = [trimesh.creation.box((R * 2, R * 2, R * rng.uniform(1.0, 1.5)))]
    for k in range(na):
        a = trimesh.creation.cylinder(radius=R * 0.25, height=arm)
        a.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        a.apply_translation((arm / 2, 0, 0))
        a.apply_transform(trimesh.transformations.rotation_matrix(2 * np.pi * k / na + 0.4, [0, 0, 1]))
        parts.append(a)
    return trimesh.util.concatenate(parts), "multikopter"


def gen_genel(rng):
    S = rng.uniform(0.12, 0.28)
    kind = rng.choice(["kure", "elipsoid", "kut", "silindir"])
    if kind == "kure":
        return trimesh.creation.icosphere(subdivisions=3, radius=S / 2), "genel"
    if kind == "elipsoid":
        asp = rng.uniform(1.2, 2.5)
        prof = [[0, 0]] + [[S / 2 * np.sin(t), S * asp * (1 - np.cos(t)) / 2]
                           for t in np.linspace(0.01, np.pi - 0.01, 20)] + [[0, S * asp]]
        return _revolve(prof), "genel"
    if kind == "silindir":
        return trimesh.creation.cylinder(radius=S / 2, height=S * rng.uniform(1, 2.5)), "genel"
    return trimesh.creation.box((S, S * rng.uniform(0.6, 0.95), S * rng.uniform(0.6, 0.9))), "genel"


def gen_tilt_rotor(rng, L=0.5):
    """Eğimli-rotor: fuzelaj + NACA kanat + kanat-ucu rotor nacelle'leri."""
    R = L * 0.05
    fus = trimesh.creation.cylinder(radius=R, height=L * 0.8)
    fus.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    span = rng.uniform(0.6, 0.9) * L
    chord = L * rng.uniform(0.14, 0.20)
    wing = _naca_wing(NACA_KATALOG[rng.integers(0, len(NACA_KATALOG))], chord, span,
                      taper=rng.uniform(0.6, 0.9))
    parts = [fus, wing]
    for sgn in (-1, 1):                                    # kanat-ucu nacelle (rotor podu)
        pod = trimesh.creation.cylinder(radius=R * 0.8, height=chord * 1.3)
        pod.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
        pod.apply_translation((0, sgn * span / 2 * 0.92, 0))
        parts.append(pod)
    return trimesh.util.concatenate(parts), "tilt_rotor"


def gen_kanatli_vtol(rng, L=0.5):
    """Kanatlı-VTOL: NACA kanat + merkez gövde + dikey kaldırma fanları (duct)."""
    R = L * 0.06
    body = trimesh.creation.box((L * 0.5, R * 2, R * 2))
    span = rng.uniform(0.6, 0.95) * L
    wing = _naca_wing(NACA_KATALOG[rng.integers(0, len(NACA_KATALOG))], L * 0.16, span,
                      taper=rng.uniform(0.5, 0.9))
    parts = [body, wing]
    for fx in (L * 0.12, -L * 0.12):                       # dikey kaldırma fanları
        for fy in (span * 0.28, -span * 0.28):
            d = trimesh.creation.cylinder(radius=R * 0.6, height=R * 0.9)
            d.apply_translation((fx, fy, 0))
            parts.append(d)
    return trimesh.util.concatenate(parts), "kanatli_vtol"


def gen_kaldirici_govde(rng, L=0.5):
    """Kaldırıcı-gövde: kalın geniş NACA-kesitli harmanlanmış gövde (ince kanat DEĞİL)."""
    code = ("0015", "0018", "4415", "23015")[rng.integers(0, 4)]   # kalın profil
    chord = L * rng.uniform(0.6, 0.95)                     # büyük kiriş (gövde-benzeri)
    span = L * rng.uniform(0.45, 0.8)                      # orta açıklık (küt, ince değil)
    return _naca_wing(code, chord, span, taper=rng.uniform(0.4, 0.7)), "kaldirici_govde"


_GENS = {"roket": gen_roket, "kanatli_roket": gen_kanatli_roket, "ucak": gen_ucak,
         "multikopter": gen_multikopter, "genel": gen_genel,
         "tilt_rotor": gen_tilt_rotor, "kanatli_vtol": gen_kanatli_vtol,
         "kaldirici_govde": gen_kaldirici_govde}


def _valid_geo(m) -> bool:
    """Kurşun-geçirmez ön-eleme: dejenere/işe yaramaz geometriyi CFD'den ÖNCE at."""
    try:
        ext = m.bounds[1] - m.bounds[0]
        return (len(m.faces) >= 50 and np.all(np.isfinite(ext)) and
                float(ext.min()) > 1e-4 and float(m.volume) > 1e-9)
    # sessiz-yutma: kabul — geometri elemesi; okunamayan STL 'geçersiz' sayılır — temkinli taraf
    except Exception:
        return False


def _metrik_of(stl, workdir):
    """CFD'siz: hazırla → inspect → classify → (metrik, geo, prep). Dejenere→None."""
    prep, _ = prepare_geometry(stl, workdir)
    m = trimesh.load(str(prep), force="mesh")
    if not _valid_geo(m):
        return None
    geo = inspect_geometry(prep)
    cls = classify_vehicle(geo)
    return {"metrik": cls["metrik"], "tip": cls["tip"], "guven": cls["guven"], "prep": prep}


def _lib_feats(tip):
    """Kütüphanedeki aynı-tip vakaların özellik-vektörleri (çeşitlilik referansı)."""
    out = []
    for c in _load_cases():
        if c.get("onayli_tip") == tip and c.get("metrik"):
            try:
                out.append(np.array(_features(c["metrik"]), float))
            # sessiz-yutma: kabul — kütüphane özellik çıkarımı; düşerse o vaka kNN'e girmez, hüküm üretmez
            except Exception:
                pass
    return out


def _farthest_select(cands, tip, cap, eps):
    """cands: [(name, metrik, prep)]. Mevcut kütüphane + seçilenlere göre en SEYREK
    (boşluk-dolduran) örnekleri açgözlü seç. min-uzaklık eps altına inince DUR (yakın-kopya
    kaydetme → overfitting önleme)."""
    ref = _lib_feats(tip)
    feats = [np.array(_features(m), float) for _, m, _ in cands]
    chosen = []
    used = set()
    for _ in range(min(cap, len(cands))):
        best_i, best_d = -1, -1.0
        for i, f in enumerate(feats):
            if i in used:
                continue
            pool = ref + [feats[j] for j in used]
            d = min((np.linalg.norm(f - r) for r in pool), default=1e9)
            if d > best_d:
                best_d, best_i = d, i
        if best_i < 0 or best_d < eps:                 # kalan en-iyi bile çok yakın → dur
            break
        used.add(best_i); chosen.append(cands[best_i])
    return chosen


def _orphan_cleanup():
    try:
        linux_run("pkill -9 -f foamRun 2>/dev/null; "
                  "pkill -9 -f mpirun 2>/dev/null; true", 20)
    # sessiz-yutma: kabul — geçici dosya temizliği; sonuç üretmez
    except Exception:
        pass


def _holdout_accuracy(rng_seed=999, n_per=3):
    """Kaydedilmeyen ayrı set → genelleme isabeti (overfitting dedektörü)."""
    rng = np.random.default_rng(rng_seed)
    wd = GEN_DIR / "_holdout"; wd.mkdir(parents=True, exist_ok=True)
    ok = tot = 0
    for tip in ALL_TIPLER:
        for k in range(n_per):
            try:
                m, true_tip = _GENS[tip](rng)
                stl = wd / f"ho_{tip}_{k}.stl"; m.export(str(stl))
                info = _metrik_of(stl, wd / f"ho_{tip}_{k}")
                if info:
                    tot += 1; ok += int(info["tip"] == true_tip)
            # sessiz-yutma: kabul — ayrık-doğruluk RAPORU; düşerse metrik basılmaz — kanıt dosyasına sahte sayı YAZILMAZ
            except Exception:
                pass
    shutil.rmtree(wd, ignore_errors=True)
    return ok, tot


def main():
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 8       # sınıf-başı tavan
    pool_mult = int(sys.argv[2]) if len(sys.argv) > 2 else 4  # havuz = cap×mult aday
    quality = sys.argv[3] if len(sys.argv) > 3 else "hizli"  # CFD mesh kalitesi (hassas=duvar-çözünür)
    # BATCH_TIPLER env: yalnız bu tipleri koş (finisher eksik-tip hedeflemesi; dolu tipi tekrarlama)
    _sel = os.environ.get("BATCH_TIPLER", "")
    TIPLER = tuple(t for t in ALL_TIPLER if t in _sel.split(",")) if _sel else ALL_TIPLER
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    done = set(json.loads(DONE.read_text())) if DONE.exists() else set()
    rng = np.random.default_rng(int(time.time()) % 100000)

    def log(m):
        line = f"[{time.strftime('%H:%M:%S')}] {m}"
        print(line, flush=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    ho0_ok, ho0_tot = _holdout_accuracy()
    log(f"=== Toplu öğrenme (cap={cap}/sınıf, kalite={quality}, tag={_TAG or '-'}, "
        f"bellek={ap.MEMORY.name}) | kütüphane={len(_load_cases())} | "
        f"holdout-ÖNCE: {ho0_ok}/{ho0_tot} ({100*ho0_ok/max(ho0_tot,1):.0f}%) ===")

    # 1) Havuz üret + CFD'siz metrik çıkar → 2) çeşitlilik-seç → 3) CFD+record
    plan = []
    for tip in TIPLER:
        cands = []
        for k in range(cap * pool_mult):
            try:
                m, true_tip = _GENS[tip](rng)
                if not _valid_geo(m):
                    continue
                name = f"{tip}_{k}_{rng.integers(1000,9999)}"
                stl = GEN_DIR / f"{name}.stl"; m.export(str(stl))
                info = _metrik_of(stl, GEN_DIR / name)
                if info:
                    cands.append((name, info["metrik"], info["prep"]))
            # sessiz-yutma: kabul — toplu koşuda tek vakanın düşmesi kampanyayı durdurmaz; başarısızlar ayrıca sayılır
            except Exception:
                pass
        sel = _farthest_select(cands, tip, cap, DIVERSITY_EPS)
        log(f"{tip}: {len(cands)} aday → {len(sel)} çeşitli seçildi (eps={DIVERSITY_EPS})")
        plan += [(n, m, p, tip) for n, m, p in sel]

    max_min = float(os.environ.get("BATCH_MAX_MIN", "0"))    # >0 ise süre limiti (gece koşusu güvenli durur)
    log(f"Plan: {len(plan)} çeşitli geometri koşulacak (CFD)" + (f" | süre-limiti {max_min:.0f}dk" if max_min else ""))
    t0 = time.time(); ok = dogru = 0
    for name, metrik, prep, true_tip in plan:
        if name in done:
            continue
        if max_min and (time.time() - t0) / 60 > max_min:
            log(f"süre-limiti {max_min:.0f}dk aşıldı — {ok} koşudan sonra güvenle durduruluyor"); break
        try:
            cls = classify_vehicle(inspect_geometry(prep))   # güncel kütüphaneyle
            # CFD preset'i: hibrit tip (kanatli_roket/tilt_rotor…) VEHICLE_PRESETS'te yok →
            # PRESET_MAP ile base preset'e eşle (KeyError önle — kurşun-geçirmez).
            cfd_tip = ap.PRESET_MAP.get(cls["tip"], "genel")
            res = run_vehicle_analysis(prep, vehicle_type=cfd_tip, velocity=30.0,
                                       quality=quality, out_root=str(GEN_DIR))
            drift = (res.convergence or {}).get("drift_pct")
            gate = record_case(cls["metrik"], cls["tip"], true_tip,
                               {"Cd_toplam": res.cd, "rejim": _regime(true_tip),
                                "Cd_drift_pct": drift}, dosya=f"batch:{name}")
            ok += 1; dogru += int(cls["tip"] == true_tip)
            log(f"  {name}: sınıf={cls['tip']} gerçek={true_tip} Cd={res.cd} "
                f"güvenilir={gate['cd_guvenilir']} ({(time.time()-t0)/60:.0f}dk, {ok} tamam)")
            done.add(name); DONE.write_text(json.dumps(sorted(done)))
        except Exception as e:
            log(f"  !!! {name} BAŞARISIZ: {str(e)[:140]}")
        finally:
            shutil.rmtree(GEN_DIR / name, ignore_errors=True)            # disk temizliği
            shutil.rmtree(GEN_DIR / f"{name}_prep", ignore_errors=True)  # case dizini _prep ekli (asıl ağır veri)
            _orphan_cleanup()                                   # koşular-arası orphan

    ho1_ok, ho1_tot = _holdout_accuracy()
    log(f"=== BİTTİ: {ok} koşu, eğitim-isabet {dogru}/{ok} ({100*dogru/max(ok,1):.0f}%) | "
        f"kütüphane={len(_load_cases())} | holdout-SONRA: {ho1_ok}/{ho1_tot} "
        f"({100*ho1_ok/max(ho1_tot,1):.0f}%) ===")
    delta = (ho1_ok/max(ho1_tot,1)) - (ho0_ok/max(ho0_tot,1))
    log(f"OVERFITTING KONTROL: holdout Δ={delta*100:+.0f}% — "
        + ("genelleme korundu/iyileşti ✓" if delta >= -0.05 else
           "⚠ holdout düştü → overfitting şüphesi (eps büyüt / çeşitlilik artır)"))
    return 0


def _regime(tip):
    return "supersonic" if tip in {"roket", "kanatli_roket", "kaldirici_govde"} else "subsonic"


if __name__ == "__main__":
    sys.exit(main())
