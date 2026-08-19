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
