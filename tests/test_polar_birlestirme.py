"""3B kanat poları — VLM taşıması + 2B kesit sürüklemesi + indüklenen direnç.

NEDEN: ince kanatta 3B viskoz RANS mutlak taşımayı VEREMİYOR (ölçüldü: firar
kenarı 1.3 hücre, hücre 20.6 kat artarken Cl %23 arttı; hedef çözünürlük için
yalnız yüzeyde ~775.000 yüz gerekir). VLM Kutta koşulunu firar kenarında
ANALİTİK dayatır — orada hücre yoktur, tıkanıklık oluşmaz.

Bu modül yeni CFD koşmaz, mevcut kanıtları birleştirir. Ama körlemesine değil:
birleştirme parçalar UYUMLUYSA geçerlidir ve uyumsuzluğu sessizce yutmak bu
depoda avlanan kusurun ta kendisidir.
"""
import polar_birlestirme as pb

_VLM = [{"alpha": 0.0, "Cl": 0.0, "Cd_i": 0.0},
        {"alpha": 4.0, "Cl": 0.2435, "Cd_i": 0.003473},
        {"alpha": 8.0, "Cl": 0.49975, "Cd_i": 0.014698}]
_KESIT = [{"alpha": 0.0, "Cl": 0.0, "Cd": 0.0085},
          {"alpha": 4.0, "Cl": 0.44, "Cd": 0.0092},
          {"alpha": 8.0, "Cl": 0.85, "Cd": 0.0130}]
_UYUMLU = {"re_kanat": 3.4e6, "re_kesit": 3.4e6,
           "kesit_cd_mesh_bagimsiz": True, "kesit_cd_band_pct": 1.71}


def test_UYUMLU_girdide_3B_polar_URETILIYOR():
    """Kapı her zaman reddediyorsa kapı değil, duvardır."""
    o = pb.birlesik_polar(_VLM, _KESIT, **_UYUMLU)
    assert o["engeller"] == []
    n4 = [x for x in o["noktalar"] if x["alpha"] == 4.0][0]
    assert "Cd_toplam" in n4 and "Cd_profil" in n4
    # Cd_toplam = Cd_profil(Cl=0.2435) + CDi
    assert abs(n4["Cd_toplam"] - (n4["Cd_profil"] + n4["CDi"])) < 1e-9
    assert 0.008 < n4["Cd_profil"] < 0.010          # 2B polardan ara değer
    assert "3B polar üretildi" in o["verdikt"]


def test_REYNOLDS_uyusmazligi_MUTLAK_Cd_uretmiyor():
    """ÖLÇÜLDÜ: MiniHawk Re=3.5e5, 2B veri Re=3.4e6 — 9.6 kat, ~%57 sapma."""
    o = pb.birlesik_polar(_VLM, _KESIT, **{**_UYUMLU, "re_kanat": 3.53e5})
    assert any("REYNOLDS" in e for e in o["engeller"])
    assert all("Cd_toplam" not in n for n in o["noktalar"])
    assert all("Cl" in n for n in o["noktalar"])     # TAŞIMA etkilenmez
    assert "YALNIZ TAŞIMA" in o["verdikt"]


def test_mesh_bagimsiz_OLMAYAN_kesitten_mutlak_Cd_yok():
    """gci_airfoil: Cd kaba gridlerde NEGATİF, en incede hâlâ tırmanıyor."""
    o = pb.birlesik_polar(_VLM, _KESIT,
                          **{**_UYUMLU, "kesit_cd_mesh_bagimsiz": False})
    assert any("MESH-BAĞIMSIZ DEĞİL" in e for e in o["engeller"])
    assert all("Cd_toplam" not in n for n in o["noktalar"])


def test_KESIT_TIPI_uyusmazligi_yakalaniyor():
    """Kamburlu 2B + simetrik VLM aynı eğriye ait değil (α_L0 kayması)."""
    o = pb.birlesik_polar(_VLM, _KESIT,
                          **{**_UYUMLU, "kesit_simetrik": False})
    assert any("KESİT TİPİ" in e for e in o["engeller"])


def test_EKSTRAPOLASYON_yok():
    """Cl 2B veri aralığı dışındaysa sayı UYDURULMAZ."""
    vlm = [{"alpha": 20.0, "Cl": 1.60, "Cd_i": 0.10}]
    o = pb.birlesik_polar(vlm, _KESIT, **_UYUMLU)
    n = o["noktalar"][0]
    assert "Cd_toplam" not in n and "DIŞINDA" in n["Cd_notu"]


def test_LINEER_bolge_disi_alfa_isaretleniyor():
    """ÖLÇÜLDÜ: 2B geçiş modeli α=8°'de %7.8, α=10°'de %45 hata veriyor."""
    vlm = _VLM + [{"alpha": 12.0, "Cl": 0.72, "Cd_i": 0.030}]
    o = pb.birlesik_polar(vlm, _KESIT, **_UYUMLU)
    n12 = [x for x in o["noktalar"] if x["alpha"] == 12.0][0]
    assert "uyari" in n12 and "lineer bölge dışında" in n12["uyari"]
    assert all("uyari" not in x for x in o["noktalar"] if x["alpha"] <= 8.0)


def test_TASIMA_BANDI_uydurulmuyor():
    """VLM bu depoda doğrulanmadı; ölçülmüş band YOK denmeli."""
    o = pb.birlesik_polar(_VLM, _KESIT, **_UYUMLU)
    assert any("TAŞIMA BANDI ÖLÇÜLMEMİŞTİR" in u for u in o["uyarilar"])


def test_band_YALNIZ_profil_bileseninden():
    """CDi'nin kendi bandı bilinmiyor; toplam bandı ondan uydurmak yanlış olur."""
    o = pb.birlesik_polar(_VLM, _KESIT, **_UYUMLU)
    n4 = [x for x in o["noktalar"] if x["alpha"] == 4.0][0]
    beklenen = 1.71 * n4["Cd_profil"] / n4["Cd_toplam"]
    assert abs(n4["Cd_band_pct"] - beklenen) < 0.01
    assert n4["Cd_band_pct"] < 1.71                  # CDi bandı seyreltiyor


def test_DEPO_verisi_gercek_hukmu_veriyor():
    """Depodaki gerçek kanıtlarla ne çıkıyorsa O doğrulanır.

    TARİHÇE — engeller sırayla kapandı ve YENİSİ açıldı:
      1. Re uyuşmazlığı (9.6 kat)      → XFOIL kesiti uçuş Re'sinde üretildi
      2. Kesit Cd mesh-bağımsız değil  → panel-bağımsızlık ölçüldü (%0.55)
      3. Profil aracın profili değil   → kesit NACA2412'ye çevrildi
      4. KESİT TİPİ UYUŞMUYOR          → AÇIK: kesit kamburlu, VLM kamburluğu
         KAPALI koşuyor (OpenVSP 3.50.4 kamburlu kesitte yüksek α'da ıraksıyor).

    Test SABİT bir sonuç değil, TUTARLILIK bağlar: engel varsa BİLİNEN engel
    listesinden olmalı ve mutlak Cd yayınlanmamalı; engel yoksa polar tam
    olmalı. Böylece yeni bir engel sessizce eklenemez.
    """
    BILINEN = ("REYNOLDS", "MESH-BAĞIMSIZ", "PROFİL", "KESİT TİPİ")
    d = pb._depo_verisi()
    o = pb.birlesik_polar(
        d["vlm_polar"], d["kesit"], re_kanat=d["re_kanat"],
        re_kesit=d["re_kesit"],
        kesit_cd_mesh_bagimsiz=d["kesit_cd_mesh_bagimsiz"],
        kesit_cd_band_pct=d.get("kesit_cd_band_pct"),
        kesit_profili=d.get("kesit_profili"), arac_profili=d.get("arac_profili"),
        **{k: d[k] for k in ("kesit_simetrik", "vlm_simetrik")
           if d.get(k) is not None})
    for e in o["engeller"]:
        assert any(b in e for b in BILINEN), f"ADI KONMAMIS engel: {e}"
    if o["engeller"]:
        assert all("Cd_toplam" not in n for n in o["noktalar"])
        assert "YALNIZ TAŞIMA" in o["verdikt"]
    else:
        assert all("Cd_toplam" in n for n in o["noktalar"])
        assert "3B polar üretildi" in o["verdikt"]
    # TASIMA her durumda uretilir — engeller yalniz MUTLAK SURUKLEMEYI keser.
    assert all("Cl" in n for n in o["noktalar"])


def test_kesit_kaynagi_HER_ZAMAN_raporlaniyor():
    """Hangi veriyle birleştirdiği görünmezse, band da anlamsız olur."""
    d = pb._depo_verisi()
    assert d.get("kesit_kaynagi")
    assert d.get("re_kesit", 0) > 0


class TestIkiBoyutluBand:
    """2B çalışmada temsili hücre boyu h = N^(-1/2), N^(-1/3) DEĞİL.

    3B formülünü 2B veriye uygulamak SESSİZ bir hatadır: (200,60,100) →
    (260,78,130) ailesinde gerçek h oranı 1.30 iken N^(-1/3) 1.19 verir. Celik'in
    r≥1.3 şartı SAĞLANDIĞI HALDE sağlanmadı görünür, gözlenen mertebe p yanlış
    çıkar ve band şişer.

    ÖLÇÜLDÜ (aynı sentetik veri): boyut=3 → U=%19.92, boyut=2 → U=%9.80. İki kat.
    """

    _C = [32000, 54080, 91260, 154880]
    _CD = [0.0130, 0.0119, 0.0114, 0.0112]

    def test_boyut_bandi_DEGISTIRIYOR(self):
        from report_generator import band_from_levels
        u3 = band_from_levels(self._C, self._CD, boyut=3)["u_pct"]
        u2 = band_from_levels(self._C, self._CD, boyut=2)["u_pct"]
        assert u3 > 1.8 * u2, (u3, u2)

    def test_2B_ailede_oran_sarti_SAGLANIYOR(self):
        r = [(self._C[i + 1] / self._C[i]) ** 0.5 for i in range(3)]
        assert min(r) >= 1.29                       # tasarlanan r≈1.3
        r3 = [(self._C[i + 1] / self._C[i]) ** (1 / 3) for i in range(3)]
        assert max(r3) < 1.3, "3B formülü şartı YANLIŞ ihlal ettiriyor"

    def test_varsayilan_3_KALDI(self):
        """Mevcut 3B çağıranların anlamı değişmemeli."""
        import inspect

        from report_generator import band_from_levels
        assert inspect.signature(band_from_levels).parameters["boyut"].default == 3

    def test_kampanya_2B_bandi_ISTIYOR(self):
        """Kampanya scripti boyut=2 geçmezse bandı iki kat şişirir."""
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / "experiments" / "kesit_re35e4.py"
        if p.exists():
            assert "boyut=2" in p.read_text(encoding="utf-8")


class TestProfilAracinProfiliMi:
    """Kapılar bileşenleri BİRBİRİYLE karşılaştırıyordu, ARAÇLA değil.

    ÖLÇÜLDÜ (MiniHawk): aracın kanadı NACA2412 (kamburlu) iken üretilen XFOIL
    kesiti NACA0012 (simetrik) ve VLM koşusunda kamburluk KAPALI idi. Üç bileşen
    kendi arasında tutarlıydı — `kesit_simetrik == vlm_simetrik` kapısı GEÇİYORDU
    — ama hiçbiri araçla tutarlı değildi. Yayınlanan polar "MiniHawk planformlu
    SİMETRİK kesitli bir kanadın" polarıydı, MiniHawk'ın değil.
    """

    def test_profil_uyusmazligi_MUTLAK_Cd_engelliyor(self):
        o = pb.birlesik_polar(_VLM, _KESIT, **_UYUMLU,
                              kesit_profili="NACA0012", arac_profili="NACA2412")
        assert any("PROFİL ARACIN PROFİLİ DEĞİL" in e for e in o["engeller"])
        assert all("Cd_toplam" not in n for n in o["noktalar"])

    def test_profil_eslesince_engel_YOK(self):
        o = pb.birlesik_polar(_VLM, _KESIT, **_UYUMLU,
                              kesit_profili="NACA2412", arac_profili="NACA2412")
        assert not any("PROFİL" in e for e in o["engeller"])

    def test_engel_metni_COZUMU_soyluyor(self):
        """Gerekçesiz ret eylem üretmez; hangi komutun koşulacağı yazılmalı."""
        o = pb.birlesik_polar(_VLM, _KESIT, **_UYUMLU,
                              kesit_profili="NACA0012", arac_profili="NACA2412")
        e = next(x for x in o["engeller"] if "PROFİL" in x)
        assert "--naca 2412" in e

    def test_simetri_bayragi_VERIDEN_turetiliyor(self):
        """Bayrak çağırana bırakılınca varsayılan ikisi de True idi ve uyumsuzluk
        görünmüyordu. α=0'daki Cl ölçümdür, varsayım değil."""
        kamburlu = [{"alpha": 0.0, "Cl": 0.2279, "Cd": 0.00724},
                    {"alpha": 4.0, "Cl": 0.7044, "Cd": 0.00926}]
        simetrik = [{"alpha": 0.0, "Cl": 0.0, "Cd": 0.00708},
                    {"alpha": 4.0, "Cl": 0.53, "Cd": 0.01013}]
        assert pb._simetrik_mi(kamburlu) is False
        assert pb._simetrik_mi(simetrik) is True
        assert pb._simetrik_mi([{"alpha": 4.0, "Cl": 0.5}]) is None   # α=0 yoksa hüküm YOK

    def test_DEPO_verisi_gercek_profilleri_tasiyor(self):
        from pathlib import Path
        if not (Path(pb.HERE) / "kesit_re35e4.json").exists():
            return
        d = pb._depo_verisi()
        assert d.get("arac_profili"), "aracin profili okunmuyor"
        assert d.get("kesit_profili"), "kesit profili okunmuyor"
