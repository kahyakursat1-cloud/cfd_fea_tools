"""Aşama arızası: rc 137 iki farklı şeydir ve kayıt bunu söylemeli.

VAKA. AR6 kanat çapası `snappyHexMesh`te düştü ve kayıt şunu yazdı:
``hata (dönüş kodu 137), 1319 s sonra''. 137 = 128+9, yani SIGKILL --- ama
KİM öldürdü? İki aday var ve çareleri ZIT:

  GNU timeout'un `-k` KILL'i   -> süre yetmedi   -> daha çok süre / ucuz ağ
  çekirdeğin OOM öldürücüsü    -> bellek yetmedi -> daha az bellek / küçük ağ

Ayrım kayıtta yoktu ve iki kez ELLE kuruldu (bir kez kod yorumunda, bir kez
bu testler yazılırken). Ölçüt zamandır: iç timeout `tmo-20`de TERM gönderir;
süre o eşiğe ULAŞMIŞSA timeout'tur, anlamlı ölçüde ALTINDAYSA süreci başkası
öldürmüştür.

İKİNCİ KUSUR. `asama_sureleri` ve `bellek` yalnız BAŞARI yolunda kaydediliyor,
düşen koşu onlardan önce dönüyordu. Yani telemetri en çok gerektiği yerde
null kalıyor, aynı bilgi ise bir Türkçe cümlenin içinde saklanıyordu.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))


def _kayit(rc: int, sure: float, tmo: int = 1800, sarildi: bool = True) -> dict:
    """`_step`in sınıflandırma kuralını AYNEN uygula.

    Kural kodda gömülü (yerel fonksiyon), o yüzden burada YENIDEN yazılıyor;
    ayrışmasınlar diye aşağıdaki `test_kural_kodda_da_ayni` kaynağı okur.
    """
    ic = max(tmo - 20, 30) if sarildi else None
    k = {"sure_s": sure, "durum": "ok" if rc == 0 else "hata", "donus_kodu": rc}
    if rc != 0 and ic is not None:
        k["ic_tmo_s"] = ic
        if rc == 124 or (rc == 137 and sure >= ic):
            k["durum"] = "ZAMAN ASIMI"
        elif rc == 137:
            k["durum"] = "DISARIDAN OLDURULDU"
    return k


def test_AR6_vakasi_bellek_olarak_okunur():
    """Gerçek vaka: 1319 s'de rc 137, iç timeout 1780 s. Süre eşiğin ALTINDA,
    yani timeout değil. Kayıttaki 'bellek' teşhisi böylece ÖLÇÜLÜ olur."""
    assert _kayit(137, 1319.0)["durum"] == "DISARIDAN OLDURULDU"


def test_gercek_zaman_asimi_timeout_olarak_okunur():
    """Aynı kod, süre eşiğe ULAŞMIŞ: bu kez timeout."""
    assert _kayit(137, 1780.0)["durum"] == "ZAMAN ASIMI"
    assert _kayit(137, 1790.0)["durum"] == "ZAMAN ASIMI"
    # TERM ile duran surec 124 verir; sure bakilmadan timeout'tur
    assert _kayit(124, 12.0)["durum"] == "ZAMAN ASIMI"


def test_baska_hatalar_ZAMAN_ASIMI_diye_etiketlenmez():
    """YANLIŞ-POZİTİF kapısı: ölçüt yalnız 124/137'ye bakmalı. Segfault (139),
    genel hata (1), OpenFOAM'ın FATAL ERROR'u (1) timeout DEĞİLDİR."""
    for rc in (1, 2, 139, 255):
        d = _kayit(rc, 1790.0)
        assert d["durum"] == "hata", f"rc {rc} yanlışlıkla {d['durum']}"


def test_sarilmamis_komut_siniflandirilmaz():
    """OF binary içermeyen komut `timeout` ile sarılmaz; orada iç eşik YOKTUR
    ve 137'yi timeout saymak dayanaksız olurdu."""
    d = _kayit(137, 5000.0, sarildi=False)
    assert d["durum"] == "hata" and "ic_tmo_s" not in d


def test_basarili_asama_dokunulmadan_gecer():
    d = _kayit(0, 10.0)
    assert d["durum"] == "ok" and "ic_tmo_s" not in d


def test_kural_kodda_da_AYNI():
    """Yukarıdaki kural kodun kendisinden ayrışmasın: `_step` içinde hem 124
    hem 137 geçmeli, ve ayrım SÜREYİ iç eşikle karşılaştırmalı."""
    src = (KOK / "analysis" / "openfoam_runner.py").read_text(encoding="utf-8")
    bas = src.index("def _step(")
    govde = src[bas:src.index("\n        return r", bas)]
    kod = "\n".join(s for s in govde.splitlines()
                    if not s.lstrip().startswith("#"))
    assert "124" in kod and "137" in kod, "sınıflandırma kodda yok"
    assert "ZAMAN ASIMI" in kod and "DISARIDAN OLDURULDU" in kod
    assert "_sure >= _ic_tmo" in kod, \
        "ayrım süreyi eşikle karşılaştırmıyor — rc tek başına yeterli değil"


def test_DUSEN_kosu_da_asama_telemetrisini_SAKLAR():
    """Telemetri yalnız başarı yolunda yazılıyordu; arıza yolunda null kalması
    tam da onu gerektiren durumdu.

    AST ile denetlenir: `if not res.success` blogunun ICINDE `base.
    asama_sureleri` atamasi bulunmali. Kaynak-metni aramak yetmezdi ---
    basari yolundaki atama da ayni dizgiyi tasiyor.
    """
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    hedef = None
    for n in ast.walk(ast.parse(src)):
        if not isinstance(n, ast.If):
            continue
        t = ast.unparse(n.test)
        if "res.success" in t and t.startswith("not "):
            hedef = n
            break
    assert hedef is not None, "arıza dalı bulunamadı — test kapsamı düşmüş"
    atanan = {ast.unparse(h) for m in ast.walk(hedef)
              if isinstance(m, ast.Assign) for h in m.targets}
    for alan in ("base.asama_sureleri", "base.bellek"):
        assert alan in atanan, f"{alan} düşen koşuda kaydedilmiyor"


def test_timeout_donus_kodlari_GERCEK_SISTEMDE_dogrulandi():
    """Kuralın DAYANDIĞI önerme sistemde ölçüldü, varsayılmadı.

    WSL'de koşuldu (2026-08-26):
        timeout -k 10 -s TERM 2 sleep 30                 -> rc 124
        timeout -k 2  -s TERM 2 bash -c 'trap "" TERM…'  -> rc 137
    Yani TERM'e uyan süreç 124, uymayıp KILL'e zorlayan 137 veriyor. İkisi de
    kuralın tanıdığı kodlar.

    ÖNEMLİ NEGATİF BULGU: `timeout` KILL'e yükseldiğinde kabuk stderr'a
    ``Killed  timeout -k …'' basıyor --- AR6 kaydındaki satırın AYNISI. Yani
    O SATIR AYIRT ETMİYOR: aynı çıktı, çocuğu dışarıdan bir SIGKILL öldürüp
    timeout onu yansıttığında da görülür. İlk okumada bu satır ``demek ki
    zaman aşımı'' diye okundu ve YANLIŞTI. Ayırt eden tek şey süredir:
    AR6 1319 s'de düştü, iç eşik 1780 s (aşama tmo'su 1800).

    Bu test o önermeyi kayda geçirir; `_step`in tmo değeri değişirse veya
    sarmalayıcı kaldırılırsa aşağıdaki bağ kopar ve test düşer.
    """
    src = (KOK / "analysis" / "openfoam_runner.py").read_text(encoding="utf-8")
    assert 'f"timeout -k 10 -s TERM {max(tmo - 20, 30)} {command}"' in src, \
        "sarmalayıcı değişti — 124/137 önermesi yeniden ölçülmeli"
    assert '"log.snappyHexMesh", 1800' in src, \
        "snappy tmo'su değişti — AR6 vakasının 1780 s eşiği artık geçerli değil"
    # AR6'nin gercek sayilariyla: 1319 s, esik 1780 -> timeout DEGIL
    assert _kayit(137, 1319.0, tmo=1800)["durum"] == "DISARIDAN OLDURULDU"
