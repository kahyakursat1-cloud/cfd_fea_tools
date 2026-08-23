"""Yer değiştirme alanı EĞİLME mi BURULMA mı — statik aeroelastiği süren budur.

NEDEN: iki-yönlü kuplaj bir tahrik bandı (sehim/açıklık %1--3) arandıktan
sonra bile fiziksel olarak sürülmedi. Ölçüldü (fsi_tahrikH, %2,47): ağ
gerçekten hareket etti ama CFD yüzeyindeki aerodinamik yük yalnız %0,2
değişti.

SEBEP GEOMETRİK: düz konsol levha SAF EĞİLME yapar. Kesit yukarı çıkar ama
yerel hücum açısı DEĞİŞMEZ, dolayısıyla basınç dağılımı da değişmez. Sehim
büyütmek bunu düzeltmez --- daha çok eğilme yine burulma üretmez. Aracın eski
öğüdü ("daha esnek yapı ya da daha yüksek dinamik basınç gerekir") bu
konfigürasyonda YANLIŞTIR.

Statik aeroelastik kuplajı süren BURULMADIR: yerel hücum açısındaki değişim.
Ok açılı bir kanatta eğilme eğimi burulmaya dönüşür
(Δα ≈ −θ·sin Λ); düz kanatta Λ=0 ve katsayı sıfırdır.

Bu modül bir yer değiştirme alanını iki bileşene ayırır ve HANGİSİNİN baskın
olduğunu söyler. Sehim/açıklık oranı GEREK şarttı; burulma YETER şartın
kendisidir.

    python fsi_burulma.py <case_dir> <yama>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

# Yerel hucum acisi bu kadar degisirse yuk OLCULEBILIR bicimde degisir.
# Olculen taban: duz levhada burulma ~0 ve aero yuk degisimi %0,2.
BURULMA_ESIGI_DEG = 0.2


def ayristir(noktalar, yerdegistirme, aciklik_ekseni: int = 1,
             veter_ekseni: int = 0, normal_ekseni: int = 2,
             uc_dilim_pct: float = 10.0) -> dict:
    """Yer değiştirme alanını EĞİLME ve BURULMA olarak ayır.

    Uç bölgedeki (`uc_dilim_pct`) noktalara veter boyunca DOĞRU uydurulur:
      * doğrunun ortalama değeri  → eğilme (rijit öteleme)
      * doğrunun eğimi            → burulma (yerel hücum açısı değişimi)

    İkisi ayrı ölçülmezse büyük bir sehim "kuplaj sürülüyor" sanılır.
    """
    p = np.asarray(noktalar, float)
    d = np.asarray(yerdegistirme, float)
    if p.shape != d.shape or len(p) < 3:
        return {"durum": "nokta/yer değiştirme uyumsuz ya da çok az"}

    y, x, w = p[:, aciklik_ekseni], p[:, veter_ekseni], d[:, normal_ekseni]
    esik = y.min() + (1.0 - uc_dilim_pct / 100.0) * (y.max() - y.min())
    uc = y >= esik
    if uc.sum() < 3 or np.ptp(x[uc]) <= 0:
        return {"durum": "uç dilimde veter boyunca yayılım yok"}

    # OK ACILI GOVDEDE VETER, ACIKLIKLA KAYAR. Ham x kullanmak ok acisini
    # burulma sanmaya yol acardi; uc dilimin KENDI veter araligina gore
    # merkezlenir.
    xu, wu = x[uc], w[uc]
    egim, kesme = np.polyfit(xu - xu.mean(), wu, 1)
    burulma_deg = float(np.degrees(np.arctan(egim)))
    return {
        "durum": "ok",
        "n_uc_nokta": int(uc.sum()),
        "veter_araligi_m": float(np.ptp(xu)),
        "egilme_mm": round(float(kesme) * 1000, 4),
        "burulma_deg": round(burulma_deg, 4),
        "burulma_baskin_mi": abs(burulma_deg) >= BURULMA_ESIGI_DEG,
        "esik_deg": BURULMA_ESIGI_DEG,
        "hukum": (
            f"BURULMA VAR ({burulma_deg:+.3f}°) — yerel hücum açısı değişiyor, "
            f"iki-yönlü kuplaj SÜRÜLEBİLİR"
            if abs(burulma_deg) >= BURULMA_ESIGI_DEG else
            f"SAF EĞİLME ({burulma_deg:+.3f}° < {BURULMA_ESIGI_DEG}°) — kesit "
            f"yukarı çıkıyor ama yerel hücum açısı DEĞİŞMİYOR; sehim "
            f"büyütmek bunu düzeltmez, geometri değişmeli (ok açısı ya da "
            f"kaydırılmış elastik eksen)"),
    }


def vakadan(case_dir, yama: str, zaman: str | None = None) -> dict:
    """Bir koşunun ağa UYGULANAN yer değiştirme alanından ayrıştırma.

    Kaynak `pointDisplacement`tir: FEA'nın hesapladığı değil, akışın GERÇEKTEN
    gördüğü alan. İkisi arasında bir taşıma adımı var ve o adım sessizce
    bozulabiliyordu.
    """
    import re

    from coupling_fsi import _parse_legacy_vtk

    case = Path(case_dir)
    zamanlar = sorted((d for d in case.iterdir()
                       if d.is_dir() and (d / "pointDisplacement").exists()),
                      key=lambda d: float(d.name) if _sayisal(d.name) else -1)
    if not zamanlar:
        return {"durum": "pointDisplacement taşıyan zaman dizini yok"}
    hedef = (next((d for d in zamanlar if d.name == str(zaman)), None)
             if zaman else zamanlar[-1])
    t = (hedef / "pointDisplacement").read_text(encoding="utf-8", errors="replace")
    blok = t[t.find(yama):] if yama in t else ""
    m = re.search(r"nonuniform List<vector>\s*(\d+)\s*\(", blok)
    if not m:
        return {"durum": f"'{yama}' yamasında nonuniform alan yok — "
                         f"ağ bu zamanda ({hedef.name}) HAREKET ETMEMİŞ"}
    # LISTE SONU ")" DEGIL ");" ILE ARANIR. Ilk ")" karakteri listenin ILK
    # vektorunun kapanisidir ve slice bos cikar; olculdu (fsi_tahrikH: "alan 0"
    # dedi, oysa 122 vektor vardi). Ayni tuzak `write_point_displacement`'ta da
    # yasanmisti — orada yazarken, burada okurken.
    bas = m.end()
    beklenen = int(m.group(1))
    son = blok.find(");", bas)
    if son < 0:
        son = blok.find("\n)", bas)
    vec = np.array([[float(a) for a in g] for g in re.findall(
        r"\(([-\d.eE+]+) ([-\d.eE+]+) ([-\d.eE+]+)\)", blok[bas:son])])
    if len(vec) != beklenen:
        return {"durum": f"yama {beklenen} vektör bildiriyor, {len(vec)} okundu"}

    vtk = sorted((case / "postProcessing" / "yuzeyBasinc").rglob("*.vtk"),
                 key=lambda p: float(p.parent.name) if _sayisal(p.parent.name) else -1)
    if not vtk:
        return {"durum": "yüzey VTK'sı yok — nokta konumları okunamıyor"}
    pts, _polys, _p, _loc = _parse_legacy_vtk(vtk[-1])
    pts = np.asarray(pts, float)
    if len(pts) != len(vec):
        return {"durum": f"nokta sayısı tutmuyor (VTK {len(pts)}, alan {len(vec)})"}
    r = ayristir(pts, vec)
    r["zaman"] = hedef.name
    return r


def _sayisal(s: str) -> bool:
    try:
        float(s)
    # sessiz-yutma: kabul — sayısal olmayan dizin adı zaman değildir; eleme
    # kriterin ta kendisi, hata değil
    except ValueError:
        return False
    return True


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 3:
        print("kullanım: python fsi_burulma.py <case_dir> <yama>")
        return 2
    import json
    print(json.dumps(vakadan(sys.argv[1], sys.argv[2]), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
