"""Ön-kontrol, ÇÖZÜCÜNÜN kullandığı yolu denemeli — yoksa yanlış güven verir.

Sabit `wsl` çağrısıyla test eden bir doctor, CFD_BACKEND=docker kullanan mühendise
"ortam hazır" der ve saatlik koşu ilk adımda düşer. Bu testler arka-uç bağını ve
hüküm mantığını çapalar; gerçek WSL/Docker gerektirmez.
"""
import on_kontrol


def test_arka_uc_uzerinden_gecer(monkeypatch):
    """docker arka ucu seçiliyse kontrol docker argv'siyle koşmalı."""
    cagrilar = []

    def sahte_run(cmd, timeout):
        cagrilar.append(cmd)

        class R:
            returncode, stdout, stderr = 0, "hazir", ""
        return R()

    monkeypatch.setenv("CFD_BACKEND", "docker")
    monkeypatch.setattr("analysis.backend.linux_run", sahte_run)
    ks = on_kontrol.kontroller()
    arka = [k for k in ks if k["ad"].startswith("linux arka uç")][0]
    assert "docker" in arka["ad"] and arka["durum"] == "ok"
    assert cagrilar, "arka uç hiç denenmemiş"


def test_arka_uc_yoksa_zorunlu_eksik(monkeypatch):
    def patlat(cmd, timeout):
        raise OSError("wsl yok")

    monkeypatch.setattr("analysis.backend.linux_run", patlat)
    ks = on_kontrol.kontroller()
    arka = [k for k in ks if k["ad"].startswith("linux arka uç")][0]
    assert arka["durum"] == "eksik" and arka["zorunlu"]
    # cozucu araclari denenemedi olarak isaretlenmeli, "yok" degil
    of = [k for k in ks if k["ad"].startswith("OpenFOAM")][0]
    assert "denenemedi" in of["detay"]
    assert "ANALİZ KOŞAMAZ" in on_kontrol.rapor(ks)


def test_yalniz_zorunlu_eksik_cikis_kodunu_bozar():
    ok = [{"ad": "a", "zorunlu": False, "durum": "uyari", "detay": ""}]
    assert "Koşabilir" in on_kontrol.rapor(ok)
    kotu = ok + [{"ad": "b", "zorunlu": True, "durum": "eksik", "detay": ""}]
    assert "ANALİZ KOŞAMAZ" in on_kontrol.rapor(kotu)


def test_tam_ortam_mesaji():
    ks = [{"ad": "a", "zorunlu": True, "durum": "ok", "detay": ""}]
    assert "Ortam tam" in on_kontrol.rapor(ks)


def test_pipeline_doctor_komutu_bagli():
    import inspect

    import pipeline
    src = inspect.getsource(pipeline.main)
    assert '"doctor"' in src and "on_kontrol" in src
    assert "doctor" in pipeline.__doc__
