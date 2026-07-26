"""`fea_runner._parse_frd` — sertifikasyon zincirinin sonuç-okuma yolu.

Bu, kanonik `analysis/frd_parser`'dan AYRI ikinci bir parser'dır (iki-hızlı miras) ve
`pipeline.py fea` → güvenlik faktörü onun üzerinden geçer. Eski golden fixture
(`test_fea_run/sphere_test.frd`) diskte yok ve sadakatle üretilemez; bu testler aynı
yolu SENTETİK ama analitik-bilinen girdiyle çapalar — her koşuda çalışır.
"""
import pytest

from fea_runner import FEASimulationRunner

parse = FEASimulationRunner._parse_frd


def _satir(nid, vals):
    """ccx'in yazdığı biçim: sabit 12 karakter, %12.5E (negatifler bitişik çıkar)."""
    return f" -1{nid:>10}" + "".join(f"{v:12.5E}" for v in vals)


def _frd(yol, disp=None, stress=None, n_dugum=4):
    s = ["    1C", f"    2C{n_dugum:>18}"]
    s += [_satir(i + 1, [i * 0.1, 0.0, 0.0]) for i in range(n_dugum)]   # düğüm koordinatları
    s.append(" -3")
    if disp is not None:
        s += [" -4  DISP        4    1"] + [_satir(n, v) for n, v in disp] + [" -3"]
    if stress is not None:
        s += [" -4  STRESS      6    1"] + [_satir(n, v) for n, v in stress] + [" -3"]
    s.append(" 9999")
    yol.write_text("\n".join(s), encoding="ascii")
    return yol


def test_deplasman_buyuklugu(tmp_path):
    r = parse(_frd(tmp_path / "a.frd",
                   disp=[(1, [0, 0, 0]), (2, [3e-3, 4e-3, 0.0])]))
    assert r["max_displacement_m"] == pytest.approx(5e-3)      # 3-4-5
    assert r["mean_displacement_m"] == pytest.approx(2.5e-3)


def test_von_mises_analitik(tmp_path):
    """Tek-eksen → σ; saf kayma → √3·τ; hidrostatik → 0."""
    r = parse(_frd(tmp_path / "b.frd",
                   stress=[(1, [200e6, 0, 0, 0, 0, 0]),
                           (2, [0, 0, 0, 50e6, 0, 0]),
                           (3, [80e6, 80e6, 80e6, 0, 0, 0])]))
    assert r["max_von_mises_pa"] == pytest.approx(200e6, rel=1e-6)
    assert r["max_von_mises_mpa"] == pytest.approx(200.0, rel=1e-6)


def test_saf_kayma_tepe_olur(tmp_path):
    r = parse(_frd(tmp_path / "c.frd", stress=[(1, [0, 0, 0, 200e6, 0, 0])]))
    assert r["max_von_mises_pa"] == pytest.approx(3 ** 0.5 * 200e6, rel=1e-6)


def test_bitisik_negatif_sayilar_ayrisir(tmp_path):
    """Parser'ın regex kullanmasının BELGELENMİŞ sebebi: ccx sabit-genişlikte negatifi
    bir öncekine bitişik yazar (`0.00000E+00-2.80000E-11`); split() bunu tek token
    yapıp atlar. Bileşen kayması sessizce yanlış von Mises üretir."""
    p = tmp_path / "d.frd"
    p.write_text("\n".join([
        "    1C", "    2C         1", _satir(1, [0.0, 0.0, 0.0]), " -3",
        " -4  STRESS      6    1",
        # negatifler bitişik: -2.8E-11 ve -5.0E+07 öncekine yapışık
        " -1         1 2.00000E+08-2.80000E-11 0.00000E+00-5.00000E+07 0.00000E+00 0.00000E+00",
        " -3", " 9999"]), encoding="ascii")
    r = parse(p)
    s11, s22, s33, s12 = 2.0e8, -2.8e-11, 0.0, -5.0e7
    beklenen = (((s11 - s22) ** 2 + (s22 - s33) ** 2 + (s33 - s11) ** 2
                 + 6 * s12 ** 2) ** 0.5) / 2 ** 0.5
    assert r["max_von_mises_pa"] == pytest.approx(beklenen, rel=1e-9)


def test_eksik_bilesenli_satir_tepe_gerilmeyi_kacirmaz(tmp_path):
    """6'dan az bileşen okunabilen satır sessizce ATLANIR. Bu, tepe gerilmenin
    kaçmasına ve SF'nin olduğundan YÜKSEK çıkmasına (tehlikeli yön) yol açar —
    davranışı dondurup görünür kılıyoruz."""
    p = tmp_path / "e.frd"
    p.write_text("\n".join([
        "    1C", "    2C         2", _satir(1, [0.0, 0.0, 0.0]), " -3",
        " -4  STRESS      6    1",
        " -1         1 5.00000E+07 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00",
        " -1         2 9.90000E+08 0.00000E+00 0.00000E+00",          # bozuk: 3 bileşen
        " -3", " 9999"]), encoding="ascii")
    r = parse(p)
    assert r["max_von_mises_pa"] == pytest.approx(5.0e7, rel=1e-6), \
        "bozuk satır atlanmalı ama sağlam satırların tepe değeri korunmalı"


def test_bos_frd_cokmez(tmp_path):
    p = tmp_path / "f.frd"
    p.write_text("    1C\n 9999\n", encoding="ascii")
    assert isinstance(parse(p), dict)


def test_iki_parser_ayni_von_mises_verir(tmp_path):
    """İki-hızlı miras: fea_runner ve analysis/frd_parser AYNI dosyada aynı hükmü
    vermeli — ayrışırlarsa hangi sayının rapora girdiği belirsizleşir."""
    import numpy as np

    from analysis.frd_parser import parse_frd
    stress = [(i + 1, [150e6, 20e6, 0, 30e6, 0, 0]) for i in range(4)]
    yol = _frd(tmp_path / "g.frd", disp=[(i + 1, [1e-3, 0, 0]) for i in range(4)],
               stress=stress)
    a = parse(yol)["max_von_mises_pa"]
    b = float(np.max(parse_frd(yol).von_mises()))
    assert a == pytest.approx(b, rel=1e-9)
