"""Koşu hangi Courant'ta çalıştı — ve beyan edilen sınır uygulanıyor mu?

ÖLÇÜLDÜ (2026-08-24, silindir 3B): `controlDict` `maxCo 2` yazıyor, koşunun
kararlı Courant maksimumu 5,19. Sebep bir YAZIM HATASI: kod
`adjustableTimeStep yes;` yazıyordu, OpenFOAM'ın anahtarı `adjustTimeStep`.
Tanınmayan anahtar sessizce geçiştirilir, varsayılan (`no`) yürürlükte kalır
ve `maxCo` ATIL olur. Log'da tek bir `deltaT = ` satırı yok; 63,4/0,025 tam
olarak adım sayısını veriyor, yani adım hiç uyarlanmadı.

Bu, deponun avladığı sınıfın bir üyesi: DOSYA YAPTIĞINDAN BAŞKA ŞEY SÖYLÜYOR.

Courant ayrıca hiçbir kanıt dosyasına yazılmıyordu. DES çapasının kaydında
`dt_s` var, Courant yok --- zaman-doğru bir koşuda bu, y⁺'ın uzayda olduğu
şeyin zamandaki karşılığıdır ve hiçbir tüketici göremiyordu.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from analysis.openfoam_runner import courant_olc  # noqa: E402


def _vaka(tmp: Path, co: list[float], maxco: str = "2",
          adjust: str | None = None) -> Path:
    (tmp / "system").mkdir(parents=True, exist_ok=True)
    (tmp / "log.foamRun").write_text("\n".join(
        f"Courant Number mean: {c/10:.4f} max: {c:.4f}" for c in co))
    t = f"deltaT          0.025;\nmaxCo           {maxco};\n"
    if adjust is not None:
        t += f"adjustTimeStep  {adjust};\n"
    (tmp / "system" / "controlDict").write_text(t)
    return tmp


def test_BASLANGIC_SICRAMASI_kosunun_courantı_sayilmiyor(tmp_path):
    """İlk adımda alan düzgün-başlangıçtan çözüme geçerken Courant fırlar;
    ölçüldü: 90,7. Bunu 'koşunun Courant'ı' saymak geçiş anına bakmaktır."""
    r = courant_olc(_vaka(tmp_path, [90.0, 80.0, 5.0, 4.9, 5.1, 4.8]))
    assert r["kararli_max"] < 6.0, "başlangıç sıçraması kararlı değere sızıyor"
    assert r["baslangic_sicramasi"] == 90.0


def test_beyan_UYGULANMIYORSA_soyleniyor(tmp_path):
    r = courant_olc(_vaka(tmp_path, [1.0, 5.0, 5.2, 4.8]))
    assert r["beyan_maxCo"] == 2.0
    assert r["adjustTimeStep"] is False
    assert r["beyan_uygulaniyor_mu"] is False
    assert r["asim_katı"] and r["asim_katı"] > 2.0


def test_uyarlama_ACIKSA_asim_bildirilmiyor(tmp_path):
    """`adjustTimeStep yes` ise maxCo gerçekten kapıdır; aşım raporlanmaz."""
    r = courant_olc(_vaka(tmp_path, [1.0, 1.9, 1.8], adjust="yes"))
    assert r["beyan_uygulaniyor_mu"] is True
    assert r["asim_katı"] is None


def test_OLCULEMEDI_sessizce_gecmiyor(tmp_path):
    (tmp_path / "system").mkdir(parents=True)
    r = courant_olc(tmp_path)
    assert r["olculdu"] is False and r["_neden"]
    (tmp_path / "log.foamRun").write_text("Courant yok\n")
    r2 = courant_olc(tmp_path)
    assert r2["olculdu"] is False


def test_YAZICI_dogru_anahtari_yaziyor(tmp_path):
    """`adjustableTimeStep` OpenFOAM anahtarı DEĞİLDİR ve sessizce yutulur.

    ÖLÇÜT DAVRANIŞA BAĞLI, METNE DEĞİL. İlk sürüm kaynakta çıplak dizgi
    arıyordu ve hatayı BELGELEYEN yorumlara takıldı --- yani düzeltmenin
    kaydını kusur sandı. Doğru soru: yazılan dosyada ne var?
    """
    from analysis.openfoam_runner import CFDCase, _write_control_dict
    (tmp_path / "system").mkdir()
    c = CFDCase(name="t", stl_path=str(tmp_path), velocity=1.0,
                transient=True, delta_t=0.01, end_time_s=1.0)
    _write_control_dict(tmp_path, c, "duvar", 1.0)
    t = (tmp_path / "system" / "controlDict").read_text(encoding="utf-8")
    assert "adjustableTimeStep" not in t, (
        "tanınmayan anahtar hâlâ YAZILIYOR — maxCo atıl kalır")
    assert "adjustTimeStep" in t, "davranış dosyada beyan edilmiyor"
    # Yazilan davranis, olceni yaniltmamali
    from analysis.openfoam_runner import courant_olc
    (tmp_path / "log.foamRun").write_text(
        "Courant Number mean: 0.2 max: 3.0\n" * 6)
    assert courant_olc(tmp_path)["beyan_uygulaniyor_mu"] is False


def test_gercek_kosu_beyani_asiyor():
    """Bulgunun dayanağı arşivden okunur; arşiv yoksa iddia da yok."""
    y = KOK / "_silindir_gecis_3b"
    if not (y / "log.foamRun").exists():
        import pytest
        pytest.skip("koşu arşivi yok (gitignore)")
    r = courant_olc(y)
    assert r["olculdu"] and r["beyan_uygulaniyor_mu"] is False
    assert r["kararli_max"] > r["beyan_maxCo"], (
        "beyan aşımı artık yok — bulgunun dayanağı düştü, metin gözden geçirilmeli")
