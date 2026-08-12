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
    EN_AZ_R2,
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
    """Gürültüye katsayı denmemeli — ama ÖLÇÜT artık oran-saçılması değil.

    Bu test önce "saçılma büyükse sayı yazılmasın" diyordu. Regresyon
    eklendikten sonra bu varsayım geçersiz: oran (artış/hücre) dağılımının
    saçılması EĞİMİ geçersiz kılmaz --- regresyonun var oluş nedeni tam olarak
    o saçılmanın sabit yükten geldiğini göstermekti. Korunması gereken kural
    şu: yayımlanan sayı ya doğrusal uyumdan gelir (ve uyum eşiği geçer) ya da
    hiç yazılmaz.
    """
    rec = calistir()
    if not rec["kosular"]:
        return
    dag = rec["dagilim"]
    if rec.get("kb_hucre") is None:
        assert "OLCULEMEDI" in rec["verdikt"]
        return
    reg = rec.get("regresyon")
    assert reg is not None, "sayı var ama regresyon yok — nereden geldi?"
    assert rec["kb_hucre"] == reg["kb_hucre"], "yayımlanan sayı eğim değil"
    assert reg["r2"] >= EN_AZ_R2, reg
    # Oran-medyani bilerek KULLANILMADI ve bu verdiktte yazili olmali.
    assert "Medyan-oran modeli" in rec["verdikt"]
    assert dag["sacilma_katı"] > 0


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


# ── raporun tablosu ölçüme bağlı mı ────────────────────────────────────────

RAPOR = KOK / "docs" / "teknik_rapor.tex"
KAYNAK = {"küp": KOK / "basarim_matrisi.json",
          "MiniHawk": KOK / "basarim_matrisi_minihawk.json"}


def _rapor_satirlari() -> list[dict]:
    """Rapordaki hızlanma tablosunu METİNDEN okur (kopyasını değil)."""
    import re
    if not RAPOR.exists():
        return []
    desen = re.compile(
        r"^(küp|MiniHawk) & ([\d.]+) & ([\d{},]+) s"
        r" & ([\d{},]+) s \(([\d{},]+)\$\\times\$\)"
        r" & ([\d{},]+) s \(([\d{},]+)\$\\times\$\)")
    out = []
    for satir in RAPOR.read_text(encoding="utf-8").splitlines():
        m = desen.match(satir.strip())
        if m:
            out.append({
                "govde": m.group(1),
                "hucre": int(m.group(2).replace(".", "")),
                "s1": float(m.group(3).replace("{,}", ".")),
                "s4": float(m.group(4).replace("{,}", ".")),
                "h4": float(m.group(5).replace("{,}", ".")),
                "s8": float(m.group(6).replace("{,}", ".")),
                "h8": float(m.group(7).replace("{,}", ".")),
            })
    return out


def test_rapor_hizlanma_tablosu_OLCUMLE_uyusuyor():
    """Tablo elle yazılmış 12 sayı taşıyor; verinin değişmesi onu bozmalı.

    Bu deponun tekrar tekrar bulduğu kusur sınıfı 'metin sabit, veri değişti'.
    Hızlanmalar ExecutionTime'dan gelir --- aşama duvar süresinden DEĞİL; ilk
    sürüm o hatayı yapmış ve 1,96x yayımlamıştı, doğrusu 3,10x.
    """
    satirlar = _rapor_satirlari()
    if not satirlar:
        return
    veri = {}
    for ad, p in KAYNAK.items():
        if not p.exists():
            continue
        for s in json.loads(p.read_text(encoding="utf-8"))["satirlar"]:
            if s["durum"] == "ok" and s.get("cozucu_exec_s"):
                veri[(ad, s["cells"], s["cekirdek"])] = s["cozucu_exec_s"]
    if not veri:
        return
    assert len(satirlar) == 6, f"tabloda 6 satır beklenir, {len(satirlar)} var"
    for r in satirlar:
        t1 = veri.get((r["govde"], r["hucre"], 1))
        assert t1, f"{r['govde']} {r['hucre']}: 1-çekirdek ölçümü YOK"
        for c, sure, hiz in ((4, r["s4"], r["h4"]), (8, r["s8"], r["h8"])):
            olculen = veri.get((r["govde"], r["hucre"], c))
            assert olculen, f"{r['govde']} {r['hucre']} c{c}: ölçüm YOK"
            assert abs(olculen - sure) <= 0.06 * max(sure, 1), (
                f"{r['govde']} {r['hucre']} c{c}: rapor {sure}s, ölçüm {olculen}s")
            assert abs(t1 / olculen - hiz) <= 0.02, (
                f"{r['govde']} {r['hucre']} c{c}: rapor {hiz}x, "
                f"ölçüm {t1 / olculen:.2f}x")


def test_geometri_bagimliligi_ONCEDEN_sabitlenmis():
    """İddialar ölçümden sonra seçilirse 'sınama' değil, süsleme olur."""
    p = KOK / "basarim_geometri_bagimliligi.json"
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    iddia = d["_onceden_sabitlenen_iddia"]
    assert {"I1", "I2", "I3"} <= set(iddia), iddia
    kaynak = (KOK / "experiments" / "basarim_geometri_bagimliligi.py").read_text(
        encoding="utf-8")
    for k in ("İ1", "İ2", "İ3"):
        assert k in kaynak.split('"""')[1], f"{k} docstring'de sabitlenmemiş"
    assert d["_kisit"].count("TEK MAKINE"), "makine kısıtı düşmüş olamaz"


def test_iki_govde_de_olculmus():
    """Geometri sınırının kapandığı iddiası TEK gövdeyle savunulamaz."""
    p = KOK / "basarim_geometri_bagimliligi.json"
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    olculen = [g for g in d["geometriler"] if g.get("butce_sayisi")]
    assert len(olculen) >= 2, "tek gövdeyle geometri bağımsızlığı iddia edilemez"
    for g in olculen:
        assert g["I1_idealin_altinda"] is True, g
