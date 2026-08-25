"""Zincir doğru soruyu mu soruyor? — yanlış bir "geçti" 16 saat harcatır.

Sonda, üç açıklama arka arkaya düştükten sonra kuruldu: tam koşu ölçülen
hızla ~16 saat (13,0 s/adım × 4400 adım) ve dördüncü açıklamanın da düşme
ihtimali gerçek. Zincirin işi o kararı bir insanın "galiba yeterli"sine
değil `gammaInt`in ölçülen minimumuna bağlamak.

Bu testler zinciri KOŞMADAN sınar: karar fonksiyonu saf, girdisi bir kanıt
dosyası.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

import gecis_zinciri as z  # noqa: E402


def _kanit(tmp_path: Path, devreye_girdi, mn=0.02, lam=3.1) -> Path:
    p = tmp_path / "sonda.json"
    p.write_text(json.dumps({
        "aralik_denetimi": {"devreye_girdi": devreye_girdi, "min": mn,
                            "laminer_hucre_orani_pct": lam},
        "verdikt": "sonda hükmü"}, ensure_ascii=False), encoding="utf-8")
    return p


def test_devreye_girmeyen_sonda_GECMEZ(tmp_path, monkeypatch):
    monkeypatch.setattr(z, "SONDA_KANIT", _kanit(tmp_path, False, 0.9872, 0.0))
    s = z.sonda_hukmu()
    assert s["gecti"] is False, "devreye girmeyen sonda tam koşuyu tetikliyor"


def test_devreye_giren_sonda_GECER(tmp_path, monkeypatch):
    monkeypatch.setattr(z, "SONDA_KANIT", _kanit(tmp_path, True))
    assert z.sonda_hukmu()["gecti"] is True


def test_OLCULEMEDI_gecti_sayilmiyor(tmp_path, monkeypatch):
    """Yokluk 'geçti' değildir — alan okunamadıysa karar YOK demektir."""
    monkeypatch.setattr(z, "SONDA_KANIT", _kanit(tmp_path, None))
    assert z.sonda_hukmu()["gecti"] is False
    p = tmp_path / "bos.json"
    p.write_text(json.dumps({"verdikt": "x"}), encoding="utf-8")
    monkeypatch.setattr(z, "SONDA_KANIT", p)
    assert z.sonda_hukmu()["gecti"] is False


def test_sonda_bitmediyse_KARAR_YOK(tmp_path, monkeypatch):
    monkeypatch.setattr(z, "SONDA_KANIT", tmp_path / "yok.json")
    assert z.sonda_hukmu() is None, "olmayan kanıttan hüküm çıkıyor"


def test_zincir_dosya_adlari_BETIKLE_TUTARLI():
    """Zincir yanlış dosyayı beklerse sonsuza kadar bekler ya da boş karar
    verir. Adlar betiğin kendi etiket kuralından türemeli."""
    src = (KOK / "experiments" / "silindir_gecis_3b.py").read_text(encoding="utf-8")
    assert 'f"_silindir_gecis_3b{etiket}"' in src
    assert 'f"silindir_gecis_3b{ti_ad}.json"' in src
    # --ag des --sonda 3 -> "_dr_des_sonda3";  --ag des -> "_dr_des"
    assert z.SONDA_KANIT.name == "silindir_gecis_3b_dr_des_sonda3.json"
    assert z.TAM_KANIT.name == "silindir_gecis_3b_dr_des.json"


def test_BELLEK_kapisi_var():
    """2,43 M hücrelik vaka RAM'i %92'ye çıkarıyor (ölçüldü). Sonda belleği
    bırakmadan tam koşuyu başlatmak ikisini de riske atar."""
    assert z.BELLEK_TAVANI_PCT <= 80.0
    src = (KOK / "experiments" / "gecis_zinciri.py").read_text(encoding="utf-8")
    i = src.index("TAM KOŞU BAŞLATILIYOR")
    assert "BELLEK_TAVANI_PCT" in src[:i], "bellek kapısı başlatmadan önce değil"


def test_bitmis_tam_kosu_TEKRARLANMIYOR(tmp_path, monkeypatch):
    """Zincir yeniden çalıştırılabilir olmalı: bitmiş koşuyu baştan almamalı."""
    p = tmp_path / "tam.json"
    p.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(z, "TAM_KANIT", p)
    assert z.main() == 0
