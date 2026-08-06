"""3B kanat poları — VLM taşıması + 2B kesit sürüklemesi + indüklenen direnç.

NEDEN BU YOL: ince kanatta 3B viskoz RANS mutlak taşımayı VEREMİYOR. Ölçüldü
(NACA0012 AR6 çapası, 2026-08-02): firar kenarı 1.3 hücre, hücre 20.6 KAT
artarken Cl yalnız %23 arttı (0.0572 → 0.0705, beklenen 0.329). Taşıma
sirkülasyondan, sirkülasyon Kutta koşulundan doğar; RANS o koşulu ağla kurar ve
bir hücrelik firar kenarında kuramaz. Hedef ≥6 hücre için yalnız yüzeyde
~775.000 yüz gerekir — bu donanımda çözülemez.

VLM/panel yöntemi Kutta koşulunu firar kenarında ANALİTİK dayatır; orada hücre
yoktur, dolayısıyla bu tıkanıklık VLM'de hiç oluşmaz. Havacılıkta ön-tasarımın
standart iş bölümü budur:

    Cl_3B(α)  ← VLM (sonlu-kanat düzeltmesi zaten içinde)
    Cd_3B(α)  = Cd_profil(Cl) [2B viskoz] + CDi [KURAM] + Δ_entegrasyon [3B RANS]

CDi NEDEN VLM'DEN DEĞİL: VSPAERO iki indüklenen direnç veriyor ve ölçüldü ki
İKİSİ DE taşıyıcı-çizgi kuramından sapıyor (AR=5, α=4):
    taper   kuram   yakın-alan      Trefftz
     1.00   0.963   0.807 (−16%)   1.032  (+7%)
     0.70   0.982   0.792 (−19%)   1.268 (+29%)
     0.50   0.991   0.787 (−21%)   1.601 (+62%)
Trefftz değeri e>1 ile Munk sınırını ihlal ediyor ve sapma taper'la büyüyor.
İkisi arasından seçim keyfî olurdu; CDi doğrulanmış kuramdan üretilir
(`lifting_line`, eliptik planformda e=1.00000 ile kendini doğrular). Kuram bu
planformda geçerli değilse (düşük AR, büyük ok açısı) VLM'in sayısına DÜŞÜLÜR
ve kapılar o zaman ENGEL olur — sessiz geri düşüş yok.

BU MODÜL YENİ CFD KOŞMAZ; mevcut kanıtları birleştirir. Ama körlemesine
birleştirmez — birleştirme ancak parçalar UYUMLUYSA geçerlidir ve uyumsuzluğu
sessizce yutmak, bu depoda avlanan kusurun ta kendisidir. Kapılar:

  1. KESİT TİPİ    simetrik/kamburlu tutarlılığı (α_L0 kayması)
  2. REYNOLDS      kesit verisi kanadın Re'sinde mi (Cd0 ~ Re^-0.2 ile ölçeklenir)
  3. MESH-BAĞIMSIZ kesit Cd'si yakınsamış mı — değilse MUTLAK Cd üretilmez
  4. α ÖRTÜŞMESİ   ekstrapolasyon yok
  5. LİNEER BÖLGE  2B geçiş modeli α≥10°'de bozuluyor (ölçüldü: Cl hatası %45)
  6. PROFİL EŞLEŞMESİ kesit verisi ARACIN profiline mi ait
  7. SPAN VERİMİ   VLM'in CDi'si Munk sınırını (e≤1) aşıyor mu — ölçüldü ki
                   sivriltilmiş kanatta aşıyor (taper 0.7 → e=1.268)

CLI:  python polar_birlestirme.py            (depodaki kanıtlarla dener)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Kesit verisi kanadın Re'sinden bu katsayıdan fazla ayrılırsa MUTLAK sürükleme
# üretilmez. Türbülanslı sürtünme Cd ~ Re^-0.2; 2 kat Re farkı ~%15 Cd farkı
# demektir ve bu, kesit bandının kendisiyle aynı mertebeye çıkar.
RE_TOLERANS = 2.0
# 2B geçiş modelinin güvenilir olduğu üst sınır — ÖLÇÜLDÜ (transition_results):
# α=8°'de Cl hatası %7.8, α=10°'de %45. Aradaki fark model bozulmasıdır.
LINEER_ALFA_MAX = 8.0


# alpha=0'da |Cl| bu esigin ustundeyse kesit KAMBURLU sayilir. Simetrik profil
# alpha=0'da tam sifir verir; sayisal gurultu bu esigin cok altindadir.
KAMBUR_ESIGI = 0.02

# Span verimi e = Cl²/(π·AR·CDi). Düzlemsel kanatta e ≤ 1 MATEMATİKSEL sınırdır
# (Munk); eliptik yükleme üst sınırdır, aşılamaz.
E_UST_SINIR = 1.0
# Engel eşiği sınırın kendisi DEĞİL, çünkü ölçüldü ki VLM temiz dikdörtgen
# kanatta bile e=1.032 veriyor ve bu fazlalık panel inceltmesiyle AZALIYOR
# (28 panel 1.100 → 80 panel 1.032, bkz. vlm_taper_capa). O mertebe ayrıklaştırma
# kaymasıdır. Taper etkisi FARKLI mertebede ve inceltmeyle kapanmıyor
# (taper 0.7 → 1.268, taper 0.5 → 1.601). Eşik ikisini ayırır.
E_ENGEL_ESIGI = 1.05


# Taşıma eğiminin kuramdan sapma eşikleri. VLM'in KENDİ model-form payı ÖLÇÜLDÜ:
# çıplak kanatta −%10 (kalınlık + sonlu panel). Uyarı eşiği onun hemen üstünde,
# engel eşiği ise gövdenin getirdiği −%40/−%54 mertebesinin altındadır — ikisini
# AYIRIR.
EGIM_UYARI_PCT = 12.0
EGIM_ENGEL_PCT = 20.0


def _vlm_egimi(polar: list[dict]) -> float | None:
    """Lineer bölgedeki (α ≤ LINEER_ALFA_MAX) Cl-α eğimi, 1/derece.

    En az iki nokta gerekir; uçlardan alınır çünkü aradaki eğrilik zaten
    lineer bölge sınırıyla dışlanmıştır.
    """
    n = sorted((p for p in polar
                if p.get("Cl") is not None
                and abs(float(p["alpha"])) <= LINEER_ALFA_MAX),
               key=lambda p: float(p["alpha"]))
    if len(n) < 2:
        return None
    da = float(n[-1]["alpha"]) - float(n[0]["alpha"])
    if abs(da) < 1e-9:
        return None
    return (float(n[-1]["Cl"]) - float(n[0]["Cl"])) / da


def span_verimi(cl: float, cdi: float, ar: float) -> float | None:
    """e = Cl²/(π·AR·CDi). Taşımasız/direncsiz noktada tanımsız."""
    if not cdi or not cl or not ar:
        return None
    return cl ** 2 / (3.141592653589793 * ar * cdi)


def _e_taperde(kanit: dict, taper: float) -> float | None:
    """Ölçülen taper→e tablosundan ara değer. Tablo dışına ÇIKILMAZ."""
    if not kanit:
        return None
    t = sorted(float(k) for k in kanit)
    if not t or taper < t[0] or taper > t[-1]:
        return None
    for i in range(len(t) - 1):
        if t[i] <= taper <= t[i + 1]:
            e0, e1 = float(kanit[_anahtar(kanit, t[i])]), float(kanit[_anahtar(kanit, t[i + 1])])
            if t[i + 1] == t[i]:
                return e0
            return e0 + (e1 - e0) * (taper - t[i]) / (t[i + 1] - t[i])
    return None


def _anahtar(kanit: dict, deger: float) -> str:
    return next(k for k in kanit if abs(float(k) - deger) < 1e-12)


def _simetrik_mi(polar: list[dict], cl_anahtar: str = "Cl") -> bool | None:
    """alpha=0 noktasindan simetri hukmu. VARSAYILAN DEGIL OLCUM.

    NEDEN: kesit/VLM simetri bayraklari cagirana birakilmisti ve varsayilan
    ikisi de True idi. Uc bilesen kendi arasinda tutarli gorunuyordu ama HICBIRI
    araca bakmiyordu (MiniHawk NACA2412 iken kesit NACA0012 uretilmisti).
    Bayrak veriden turetilirse o sinif hata kapida yakalanir.
    """
    for n in polar:
        if abs(float(n.get("alpha", 99))) < 1e-6:
            return abs(float(n.get(cl_anahtar, 0.0))) < KAMBUR_ESIGI
    return None


def _re_olcek(re_hedef: float, re_kaynak: float) -> float:
    """Türbülanslı sürtünme sürüklemesinin Reynolds ölçeklemesi (Cf ~ Re^-0.2).

    Bu bir DÜZELTME DEĞİL, bir BÜYÜKLÜK KESTİRİMİdir: kesit verisi yanlış Re'de
    ise ne kadar yanıldığımızı söyler. Düzeltip kullanmak, ölçülmemiş bir modeli
    ölçüm gibi sunmak olurdu.
    """
    return (re_kaynak / max(re_hedef, 1.0)) ** 0.2


def kesit_polari(kayitlar: list[dict]) -> list[tuple[float, float]]:
    """(Cl, Cd) çiftleri — sürükleme poları. Cl'e göre sıralı."""
    return sorted(((float(k["Cl"]), float(k["Cd"])) for k in kayitlar),
                  key=lambda t: t[0])


def _ara_deger(polar: list[tuple[float, float]], cl: float) -> float | None:
    """Cl'de doğrusal ara değer. EKSTRAPOLASYON YOK — dışarıdaysa None."""
    if len(polar) < 2 or cl < polar[0][0] or cl > polar[-1][0]:
        return None
    for (c0, d0), (c1, d1) in zip(polar, polar[1:]):
        if c0 <= cl <= c1:
            if abs(c1 - c0) < 1e-12:
                return d0
            return d0 + (d1 - d0) * (cl - c0) / (c1 - c0)
    return None


def birlesik_polar(vlm_polar: list[dict], kesit: list[dict], *,
                   re_kanat: float, re_kesit: float,
                   kesit_cd_mesh_bagimsiz: bool,
                   kesit_cd_band_pct: float | None = None,
                   kesit_simetrik: bool = True, vlm_simetrik: bool = True,
                   delta_entegrasyon: float = 0.0,
                   vlm_band_pct: float | None = None,
                   vlm_band_kaynagi: str | None = None,
                   kesit_profili: str | None = None,
                   arac_profili: str | None = None,
                   vlm_ar: float | None = None,
                   vlm_taper: float | None = None,
                   vlm_ok_acisi: float | None = None,
                   band_ailesi: list[dict] | None = None,
                   band_kaynak_dosyasi: str | None = None,
                   taper_kaniti: dict | None = None) -> dict:
    """VLM + 2B kesit → 3B polar. Kapılardan geçmeyen bileşen ÜRETİLMEZ.

    Döner: {"noktalar": [...], "engeller": [...], "uyarilar": [...], "verdikt"}
    Engel varsa `noktalar` yalnız TAŞIMA taşır; mutlak Cd yayınlanmaz.
    """
    engeller: list[str] = []
    uyarilar: list[str] = []

    if kesit_simetrik != vlm_simetrik:
        engeller.append(
            f"KESİT TİPİ UYUŞMUYOR: 2B veri {'simetrik' if kesit_simetrik else 'kamburlu'}, "
            f"VLM {'simetrik' if vlm_simetrik else 'kamburlu'} — α_L0 kayması "
            "birinde var birinde yok; polarlar aynı eğriye ait değil")

    # PROFİL ARACIN PROFİLİ Mİ? Yukarıdaki kapı 2B veri ile VLM KURULUMUNU
    # karşılaştırır; ikisi de simetrikse geçer. Ama HİÇBİRİ aracın GERÇEK
    # profiline bakmıyordu.
    #
    # ÖLÇÜLDÜ (MiniHawk): aracın kanadı NACA2412 (KAMBURLU) ama üretilen XFOIL
    # kesiti NACA0012 (SİMETRİK) ve VLM koşusunda kamburluk KAPALI. Üç bileşen
    # kendi aralarında tutarlıydı, hiçbiri araçla tutarlı değildi. Sonuç: polar
    # "MiniHawk planformlu SİMETRİK-kesitli bir kanadın" polarıdır — MiniHawk'ın
    # değil. Kamburluk α_L0'ı kaydırır, yani Cl(0)≠0 olur ve tüm eğri ötelenir.
    if kesit_profili and arac_profili and kesit_profili != arac_profili:
        engeller.append(
            f"PROFİL ARACIN PROFİLİ DEĞİL: 2B kesit verisi {kesit_profili}, aracın "
            f"kanadı {arac_profili}. Bu polar {kesit_profili} kesitli bir kanada "
            "aittir; kamburluk farkı α_L0'ı kaydırır ve TÜM eğriyi öteler. "
            f"Kesit verisi {arac_profili} için üretilmeli "
            f"(xfoil_kesit.py --naca {arac_profili.replace('NACA', '')})")

    oran = max(re_kanat, re_kesit) / max(min(re_kanat, re_kesit), 1.0)
    if oran > RE_TOLERANS:
        engeller.append(
            f"REYNOLDS UYUŞMUYOR: kanat Re={re_kanat:.2e}, kesit verisi Re={re_kesit:.2e} "
            f"({oran:.1f} kat). Türbülanslı sürtünme Cd~Re^-0.2 ile ölçeklenir; bu fark "
            f"profil sürüklemesinde ~{(_re_olcek(re_kanat, re_kesit) - 1) * 100:.0f}% "
            "sistematik sapma demektir. Kesit verisi kanadın Re'sinde koşulmalı")

    if not kesit_cd_mesh_bagimsiz:
        engeller.append(
            "KESİT Cd MESH-BAĞIMSIZ DEĞİL: bu veriden MUTLAK profil sürüklemesi "
            "üretilmez. (Taşıma etkilenmez — Cl mesh'e çok daha az duyarlıdır.)")

    # VLM'İN İNDÜKLENEN DİRENCİ FİZİKSEL Mİ? Bu kapı yoktu: `vlm_capa` VLM'i
    # SADE DİKDÖRTGEN kanatta doğrulamıştı ve orada doğrulanan şey TAŞIMA
    # EĞİMİYDİ. Birleştirici ise Cd_toplam'a CDi'yi de VLM'den katıyor.
    #
    # ÖLÇÜLDÜ (vlm_taper_capa, alan/açıklık/AR inşa edilen geometriden sabit
    # doğrulanmış): taper 1.0→0.5 arasında e = 1.032 / 1.129 / 1.268 / 1.601.
    # Teorik beklenti CDi'nin %1-2 düşmesiydi; ölçülen %30. MiniHawk taper=0.7,
    # yani CDi'si ~%23 DÜŞÜK. Kamburluk, gövde, kuyruk, uç kümelemesi, iz
    # gevşetmesi ve panel sayısı ayrı ayrı elendi.
    e_ler = [(float(p["alpha"]), span_verimi(float(p.get("Cl", 0.0)),
                                             float(p.get("Cd_i", 0.0)), vlm_ar))
             for p in vlm_polar] if vlm_ar else []
    e_asan = [(a, e) for a, e in e_ler if e is not None and e > E_ENGEL_ESIGI]
    e_sinir_ustu = [(a, e) for a, e in e_ler
                    if e is not None and E_UST_SINIR < e <= E_ENGEL_ESIGI]

    # İNDÜKLENEN DİRENÇ ARTIK VLM'DEN ALINMIYOR. Ölçüldü ki VSPAERO'nun İKİ
    # çıktısı da kuramdan sapıyor (vlm_induklenen_capa, AR=5, α=4):
    #   taper   kuram   yakın-alan      Trefftz
    #    1.00   0.963   0.807 (−16%)   1.032  (+7%)
    #    0.70   0.982   0.792 (−19%)   1.268 (+29%)
    #    0.50   0.991   0.787 (−21%)   1.601 (+62%)
    # Aralarından seçmek keyfî olurdu; hakem taşıyıcı-çizgi kuramıdır ve
    # KENDİNİ DOĞRULUYOR (eliptik planform → e=1.00000). Kuram geçerli değilse
    # (düşük AR, büyük ok açısı) VLM'in sayısına DÜŞÜLÜR ve o zaman aşağıdaki
    # kapılar ENGEL olur — sessiz bir geri düşüş değildir.
    cdi_kuramsal = None
    cdi_yontem = "VLM (VSPAERO CDiw)"
    if vlm_ar:
        import lifting_line as _ll

        # TAŞIMA EĞİMİ DE KURAMA KARŞI ÖLÇÜLÜR. CDi kapısını kurarken ortaya
        # çıktı: aynı hakem taşımayı da yargılayabiliyordu ve kimse sormamıştı.
        # ÖLÇÜLDÜ (MiniHawk planformu, AR=5, taper 0.7, kuram 0.07661/°):
        #   çıplak kanat (gövde YOK)  0.06908/°  → −%10   (VLM'in model-form payı)
        #   kanat + gövde             0.03538/°  → −%54
        #   tam araç                  0.04595/°  → −%40
        # Gövdeyi eklemek eğimi YARIYA indiriyor — gövde taşımayı bu kadar
        # düşüremez. Kusur VSPAERO'daki kalın gövde temsilinde; yeri burası
        # değil ama SONUÇ buradan geçiyor, o yüzden kapı burada.
        _egim = _vlm_egimi(vlm_polar)
        if _egim is not None and not _ll.gecerli_mi(vlm_ar, vlm_ok_acisi or 0.0):
            _kuram = _ll.tasima_egimi(vlm_ar, vlm_taper or 1.0) * math.pi / 180.0
            _sapma = (_egim / _kuram - 1) * 100
            if abs(_sapma) > EGIM_ENGEL_PCT:
                engeller.append(
                    f"VLM TAŞIMA EĞİMİ KURAMDAN SAPIYOR: ölçülen {_egim:.5f}/°, "
                    f"taşıyıcı-çizgi {_kuram:.5f}/° (%{_sapma:+.0f}). Eşik "
                    f"%±{EGIM_ENGEL_PCT:g} ve VLM'in kendi model-form payı ÖLÇÜLDÜ "
                    f"(çıplak kanat −%10). Bu mertebede sapma Cl'i, Cl üzerinden "
                    "Cd_profil'i ve Cl² üzerinden CDi'yi birlikte kaydırır; mutlak "
                    "sürükleme yayınlanmaz. Ölçüldü ki farkı GÖVDE getiriyor "
                    "(çıplak kanat −%10, kanat+gövde −%54)")
            elif abs(_sapma) > EGIM_UYARI_PCT:
                uyarilar.append(
                    f"VLM TAŞIMA EĞİMİ kuramdan %{_sapma:+.0f} sapıyor "
                    f"({_egim:.5f}/° vs {_kuram:.5f}/°) — eşiğin altında ama "
                    "band okunurken hesaba katılmalı")

        _neden = _ll.gecerli_mi(vlm_ar, vlm_ok_acisi or 0.0)
        if _neden:
            uyarilar.append(
                f"İNDÜKLENEN DİRENÇ KURAMDAN ÜRETİLEMEDİ: {_neden}. VLM'in kendi "
                "CDi'si kullanılıyor ve o sayı kurama karşı ölçülmüş sapma taşıyor "
                "(vlm_induklenen_capa.json)")
        else:
            _e = _ll.span_verimi(vlm_ar, vlm_taper if vlm_taper else 1.0)
            cdi_kuramsal = _e
            cdi_yontem = (f"taşıyıcı-çizgi (Glauert), e={_e:.4f} "
                          f"— AR={vlm_ar:.2f}, taper={vlm_taper or 1.0:g}")

    if cdi_kuramsal is not None:
        if e_asan or e_sinir_ustu:
            uyarilar.append(
                "VLM'İN KENDİ CDi'Sİ FİZİKSEL DEĞİL (kullanılmadı): span verimi "
                + ", ".join(f"α={a:g}°→e={e:.3f}" for a, e in (e_asan + e_sinir_ustu))
                + f" — düzlemsel kanatta e≤{E_UST_SINIR} matematiksel sınırdır "
                  "(Munk). İndüklenen direnç kuramdan üretildiği için bu sapma "
                  "sonuca GİRMİYOR; kayda geçiyor")
    elif e_asan:
        engeller.append(
            "VLM İNDÜKLENEN DİRENCİ FİZİKSEL DEĞİL: span verimi "
            + ", ".join(f"α={a:g}°→e={e:.3f}" for a, e in e_asan)
            + f" — düzlemsel kanatta e≤{E_UST_SINIR} matematiksel sınırdır (Munk). "
              "CDi bu kadar düşükse Cd_toplam da düşük çıkar; mutlak sürükleme "
              "yayınlanmaz. Ölçüm ve elenen adaylar: vlm_taper_capa.json")
    elif e_sinir_ustu:
        uyarilar.append(
            "SPAN VERİMİ SINIRIN HAFİF ÜSTÜNDE: "
            + ", ".join(f"α={a:g}°→e={e:.3f}" for a, e in e_sinir_ustu)
            + f" (engel eşiği {E_ENGEL_ESIGI}). Bu mertebe VLM'in panel "
              "ayrıklaştırma kayması olarak ölçüldü ve inceltmeyle azalıyor; "
              "CDi optimist tarafta, Cd_toplam ALT SINIR gibi okunmalı")
    elif not e_ler:
        uyarilar.append(
            "SPAN VERİMİ KONTROL EDİLMEDİ: vlm_ar verilmedi, dolayısıyla VLM'in "
            "indüklenen direncinin fiziksel sınır içinde olup olmadığı BİLİNMİYOR")

    # TAM ARAÇ POLARINDA e≤1 GEÇMESİ TEMİZE ÇIKARMAZ. Munk sınırı TEK DÜZLEMSEL
    # yüzey için teoremdir; kanat+kuyruk sisteminde değil. ÖLÇÜLDÜ (MiniHawk):
    # izole kanat e=1.19 (İHLAL) iken tam araç e=0.89 — kuyruk, taşımaya az
    # katkı verip direnç eklediği için ihlali MASKELİYOR. Bu yüzden taper kusuru
    # AYRI kapıdır ve poların kendisine değil, KANAT PLANFORMUNA bakar.
    if vlm_taper is not None and taper_kaniti and cdi_kuramsal is None:
        e_taper = _e_taperde(taper_kaniti, vlm_taper)
        if e_taper is None:
            uyarilar.append(
                f"TAPER KANITI KAPSAMIYOR: kanat taper={vlm_taper:g}, ölçülen "
                f"taperler {sorted(taper_kaniti)}. CDi sapması bu planformda "
                "ölçülmedi — ekstrapolasyon yapılmaz")
        elif e_taper > E_ENGEL_ESIGI:
            engeller.append(
                f"VLM CDi TAPER'DA SAPIYOR: kanat taper={vlm_taper:g} ve bu "
                f"taperde izole kanatta span verimi e={e_taper:.3f} ÖLÇÜLDÜ "
                f"(sınır {E_UST_SINIR}). CDi ~%{(1 - 1 / e_taper) * 100:.0f} DÜŞÜK "
                "çıkıyor; mutlak sürükleme yayınlanmaz. Tam aracın polarında e "
                "sınırın altında görünebilir — kuyruk ihlali maskeler, temize "
                "çıkarmaz. Ölçüm: vlm_taper_capa.json")

    # BAND BU AYARIN AILESINE MI AIT? Yakinsama calismasi bir AILE icin band
    # verir; uretim baska bir ayarda kosuyorsa o band O SAYIYA ait degildir.
    # Bu depoda tam bu sinif hata iki kez cikti (capa bandini gercek araca
    # tasimak, tek yonlu bandi iki yonlu aileye tasimak).
    if vlm_band_pct is not None and band_ailesi:
        ayar = next(((p.get("span_panel"), p.get("kiris_panel"))
                     for p in vlm_polar if p.get("span_panel")), None)
        aile = {(k.get("span"), k.get("kiris")) for k in band_ailesi}
        if ayar and None not in ayar and ayar not in aile:
            engeller.append(
                f"BAND BU AYARA AIT DEGIL: polar {ayar[0]}x{ayar[1]} panelle "
                f"kosulmus ama band ailesi {sorted(aile)}. Yakinsama bandi bir "
                "AILE icin olculur; aile disindaki bir ayara tasinmasi, "
                "olculmemis bir kesinlik yayinlamaktir. Ya uretim ayari ailenin "
                "bir kademesine cekilmeli ya da o ayar icin aile olculmeli")
        elif not ayar:
            uyarilar.append(
                "POLARIN PANEL AYARI KAYITLI DEGIL: yayinlanan bandin bu koşuya "
                "ait olup olmadigi DOGRULANAMIYOR (eski kanit dosyasi)")

    polar2b = kesit_polari(kesit)
    noktalar = []
    for p in vlm_polar:
        a = float(p["alpha"])
        cl = float(p.get("Cl", 0.0))
        cdi_vlm = float(p.get("Cd_i", 0.0))
        # KURAM VARSA O KULLANILIR — VLM'in sayısı kayda geçer ama hesaba girmez.
        cdi = (cl ** 2 / (3.141592653589793 * vlm_ar * cdi_kuramsal)
               if cdi_kuramsal is not None else cdi_vlm)
        n = {"alpha": a, "Cl": round(cl, 5), "CDi": round(cdi, 6),
             "CDi_kaynagi": cdi_yontem}
        if cdi_kuramsal is not None:
            n["CDi_vlm"] = round(cdi_vlm, 6)
        if a > LINEER_ALFA_MAX:
            n["uyari"] = (f"α={a}° lineer bölge dışında (>{LINEER_ALFA_MAX}°); 2B geçiş "
                          "modeli burada bozuluyor — ÖLÇÜLDÜ: α=10°'de Cl hatası %45")
        if not engeller:
            cd0 = _ara_deger(polar2b, cl)
            if cd0 is None:
                n["Cd_notu"] = (f"Cl={cl:.3f} 2B veri aralığının "
                                f"[{polar2b[0][0]:.3f}, {polar2b[-1][0]:.3f}] DIŞINDA "
                                "— ekstrapolasyon yapılmaz")
            else:
                n["Cd_profil"] = round(cd0, 6)
                n["Cd_toplam"] = round(cd0 + cdi + delta_entegrasyon, 6)
                if n["Cd_toplam"] > 0:
                    # BANDLAR BİRLEŞTİRİLİR. Eski sürüm YALNIZ kesit bandını
                    # taşıyordu ve taşıma bandını hiç katmıyordu — oysa Cd_profil
                    # Cl'DE değerlendiriliyor ve CDi ∝ Cl². Yani Cl'deki
                    # belirsizlik doğrudan Cd'ye geçer. Kamburluk açıldıktan
                    # sonra taşıma bandı ±%2.18'den ±%19.72'ye çıktı ve bu ihmal
                    # artık baskın terimi düşürmek olurdu.
                    pay = []
                    if kesit_cd_band_pct is not None:
                        pay.append(kesit_cd_band_pct * cd0 / n["Cd_toplam"])
                    if vlm_band_pct:
                        # Cl'i band kadar oynat, Cd_toplam'ı YENİDEN kur; profil
                        # bileşeninin eğimi lineer olmadığı için türev
                        # varsayılmaz, iki uçta hesaplanır.
                        sapmalar = []
                        for isaret in (1.0, -1.0):
                            cl_s = cl * (1 + isaret * vlm_band_pct / 100.0)
                            cd0_s = _ara_deger(polar2b, cl_s)
                            if cd0_s is None:
                                continue
                            cdi_s = (cl_s ** 2 / (3.141592653589793 * vlm_ar
                                                  * cdi_kuramsal)
                                     if cdi_kuramsal is not None else cdi)
                            sapmalar.append(
                                abs(cd0_s + cdi_s - (cd0 + cdi)) / n["Cd_toplam"])
                        if sapmalar:
                            pay.append(max(sapmalar) * 100.0)
                            n["Cd_band_tasima_pct"] = round(max(sapmalar) * 100.0, 2)
                        else:
                            n["Cd_band_notu"] = (
                                "taşıma bandının ucu 2B veri aralığının dışına "
                                "düşüyor — bandın Cd'ye katkısı ÖLÇÜLEMEDİ")
                    if pay:
                        n["Cd_band_pct"] = round(
                            sum(p ** 2 for p in pay) ** 0.5, 2)
        noktalar.append(n)

    if vlm_band_pct is None:
        uyarilar.append(
            "TAŞIMA BANDI ÖLÇÜLMEMİŞTİR: VLM bu geometride panel-yakınsaması "
            "ölçülmedi; Cl değerleri literatür-öncül statüsündedir. Ölçüm için: "
            "experiments/vlm_panel_yakinsamasi.py")
    else:
        for n in noktalar:
            n["Cl_band_pct"] = vlm_band_pct
        # METIN KANITTAN URETILIR, SABIT YAZILMAZ. Ilk surumde olculen seri
        # metne GOMULMUSTU; uc kumelemesi eklenip seri monotonlasinca metin
        # "dizi MONOTON DEGIL" demeye DEVAM ETTI — yani rapor, uzerinde
        # calistigi veriyle celisiyordu. Bu depoda avlanan kusurun rapor
        # katmanindaki hali.
        uyarilar.append(
            f"TAŞIMA BANDI ÖLÇÜLDÜ: ±%{vlm_band_pct} — bu bir DOĞRULAMA bandı "
            "DEĞİL, VLM'in bu geometrideki PANEL AYRIKLAŞTIRMA bandıdır"
            + (f" ({vlm_band_kaynagi})" if vlm_band_kaynagi else "")
            + ". Temiz dikdörtgen kanat çapasındaki doğrulama bandı buraya "
              "TAŞINAMAZ; taşınsaydı olmayan bir kesinlik yayınlanırdı."
            # KAYNAK DOSYA ADI DA SABIT YAZILMAZ: band iki yonlu aileye
            # gecince metin hala TEK YONLU dosyayi gosteriyordu.
            + f" Ayrıntı: {band_kaynak_dosyasi or 'panel yakınsama kanıtı'}")

    verdikt = ("3B polar üretildi (Cl + Cd)" if not engeller else
               "YALNIZ TAŞIMA üretildi — mutlak sürükleme için engeller var: "
               + " | ".join(e.split(":")[0] for e in engeller))
    return {"noktalar": noktalar, "engeller": engeller, "uyarilar": uyarilar,
            "verdikt": verdikt,
            "CDi_yontemi": cdi_yontem,
            "yontem": (f"Cl_3B ← VLM; Cd_3B = Cd_profil(Cl) [2B viskoz] + CDi [{cdi_yontem}]"
                       + (" + Δ_entegrasyon [3B RANS]" if delta_entegrasyon else ""))}


def _depo_verisi() -> dict:
    """Depodaki kanıtlarla dene — sayılar KANITTAN, elle yazılmaz.

    KESİT KAYNAĞI ÖNCELİĞİ: XFOIL kesiti kanadın kendi Re'sinde üretilmişse o
    kullanılır; yoksa eski RANS/O-grid verisine düşülür. Düşülürse engeller
    (Re uyuşmazlığı, mesh-bağımsızlık yok) zaten devreye girer ve mutlak
    sürükleme yayınlanmaz — sessiz bir geri düşüş DEĞİLDİR.
    """
    vlm = json.loads((HERE / "vspaero_polar.json").read_text(encoding="utf-8"))
    # VLM TASIMA BANDI: capadaki %1.22 TEMIZ kanata aittir ve gercek araca
    # tasinmaz. Bu geometrinin KENDI panel sacilmasi olculduyse o kullanilir.
    # IKI YONLU AILE VARSA O KULLANILIR. Tek yonlu aile (yalniz aciklik)
    # YAKINSAMA GOSTEREMIYORDU: sabit tutulan kiris yonunun kendi gurultusu
    # (%1.9) aciklik adimlarindan (%0.5-1.2) buyuktu ve band %28.32'de
    # takiliyordu. Iki yon birlikte inceltilince %1.36 (20.8 kat).
    _iki = HERE / "vlm_iki_yonlu_yakinsama.json"
    _pk = HERE / "vlm_panel_yakinsamasi.json"
    vlm_band = vlm_band_kaynagi = None
    band_ailesi = band_kaynak_dosyasi = None
    if _iki.exists():
        _d = json.loads(_iki.read_text(encoding="utf-8"))
        vlm_band = _d.get("vlm_band_pct")
        _kb = _d.get("kanonik_band") or {}
        band_ailesi = _d.get("kademeler")
        band_kaynak_dosyasi = _iki.name
        vlm_band_kaynagi = (
            f"{_kb.get('kaynak', 'panel serisi')}; dizi "
            f"{'monoton' if _d.get('monoton') else 'MONOTON DEGIL'}, "
            f"IKI YONLU aile {[(k['span'], k['kiris']) for k in band_ailesi or []]}")
    elif _pk.exists():
        _d = json.loads(_pk.read_text(encoding="utf-8"))
        vlm_band = _d.get("vlm_band_pct")
        _kb = _d.get("kanonik_band") or {}
        _y = _d.get("yakinsama") or {}
        vlm_band_kaynagi = (
            f"{_kb.get('kaynak', 'panel serisi')}; dizi "
            f"{'monoton' if _y.get('monoton') else 'MONOTON DEGIL'}, "
            f"TEK YONLU aile (yalniz aciklik) {_d.get('paneller')}, uc kumeleme "
            f"{(_d.get('kayitlar') or [{}])[-1].get('uc_kumeleme')}")
        band_kaynak_dosyasi = _pk.name
    from aircraft_geometry import AircraftLibrary
    ac = AircraftLibrary().get_template("mini_hawk")()
    arac_profili = getattr(getattr(ac.wing, "airfoil", None), "name", None)
    kiris = ac.wing.root_chord()
    re_kanat = 15.0 * kiris / 1.5e-5
    # AR span verimi kapisi icin GEREKLI. Dataclass'taki aspect_ratio alanina
    # DEGIL, aciklik/alandan turetilene bakilir: ikisi celisirse VLM'in
    # gordugu geometri span/alandir.
    vlm_ar = ac.wing.span ** 2 / ac.wing.area
    vlm_taper = getattr(ac.wing, "taper_ratio", None)
    vlm_ok_acisi = getattr(ac.wing, "sweep_angle", 0.0)
    # TAPER KANITI DOSYADAN OKUNUR, KODA GOMULMEZ: sayilar degisirse kapi da
    # degisir, tersi degil.
    _tc = HERE / "vlm_taper_capa.json"
    taper_kaniti = (json.loads(_tc.read_text(encoding="utf-8")).get("span_verimi")
                    if _tc.exists() else None)

    xf = HERE / "kesit_re35e4.json"
    if xf.exists():
        d = json.loads(xf.read_text(encoding="utf-8"))
        pb = d.get("panel_bagimsizligi") or {}
        return {"vlm_polar": vlm["polar"], "kesit": d["polar"],
                "kesit_simetrik": _simetrik_mi(d["polar"]),
                "vlm_simetrik": _simetrik_mi(vlm["polar"]),
                "re_kanat": re_kanat, "re_kesit": float(d["re"]),
                # XFOIL'de mesh yok; AYRIKLASTIRMA parametresi PANEL SAYISIDIR ve
                # bandi OLCULDU. "Bagimsiz" iddiasi olcume dayanir, varsayima degil.
                "kesit_cd_mesh_bagimsiz": bool(pb) and pb["en_kotu_sapma_pct"] < 5.0,
                "kesit_cd_band_pct": pb.get("en_kotu_sapma_pct"),
                "kesit_kaynagi": f"XFOIL ({d.get('yontem', '')})",
                "vlm_band_pct": vlm_band,
                "vlm_band_kaynagi": vlm_band_kaynagi,
                "arac_profili": arac_profili,
                "kesit_profili": f"NACA{d.get('naca')}" if d.get("naca") else None,
                "vlm_ar": vlm_ar, "vlm_taper": vlm_taper,
                "vlm_ok_acisi": vlm_ok_acisi, "band_ailesi": band_ailesi,
                "band_kaynak_dosyasi": band_kaynak_dosyasi,
                "taper_kaniti": taper_kaniti, "kiris": kiris}

    tr = json.loads((HERE / "transition_results.json").read_text(encoding="utf-8"))
    gci = json.loads((HERE / "gci_airfoil.json").read_text(encoding="utf-8"))
    kesit = [{"alpha": float(a), **v} for a, v in tr.items()
             if a.lstrip("-").isdigit() and isinstance(v, dict)]
    ref = (gci.get("reference") or {}).get("kaynak", "")
    re_kesit = 3.4e6 if "3.4e6" in ref else 0.0
    return {"vlm_polar": vlm["polar"], "kesit": kesit, "re_kanat": re_kanat,
            "re_kesit": re_kesit, "kesit_cd_mesh_bagimsiz": False,
            "kesit_cd_band_pct": None,
            "kesit_kaynagi": "RANS O-grid (Re=3.4e6 — kanadin Re'si DEGIL)",
            "vlm_band_pct": vlm_band, "vlm_band_kaynagi": vlm_band_kaynagi,
            "arac_profili": arac_profili, "kesit_profili": "NACA0012",
            "vlm_ar": vlm_ar, "vlm_taper": vlm_taper,
            "taper_kaniti": taper_kaniti, "kiris": kiris}


def main() -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    d = _depo_verisi()
    out = birlesik_polar(d["vlm_polar"], d["kesit"],
                         re_kanat=d["re_kanat"], re_kesit=d["re_kesit"],
                         kesit_cd_mesh_bagimsiz=d["kesit_cd_mesh_bagimsiz"],
                         kesit_cd_band_pct=d.get("kesit_cd_band_pct"),
                         vlm_band_pct=d.get("vlm_band_pct"),
                         vlm_band_kaynagi=d.get("vlm_band_kaynagi"),
                         kesit_profili=d.get("kesit_profili"),
                         arac_profili=d.get("arac_profili"),
                         vlm_ar=d.get("vlm_ar"),
                         vlm_taper=d.get("vlm_taper"),
                         vlm_ok_acisi=d.get("vlm_ok_acisi"),
                         band_ailesi=d.get("band_ailesi"),
                         band_kaynak_dosyasi=d.get("band_kaynak_dosyasi"),
                         taper_kaniti=d.get("taper_kaniti"),
                         **{k: d[k] for k in ("kesit_simetrik", "vlm_simetrik")
                            if d.get(k) is not None})
    print(f"MiniHawk kiris={d['kiris']:.3f} m, V=15 m/s → Re={d['re_kanat']:.2e}")
    print(f"2B kesit: {d.get('kesit_kaynagi', '?')}  Re={d['re_kesit']:.2e}"
          + (f"  ayrıklaştırma bandı %{d['kesit_cd_band_pct']}"
             if d.get("kesit_cd_band_pct") is not None else "") + "\n")
    for n in out["noktalar"]:
        s = f"  α={n['alpha']:>5.1f}°  Cl={n['Cl']:.4f}  CDi={n['CDi']:.5f}"
        if "Cd_toplam" in n:
            s += (f"  Cd_profil={n['Cd_profil']:.5f}  Cd={n['Cd_toplam']:.5f}"
                  + (f" ±%{n['Cd_band_pct']}" if "Cd_band_pct" in n else ""))
        print(s)
        for k in ("uyari", "Cd_notu"):
            if k in n:
                print(f"          ⚠ {n[k]}")
    print()
    for e in out["engeller"]:
        print("⛔ " + e)
    for u in out["uyarilar"]:
        print("⚠  " + u)
    print("\n" + out["verdikt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
