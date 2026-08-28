"""Kıyaslama zinciri yöneticisi: dokuz kayıt, tek hüküm --- ve BAYATLIK.

Zincir dokuz betiğe dağılmıştı ve her biri kendi kanıtını yazıyordu; ``bu
platform FSI'da nerede duruyor'' sorusu dokuz JSON'u elle açmayı
gerektiriyordu. Ölçüm vardı, TOPLU HÜKÜM yoktu.

YÖNETİCİ İLK KOŞUSUNDA GERÇEK BİR KUSUR BULDU: `gmsh` ve `CFD1` kanıtları
kendi betiklerinden ESKİYDİ --- ağ ailesi için o betiklere parametre
eklenmiş, kanıt yenilenmemişti. Yeniden koşulunca sayılar birebir aynı
çıktı (ağ üretimi deterministik) ama CFD1'in hükmü ``ağ-bağımsızlığı
sınanmadı'' demeye devam ediyordu --- oysa aile onu kapatmıştı. O cümle
artık kanıttan türetiliyor.

TESTLERİN ODAĞI: yönetici DEĞER üretmemeli, YOL bilmeli. Sayıları burada
yeniden hesaplasaydı ikinci bir kaynak olur ve biri sessizce eskirdi.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "turek_hron_kiyaslama.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("turek_hron_kiyaslama.json yok "
                    "(python experiments/turek_hron_kiyaslama.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_HICBIR_ASAMA_BAYAT_DEGIL(kanit):
    """Asıl iddia. Bayat bir kanıt 'geçti' der ama kod değişmiştir; bu
    testin ilk koşusu iki aşamayı bayat buldu ve kusur oradan çıktı."""
    bayat = [a["ad"] for a in kanit["asamalar"] if a.get("bayat")]
    assert not bayat, (
        f"kanıtı betiğinden eski aşamalar: {bayat} --- yeniden koşulmalı")


def test_HICBIR_ASAMA_EKSIK_DEGIL(kanit):
    yok = [a["ad"] for a in kanit["asamalar"]
           if a["durum"] in ("KOŞULMADI", "OKUNAMADI")]
    assert not yok, f"koşulmayan/okunamayan aşamalar: {yok}"


def test_OLCUT_TASIYAN_ASAMALAR_BANDINDA(kanit):
    asan = [(a["ad"], a["asan"]) for a in kanit["asamalar"]
            if a["durum"] == "AŞIYOR"]
    assert not asan, f"bandı aşan aşamalar: {asan}"


def test_DEGERLER_KANIT_DOSYALARIYLA_AYNI(kanit):
    """Yönetici DEĞER üretmemeli. Her ölçümü kendi kaynak dosyasından
    yeniden okuyup karşılaştır --- ayrışırsa ikinci bir kaynak doğmuştur."""
    from turek_hron_kiyaslama import ZINCIR, _gez
    yol = {a["ad"]: (a["kanit"], a["olcut"]) for a in ZINCIR}
    for a in kanit["asamalar"]:
        dosya, olcutler = yol[a["ad"]]
        kaynak = json.loads((KOK / dosya).read_text(encoding="utf-8"))
        for m, (etiket, iz, _band) in zip(a.get("olcum", []), olcutler,
                                          strict=True):
            assert m["etiket"] == etiket
            ham = _gez(kaynak, iz)
            if m["deger_pct"] is None:
                assert ham is None
            else:
                assert m["deger_pct"] == pytest.approx(float(ham), abs=1e-3), (
                    f"{a['ad']}/{etiket}: yönetici {m['deger_pct']}, kayıt "
                    f"{ham} --- iki kaynak ayrışmış")


def test_YONETICI_SAYI_YAZMIYOR():
    """Ölçüt mekanizmaya bağlanır: dosyada bir sapma sayısı SABİT yazılı
    olmamalı. Bandlar (eşikler) beyandır ve muaftır; ölçüm değerleri
    değildir."""
    import ast
    src = (KOK / "experiments" / "turek_hron_kiyaslama.py").read_text(
        encoding="utf-8")
    agac = ast.parse(src)
    # ZINCIR icindeki sayilar BAND'dir; onlarin disinda kalan float
    # sabitleri suphelidir. ZINCIR atamasini haric tutup tara.
    zincir = next((n for n in ast.walk(agac) if isinstance(n, ast.Assign)
                   and any(getattr(t, "id", "") == "ZINCIR"
                           for t in n.targets)), None)
    assert zincir is not None
    disarida = [n.value for n in ast.walk(agac)
                if isinstance(n, ast.Constant)
                and isinstance(n.value, float)
                and not (zincir.lineno <= n.lineno <= (zincir.end_lineno or 0))]
    assert not disarida, (
        f"ZINCIR dışında float sabit var: {disarida} --- yönetici değer "
        "taşımaya başlamış olabilir")


def test_FSI2_FSI3_ZINCIRDE_YOK(kanit):
    """Olmayan bir aşamayı 'başarısız' göstermek yanlış olurdu; ama
    yokluğu da SÖYLENMELİ, yoksa okur zinciri tam sanır."""
    adlar = [a["ad"] for a in kanit["asamalar"]]
    assert not [x for x in adlar if "FSI2" in x or "FSI3" in x]
    assert "FSI2/FSI3" in kanit["verdikt"]
    assert "yazılmadı" in kanit["verdikt"]


def test_HUKUM_GCI_DEMIYOR(kanit):
    """En tehlikeli okuma: 'hepsi bandında' = 'sayısal belirsizlik
    ölçüldü'. Bandlar kabul eşikleridir."""
    assert "GCI BEYANI DEĞİLDİR" in kanit["verdikt"]


def test_KISIT_TEK_YONLU_FSI1in_uy_OLCUT_OLMADIGINI_soyluyor(kanit):
    """Tek yönlü koşu uy'yi tutturmaz ve tutturması BEKLENMEZ; bu ölçüt
    dışı bırakma gerekçesiyle yazılı olmalı, yoksa keyfi görünür."""
    k = kanit["_kisit"]
    assert "Tek yonlu FSI1'in uy sapmasi olcut" in k
    assert "rijit" in k
