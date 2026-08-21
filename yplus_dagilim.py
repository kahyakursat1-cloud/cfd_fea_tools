"""y⁺ DAĞILIMI — ortalama ve tepe tek başına yanıltır.

NEDEN: mevcut ölçüm üç sayı veriyordu (min / max / ortalama) ve çapa-atama
kapısı bu ikisine bakıyordu. İkisinin de bilinen kusuru var ve ikisi ZIT
yönde yanılır:

  * ORTALAMA lokal kötü bölgeleri gizler. Ahmed 25°: ortalama 46 (bandın
    içinde) ama duvarın bir bölümü hiçbir zaman log-bölgesinde değil.
  * TEPE tek bir kötü hücreye aşırı duyarlıdır. Ahmed'in tepesi 1237; bu
    16.903 yüzün BİRİ bile olabilir ve o zaman çapayı reddetmek orantısız
    olurdu.

Dış inceleme (2026-08-21) doğru metriği önerdi: yüzdelikler + LOG-BÖLGESİNDE
KALAN DUVAR ALANI YÜZDESİ. Alan ağırlığı şart --- yüz-sayısı oranı büyük bir
hücreyi küçük bir hücreyle eşit sayar, oysa duvar yasasının geçerliliği
kapladığı ALANLA ölçülür.

    python yplus_dagilim.py <case_dir> [patch]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))


def _patch_degerleri(yplus_dosyasi: Path, patch: str) -> np.ndarray | None:
    """Bir yamanın y⁺ değerleri. Yama uniform ise (duvar değil) None."""
    t = yplus_dosyasi.read_text(encoding="utf-8", errors="replace")
    i = t.find("boundaryField")
    if i < 0:
        return None
    m = re.search(rf"^\s{{4}}{re.escape(patch)}\s*$", t[i:], re.M)
    if not m:
        return None
    blok = t[i + m.end():]
    n = re.search(r"nonuniform List<scalar>\s*(\d+)\s*\(", blok)
    if not n:
        return None
    bas = n.end()
    son = blok.find(")", bas)
    return np.fromstring(blok[bas:son], sep=" ")


def _patch_alanlari(case: Path, patch: str) -> np.ndarray | None:
    """Yamanın yüz ALANLARI — polyMesh'ten. Alan ağırlığı bunsuz kurulamaz."""
    b = case / "constant" / "polyMesh" / "boundary"
    if not b.exists():
        return None
    m = re.search(rf"{re.escape(patch)}\s*\{{[^}}]*nFaces\s+(\d+);[^}}]*"
                  rf"startFace\s+(\d+);", b.read_text(encoding="utf-8"), re.S)
    if not m:
        return None
    n_yuz, bas_yuz = int(m.group(1)), int(m.group(2))
    pts = np.array([[float(v) for v in g.groups()] for g in re.finditer(
        r"\(([-\d.eE+]+) ([-\d.eE+]+) ([-\d.eE+]+)\)",
        (case / "constant" / "polyMesh" / "points").read_text(encoding="utf-8"))])
    yuzler = re.findall(r"(\d+)\((\d[\d\s]*)\)",
                        (case / "constant" / "polyMesh" / "faces").read_text(encoding="utf-8"))
    alan = np.empty(n_yuz)
    for k, g in enumerate(yuzler[bas_yuz:bas_yuz + n_yuz]):
        v = pts[[int(x) for x in g[1].split()]]
        nrm = np.zeros(3)
        for j in range(1, len(v) - 1):
            nrm += np.cross(v[j] - v[0], v[j + 1] - v[0])
        alan[k] = 0.5 * float(np.linalg.norm(nrm))
    return alan


def dagilim(case_dir, patch: str, zaman: str | None = None) -> dict:
    """y⁺ dağılımı + log-bölgesindeki duvar ALANI yüzdesi."""
    from validity_envelope import YPLUS_BANDI, YPLUS_DUVAR_COZUNUR

    case = Path(case_dir)
    adaylar = []
    for d in case.iterdir():
        if not (d / "yPlus").exists():
            continue
        try:
            adaylar.append((float(d.name), d / "yPlus"))
        # sessiz-yutma: kabul — sayısal olmayan dizin adı zaman değildir;
        # eleme kriterin ta kendisi, hata değil
        except ValueError:
            continue
    if not adaylar:
        return {"durum": "yPlus alanı yok — foamPostProcess -func yPlus koşulmalı"}
    t, dosya = (max(adaylar) if zaman is None
                else next((a for a in adaylar if a[0] == float(zaman)), max(adaylar)))

    y = _patch_degerleri(dosya, patch)
    if y is None or len(y) == 0:
        return {"durum": f"'{patch}' yaması yPlus alanında yok ya da uniform"}
    a = _patch_alanlari(case, patch)
    alan_agirlikli = a is not None and len(a) == len(y)

    lo, hi = YPLUS_BANDI
    w = a if alan_agirlikli else np.ones_like(y)
    toplam = float(w.sum())
    sirala = np.argsort(y)
    kum = np.cumsum(w[sirala]) / toplam

    def yzd(p):
        return float(y[sirala][int(np.searchsorted(kum, p))])

    return {
        "zaman": t, "patch": patch, "n_yuz": int(len(y)),
        "agirlik": "ALAN" if alan_agirlikli else "YÜZ SAYISI (alan okunamadı)",
        "min": round(float(y.min()), 2), "p05": round(yzd(0.05), 2),
        "p50": round(yzd(0.50), 2), "p95": round(yzd(0.95), 2),
        "max": round(float(y.max()), 2),
        "ort": round(float((y * w).sum() / toplam), 2),
        "bandda_alan_pct": round(100 * float(w[(y >= lo) & (y <= hi)].sum()) / toplam, 1),
        "cozunur_alan_pct": round(100 * float(w[y <= YPLUS_DUVAR_COZUNUR].sum()) / toplam, 1),
        "band": [lo, hi], "cozunur_esik": YPLUS_DUVAR_COZUNUR,
    }


def duvar_islemi_kapsami(d: dict, duvar_islemi: str = "wall_function",
                         esik_pct: float = 80.0) -> dict:
    """Duvar işlemi duvarın NE KADARINI temsil ediyor — hüküm değil, KAPSAM.

    Mevcut kapı (`yplus_duvar_sinifi`) ortalama ve tepeye bakar. İkisi de
    bantta olabilir ve duvarın üçte biri yine de bandın dışında kalabilir;
    ölçüldü (2026-08-22, katman onarımı SONRASI koşular):

        Ahmed 25°  ort 30,5 · tepe 74,6 · bantta ALAN yalnız % 65,8
        küp        ort 40,9 · tepe 117,8 · bantta ALAN yalnız % 69,4

    Yani iki çapa da kapıdan geçiyor ama duvar yasası duvarın yaklaşık üçte
    birinde geçerli değil. Bu fonksiyon o gerçeği SAYIYLA taşır.

    KAPSAM ÇAPANIN KENDİ DUVAR İŞLEMİNE GÖRE ÖLÇÜLÜR. `duvar_islemi`
    parametresi bu yüzden zorunlu bir ayrımdır: küre çapası duvar-ÇÖZÜNÜR
    koşar ve log-bandındaki alanı %0,4'tür. O sayıyı "kapsam yetersiz" diye
    okumak tam tersini söyler --- çapa zaten bandın ALTINDA olmayı amaçlar
    (y⁺≤5 alanı %99,9). Tek bir yüzdeyi duvar işleminden bağımsız yorumlamak,
    bu ölçerin engellemek için yazıldığı kusurun kendisidir.

    EŞİK DAYATILMIYOR: `esik_pct` bir öneridir ve hüküm `yeterli` alanında
    ayrı durur. Kapıyı bugün sıkılaştırmak `bluff.wall_function` hücresinin
    iki çapasını da düşürür ve bandı ölçmeden genişletirdi --- bedeli
    ölçülmemiş bir sıkılaştırma, bu deponun reddettiği türden bir karardır.
    """
    if "bandda_alan_pct" not in d:
        return {"kapsam_olculdu": False, "neden": d.get("durum", "dağılım yok")}
    cozunur = duvar_islemi == "wall_resolved"
    pct = d["cozunur_alan_pct"] if cozunur else d["bandda_alan_pct"]
    olcut = (f"y+≤{d.get('cozunur_esik', 5):.0f}" if cozunur else
             f"{d['band'][0]:.0f}<y+<{d['band'][1]:.0f}")
    return {
        "kapsam_olculdu": True,
        "duvar_islemi": duvar_islemi,
        "kapsam_pct": pct,
        "bandda_alan_pct": d["bandda_alan_pct"],
        "cozunur_alan_pct": d["cozunur_alan_pct"],
        "esik_pct": esik_pct,
        "yeterli": pct >= esik_pct,
        "p05": d.get("p05"), "p50": d.get("p50"), "p95": d.get("p95"),
        "agirlik": d.get("agirlik"),
        "hukum": (f"duvar alanının %{pct:.1f}'i {olcut} ({duvar_islemi})"
                  + ("" if pct >= esik_pct else
                     f" — %{esik_pct:.0f} önerisinin ALTINDA: kullanılan duvar "
                     f"modeli yüzeyin %{100 - pct:.1f}'inde geçerli değil")),
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 3:
        print("kullanım: python yplus_dagilim.py <case_dir> <patch>")
        return 2
    import json
    print(json.dumps(dagilim(sys.argv[1], sys.argv[2]), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
