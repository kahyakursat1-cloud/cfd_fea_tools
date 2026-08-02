"""Rezidüel PLATOSU: "bütçe yetmedi" ile "limit çevrimi" ayrı dertlerdir.

Kapı yalnız SON rezidüeli hedefle kıyaslıyor ve reddedince "rezidueller hedefin
üzerinde" diyordu. Bu mesaj YANLIŞ ÇÖZÜME yönlendirir — okuyan "daha uzun
koşayım" diye anlar. Oysa düşüş DURMUŞSA daha fazla iterasyon hiçbir şey
değiştirmez.

ÖLÇÜLDÜ (Ahmed 25° çapası, 800 iterasyon, gerçek log.foamRun):
  Uy dilim ortalamaları  2.99e-3 → 1.62e-3 → 1.69e-3 → 1.67e-3
  p                      1.64e-3 → 8.71e-4 → 9.41e-4 → 9.71e-4
Son ~200 iterasyonda düşüş durmuş, p hafif YÜKSELMİŞ: kararlı RANS'ın bu akışta
sabit noktası yok.
"""
import vehicle_pipeline as vp


def _dusen(n=400, bas=1e-2, kat=0.99):
    return [bas * kat ** i for i in range(n)]


def _plato(n=400, deger=1.6e-3):
    return [deger * (1 + 0.02 * (i % 7 - 3)) for i in range(n)]


def test_DUSEN_seri_plato_sayilmiyor():
    r = vp.rezidual_platosu({"Ux": _dusen(), "p": _dusen()})
    assert r["plato"] is False
    assert all(v < vp.PLATO_ORANI for v in r["oranlar"].values())


def test_DUZLESEN_seri_plato():
    r = vp.rezidual_platosu({"Ux": _plato(), "p": _plato()})
    assert r["plato"] is True
    assert all(v >= vp.PLATO_ORANI for v in r["oranlar"].values())


def test_COGUNLUK_kurali_tek_alana_bakmiyor():
    """p oturmuşken Uy hâlâ düşüyor olabilir; tek alana bakmak yanıltır."""
    r = vp.rezidual_platosu({"Ux": _dusen(), "Uy": _dusen(), "p": _plato()})
    assert r["plato"] is False                      # 1/3 plato → çoğunluk değil
    r2 = vp.rezidual_platosu({"Ux": _plato(), "Uy": _plato(), "p": _dusen()})
    assert r2["plato"] is True                      # 2/3 plato


def test_kisa_seri_plato_IDDIA_ETMIYOR():
    """İki dilim çıkmıyorsa ölçüm yok; 'plato' demek kanıtsız olurdu."""
    r = vp.rezidual_platosu({"Ux": [1e-3, 9e-4, 8e-4]})
    assert r["plato"] is False and r["oranlar"] == {}


def test_momentum_disi_alanlar_sayilmiyor():
    r = vp.rezidual_platosu({"k": _plato(), "omega": _plato()})
    assert r["oranlar"] == {}


def test_RET_GEREKCESI_dogru_cozume_yonlendiriyor():
    # iterasyon < QOI_MUAFIYET_MIN_ITER: durağanlık muafiyeti devreye girmesin,
    # rezidüel mesajı görünsün (muafiyet ayrı bir testin konusu).
    ortak = {"drift_ok": True, "cd_drift_son20pct": 0.1, "iterasyon": 150,
             "rezidual_ok": False, "son_rezidualler": {"Uy": "1.67e-03"},
             "salinim": {"osilasyon": False}}
    _, neden = vp.seviye_yakinsadi_mi(
        {**ortak, "rezidual_platosu": {"plato": True, "oranlar": {"Uy": 0.99}}})
    assert "PLATOYA OTURDU" in neden and "DAHA COK ITERASYON COZMEZ" in neden
    assert "URANS" in neden

    _, neden2 = vp.seviye_yakinsadi_mi(
        {**ortak, "rezidual_platosu": {"plato": False, "oranlar": {"Uy": 0.4}}})
    assert "dusus SURUYOR" in neden2 and "butcesi yetersiz" in neden2


def test_teshis_platoyu_TASIYOR():
    """Ölçülüp taşınmazsa kapı yine eski mesajı verir (bu oturumun deseni)."""
    import inspect
    src = inspect.getsource(vp.yakinsama_teshisi)
    assert '"rezidual_platosu": rezidual_platosu(residuals)' in src
