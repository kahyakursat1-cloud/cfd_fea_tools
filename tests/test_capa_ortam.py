"""Çapa koşuları ÇÖZÜCÜ sürümünü taşıyor mu — ortam.py'nin varoluş gerekçesi.

`ortam.py` şunu savunuyor: "aynı komut farklı bir OpenFOAM ile farklı sayı
verebilir ve hiçbir şey bunu söylemez". Ama araç hattı damgayı `parmak_izi()`
VARSAYILANIYLA basıyordu (`cozucu=False`) --- yani damga python/paket/os/
çekirdek taşıyordu ve çözücü sürümü tam da CFD sonucunda KAYITSIZDI. Savunma
vardı, üretim yolu onu eksik çağırıyordu.

Ölçüldü ve düzeltildi 2026-08-22. Sorgu 8,1 s; saatlerce WSL'de koşan bir
vaka için ihmal edilebilir.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))


def _cagri_kwarg(kaynak: str, fon: str, isim: str):
    """`fon(...)` çağrılarında `isim=` argümanının değerleri — AST ile.

    Metin araması yapılmıyor: `parmak_izi(cozucu=True)` dizisi bir yorum
    satırında da geçebilir ve bu depoda tam olarak o kusur (kendi açıklayıcı
    yorumuyla eşleşen test) daha önce üç kez yaşandı.
    """
    out = []
    for d in ast.walk(ast.parse(kaynak)):
        if not isinstance(d, ast.Call):
            continue
        ad = (d.func.attr if isinstance(d.func, ast.Attribute)
              else getattr(d.func, "id", None))
        if ad != fon:
            continue
        out.append(next((k.value.value for k in d.keywords
                         if k.arg == isim and isinstance(k.value, ast.Constant)),
                        None))
    return out


def test_arac_hatti_COZUCU_surumunu_de_damgaliyor():
    """Damga çözücüsüz olursa `ortam.py`'nin ana iddiası boşa çıkar."""
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    degerler = _cagri_kwarg(src, "parmak_izi", "cozucu")
    assert degerler, "vehicle_pipeline parmak_izi() çağırmıyor"
    assert all(v is True for v in degerler), (
        f"parmak_izi çözücüsüz çağrılıyor: {degerler} — çözücü sürümü "
        f"kaydedilmezse aynı komut farklı OpenFOAM ile farklı sayı verir "
        f"ve kanıt bunu söyleyemez")


def test_DUSEN_kosu_da_damgalaniyor():
    """Arızanın ortama bağlı olduğu durum tam da düşen koşudur.

    AR6 çapası snappyHexMesh'te rc 137 ile (bellek) düştü ve kaydında ne
    çekirdek sayısı ne sürüm vardı; teşhis elle yeniden kuruldu.
    """
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    agac = ast.parse(src)
    # `status="failed"` ile kurulan sonucu DONDUREN fonksiyon, donmeden once
    # base.ortam atamis olmali.
    bulundu = False
    for f in ast.walk(agac):
        if not isinstance(f, ast.FunctionDef):
            continue
        govde = ast.dump(f)
        if '"failed"' not in govde and "'failed'" not in govde:
            continue
        atamalar = [d for d in ast.walk(f) if isinstance(d, ast.Assign)
                    and any(isinstance(t, ast.Attribute) and t.attr == "ortam"
                            for t in d.targets)]
        if len(atamalar) >= 2:      # basari yolu + dusen yol
            bulundu = True
    assert bulundu, ("düşen koşu yolunda `base.ortam` ataması yok — başarısız "
                     "koşu ortamsız kaydediliyor")


def test_LOGDAN_okuma_BUGUNKU_surumu_yazmiyor():
    """Retro-doldurma bir ALINTI olmalı, kestirim değil."""
    import ortam
    src = (KOK / "ortam.py").read_text(encoding="utf-8")
    i = src.index("def logdan_cozucu(")
    govde = src[i:src.index("\ndef ", i + 10)]
    assert "cozucu_surumleri" not in govde, (
        "logdan_cozucu bugünkü sürümü sorguluyor — koşuyu üreten sürüm o "
        "olmayabilir ve boşluğa bugünkünü yazmak YALAN olur")
    assert "_kaynak" in govde, "alıntının kaynağı damgaya yazılmalı"
    assert ortam.logdan_cozucu(KOK / "yok_boyle_bir_dizin") is None


def test_CAPA_kosulari_cozucu_surumu_TASIYOR():
    kok = KOK / "validation_anchors_runs"
    if not kok.exists():
        pytest.skip("çapa koşu arşivi yok")
    eksik = []
    for sj in sorted(kok.glob("*/sonuc.json")):
        s = json.loads(sj.read_text(encoding="utf-8"))
        if s.get("status") != "ok":
            continue          # dusen kosu ayri konu — yukaridaki test bagliyor
        if not ((s.get("ortam") or {}).get("cozucu") or {}).get("openfoam"):
            eksik.append(sj.parent.name)
    assert not eksik, f"çözücü sürümü olmayan BAŞARILI çapa koşusu: {eksik}"


def test_TAMAMLAMA_idempotent_ve_KURU_KOSU_varsayilan():
    """İkinci koşu hiçbir şey değiştirmemeli; kuru koşu dosyaya dokunmamalı."""
    from capa_ortam_tamamla import tara, uygula
    r = uygula(tara(), yaz=False)
    assert r["tamamlanan"] == [], (
        f"hâlâ tamamlanacak koşu var: {r['tamamlanan']} — "
        f"python experiments/capa_ortam_tamamla.py --yaz")
    assert len(r["zaten_tam"]) >= 4


def test_KAPSAM_kaniti_tamamlanamayanlari_ADIYLA_yaziyor():
    """"22 koşu damgasız" demek yetmez; hangileri olduğu yazılmalı."""
    p = KOK / "kosu_ortam_kapsami.json"
    if not p.exists():
        pytest.skip("kosu_ortam_kapsami.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["tamamlanamayan"], "tamamlanamayanlar listelenmemiş"
    for satir in d["tamamlanamayan"]:
        assert "—" in satir, f"gerekçesiz satır: {satir}"
    assert d["capa_cozucu_tam"] >= d["capa_kosusu"] - 1
    assert "retroaktif KURULAMAZ" in d["verdikt"] or "TAM" in d["verdikt"]
