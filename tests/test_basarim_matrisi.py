"""Başarım matrisi ve bellek katsayısı: ölçülene ölçüm, gürültüye gürültü denir.

Matris hücre × çekirdek süresini ölçtü. Aynı koşular bellek de ölçtü — ve
kB/hücre 0,9 ile 9,75 arasında saçıldı (10,4 kat), üstelik dokuz koşunun
dokuzunda da artış gürültü eşiğinin altında kaldı. O yüzden medyan bir merkez
DEĞİLDİR ve katsayı olarak yazılmaz; bellek kapısı öncülle çalışmaya devam eder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from bellek_katsayisi import (  # noqa: E402
    EN_AZ_ARTIS_GB,
    EN_COK_SACILMA,
    calistir,
    topla,
)


def _matris() -> dict:
    p = KOK / "basarim_matrisi.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# ── matris ─────────────────────────────────────────────────────────────────

def test_matris_cozucu_suresini_olcuyor():
    """Telemetride delik vardı: foamRun `_step`'ten geçmediği için EN PAHALI
    aşama kaydedilmiyordu. Matris onu görüyorsa delik kapanmış demektir."""
    d = _matris()
    if not d:
        return
    ok = [x for x in d["satirlar"] if x["durum"] == "ok"]
    assert ok, "matriste tamamlanmış koşu yok"
    assert all(x["cozucu_s"] for x in ok), "çözücü süresi ölçülmemiş"
    for x in ok:
        adlar = [a["asama"] for a in x["asama_sureleri"]]
        assert "foamRun" in adlar, f"{x['etiket']}: foamRun telemetride yok"


def test_hizlanma_IDEALIN_altinda_ve_boyutla_artiyor():
    """Ölçülen gerçek: küçük ağda ayrıştırma yükü baskın. İdeal hızlanma
    iddiası yapılmıyor — bu bir kıyaslama değil, ölçülen eğilim."""
    d = _matris()
    h = (d.get("olcek") or {}).get("cekirdek_hizlanmasi") or {}
    if not h:
        return
    for _butce, kayit in h.items():
        for cek, hiz in kayit.items():
            assert hiz <= int(cek) + 1e-9, "hızlanma ideali AŞAMAZ"
    if len(h) >= 2:
        anahtar = sorted(h, key=lambda k: int(k.rstrip("k")))
        ilk, son = h[anahtar[0]], h[anahtar[-1]]
        if "8" in ilk and "8" in son:
            assert son["8"] > ilk["8"], "hızlanma büyük ağda daha iyi olmalı"


def test_matris_KIYASLAMA_olmadigini_soyluyor():
    d = _matris()
    if not d:
        return
    assert "KIYASLAMA DEGILDIR" in d["_kisit"]
    assert "sirali" in d["kurulum"]


# ── bellek katsayısı: gürültü reddi ────────────────────────────────────────

def test_sacilan_olcum_katsayi_SAYILMAZ():
    rec = calistir()
    if not rec["kosular"]:
        return
    dag = rec["dagilim"]
    if dag["sacilma_katı"] > EN_COK_SACILMA or dag["gurultu_alti_kosu"] == dag["n_kosu"]:
        assert rec["kb_hucre"] is None, "gürültüye katsayı denmiş"
        assert "OLCULEMEDI" in rec["verdikt"]


def test_gurultu_esikleri_kaynakli():
    """Eşikler keyfî olamaz: ikisi de ölçülen saçılmadan türetildi."""
    assert EN_AZ_ARTIS_GB > 0 and EN_COK_SACILMA > 1
    kaynak = (KOK / "experiments" / "bellek_katsayisi.py").read_text(encoding="utf-8")
    assert "0.9 ile 9.75" in kaynak, "eşiğin dayandığı ölçüm yazılı olmalı"


def test_matris_kosulari_katsayi_toplamasina_giriyor():
    """Matris kendi çalışma dizinine yazıyor; `vehicle_runs` taraması onu
    görmezdi ve elimizdeki en kontrollü ölçüm seti dışarıda kalırdı."""
    kayit = topla()
    if not (KOK / "basarim_matrisi.json").exists():
        return
    assert any(k["kosu"].startswith("basarim/") for k in kayit)


def test_katsayi_olculurse_kapi_ONCULU_birakir(tmp_path, monkeypatch):
    """Kural simetrik olmalı: gürültü reddediliyor ama geçerli ölçüm de
    kullanılabilmeli, yoksa kapı sonsuza dek öncülde kalır."""
    import bellek_kapisi as bk
    kanit = tmp_path / "k.json"
    kanit.write_text(json.dumps({"kb_hucre": 1.8, "n_kosu": 6}), encoding="utf-8")
    monkeypatch.setattr(bk, "KANIT", kanit)
    k = bk.katsayi()
    assert k["olculdu"] is True and k["kb_hucre"] == 1.8
