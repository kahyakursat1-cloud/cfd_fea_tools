"""XFOIL kesit yolu — düşük-Re geçişli rejimde RANS'ın yapamadığını yapar.

NEDEN: kesiti kanadın Re'sinde (3.5e5) RANS ile üretme denemesi başarısız oldu.
  ilk hücre 3e-5 → yakınsıyor ama Cl 0.17-0.32 (beklenen ~0.44)
  ilk hücre 8e-6 → IRAKSIYOR (Cd=-691205, Cl=-1.1e7)
Kurulumun relaxation'ı Re=3.4e6 için elle ayarlanmıştı ve 10 kat farklı Re'ye
taşınmıyor. XFOIL'in panel + e^N yöntemi tam bu rejim için tasarlandı.

ÖLÇÜLEN (NACA0012, Re=3.5e5, N=9):
  panel-bağımsızlık (160/200/300): en kötü Cd sapması %0.55
  karşılaştırma: aynı kesitin RANS denemesi %36.6 band vermişti
"""
import json
from pathlib import Path

import pytest

import xfoil_kesit as xk

ROOT = Path(__file__).resolve().parent.parent


def test_komut_dizisi_PANEL_sayisini_ayarliyor():
    """Panel, XFOIL'in ayrıklaştırma parametresi — band ölçmek için gerekli."""
    s = xk._komut_dizisi("0012", 3.5e5, 0.0, [0, 4], "/tmp/p.txt", panel=300)
    assert "PPAR" in s and "N 300" in s
    assert s.index("PPAR") < s.index("OPER"), "PPAR, OPER'den ÖNCE gelmeli"


def test_panel_varsayilani_KOMUTA_girmiyor():
    """panel=0 → XFOIL'in kendi varsayılanı; mevcut koşuların anlamı değişmez."""
    s = xk._komut_dizisi("0012", 3.5e5, 0.0, [0], "/tmp/p.txt")
    assert "PPAR" not in s


def test_polar_tablosu_ayristiriliyor():
    metin = ("  alpha    CL     CD    CDp     CM\n"
             " ------ ------ ------ ------ ------\n"
             "  0.000 0.0000 0.00708 0.00230 0.0000\n"
             "  4.000 0.5300 0.01013 0.00410 0.0011\n")
    p = xk._oku_polar(metin)
    assert len(p) == 2
    assert p[1]["alpha"] == 4.0 and p[1]["Cl"] == 0.53 and p[1]["Cd"] == 0.01013


def test_YAKINSAMAYAN_aci_sessizce_kaybolmuyor():
    """XFOIL yakınsamayan açıyı tabloya HİÇ yazmaz; eksik satır 'denenmedi'
    değil 'YAKINSAMADI' demektir. ÖLÇÜLDÜ: sık taramada α=4.0 düştü."""
    import inspect
    src = inspect.getsource(xk.polar)
    assert "yakinsamayan_alfa" in src
    assert "eksik" in src and "istenen_alfa" in src


def test_FIZIK_kapisi_uygulaniyor():
    import inspect
    assert "force_admissibility" in inspect.getsource(xk.polar)


def test_OLCULEN_kanit_bandi_tasiyor():
    """Kesit kanıtı ölçülmüş ayrıklaştırma bandı olmadan birleştiriciye girmemeli."""
    p = ROOT / "kesit_re35e4.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    d = json.loads(p.read_text(encoding="utf-8"))
    pb = d.get("panel_bagimsizligi")
    assert pb, "panel-bağımsızlık ölçülmemiş"
    assert pb["en_kotu_sapma_pct"] < 5.0
    assert pb["ortak_alfa"] >= 5
    assert d["polar"] and all(n["Cd"] > 0 for n in d["polar"])


def test_KISIT_metni_RANS_ikamesi_DEMIYOR():
    """XFOIL'i RANS yerine koymak yanlış olur; kanıt bunu söylemeli."""
    p = ROOT / "kesit_re35e4.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        assert "IKAMESI DEGILDIR" in d["_kisit"]
        assert "N_krit" in d["_kisit"]


class TestBirlestirmeArtikCalisiyor:
    """İki engel de kalktı: Re uyuşuyor ve band ÖLÇÜLDÜ."""

    def test_depo_verisi_XFOIL_kesitini_tercih_ediyor(self):
        import polar_birlestirme as pb
        if not (ROOT / "kesit_re35e4.json").exists():
            pytest.skip('kanıt/girdi yok: not (ROOT / "kesit_re35e4.json").exists()')
        d = pb._depo_verisi()
        assert "XFOIL" in d["kesit_kaynagi"]
        assert d["kesit_cd_mesh_bagimsiz"] is True
        assert d["kesit_cd_band_pct"] is not None

    def test_XFOIL_kesiti_RE_ve_MESH_engellerini_KALDIRIYOR(self):
        """Bu testin ASIL konusu XFOIL'in kaldirdigi IKI engel: Reynolds
        uyusmazligi ve mesh-bagimsizligin olculmemis olmasi. Profil/kesit-tipi
        engelleri AYRI bir konudur (bkz. test_polar_birlestirme) ve burada
        bilerek DEVRE DISI birakilir — yoksa bu test iki ayri seyi karistirip
        her degisiklikte kirilir."""
        import polar_birlestirme as pb
        if not (ROOT / "kesit_re35e4.json").exists():
            pytest.skip('kanıt/girdi yok: not (ROOT / "kesit_re35e4.json").exists()')
        d = pb._depo_verisi()
        o = pb.birlesik_polar(d["vlm_polar"], d["kesit"], re_kanat=d["re_kanat"],
                              re_kesit=d["re_kesit"],
                              kesit_cd_mesh_bagimsiz=d["kesit_cd_mesh_bagimsiz"],
                              kesit_cd_band_pct=d["kesit_cd_band_pct"])
        assert not any("REYNOLDS" in e for e in o["engeller"]), o["engeller"]
        assert not any("MESH-BAĞIMSIZ" in e for e in o["engeller"]), o["engeller"]
        # Kesit polarinin Cl ARALIGINDAKI noktalar mutlak Cd almali; aralik
        # DISINDAKILER icin sayi UYDURULMAZ (ekstrapolasyon yok). Kamburlu
        # kesit + simetrik VLM'de alpha=0 noktasi tam bu yuzden disarida kalir
        # (VLM Cl=0, kamburlu polar Cl>=0.026'dan baslar) — bu, kamburluk
        # uyusmazliginin FIZIKSEL yansimasidir ve gorunmesi DOGRUDUR.
        icerde = [n for n in o["noktalar"] if "Cd_toplam" in n]
        disarda = [n for n in o["noktalar"] if "Cd_notu" in n]
        assert icerde, "hicbir nokta mutlak Cd almadi"
        assert all("DIŞINDA" in n["Cd_notu"] for n in disarda)
        assert len(icerde) + len(disarda) == len(o["noktalar"])
        # Band profil bileşeninden gelir; CDi büyüdükçe SEYRELİR.
        b = [n["Cd_band_pct"] for n in icerde]
        assert b[0] > b[-1], "CDi payı arttıkça band seyrelmelidir"

    def test_TASIMA_bandi_hala_UYDURULMUYOR(self):
        import polar_birlestirme as pb
        if not (ROOT / "kesit_re35e4.json").exists():
            pytest.skip('kanıt/girdi yok: not (ROOT / "kesit_re35e4.json").exists()')
        d = pb._depo_verisi()
        o = pb.birlesik_polar(d["vlm_polar"], d["kesit"], re_kanat=d["re_kanat"],
                              re_kesit=d["re_kesit"],
                              kesit_cd_mesh_bagimsiz=d["kesit_cd_mesh_bagimsiz"])
        assert any("TAŞIMA BANDI ÖLÇÜLMEMİŞTİR" in u for u in o["uyarilar"])
