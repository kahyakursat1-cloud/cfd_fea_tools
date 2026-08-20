"""Bellek kapısı: hücre bütçesi artık makinenin belleğinden haberdar.

`max_cells` sabit bir sayıydı (hassas: 2,5 M). 32 GB'lık makinede rahat,
8 GB'likte takas-çilesi ya da OOM; ikisi de aynı preset'i kullanıyordu. Disk
için bekçi vardı (kuyruk, 8 GB), bellek için yoktu.

Kapının tasarım kuralı: katsayı ÖLÇÜLMEDİKÇE öncül kullanılır ve bu her
çıktıda yazılır. Öncül bir tahmindir, sayı gibi davranılmaz — bu yüzden kapı
boru hattında ENGEL değil UYARI üretir.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import bellek_kapisi as bk  # noqa: E402

# ── katsayı: ölçüm mü öncül mü ─────────────────────────────────────────────

def test_kanit_yokken_ONCUL_oldugu_soyleniyor(tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "KANIT", tmp_path / "yok.json")
    k = bk.katsayi()
    assert k["olculdu"] is False
    assert "ÖNCÜL" in k["kaynak"] and "DEĞİLDİR" in k["kaynak"]
    assert k["kb_hucre"] == bk.ONCUL_KB_HUCRE


def test_olculen_katsayi_onculu_devre_disi_birakir(tmp_path, monkeypatch):
    kanit = tmp_path / "bellek_katsayisi.json"
    kanit.write_text(json.dumps({"kb_hucre": 2.4, "n_kosu": 5}), encoding="utf-8")
    monkeypatch.setattr(bk, "KANIT", kanit)
    k = bk.katsayi()
    assert k["olculdu"] is True and k["kb_hucre"] == 2.4
    assert "ölçülen" in k["kaynak"] and "5 koşu" in k["kaynak"]


def test_bos_kanit_onculu_bozmaz(tmp_path, monkeypatch):
    kanit = tmp_path / "k.json"
    kanit.write_text(json.dumps({"kb_hucre": None}), encoding="utf-8")
    monkeypatch.setattr(bk, "KANIT", kanit)
    assert bk.katsayi()["olculdu"] is False


# ── hüküm ───────────────────────────────────────────────────────────────────

def test_sigmayan_butce_reddedilir_ve_SIGACAK_sayi_soylenir():
    h = bk.hukum(20_000_000, bos_gb=4.0)
    assert h["kosulabilir"] is False
    assert 0 < h["onerilen_max_cells"] < 20_000_000
    assert "hücreye" in h["mesaj"]


def test_sigan_butce_gecer():
    h = bk.hukum(300_000, bos_gb=8.0)
    assert h["kosulabilir"] is True


def test_mutlak_taban_altinda_hicbir_kosu_baslamaz():
    h = bk.hukum(1000, bos_gb=0.5)
    assert h["kosulabilir"] is False
    assert "mutlak taban" in h["mesaj"]


def test_bellek_okunamazsa_ENGEL_degil_ama_sessiz_de_degil(monkeypatch):
    monkeypatch.setattr(bk, "bos_bellek_gb", lambda: None)
    h = bk.hukum(500_000)
    assert h["kosulabilir"] is None
    assert "OKUNAMADI" in h["mesaj"]


def test_guvenlik_payi_ham_tahminin_uzerine_biner():
    t = bk.tahmini_gb(1_000_000)
    assert t["gereken_gb"] == pytest.approx(t["ham_gb"] * bk.GUVENLIK_PAYI, rel=1e-3)


def test_tahmin_kaynagi_HER_mesajda_yaziyor():
    """Öncülle üretilmiş bir sayının ölçüm sanılması bu deponun ana kusuru."""
    for cells, bos in ((300_000, 8.0), (20_000_000, 4.0)):
        assert "kaynağı" in bk.hukum(cells, bos_gb=bos)["mesaj"]


# ── tüketiciler ────────────────────────────────────────────────────────────

def test_boru_hatti_kapiyi_GERCEKTEN_cagiriyor():
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    assert "from bellek_kapisi import hukum" in src
    i = src.index("_bellek = _bellek_hukmu(")
    assert "kurulum_uyarilari.append" in src[i:i + 400]


def test_kuyruk_bellek_kotasi_isi_BEKLETIR_hata_yapmaz(tmp_path, monkeypatch):
    import kuyruk
    monkeypatch.setattr(kuyruk, "KUYRUK", tmp_path / "q.jsonl")
    monkeypatch.setattr(kuyruk, "KILIT", tmp_path / "q.lock")
    monkeypatch.setattr(kuyruk.bellek_kapisi, "bos_bellek_gb", lambda: 0.5)
    kuyruk.ekle({"stl_path": "a.stl", "vehicle_type": "ucak", "velocity": 15.0})
    kosulan = []
    ozet = kuyruk.calis(runner=lambda p: kosulan.append(p) or {"status": "ok"})
    assert kosulan == [], "bellek dolu iken iş koşulmamalı"
    assert ozet["bekletildi_bellek"] == 1
    # HATA DEGIL: bellek bosalinca ayni kuyruk onu kosar
    kayit = kuyruk.listele()[0]
    assert kayit["durum"] == "bekliyor"
    assert "BEKLİYOR" in kayit["bellek_notu"]


def test_bellek_bosalinca_ayni_is_kosar(tmp_path, monkeypatch):
    import kuyruk
    monkeypatch.setattr(kuyruk, "KUYRUK", tmp_path / "q.jsonl")
    monkeypatch.setattr(kuyruk, "KILIT", tmp_path / "q.lock")
    kuyruk.ekle({"stl_path": "a.stl", "vehicle_type": "ucak", "velocity": 15.0})
    monkeypatch.setattr(kuyruk.bellek_kapisi, "bos_bellek_gb", lambda: 0.5)
    kuyruk.calis(runner=lambda p: {"status": "ok"})
    monkeypatch.setattr(kuyruk.bellek_kapisi, "bos_bellek_gb", lambda: 32.0)
    kosulan = []
    kuyruk.calis(runner=lambda p: kosulan.append(p) or {"status": "ok"})
    assert len(kosulan) == 1
    assert kuyruk.listele()[0]["durum"] == "bitti"


# ── telemetri: katsayının ölçülebilir olması ───────────────────────────────

def test_cozucu_bellek_alani_tasiyor():
    from analysis.openfoam_runner import CFDResult
    assert "bellek" in CFDResult.__dataclass_fields__
    src = (KOK / "analysis" / "openfoam_runner.py").read_text(encoding="utf-8")
    assert "_bellek_gb()" in src
    assert "artis_gb" in src, "taban-üstü ARTIŞ raporlanmalı, ham kullanım değil"


def test_katsayi_olcumu_kosu_yokken_UYDURMAZ():
    sys.path.insert(0, str(KOK / "experiments"))
    from bellek_katsayisi import calistir
    rec = calistir()
    if rec["kb_hucre"] is None:
        assert "OLCULEMEDI" in rec["verdikt"]
    else:
        assert rec["n_kosu"] >= 1 and rec["kb_hucre"] > 0


def test_SIGAR_hukmu_KAPSAMINI_soyluyor():
    """"Sığar" hangi aşama için geçerli? Söylenmezse okuyucu tümü sanar.

    ÖLÇÜLDÜ (2026-08-19, AR6 çapası 4. deneme): kapı "6.000.000 hücre
    ~6,07 GB; boş 7,9 GB — sığar" dedi ve snappyHexMesh 1319 saniye sonra
    SIGKILL ile öldürüldü (çıkış 137), KATMAN ekleme adımında
    (displacementMedialAxis). Hüküm yanlıştı.

    KÖK NEDEN AŞAMA KÖRLÜĞÜ: katsayı ÇÖZÜM koşularından türetildi
    (basarim/b60k_c*, 0,779 kB/hücre + 0,215 GB, R²=0,96) ve çözücünün
    belleğini ölçüyor. snappy'nin katman adımı bambaşka bir tepe yapar;
    medial-axis geçici veri yapıları son hücre sayısıyla orantılı DEĞİL.

    Snappy için bir katsayı UYDURULMADI — ölçülmedi. Yapılan tek şey hükmün
    kapsamını beyan etmek.
    """
    from bellek_kapisi import hukum
    h = hukum(1000, bos_gb=100.0)          # rahatça sığan bir vaka
    assert h["kosulabilir"] is True
    assert h.get("kapsam") == "ÇÖZÜM aşaması"
    assert "snappyHexMesh" in (h.get("kapsanmayan") or ""), (
        "kapsanmayan aşama adıyla yazılmıyor")
    assert "UYARI" in h["mesaj"] and "OOM" in h["mesaj"], (
        "mesaj okuyucuya meshleme riskini söylemiyor")


def test_SIGMAZ_hukmu_bozulmadi():
    """Kapsam beyanı yalnız 'sığar' tarafında; ret hükümleri değişmemeli."""
    from bellek_kapisi import hukum
    h = hukum(10_000_000_000, bos_gb=8.0)
    assert h["kosulabilir"] is False
    assert "onerilen_max_cells" in h
