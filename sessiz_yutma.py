"""Sessiz yutma denetimi — "savunma kuruldu ama hükmü kullanıcıya ulaşmıyor" sınıfı.

Bu oturumda ÜÇ kez aynı kusur ölçüldü:
  * salinim_analizi hesaplanıyordu, hiçbir tüketicisi yoktu → salınan çözüme "yakınsadı"
  * measure_yplus `except: pass` ile None döndü → y⁺=5399 kanıta hiç girmedi
  * geometry_sanity eksen kontrolü tipe bağlıydı → 12× A_ref hatası görünmedi
Ortak imza: bir `except` bloğu sebebi YUTUYOR ve çağıran "değer yok" ile "değer iyi"
arasındaki farkı göremiyor.

Bu araç o imzayı AST ile arar (grep çok satırlı bloklarda yanılır) ve RİSKE göre
sıralar: sonucu bir sayıya/hükme dönüşen fonksiyonlar önce gelir.

    python sessiz_yutma.py            # tablo
    python sessiz_yutma.py --json     # sessiz_yutma.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Tablo '✓' ve Türkçe karakter içeriyor; Windows konsolu cp1254'te UnicodeEncodeError
# atıp DENETİMİ İLK SATIRDA KESİYORDU — sessiz yutmayı arayan aracın kendisi çıktısını
# yutuyordu. (Aynı kusur naca2412_kesit.py'de de vardı.)
for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        _akis.reconfigure(encoding="utf-8", errors="replace")
# `experiments` ÖNCE atlanıyordu — oysa V&V ÇAPALARI orada üretiliyor (düz levha,
# basamak, FEA doğrulamaları). Kanıt üreten kodun sessizliği en az hüküm veren kodunki
# kadar önemlidir; kapsama alındı.
ATLA = {"tests", "__pycache__", ".venv", "Construct2D", "sources",
        "vehicle_runs", "_basamak", "_duz_levha", "nx_geo", "nx_geo_egitim", "nx_geo_kor"}
# Hükme/sayıya dönüşen katman — buradaki sessizlik mühendisi yanıltır.
#
# İLK SÜRÜM YALNIZ KÖK DOSYALARI SAYIYORDU ve "güven yolunda incelenmemiş = 0" iddiası
# bu yüzden KAPSAM OLARAK YANLIŞTI: CLAUDE.md'nin KANONİK katman dediği `analysis/`
# (openfoam_runner, ccx_runner, frd_parser, tet_mesher, geometry_loader) hiç
# sayılmıyordu — orada 11 gerekçesiz sessizlik vardı. Dizin bazlı kapsam eklendi.
GUVEN_YOLU_DIZIN = {"analysis", "solvers", "tmr_cfd", "post_processing", "experiments"}
GUVEN_YOLU = {"vehicle_pipeline.py", "validity_envelope.py", "auto_pilot.py",
              "vehicle_report.py", "report_generator.py", "vehicle_fea.py",
              "vehicle_polar.py", "vehicle_topopt.py", "supersonic_report.py",
              "zarf.py", "kanit.py", "mentor.py", "gci_advisor.py"}


def _guven_yolu(rel: str) -> bool:
    parcalar = rel.split("/")
    return (parcalar[0] in GUVEN_YOLU_DIZIN) or (parcalar[-1] in GUVEN_YOLU)


def _dosyalar():
    for f in sorted(ROOT.rglob("*.py")):
        if not (set(f.parts) & ATLA) and f.name != Path(__file__).name:
            yield f


def _yutuyor_mu(gov: list[ast.stmt]) -> str | None:
    """Blok sebebi kaydetmeden akışı sürdürüyorsa nasıl yuttuğunu döner."""
    if len(gov) == 1:
        d = gov[0]
        if isinstance(d, ast.Pass):
            return "pass"
        if isinstance(d, ast.Return):
            if d.value is None or (isinstance(d.value, ast.Constant) and d.value.value is None):
                return "return None"
            if isinstance(d.value, ast.Constant) and d.value.value in (False, 0, ""):
                return f"return {d.value.value!r}"
            if isinstance(d.value, (ast.List, ast.Dict, ast.Tuple)) and not getattr(
                    d.value, "elts", getattr(d.value, "keys", [1])):
                return "return boş koleksiyon"
        if isinstance(d, ast.Continue):
            return "continue"
    return None


KABUL_IM = "sessiz-yutma: kabul"


def _kabul_gerekcesi(kaynak: list[str], lineno: int) -> str | None:
    """`except` satırının hemen ÜSTÜNDE yazılı kabul gerekçesi.

    Ham sayı "incelendi ve kabul edildi" ile "henüz bakılmadı"yı aynı gösteriyordu —
    bu oturumda avlanan kusurun ta kendisi. Kabul, koda YAZILI bir gerekçe ister ve
    gerekçe o satırın yanında durur; denetim onu ayırır.
    """
    for i in range(lineno - 2, max(lineno - 8, -1), -1):
        satir = kaynak[i].strip()
        if KABUL_IM in satir:
            return satir.split(KABUL_IM, 1)[1].lstrip(" :—-") or "(gerekçe boş)"
        if satir and not satir.startswith("#"):
            break
    return None


def _kaydediyor_mu(gov: list[ast.stmt]) -> bool:
    """Blokta sebebi bir yere yazan bir çağrı/atama var mı (log, uyarı, alan)."""
    for d in gov:
        for n in ast.walk(d):
            if isinstance(n, ast.Call):
                ad = getattr(n.func, "attr", getattr(n.func, "id", ""))
                if ad in {"print", "warning", "warn", "error", "append", "info",
                          "exception", "debug", "log"}:
                    return True
            if isinstance(n, (ast.Assign, ast.AugAssign)):
                return True
            if isinstance(n, ast.Raise):
                return True
    return False


def tara() -> list[dict]:
    bulgular = []
    for f in _dosyalar():
        metin = f.read_text(encoding="utf-8-sig", errors="replace")
        try:
            agac = ast.parse(metin)
        except SyntaxError:
            continue
        satirlar = metin.splitlines()
        fonk = {}
        for n in ast.walk(agac):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for c in ast.walk(n):
                    fonk[id(c)] = n.name
        for n in ast.walk(agac):
            if not isinstance(n, ast.ExceptHandler):
                continue
            nasil = _yutuyor_mu(n.body)
            if not nasil or _kaydediyor_mu(n.body):
                continue
            rel = f.relative_to(ROOT).as_posix()
            kabul = _kabul_gerekcesi(satirlar, n.lineno)
            bulgular.append({
                "dosya": rel, "satir": n.lineno,
                "fonksiyon": fonk.get(id(n), "<modül>"),
                "nasil": nasil,
                "yakalanan": ast.unparse(n.type) if n.type else "BARE except",
                "guven_yolu": _guven_yolu(rel),
                "kabul": kabul,
            })
    # Risk sırası: güven yolu önce, sonra bare except, sonra return None
    # İNCELENMEMİŞ olanlar en üste: kabul edilmişler zaten gerekçesini taşıyor.
    bulgular.sort(key=lambda b: (b["kabul"] is not None, not b["guven_yolu"],
                                 b["yakalanan"] != "BARE except",
                                 b["nasil"] != "return None", b["dosya"], b["satir"]))
    return bulgular


def incelenmemis(bulgular=None) -> list[dict]:
    """Gerekçesi YAZILMAMIŞ sessiz yutmalar — asıl izlenmesi gereken sayı."""
    return [x for x in (bulgular if bulgular is not None else tara()) if not x["kabul"]]


def main() -> int:
    b = tara()
    gy = [x for x in b if x["guven_yolu"]]
    inc = incelenmemis(b)
    inc_gy = [x for x in inc if x["guven_yolu"]]
    print(f"{'dosya:satır':38} {'fonksiyon':32} {'yakalanan':22} nasıl")
    for x in b[:40]:
        yer = f"{x['dosya']}:{x['satir']}"
        isaret = ("✓ " if x["kabul"] else ("⚠ " if x["guven_yolu"] else "  "))
        print(f"{isaret}{yer:36} {x['fonksiyon']:32} {x['yakalanan'][:22]:22} {x['nasil']}")
    print(f"\n**Toplam:** {len(b)} sessiz yutma ({len(gy)} güven yolunda)")
    print(f"**İNCELENMEMİŞ:** {len(inc)} ({len(inc_gy)} güven yolunda) — asıl izlenen sayı")
    print(f"**Kabul edilmiş (gerekçesi kodda yazılı):** {len(b) - len(inc)}")
    if "--json" in sys.argv:
        (ROOT / "sessiz_yutma.json").write_text(
            json.dumps({"toplam": len(b), "guven_yolu": len(gy),
                        "incelenmemis": len(inc), "incelenmemis_guven_yolu": len(inc_gy),
                        "bulgular": b},
                       indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("-> sessiz_yutma.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
