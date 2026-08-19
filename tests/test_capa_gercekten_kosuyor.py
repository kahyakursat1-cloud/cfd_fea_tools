"""Bir çapa "yazılmış" olabilir ama HİÇ KOŞMAMIŞ olabilir.

ÖLÇÜLDÜ (2026-08-19): `experiments/fea_capa_bagimsiz.py` içindeki burulma
çapası (`mil_burulma`) kodda tamdı, ana döngüde çağrılıyordu ve tüm testlerden
geçiyordu — ama `if __name__ == "__main__"` bloğu o fonksiyondan ÖNCE
geliyordu. Yani main() çalıştığında ad henüz tanımlı değildi ve betik
`NameError: name 'mil_burulma' is not defined` ile düşüyordu. Kanıt dosyasında
"mil" anahtarı hiç yoktu ve bunu kimse fark etmemişti.

Bu, deponun tekrar tekrar yakaladığı desenin bir başka yüzü: savunma/ölçüm
VAR, ama çalışan yol ondan geçmiyor. Burada kapı şunu sorar: ana döngünün
saydığı her çapa, üretilen kanıtta da var mı?

Testler kanıt dosyası yoksa sessizce geçer — üretim komutu kayıtlıdır ve
`test_kanit_manifest` eksikliği ayrıca izler.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

BETIK = KOK / "experiments" / "fea_capa_bagimsiz.py"
KANIT = KOK / "fea_capa_bagimsiz.json"


def _dongudeki_capalar() -> list[str]:
    """main() içindeki çapa demetinden adları AST ile çıkar.

    Metin arama yerine AST: demet elle güncellendiğinde test kendiliğinden
    güncel kalır ve yorum satırlarındaki adları yanlışlıkla saymaz.
    """
    agac = ast.parse(BETIK.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(agac)
              if isinstance(n, ast.FunctionDef) and n.name == "main")
    adlar: list[str] = []
    for dugum in ast.walk(fn):
        if not isinstance(dugum, ast.Tuple) or len(dugum.elts) != 4:
            continue
        ilk = dugum.elts[0]
        if isinstance(ilk, ast.Constant) and isinstance(ilk.value, str):
            adlar.append(ilk.value)
    return adlar


def test_dongudeki_her_capa_KANITTA_var():
    adlar = _dongudeki_capalar()
    assert adlar, "main() içinde çapa demeti bulunamadı — test kör kalmış"
    if not KANIT.exists():
        return
    d = json.loads(KANIT.read_text(encoding="utf-8"))
    eksik = [a for a in adlar if a not in d]
    assert not eksik, (
        f"ana döngü bu çapaları sayıyor ama kanıtta YOKLAR: {eksik}. "
        "Çapa yazılmış olabilir ama koşmamıştır — "
        "python experiments/fea_capa_bagimsiz.py")


def test_dongudeki_her_capa_FONKSIYONU_main_ONCESINDE_tanimli():
    """NameError'ı koşmadan yakala: ad, main çağrılmadan tanımlı olmalı.

    Burulma çapası tam bu yüzden hiç koşmamıştı — fonksiyon dosyada VARDI ama
    giriş noktasından SONRA geliyordu.
    """
    kaynak = BETIK.read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    tanim_satiri = {n.name: n.lineno for n in agac.body
                    if isinstance(n, ast.FunctionDef)}
    giris = [n.lineno for n in agac.body
             if isinstance(n, ast.If) and "__main__" in ast.dump(n.test)]
    assert giris, "`if __name__ == \"__main__\"` bloğu yok"
    giris_satiri = min(giris)

    fn = next(n for n in ast.walk(agac)
              if isinstance(n, ast.FunctionDef) and n.name == "main")
    gec = []
    for dugum in ast.walk(fn):
        if not isinstance(dugum, ast.Tuple) or len(dugum.elts) != 4:
            continue
        f = dugum.elts[1]
        if isinstance(f, ast.Name) and tanim_satiri.get(f.id, 0) > giris_satiri:
            gec.append(f.id)
    assert not gec, (
        f"bu çapa fonksiyonları giriş noktasından SONRA tanımlı: {gec} — "
        "main() çağrıldığında ad henüz yok, betik NameError ile düşer")


def test_burulma_capasi_BAGIMSIZ_ve_gercekten_olculmus():
    """Burulma, mevcut çapalardan farklı bir yükleme tipi olmalı ve sayı taşımalı."""
    if not KANIT.exists():
        return
    d = json.loads(KANIT.read_text(encoding="utf-8"))
    mil = d.get("mil")
    if mil is None:
        raise AssertionError(
            "burulma çapası kanıtta yok — python experiments/fea_capa_bagimsiz.py")
    ince = mil.get("en_ince") or {}
    assert ince.get("durum") == "ok", f"burulma çapası çözülemedi: {ince}"
    assert ince.get("hata_pct") is not None
    # St. Venant dairesel kesitte KESİN; birkaç yüzde sapma ağ/kurulum işaretidir.
    assert ince["hata_pct"] < 10.0, (
        f"burulma sapması %{ince['hata_pct']:.2f} — kapalı-form kesin olduğu "
        "için bu kadar sapma ağ ya da sınır koşulu kusuruna işaret eder")


# ── TO stres kapısı: ağ marjı ELEMAN MERTEBESİNİ kapsamıyor ────────────────

def test_TO_kapisi_lineer_tetten_GUVENLI_demiyor():
    """C3D4 ağında hesaplanan SF'den "güvenli" hükmü çıkmamalı.

    ÖLÇÜLDÜ (fea_element_order.json, 2026-08-19): ankastre kirişte C3D4
    eğilme gerilmesini %59–74 DÜŞÜK veriyor (C3D10 %0,0, σ(z) uydurma R²≈1).
    Düşük gerilme YÜKSEK SF demektir — güvensiz yön.

    `vehicle_topopt` SF'yi `generate_tet_mesh(second_order=False)` ağında
    hesaplıyor ama ağ marjı (`_ag_buyumesi`) AYNI eleman tipiyle yapılmış bir
    inceltme çalışmasından geliyor: ayrıklaştırmayı ölçüyor, eleman
    mertebesini DEĞİL. İki ayrı hata kaynağı, tek marjla kapatılamaz.
    """
    from vehicle_topopt import _stress_gate
    # Ag marjini RAHATCA gecen bir SF (esik ~2,2).
    h = _stress_gate({"emniyet_faktoru_temsili": 9.9})
    assert h["durum"] != "güvenli", (
        f"lineer tet ağından 'güvenli' hükmü çıktı (SF={h.get('SF')})")
    assert "eleman_mertebesi" in h, "eleman mertebesi hükümde beyan edilmiyor"
    assert h["eleman_mertebesi"]["bu_geometride_olculdu_mu"] is False
    assert "C3D10" in h["mesaj"], "çare (C3D10 ile bağımsız analiz) söylenmiyor"


def test_TO_kapisi_AKMA_hukmunu_hala_veriyor():
    """Kısıtlama yalnız 'güvenli' tarafında; güvensiz hükümler bozulmamalı."""
    from vehicle_topopt import _stress_gate
    assert _stress_gate({"emniyet_faktoru_temsili": 0.6})["durum"] == "akma_asildi"
    assert _stress_gate({"emniyet_faktoru_temsili": 1.2})["durum"] == "marjinal"
    assert _stress_gate({"emniyet_faktoru_temsili": None})["durum"] == "değerlendirilemedi"


def test_eleman_mertebesi_kaniti_GERILMEYI_de_olcuyor():
    """Sehim yetmez: TO'nun SF'si gerilmeye dayanıyor."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "fea_element_order.json"
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    g = d.get("gerilme_ekseni")
    assert g, "kanıt yalnız sehim ekseni taşıyor"
    assert g["C3D4_hata_pct"] is not None and g["C3D10_hata_pct"] is not None
    # C3D10 gerilmede analitige yakin olmali; degilse estimator bozuktur.
    assert abs(g["C3D10_hata_pct"]) < 5.0, (
        f"C3D10 gerilme hatası %{g['C3D10_hata_pct']} — kapalı-form kirişte "
        "bu kadar sapma tahmin ediciyi şüpheli kılar")
    # Uydurma kalitesi de kayitli olmali.
    for r in d["kosular"]:
        if r["eleman"] == "C3D10" and r.get("sigma_uydurma_R2") is not None:
            assert r["sigma_uydurma_R2"] > 0.95


# ── Mertebe yükseltmesi: kapıyı besleyen kanıt GERÇEKTEN üretiliyor mu ─────

def test_tet4_to_tet10_KENAR_dugumlerini_PAYLASIYOR():
    """Komşu tetlerin ortak kenarı TEK düğüm olmalı; yoksa ağ yırtılır."""
    import numpy as np

    from vehicle_topopt import tet4_to_tet10
    P = np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]])
    t = np.array([[0, 1, 2, 3], [1, 2, 3, 4]])
    P10, t10 = tet4_to_tet10(P, t)
    # 2 tet × 6 kenar = 12, ortak yüzün 3 kenarı paylaşılır → 9 tekil
    assert len(P10) == len(P) + 9, f"kenar düğümü paylaşılmıyor: {len(P10)}"
    assert t10.shape[1] == 10
    # Koseler DEGISMEDI: mevcut NSET/CLOAD blokları geçerli kalmalı.
    assert np.array_equal(t10[:, :4], t)
    assert np.allclose(P10[:len(P)], P)


def test_tet4_to_tet10_C3D10_SIRASI_dogru():
    """Yanlış sıra sessizce çözülür ama YANLIŞ gerilme verir.

    CalculiX/Abaqus C3D10: 4 köşe + kenarlar (0-1, 1-2, 2-0, 0-3, 1-3, 2-3).
    """
    import numpy as np

    from vehicle_topopt import tet4_to_tet10
    P = np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])
    P10, t10 = tet4_to_tet10(P, np.array([[0, 1, 2, 3]]))
    for j, (a, b) in enumerate([(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]):
        assert np.allclose(P10[t10[0][4 + j]], 0.5 * (P[a] + P[b])), (
            f"kenar {a}-{b} yanlış konumda (sıra bozuk)")


def test_TO_final_analizi_C3D10_DOGRULAMASI_uretiyor():
    """Kapı kanıt istiyor — üreten yol gerçekten var mı?

    `_stress_gate` "güvenli" için `sa["eleman_mertebesi"]["dogrulandi"]`
    arıyor. O alanı hiçbir yer doldurmuyorsa kapı kalıcı olarak kapalı kalır
    ve kısıtlama bir ölçüm değil bir engel olur.
    """
    import inspect

    import vehicle_topopt as vt
    src = inspect.getsource(vt.run_topopt)
    assert "tet4_to_tet10" in src, "mertebe yükseltmesi TO akışında çağrılmıyor"
    assert 'eleman_tipi="C3D10"' in src, "C3D10 inp'si yazılmıyor"
    assert 'sa["eleman_mertebesi"] = eo' in src, "kanıt kapıya bağlanmıyor"
    # Hukum YUKSEK MERTEBEDEN okunmali; kanit uretip dusuk mertebeyi
    # kullanmak dogrulamayi susleme haline getirirdi.
    i = src.index('sa["eleman_mertebesi"] = eo')
    assert "sa = {**sa2" in src[:i], (
        "C3D10 çözüldüğü hâlde hüküm hâlâ C3D4 sonucundan veriliyor")
