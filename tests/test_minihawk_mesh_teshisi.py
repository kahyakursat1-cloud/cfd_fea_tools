"""MiniHawk RANS mesh teşhisi — GCI %379 bir BELİRTİ, sebep değil.

ÖLÇÜLDÜ (koşunun kendi loglarından): araç yüzeyi mesh'te 8 / 144 / 74 yüzle
temsil ediliyor, eşik 500. En ince seviye ortadan 7 KAT fazla taban hücreyle
DAHA AZ yüzey yüzü veriyor — kademeler aynı geometrinin farklı çözünürlükleri
değil. Kök neden dağıtım: alan 1.5 m açıklıklı uçak için 38×22.5×21 m ve arka
plan mesh'i oraya düzgün seriliyor.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KANIT = ROOT / "minihawk_mesh_teshisi.json"
DELTA = ROOT / "delta_entegrasyon.json"


def _d():
    return json.loads(KANIT.read_text(encoding="utf-8")) if KANIT.exists() else None


def test_ESIK_kodun_TEK_KAYNAGINDAN():
    """Eşik burada tekrar yazılırsa ikisi ayrışır; kanonik değer okunmalı."""
    from analysis.openfoam_runner import YUZEY_YUZ_ESIGI
    d = _d()
    if not d:
        return
    assert d["yuzey_yuz_esigi"] == YUZEY_YUZ_ESIGI


def test_YUZEY_YUZ_monotonlugu_OLCULUYOR():
    """Hücre artarken yüzey yüzü artmıyorsa aile tek-parametreli değildir."""
    d = _d()
    if not d:
        return
    y = [v for _, v in ((k["ad"], k.get("yuzey_yuz")) for k in d["seviyeler"]) if v]
    gercek = all(a <= b for a, b in zip(y, y[1:]))
    assert d["yuzey_yuz_monoton"] == gercek
    if not gercek:
        assert "MONOTON DEGIL" in d["verdikt"]


def test_BELIRTI_ile_SEBEP_ayriliyor():
    """GCI ve y+ SONUÇ; sebep yüzeyin çözülmemesi. Yüzey ÇÖZÜLMEMİŞSE rapor
    bunu söylemeli; çözülmüşse o cümleyi TEKRARLAMAMALI (rapor kendi verisiyle
    çelişmemeli)."""
    d = _d()
    if not d:
        return
    assert "arka plan" in d["_kok_neden"].lower()
    if d.get("yuzey_cozuldu"):
        assert "COZULDU" in d["verdikt"]
        assert "MESH'TE YOK" not in d["verdikt"]
    else:
        assert "SONUCUDUR" in d["verdikt"]


def test_ZATEN_DUZELTILMIS_oldugu_yaziyor():
    """Bu bir kusur raporu DEĞİL: kök neden kodda çözülmüş (b62980c,
    arka_plan_hucre_boyu bütçenin %25'i). Kayıt o düzeltmeden ÖNCEKİ boru
    hattına ait. Dosya yeni bir kusur ima ederse okuyucu var olmayan bir işi
    yapmaya kalkar."""
    d = _d()
    if not d:
        return
    assert "b62980c" in d.get("_zaten_duzeltildi", "")
    assert "YENIDEN KOSU" in d.get("_gereken", "").upper()
    assert "b62980c" in d["verdikt"]


def test_DUZELTME_kodda_GERCEKTEN_var():
    """Kanıt "düzeltildi" diyorsa kod da öyle demeli."""
    from analysis.openfoam_runner import ARKA_PLAN_BUTCE_PAYI, arka_plan_hucre_boyu
    assert 0 < ARKA_PLAN_BUTCE_PAYI <= 0.5
    # Butceyi asan bir istek KABALASTIRILMALI (asla inceltilmemeli).
    boy, bilgi = arka_plan_hucre_boyu((0, 0, 0), (38.2, 22.5, 21.1), 0.1663,
                                      1_200_000)
    assert bilgi["kabalastirildi"], "arka plan butce icin kabalastirilmiyor"
    assert bilgi["arka_plan_hucre"] <= 1_200_000


def test_YAMA_YOK_ile_SIFIR_YUZ_ayri():
    """Patch hiç yoksa bu '0 yüz' demek değildir; ikisi karışmamalı."""
    d = _d()
    if not d:
        return
    # Hukum yalniz GUNCEL kademelerden verilir; bayatlar kayitta kalir.
    for k in d["seviyeler"]:
        if k.get("yuzey_yuz") is None and k["ad"] in d["guncel_seviyeler"]:
            assert k["ad"] in d["esik_altinda_seviyeler"]
    assert set(d["guncel_seviyeler"]).isdisjoint(d["bayat_seviyeler"])


def test_KISIT_yeniden_hesaplama_IDDIA_ETMIYOR():
    """Teşhis loglardan üretildi; çözücü sonuçları yeniden koşulmadı."""
    d = _d()
    if not d:
        return
    assert "YENIDEN HESAPLANMADI" in d["_kisit"]


def test_DELTA_kok_nedeni_ONCE_soyluyor():
    """Δ 'GCI yüksek' deyip kök nedeni atlarsa okuyucu yanlış işi yapar."""
    if not DELTA.exists() or not KANIT.exists():
        return
    d = json.loads(DELTA.read_text(encoding="utf-8"))
    assert "(0)" in d["_gerekli"], "gerekli adimlar sirali degil"
    # Adimlar OLCUMDEN turetilmeli: yuzey cozulduyse (0) ISARETLI olmali,
    # cozulmediyse ENGEL listesinde adi gecmeli.
    t = json.loads(KANIT.read_text(encoding="utf-8")) if KANIT.exists() else {}
    if t.get("yuzey_cozuldu"):
        assert "✔" in d["_gerekli"]
    else:
        assert any("ARAC YUZEYI" in e for e in d["engeller"])
