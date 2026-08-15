"""Ortam kapısı — "konteyner masaüstüyle aynı sonucu verir" iddiasını sürüm öncesi bağlar.

Bu iddia dağıtımın TEK gerekçesidir: okulda, bulutta ya da bir ortağın
makinesinde koşan sonuç, burada üretilenle karşılaştırılabilir olmalıdır. İddia
2026-08-15'te bir kez ölçüldü (Cd farkı \\%0,099, ağ bit-aynı, sınıf aynı) ama
tek seferlik bir ölçüm, bir sonraki imaj inşasında sessizce geçersizleşir.

Kapı iki şeyi ayrı ayrı sınar ve İKİSİ DE gereklidir:

  1. ÖLÇÜM TAZE Mİ. Kıyas dosyası hangi imaj ve hangi kaynak üzerinde
     üretildiğini taşır. İmaj yeniden inşa edildiyse ya da kaynak ilerlediyse,
     dosyadaki sayı bugünün ikilisi hakkında bir şey söylemez. Bayat bir dosyayı
     okuyup "örtüşüyor" demek, tam olarak bu deponun avladığı kusurdur.
  2. ÖLÇÜM GEÇTİ Mİ. Cd farkı eşiğin altında, hücre sayısı aynı, geçerlilik
     sınıfı aynı. Sınıf ölçütün parçasıdır: sayı örtüşüp hüküm ayrışırsa iki
     ortam aynı sonucu vermiyordur.

    python ortam_kapisi.py           # yalnız dener, ölçmez
    python ortam_kapisi.py --olc     # bayatsa yeniden ölçer (dakikalar sürer)
Çıkış: 0 = ortamlar bağlı, 1 = engel var.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
OLCUM = KOK / "ortam_capraz_olcumu.json"
OLCUM_BETIGI = "experiments/ortam_capraz_olcumu.py"


def _kabuk(argv: list[str]) -> str | None:
    try:
        r = subprocess.run(argv, cwd=KOK, capture_output=True, text=True, timeout=60)
        return (r.stdout.strip() or None) if r.returncode == 0 else None
    # sessiz-yutma: kabul — `None` BURADA BİR SİNYALDİR, yutulan bir hata değil.
    # Çağıran (denetle) onu "belirlenemedi" diye okur ve ilgili engeli DÜŞÜRÜR
    # ("konteyner erişimi ❌"). Yani docker/git yoksa kapı sessizce geçmez,
    # aksine geçmez; doğrulanamayan tazelik olumlu kanıt sayılmaz.
    except (OSError, subprocess.SubprocessError):
        return None


def _guncel_imaj() -> str | None:
    kap = _kabuk(["docker", "compose", "-f", "docker/compose.yaml", "ps", "-q", "worker"])
    return _kabuk(["docker", "inspect", "--format", "{{.Image}}", kap]) if kap else None


def denetle() -> list[dict]:
    """Her engel: {ad, gecti, detay}."""
    out: list[dict] = []
    if not OLCUM.exists():
        return [{"ad": "kıyas ölçümü", "gecti": False,
                 "detay": f"{OLCUM.name} yok — `python {OLCUM_BETIGI}` koşun"}]
    d = json.loads(OLCUM.read_text(encoding="utf-8-sig"))
    damga = d.get("damga") or {}

    # ── 1. TAZELİK ──
    if not damga:
        out.append({"ad": "ölçüm damgası", "gecti": False,
                    "detay": "damgasız ölçüm — hangi imaj/kaynak üzerinde "
                             "üretildiği bilinmiyor, tazelik denetlenemez"})
    else:
        simdiki = _guncel_imaj()
        olculen = damga.get("konteyner_imaji")
        if simdiki is None:
            out.append({"ad": "konteyner erişimi", "gecti": False,
                        "detay": "worker ayakta değil — tazelik doğrulanamıyor. "
                                 "`docker compose -f docker/compose.yaml up -d`"})
        else:
            ayni = simdiki == olculen
            out.append({"ad": "imaj tazeliği", "gecti": ayni,
                        "detay": "" if ayni else
                                 f"ölçüm {str(olculen)[:19]}… üzerinde yapıldı, "
                                 f"ayakta olan {simdiki[:19]}… — yeniden ölçün"})
        islem = _kabuk(["git", "rev-parse", "--short=7", "HEAD"])
        ayni_kaynak = islem is not None and islem == damga.get("kaynak_islemesi")
        out.append({"ad": "kaynak tazeliği", "gecti": ayni_kaynak,
                    "detay": "" if ayni_kaynak else
                             f"ölçüm {damga.get('kaynak_islemesi')} işlemesinde "
                             f"yapıldı, şimdiki {islem} — yeniden ölçün"})
        # Kirli ağaçta alınan işleme damgası kaynağı TANIMLAMAZ: aynı hash,
        # işlenmemiş değişikliklerle birlikte bambaşka bir koda karşılık gelir.
        temiz = not damga.get("kaynak_kirli", True)
        out.append({"ad": "ölçüm temiz ağaçta", "gecti": temiz,
                    "detay": "" if temiz else
                             "ölçüm işlenmemiş değişikliklerle yapıldı; işleme "
                             "damgası kaynağı tanımlamıyor — işleyip yeniden ölçün"})

    # ── 2. ÖLÇÜMÜN HÜKMÜ ──
    esik = d.get("esik_yuzde", 1.0)
    fark = d.get("fark_yuzde")
    out.append({"ad": f"Cd farkı ≤ %{esik}", "gecti": bool(d.get("ortamlar_ortusuyor")),
                "detay": "" if d.get("ortamlar_ortusuyor") else
                         f"fark %{fark} (eşik %{esik}) — {d.get('neden', '')}"})
    out.append({"ad": "geçerlilik sınıfı aynı", "gecti": bool(d.get("sinif_ayni")),
                "detay": "" if d.get("sinif_ayni") else
                         "sayı örtüşse bile HÜKÜM ayrışıyor; sınıf sonucun parçasıdır"})
    hs = d.get("hucre_sayilari") or {}
    ayni_ag = bool(hs) and hs.get("host") == hs.get("konteyner")
    out.append({"ad": "ağ bit-aynı", "gecti": ayni_ag,
                "detay": "" if ayni_ag else
                         f"hücre sayısı ayrışıyor: {hs} — aynı çözücü koşmuyor olabilir"})
    return out


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")

    if "--olc" in sys.argv:
        print(f"ölçüm koşuluyor ({OLCUM_BETIGI}) — dakikalar sürer…", flush=True)
        r = subprocess.run([sys.executable, OLCUM_BETIGI], cwd=KOK)
        if r.returncode not in (0, 1):
            print("ölçüm koşulamadı", file=sys.stderr)
            return 1

    ks = denetle()
    print("Ortam kapısı — masaüstü ile konteyner bağlı mı")
    print("=" * 50)
    for k in ks:
        im = "✅" if k["gecti"] else "❌"
        print(f"{im} {k['ad']}" + (f"  — {k['detay']}" if k["detay"] else ""))
    engel = [k for k in ks if not k["gecti"]]
    print("-" * 50)
    if engel:
        print(f"❌ {len(engel)} engel — ortam eşdeğerliği İDDİA EDİLEMEZ.")
        return 1
    print("✅ Ortamlar bağlı: ölçüm bu imaj ve bu kaynak üzerinde yapıldı ve geçti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
