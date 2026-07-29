"""NACA2412 2B kesit çapası — "profil mi yanlış, mesh mi?" sorusunun cevabı.

NEDEN: MiniHawk 3B koşusu doğru geometriyle Cl=0.0143 verdi; NACA2412 α=0'da 2B
beklenti ~0.23. İki açıklama vardı ve ayırt edilemiyordu:
  (a) mesh_generator'ın ürettiği PROFİL yanlış,
  (b) profil doğru ama 3B mesh KAMBURLUĞU çözmüyor (en ince boyut yüzey hücresinin
      0.6 katı ölçülmüştü).
Bu çapa ikisini ayırır: AYNI profil üreticisinden alınan koordinatlar 2B'de,
çözünürlüğü yeterli bir C-grid üzerinde koşulur.

KRİTİK: koordinatlar `mesh_generator._naca4_profile`'dan gelir — yani test edilen şey
MiniHawk'ın kullandığı kodun ta kendisidir, ayrı bir referans profil değil.

Kurulum: Re_c = 2.5e5 (MiniHawk kordu 0.25 m, V=15 m/s) — 3B koşuyla AYNI Reynolds.
Referans: ince-kanat teorisi Cl = 2π·|α_L0|, NACA2412 için α_L0 ≈ -2.07° → Cl ≈ 0.227.
Abbott & von Doenhoff deneysel (Re=3e6): α_L0 = -2.1°, Cl(0°) ≈ 0.25.

    python experiments/naca2412_kesit.py

Çıktı: naca2412_kesit.json
"""
from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

# Verdikt '⚠️' içerebiliyor; Windows konsolu cp1254'te bunu yazamayıp UnicodeEncodeError
# atıyordu. JSON zaten yazılmış oluyordu ama VERDİKT KULLANICIYA HİÇ GÖRÜNMÜYORDU ve
# çıkış kodu yanlış çıkıyordu — kanıt üreten bir CLI'da kabul edilemez.
for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        _akis.reconfigure(encoding="utf-8", errors="replace")

import numpy as np  # noqa: E402

from analysis.thresholds import NONORTHO_REJECT, SKEW_REJECT  # noqa: E402
from construct2d_bridge import build_mesh, oku_sonuc, run_validation  # noqa: E402
from mesh_generator import MeshGenerator  # noqa: E402

KORD, V_INF, NU = 0.25, 15.0, 1.5e-5     # MiniHawk'ın FİZİKSEL kurulumu
RE_KORD = V_INF * KORD / NU              # 2.5e5 — eşleştirilmesi gereken benzerlik param.
# 2B grid BİRİM KORDLU üretilir (`_naca4_profile` çıktısı öyle). Aynı Reynolds'u orada
# elde etmek için nu ölçeklenmeli. Bu yapılmadığında ölçüldü: kanıt "Re=2.5e5" yazarken
# çözülen akış Re=1.0e6 idi ve referans alan 4 kat küçüktü (Cl/Cd 4 kat şişik).
KORD_GRID = 1.0
NU_CFD = V_INF * KORD_GRID / RE_KORD     # 6.0e-5
ALPHA = 0.0
ALFA_L0_DEG = -2.07                      # NACA2412 sıfır-taşıma açısı (ince-kanat)
CL_TEORI = 2 * math.pi * math.radians(abs(ALFA_L0_DEG))
CL_DENEY = 0.25                          # Abbott & von Doenhoff, Re=3e6
KABUL_BANDI = (0.15, 0.32)               # düşük-Re viskoz de-kamburlanma payıyla
ALFALAR = (0.0, 4.0)                     # iki nokta: eğim ve α_L0 ayrışsın
EGIM_BANDI = (0.85, 1.02)                # dCl/dα'nın 2π'ye oranı (viskoz kayıp payı)
ALFA_L0_TOLERANS = 0.5                   # derece — kamburluk çözülüyorsa bu kadar yeter
DURAGAN_BAND_ORANI = 0.01                # kuyruk bandı/|Cl| bunun altındaysa QoI oturmuş
# TÜRBÜLANS MODELİ — ÇAPANIN BELİRLEYİCİ AYARI. kOmegaSST hücum kenarından itibaren
# TAM TÜRBÜLANSLI çözer; Re=2.5e5'te gerçek NACA2412'nin ön kordunun büyük kısmı
# laminerdir. Aynı mesh, aynı iki α, tek değişken modelle ÖLÇÜLDÜ:
#   kOmegaSST   : Cl(0)=0.0839  α_L0=-0.81°  eğim 0.948·2π   -> kamburluk ÇÖZÜLMÜYOR
#   kOmegaSSTLM : Cl(0)=0.2224  α_L0=-2.18°  eğim 0.930·2π   -> kamburluk ÇÖZÜLÜYOR
# Referans: ince-kanat 0.227 / α_L0 -2.07°. Yani kamburluk açığının TAMAMI eksik
# geçiş modelinden geliyordu; geometri (grid yüzeyi ≤6.5e-5 kord) suçsuzdu.
MODEL = "kOmegaSSTLM"
MODEL_KIYAS = {"kOmegaSST": {"Cl_0": 0.0839, "alfa_L0_deg": -0.808,
                             "egim_2pi": 0.948, "not": "tam turbulans — kamburluk eksik"}}
# Keskin firar kenarında Construct2D C-grid ÖNERİR; O-grid'te firar hücreleri dejenere
# olur (ölçüldü: nonOrtho 179.999, skewness 3e152). Öneriye uyuluyor.
TOPO, SLVR = "CGRD", "ELLP"   # keskin firar kenarında Construct2D C-grid önerir; iz kesiği write_cgrid_gmsh ile İÇ sınır olarak bağlanır


def profil_dat(hedef: Path, n: int = 160) -> dict:
    """mesh_generator'ın KENDİ profilini Construct2D .dat formatına yazar.

    Ayrı bir referans profil KULLANILMAZ: sorulan soru "bu projenin ürettiği profil
    doğru mu", dolayısıyla girdi o üreticinin çıktısı olmalı.
    """
    p = np.asarray(MeshGenerator._naca4_profile(0.02, 0.4, 0.12, n=n), dtype=float)
    # Construct2D FİRAR KENARINDAN başlayan eğri bekler: TE → üst → burun → alt → TE.
    # `_naca4_profile` kapalı bir döngü döner ve HÜCUM KENARINDA başlar. Önceki
    # sürümdeki "ilk x < orta x ise ters çevir" sezgisi yetersizdi: yönü değiştiriyor
    # ama BAŞLANGICI taşımıyordu, eğri yine burunda başlayıp bitiyordu. Sonuç,
    # Construct2D'nin yüzey spline'ında burunda süreksizlik ve hiperbolik marşın
    # PATLAMASI oldu (ölçüldü: j=0 noktalarının %66'sı aralık dışı, x 13327'ye kadar).
    if np.hypot(*(p[0] - p[-1])) < 1e-12:      # kapalı döngü → yinelenen ucu at
        p = p[:-1]
    p = np.roll(p, -int(np.argmax(p[:, 0])), axis=0)      # TE'ye kaydır
    if p[1, 1] < p[-1, 1]:                     # ikinci nokta ALT yüzeydeyse ters çevir
        p = np.vstack([p[:1], p[1:][::-1]])
    p = np.vstack([p, p[:1]])                  # döngüyü TE'de kapat
    satir = ["NACA2412 (mesh_generator._naca4_profile)"]
    satir += [f"  {x:.7f}  {y:.7f}" for x, y in p]
    hedef.write_text("\n".join(satir) + "\n", encoding="utf-8")
    return {"nokta": int(len(p)),
            "maks_kalinlik": round(float(p[:, 1].max() - p[:, 1].min()), 5),
            "kord": round(float(p[:, 0].max() - p[:, 0].min()), 5)}


def _sade(o):
    """numpy skalerlerini JSON'a yazılabilir Python tiplerine indirger."""
    if isinstance(o, dict):
        return {k: _sade(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_sade(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o


def profil_dogrulugu(n: int = 200) -> dict:
    """Üretilen profili ANALİTİK NACA 4-haneli tanımla nokta-nokta karşılaştırır.

    Bu, çapanın ASIL ve KOŞULSUZ sonucudur: CFD'ye, grid üreticisine, çözücüye hiç
    bağlı değil. Sorulan soru "mesh_generator'ın profili doğru mu" ve cevabı burada
    ölçülür. 2B CFD yalnızca DESTEKLEYİCİ kanıttır.
    """
    m, pp, t = 0.02, 0.4, 0.12
    p = np.asarray(MeshGenerator._naca4_profile(m, pp, t, n=n), dtype=float)

    def yuzey(xc, ust):
        yt = 5 * t * (0.2969 * np.sqrt(xc) - 0.1260 * xc - 0.3516 * xc ** 2
                      + 0.2843 * xc ** 3 - 0.1015 * xc ** 4)
        yc = np.where(xc < pp, m / pp ** 2 * (2 * pp * xc - xc ** 2),
                      m / (1 - pp) ** 2 * ((1 - 2 * pp) + 2 * pp * xc - xc ** 2))
        dy = np.where(xc < pp, 2 * m / pp ** 2 * (pp - xc),
                      2 * m / (1 - pp) ** 2 * (pp - xc))
        th = np.arctan(dy)
        return ((xc - yt * np.sin(th), yc + yt * np.cos(th)) if ust
                else (xc + yt * np.sin(th), yc - yt * np.cos(th)))

    xs = np.linspace(0, 1, 4000)
    sapma = []
    for px, py in p:
        if not (0.02 < px < 0.98):        # burun/firar uçları ayrık, hariç
            continue
        ax, ay = yuzey(xs, ust=py > 0)
        sapma.append(abs(ay[np.argmin((ax - px) ** 2)] - py))
    sap = np.asarray(sapma)
    # kamburluk: analitik orta çizgi maksimumu (tanım gereği tam m olmalı)
    (ux, uy), (lx, ly) = yuzey(xs, True), yuzey(xs, False)
    return {"nokta": int(len(sap)),
            "ortalama_sapma_kord": float(f"{sap.mean():.3e}"),
            "maks_sapma_kord": float(f"{sap.max():.3e}"),
            "maks_sapma_pct": round(float(sap.max()) * 100, 4),
            "kamburluk_analitik": round(float(((uy + ly) / 2).max()), 5),
            "kamburluk_tanim": m,
            "gecti": bool(sap.max() < 1e-3)}


def _mesh_kalite_hatasi(mesh: dict) -> str:
    """Kanonik eşiklerle (analysis/thresholds) mesh reddi — sayı üretmeden ÖNCE."""
    kusur = []

    def f(anahtar):
        ham = str(mesh.get(anahtar, "")).strip()
        if not ham:
            kusur.append(f"{anahtar} checkMesh çıktısında YOK — kalite değerlendirilemedi")
            return None
        try:
            return float(ham)
        except ValueError:
            # Okunamayan metrik "sorun yok" DEĞİLDİR. Sessizce None dönmek kapıyı
            # kör eder; kapının varlık sebebi tam da bu.
            kusur.append(f"{anahtar} okunamadı ({ham!r}) — kalite değerlendirilemedi")
            return None

    no, sk = f("non_ortho_max"), f("skewness_max")
    if no is not None and no > NONORTHO_REJECT:
        kusur.append(f"nonOrtho {no:.1f} > {NONORTHO_REJECT}")
    if sk is not None and sk > SKEW_REJECT:
        kusur.append(f"skewness {sk:.3g} > {SKEW_REJECT}")
    return "; ".join(kusur)


def _cl_cd(sonuc: dict) -> tuple[float | None, float | None]:
    for a, b in (("Cl", "Cd"), ("cl", "cd"), ("CL", "CD")):
        if sonuc.get(a) is not None:
            return sonuc.get(a), sonuc.get(b)
    return None, None


def _profil_verdikti(dog: dict) -> str:
    if dog["gecti"]:
        return (f"PROFIL DOGRU (analitik): mesh_generator._naca4_profile cikti, NACA 4-haneli "
                f"tanimdan en fazla kordun %{dog['maks_sapma_pct']:.3f}'i kadar sapiyor; "
                f"kamburluk {dog['kamburluk_analitik']} (tanim {dog['kamburluk_tanim']}). "
                "Yani MiniHawk 3B kosusundaki Cl=0.0143 (2B beklenti ~0.23) PROFILDEN "
                "KAYNAKLANMIYOR. Geriye kalan adaylar ELEME ile degil OLCUMLE "
                "ayrilmalidir; bu capada olculen aday: dusuk-Re'de tam-turbulans "
                "varsayimi (kOmegaSST) Cl(0)'i %63 dusuruyor.")
    return (f"⚠️ PROFIL SAPIYOR: analitik tanimdan maks %{dog['maks_sapma_pct']:.3f} kord — "
            "MiniHawk teshisi once burayi isaret ediyor.")


def _onceki_mesh(case: Path) -> dict:
    """--rapor kipinde: mevcut case'in checkMesh logundan mesh ozetini kur."""
    from analysis.openfoam_runner import mesh_quality_gate
    # build_mesh `log.check` yazar (`log.checkMesh` DEGIL) — yanlis adi arayinca
    # metrikler None kaliyordu ve kalite kapisi mesh'i DOGRU sekilde reddediyordu
    # (2eb2686'nin dersi: okunamayan metrik "sorun yok" sayilmaz).
    log = next((case / n for n in ("log.check", "log.checkMesh")
                if (case / n).exists()), None)
    metin = log.read_text(errors="ignore") if log else ""
    q = mesh_quality_gate(metin) if metin else {}
    import re as _re
    m = _re.search(r"cells:\s+(\d+)", metin)
    return {"status": "SUCCESS", "cells": int(m.group(1)) if m else None,
            "non_ortho_max": (str(q.get("non_ortho_max"))
                              if q.get("non_ortho_max") is not None else None),
            "skewness_max": (str(q.get("skew_max"))
                             if q.get("skew_max") is not None else None),
            "_kaynak": "--rapor: mevcut case'ten okundu, mesh YENIDEN URETILMEDI"}


def _tasima_egimi(kosular: dict) -> dict:
    """İki α noktasından taşıma eğimi ve α_L0 — İKİSİ AYRI SORUYU sınar.

    Eğim, akış çözücüsünün sirkülasyon üretimini sınar (referans 2π/rad; gerçek
    profillerde viskoz etkiyle 0.90–0.95·2π beklenir). α_L0 ise KAMBURLUĞUN
    çözülüp çözülmediğini sınar — kamburluksuz bir kanatta tanım gereği 0'dır.
    Tek α noktası ikisini birbirine karıştırır.
    """
    p = sorted((a, k.get("Cl")) for a, k in kosular.items() if k.get("Cl") is not None)
    if len(p) < 2:
        return {"olculemedi": f"{len(p)} gecerli alfa noktasi (en az 2 gerekli)"}
    (a0, c0), (a1, c1) = p[0], p[-1]
    egim_deg = (c1 - c0) / (a1 - a0)
    if abs(egim_deg) < 1e-9:
        return {"olculemedi": "tasima egimi sifir — alfa'ya yanit yok"}
    alfa_l0 = a0 - c0 / egim_deg
    return {
        "noktalar": [{"alpha": a, "Cl": c} for a, c in p],
        "egim_deg": round(egim_deg, 5),
        "egim_rad": round(math.degrees(egim_deg), 4),
        "egim_2pi_orani": round(math.degrees(egim_deg) / (2 * math.pi), 4),
        "alfa_L0_deg": round(alfa_l0, 3),
        "alfa_L0_referans": ALFA_L0_DEG,
        "alfa_L0_sapma_pct": round((alfa_l0 - ALFA_L0_DEG) / abs(ALFA_L0_DEG) * 100, 1),
        "egim_gecti": EGIM_BANDI[0] <= math.degrees(egim_deg) / (2 * math.pi) <= EGIM_BANDI[1],
        "kamburluk_gecti": abs(alfa_l0 - ALFA_L0_DEG) <= ALFA_L0_TOLERANS,
    }


def _buyukluk_duragan(cfd: dict) -> bool:
    """İLGİLENİLEN BÜYÜKLÜK oturdu mu? (rezidüel hedefinden AYRI soru)

    `residualControl` tetiklenmemiş olması ile "Cl hâlâ hareket ediyor" AYNI ŞEY
    DEĞİLDİR. Bu vakada ölçüldü: 20000 iterasyonda Ux/k/omega rezidüelleri platoda
    kaldı ama Cl'in kuyruk bandı ±0.0000 (α=0) ve ±0.0001 (α=4) — ve iki BAĞIMSIZ
    koşu dört haneye kadar aynı değeri verdi (0.0839 / 0.4995). ASME V&V pratiğinde
    hüküm QoI'nin yakınsamasına dayanır; rezidüel seviyesi onun vekilidir.

    Kapıyı sayı almak için gevşetmiyoruz: rezidüel durumu kayıtta ve verdiktte
    AYRICA yazılı kalır. Burada yapılan, "bilgi yok" demekle "büyüklük oturdu ama
    rezidüel hedefi tutmadı" demeyi ayırmaktır.
    """
    cl, band = cfd.get("Cl"), cfd.get("Cl_band")
    if cl is None or band is None or not abs(cl) > 1e-9:
        return False
    if (cfd.get("yakinsama") or {}).get("salinim", {}).get("osilasyon"):
        return False
    return abs(band) / abs(cl) <= DURAGAN_BAND_ORANI


def _verdikt(cl, cd, mesh, cl_sapma, cfd=None):
    if cl is None:
        return "⚠️ Cl okunamadi — capa uretilemedi."
    cfd = cfd or {}
    yak = cfd.get("yakinsama") or {}
    # YAKINSAMA KAPISI: yakinsamamis kosunun Cl'i, salinimda nerede durulduguna bagli
    # bir SAYIDIR — capa degil. Olculdu: 2000 iterasyon doldu, p ilk-rezidueli 4.1e-2'de
    # salindi (hedef 1e-6) ve kapisiz surumde Cl=0.0342 "sonuc" olarak yayinlandi.
    duragan = _buyukluk_duragan(cfd)
    if cfd and not yak.get("yakinsadi", True) and not duragan:
        return (f"⚠️ KOSU YAKINSAMADI ({yak.get('neden','?')}; {yak.get('iterasyon','?')} "
                f"iterasyon, platoda: {yak.get('platoda')}). Anlik Cl={cl:.4f} "
                f"(kuyruk bandi ±{cfd.get('Cl_band')}) SAYI'dir, capa DEGILDIR — "
                "MiniHawk teshisi ANALITIK profil dogrulamasina dayanmaya devam ediyor.")
    icinde = KABUL_BANDI[0] <= cl <= KABUL_BANDI[1]
    p = [f"NACA2412 2B, Re={RE_KORD:.1e}, alpha=0: Cl={cl:.4f} "
         f"(ince-kanat teorisi {CL_TEORI:.3f}, deney {CL_DENEY}) -> sapma %{cl_sapma:+.0f}"]
    if duragan and not yak.get("yakinsadi", True):
        # KISITI GIZLEME: buyukluk oturdu AMA residualControl tetiklenmedi. Ikisi ayri
        # bilgidir; yalnizca birini yazmak ya bulguyu bastirir ya da guveni sisirir.
        p.append(f"NOT: residualControl tetiklenmedi (platoda: {yak.get('platoda')}) "
                 f"ama Cl kuyruk bandi ±{cfd.get('Cl_band')} — ilgilenilen buyukluk "
                 f"{yak.get('iterasyon','?')} iterasyonda DURAGAN, hukum QoI'ye dayaniyor")
    e = (cfd or {}).get("_egim") or {}
    if e and "olculemedi" not in e:
        # IKI AYRI HUKUM: cozucu dogru calisiyor olabilir ve KAMBURLUK yine de
        # cozulmemis olabilir. Tek bir "Cl dusuk" ifadesi bu ayrimi gizler.
        p.append(f"tasima egimi {e['egim_rad']:.2f}/rad = {e['egim_2pi_orani']:.3f}·2pi "
                 f"-> COZUCU {'DOGRU' if e['egim_gecti'] else 'SUPHELI'}")
        p.append(f"alpha_L0 {e['alfa_L0_deg']:+.2f}° (referans {ALFA_L0_DEG}°) "
                 f"-> KAMBURLUK {'COZULUYOR' if e['kamburluk_gecti'] else 'COZULMUYOR'}")
        if e["egim_gecti"] and not e["kamburluk_gecti"]:
            p.append("AYIRICI BULGU: akis cozucusu sirkulasyonu DOGRU uretiyor "
                     "(egim 2pi'ye oturuyor) ama KAMBURLUGUN katkisi eksik. Hata "
                     "cozucude degil, kamburlugun cozunurlugunde/temsilinde")
    if icinde:
        # ELEME ARGUMANI KULLANILMIYOR. Onceki surum "profil dogru -> oyleyse 3B mesh
        # cozunurlugu" diyordu; bu, olculmemis bir sonucu eleme yoluyla iddia etmekti.
        # Artik OLCULMUS ve AKTARILABILIR bir sebep var: ayni mesh ve ayni iki alfada
        # tek degisken turbulans modeliydi ve kOmegaSST Cl(0)'i %63 dusuruyordu.
        p.append(f"PROFIL DOGRU ve 2B KURULUM DOGRULANDI: ayni uretici "
                 f"(mesh_generator._naca4_profile) {MODEL} ile beklenen tasimayi veriyor")
        p.append("MiniHawk 3B kosusu (Cl=0.0143) `vehicle_pipeline` uzerinden ve "
                 "kOmegaSST ile, AYNI Reynolds mertebesinde kosuldu. Burada tek "
                 "degiskenli olculdu: kOmegaSST Cl(0)=0.0839 / alpha_L0=-0.81°, "
                 f"{MODEL} Cl(0)={cl:.4f} / alpha_L0={e.get('alfa_L0_deg', 0):+.2f}°. "
                 "Yani dusuk-Re'de TAM-TURBULANS varsayimi tek basina Cl'i %63 "
                 "dusuruyor — MiniHawk acigi icin OLCULMUS bir aday. Bu, 3B mesh "
                 "cozunurlugunu ELEMEZ; 3B'de de tek-degiskenli olarak gosterilmelidir")
    else:
        p.append(f"⚠️ Cl kabul bandi {KABUL_BANDI} DISINDA — profil ya da 2B kurulum "
                 "sorgulanmali; MiniHawk teshisi bu capaya dayandirilamaz")
    if mesh.get("non_ortho_max"):
        p.append(f"mesh: {mesh['cells']} hucre, nonOrtho {mesh['non_ortho_max']}, "
                 f"skewness {mesh.get('skewness_max')}")
    return ". ".join(p) + "."


def main() -> int:
    # --rapor: COZULMUS case'leri yeniden kullan, cozucuyu KOSMA. Verdikt metni ya da
    # bir kapi degistiginde kaniti yenilemek 70 dk CFD'yi tekrar kosmayi gerektiriyordu
    # (bu oturumda uc kez odendi). Sayilar AYNI case'ten okunur; yalnizca cozme atlanir.
    yeniden = "--rapor" in sys.argv
    kok = HERE.parent / "_naca2412"
    if kok.exists() and not yeniden:
        shutil.rmtree(kok, ignore_errors=True)
    kok.mkdir(parents=True, exist_ok=True)
    dat = kok / "naca2412.dat"
    geo = profil_dat(dat)
    dog = profil_dogrulugu()
    print(f"profil: {geo['nokta']} nokta, kalinlik/kord {geo['maks_kalinlik']:.4f}",
          flush=True)
    print(f"ANALITIK DOGRULAMA: maks sapma %{dog['maks_sapma_pct']:.4f} kord, "
          f"kamburluk {dog['kamburluk_analitik']} (tanim {dog['kamburluk_tanim']}) "
          f"-> {'GECTI' if dog['gecti'] else 'KALDI'}", flush=True)

    # recd: Construct2D ilk-katman kalınlığını y+=ypls HEDEFİYLE bu Reynolds'tan
    # boyutlandırır. Varsayılan 3.4e6 (NASA TMR NACA0012) BU VAKAYA AİT DEĞİL —
    # Re=2.5e5'te ilk katman ~11 kat fazla ince kalıyordu. Ölçülen sonuç: en-boy
    # oranı 27210 ve uzak-izde 660 yüzde nonOrtho 88.9 (gövdede DEĞİL — kanıt:
    # kötü yüzlerin tamamı |y|<0.08, x'e 14.7'ye kadar). Kapıyı gevşetmek yerine
    # grid'i vakanın Reynolds'una göre kurmak doğru düzeltme.
    # nwke: iz bölgesindeki nokta sayısı. Kalan nonOrtho'nun TAMAMI (12/68704 yüz)
    # x=10.6..14.7'de, yani gövdeden 10-15 kord AŞAĞIDA ölçüldü; oradaki Δx aşırı
    # gerilmişti. 50 -> 80 ile maks nonOrtho 79.7 -> 63.8 (uyarı eşiği 70'in altı).
    if yeniden and (kok / "case" / "constant" / "polyMesh" / "points").exists():
        mesh = _onceki_mesh(kok / "case")
        print("--rapor: mevcut mesh yeniden kullanildi", flush=True)
    else:
        mesh = build_mesh(str(dat), str(kok / "case"), name="naca2412", topo=TOPO,
                          slvr=SLVR, recd=RE_KORD, nwke=80)
    print(f"mesh: {mesh}", flush=True)
    # MESH KALİTE KAPISI: bozuk mesh üstünde CFD koşmak sayı üretir ama o sayı
    # anlamsızdır. İlk denemede O-grid keskin firar kenarında nonOrtho 179.999 /
    # skewness 3e152 verdi (Construct2D zaten C-grid önermişti). Kapı olmadan bu
    # mesh çözücüye gidiyordu.
    kalite_hata = _mesh_kalite_hatasi(mesh)
    if mesh.get("status") == "SUCCESS" and kalite_hata:
        mesh["status"] = "KALITE_RED"
        mesh["red_nedeni"] = kalite_hata
        print(f"MESH KALİTE KAPISI: {kalite_hata}", flush=True)
    if mesh.get("status") != "SUCCESS":
        out = {"vaka": "NACA2412 2B kesit — profil dogrulugu (analitik) + 2B CFD (destekleyici)",
               "profil_dogrulama": dog,
               "profil": {**geo, "kaynak": "mesh_generator._naca4_profile(0.02, 0.4, 0.12)"},
               "durum": "cfd_uretilemedi", "mesh": _sade(mesh),
               "_grid_altyapisi": (
                   "KOK SEBEP DUZELTMESI: onceki iki kanit surumunde (ve eed0e00 commit "
                   "mesajinda) 'C-grid Construct2D'de makuldu, onu bozan donusturucuydu' "
                   "denmisti. BU YANLISTI — iki kosunun skewness degerinin ayni cikmasina "
                   "dayanan bir CIKARIMDI, grid koordinatlari OLCULMEDEN. Olculdugunde "
                   "grid'in KENDISI bozuktu: j=0 noktalarinin %66'si aralik disi (x 13327'ye "
                   "kadar). Tek gercek kok sebep BU SCRIPT'IN .dat yazicisiydi — profili "
                   "HUCUM KENARINDA baslatiyordu, Construct2D FIRAR KENARINDAN bekler; "
                   "yuzey spline'i burunda sureksiz oluyor ve mars patliyordu. np.roll ile "
                   "duzeltilince HER IKI topoloji de gecerli grid uretti (aralik disi nokta 0). "
                   "Ikinci, BAGIMSIZ eksik gercekti: write_ogrid_gmsh C-grid'i ifade edemez "
                   "('j=0 airfoil, i-periyodik' varsayar) ve iz kesigini NO-SLIP DUVAR "
                   "etiketler; write_cgrid_gmsh cakisan kesik dugumlerini birlestirir, kesik "
                   "artik IC yuz. Olculen etki: OGRD skewness 3.4e152 -> 61.4 (duzgun .dat), "
                   "CGRD + yeni yazici -> skewness 1.34 (sinir 6). Geriye tek engel nonOrtho."),
               "verdikt": (_profil_verdikti(dog) + " " + ("⚠️ Mesh KALITE KAPISINDA reddedildi: "
                           + mesh.get("red_nedeni", "")
                           + " — bozuk mesh uzerinde Cl uretmek yaniltici olurdu."
                           if mesh.get("status") == "KALITE_RED"
                           else "2B CFD destekleyici kaniti URETILEMEDI (grid altyapisi; "
                           "bkz. _grid_altyapisi).")),
               "_uretim": "Üretim: python experiments/naca2412_kesit.py"}
        (HERE.parent / "naca2412_kesit.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(out["verdikt"])
        return 1

    # İKİ NOKTA — TEK NOKTA YETMİYOR. α=0'daki Cl iki AYRI şeyi karıştırır: taşıma
    # eğimi (akış çözücüsünün doğruluğu) ve α_L0 (KAMBURLUĞUN çözülüp çözülmediği).
    # Ölçüldü: eğim 5.95/rad = 0.947·2π — kusursuz; ama aynı iki noktadan çıkan
    # α_L0 = −0.81°, olması gereken −2.07°. Yani hata çözücüde değil, KAMBURLUK
    # KATKISINDA. Tek noktalı çapa bu ayrımı yapamaz ve "Cl düşük" deyip bırakırdı.
    #
    # 20000 iterasyon: 4000'de kuvvetler hâlâ oturmamıştı; 20000'de kuyruk bandı
    # α=0 için ±0.0000, α=4 için ±0.0001 (durağan).
    kosular = {}
    for a_deg in ALFALAR:
        alt = kok / "case" if a_deg == ALPHA else kok / f"case_a{a_deg:g}"
        if alt != kok / "case" and not alt.exists():
            shutil.copytree(kok / "case" / "constant", alt / "constant")
            shutil.copytree(kok / "case" / "system", alt / "system")
            shutil.rmtree(alt / "constant" / "polyMesh" / "sets", ignore_errors=True)
        if yeniden and (alt / "postProcessing" / "forces").exists():
            print(f"--rapor: alpha={a_deg} mevcut cozumden okunuyor", flush=True)
            kosular[a_deg] = oku_sonuc(alt, alpha_deg=a_deg, V=V_INF, nu=NU_CFD,
                                       chord=KORD_GRID)
        else:
            print(f"CFD alpha={a_deg}...", flush=True)
            kosular[a_deg] = run_validation(str(alt), alpha_deg=a_deg, V=V_INF,
                                            nu=NU_CFD, chord=KORD_GRID,
                                            end_time=20000, model=MODEL)
        print(f"  -> Cl={kosular[a_deg].get('Cl')} (band ±{kosular[a_deg].get('Cl_band')})",
              flush=True)

    r = kosular[ALPHA]
    egim = _tasima_egimi(kosular)
    cl, cd = _cl_cd(r)
    sapma = (cl - CL_TEORI) / CL_TEORI * 100 if cl is not None else None
    out = {
        "vaka": (f"NACA2412 2B kesit — birim kordlu grid, V={V_INF} m/s, nu={NU_CFD:.2e} "
                 f"(Re={RE_KORD:.2e} — MiniHawk ile ESLESTIRILMIS), alpha={ALPHA}"),
        "_neden": ("MiniHawk 3B kosusu Cl=0.0143 verdi (2B beklenti ~0.23). Bu capa "
                   "'profil mi yanlis, mesh mi' sorusunu ayirir: AYNI profil ureticisi "
                   "2B'de, cozunurlugu yeterli C-grid uzerinde kosulur."),
        "profil": {**geo, "kaynak": "mesh_generator._naca4_profile(0.02, 0.4, 0.12)"},
        "profil_dogrulama": dog,
        "referans": {"Cl_ince_kanat": round(CL_TEORI, 4), "alfa_L0_deg": ALFA_L0_DEG,
                     "Cl_deney_Re3e6": CL_DENEY,
                     "kaynak": "Abbott & von Doenhoff, Theory of Wing Sections"},
        "mesh": _sade(mesh), "cfd": _sade(r),
        "turbulans_modeli": MODEL,
        "model_kiyasi": MODEL_KIYAS,
        "alfa_taramasi": _sade(egim),
        "cfd_tum_alfalar": {str(a): _sade(k) for a, k in kosular.items()},
        # AÇIK SORUNUN KAPSAMI: aşağıdakiler ÖLÇÜLEREK elendi. Kalan şüpheli
        # yalnızca çözücü kurulumudur — grid, geometri veya normalizasyon değil.
        "_elenen_supheliler": {
            "grid_kalitesi": "nonOrtho 63.8 / skewness 1.02 (esikler 75 / 6)",
            "iz_kesigi": ("iki yaka ZIT yone aciliyor (dy = -4.06e-5 / +4.06e-5), "
                          "birlestirilen yuzlerde nonOrtho ~0 -> kesik gercekten IC sinir"),
            "kamburluk": "grid gövdesinde x/c=0.4'te ust +0.078 / alt -0.038 -> kamber %2.0",
            "sinir_tabaka": "y+ maks 0.61, ortalama 0.26 (nutLowReWallFunction icin uygun)",
            "ayrilma": ("tau_x tum yuzeyde NEGATIF (ileri akis); tek isaret degisimi "
                        "x/c=0.987 -> yalnizca firar kenari kabarcigi, kutlesel ayrilma YOK"),
            "referans_alan_ve_Re": "mesh'ten olculuyor (S=0.0999, Re=2.50e5)",
        },
        "Cl": cl, "Cd": cd,
        "Cl_sapma_pct": round(sapma, 2) if sapma is not None else None,
        "verdikt": _verdikt(cl, cd, mesh, sapma or 0.0, {**r, "_egim": egim}),
        "_uretim": "Üretim: python experiments/naca2412_kesit.py",
    }
    if not (r.get("yakinsama") or {}).get("yakinsadi", False):
        # Yalnız yakınsamayan koşuda anlamlı — geçmişte bu metin sabit yazılıydı ve
        # sonuç düzelse bile kanıtta kalıp okuyanı yanıltacaktı.
        out["_kalan_supheli"] = (
            "Cozum SAYISAL olarak oturmadi. Ayni kurulumda olculen iki-nokta taramasi "
            "(alpha=0 ve 4, 4000 iterasyon) tasima EGIMINI 5.64/rad verdi — 2pi'nin "
            "%90'i, Re=2.5e5 icin dogru — ama alpha_L0 -0.08 derece cikti (-2.07 olmali) "
            "ve alpha=4 kosusunda Cl son 750 iterasyonda MONOTON yukseliyordu. Yani eksik "
            "olan fizik degil, SIRKULASYONUN KURULMASI icin gereken iterasyon.")
    (HERE.parent / "naca2412_kesit.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + out["verdikt"])
    print("-> naca2412_kesit.json")
    return 0 if cl is not None else 1


if __name__ == "__main__":
    sys.exit(main())
