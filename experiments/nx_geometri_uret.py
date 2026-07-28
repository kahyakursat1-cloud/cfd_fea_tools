"""Siemens NX ile araç geometrisi test seti üretir (NX journal — NX Python'unda koşar).

NEDEN: auto_pilot sınıflandırıcısının hafızasındaki 241 kaydın 234'ü ya uzman-etiket
ya da projenin KENDİ parametrik şekillerinden geliyor; yalnız 7'si dış CAD. Yani
sınıflandırıcı kendi ürettiği dağılımda ölçülmüş durumda. Bu script, NX'in analitik
yüzeylerinden ve gerçek boolean kesişimlerinden BAĞIMSIZ bir aile üretir — etiketi
inşa ederken bilindiği için AYRILMIŞ TEST SETİ olarak kullanılabilir.

    "C:\\Program Files\\Siemens\\NX2412\\NXBIN\\run_journal.exe" experiments/nx_geometri_uret.py

Çıktı: experiments/nx_geo/*.stl (mm) + etiketler.json
Değerlendirme: python experiments/nx_siniflandirici_testi.py
"""
import json
import math
import os
import traceback

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities

# İki AYRI aile: "test" (ayrık değerlendirme) ve "egitim" (eşik kalibrasyonu).
# Eşiği test setinde kalibre etmek ölçümü değersiz kılar; aileler alt-şekil düzeyinde
# ayrıktır (test: + kollu quad / düz kanat; eğitim: hexa-tri-X kollu / uçan kanat…).
AILE_ADI = os.environ.get("NX_AILE", "test")
CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "nx_geo" if AILE_ADI == "test" else "nx_geo_egitim")
KABA_TOLERANS = 0.6      # tessellation duyarlılığı ölçümü için ikinci ihracat
INCE_TOLERANS = 0.05

s = NXOpen.Session.GetSession()
lw = s.ListingWindow
lw.Open()


class Parca:
    """Tek bir araç gövdesi — primitifler eklendikçe otomatik birleştirilir."""

    def __init__(self, ad):
        self.ad = ad
        self.p = s.Parts.NewDisplay(ad + ".prt", NXOpen.Part.Units.Millimeters)

    def _eksen(self, o, v):
        pt = self.p.Points.CreatePoint(NXOpen.Point3d(float(o[0]), float(o[1]), float(o[2])))
        d = self.p.Directions.CreateDirection(
            NXOpen.Point3d(float(o[0]), float(o[1]), float(o[2])),
            NXOpen.Vector3d(float(v[0]), float(v[1]), float(v[2])),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        return self.p.Axes.CreateAxis(pt, d, NXOpen.SmartObject.UpdateOption.WithinModeling)

    def _birlestir(self, b):
        gov = list(self.p.Bodies)
        if gov:
            b.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite
            b.BooleanOption.SetTargetBodies(gov)

    def silindir(self, o, cap, boy, eksen=(0, 0, 1)):
        b = self.p.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        b.Type = NXOpen.Features.CylinderBuilder.Types.AxisDiameterAndHeight
        b.Diameter.RightHandSide = "%.4f" % cap
        b.Height.RightHandSide = "%.4f" % boy
        b.Axis = self._eksen(o, eksen)
        self._birlestir(b)
        b.CommitFeature()
        b.Destroy()
        return self

    def koni(self, o, taban_cap, tepe_cap, boy, eksen=(0, 0, 1)):
        b = self.p.Features.CreateConeBuilder(NXOpen.Features.Cone.Null)
        b.Type = NXOpen.Features.ConeBuilder.Types.DiametersAndHeight
        b.BaseDiameter.RightHandSide = "%.4f" % taban_cap
        b.TopDiameter.RightHandSide = "%.4f" % tepe_cap
        b.Height.RightHandSide = "%.4f" % boy
        b.Axis = self._eksen(o, eksen)
        self._birlestir(b)
        b.CommitFeature()
        b.Destroy()
        return self

    def blok(self, o, dx, dy, dz):
        # BlockFeatureBuilder BooleanOption'ı yok sayıyor (ilk sürümde kanatlı roket
        # 3 AYRI gövde olarak çıktı, hata vermeden). SetBooleanOperationAndTarget
        # geometri tanımlandıktan SONRA çağrılmalı.
        b = self.p.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
        b.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        b.SetOriginAndLengths(NXOpen.Point3d(float(o[0]), float(o[1]), float(o[2])),
                              "%.4f" % dx, "%.4f" % dy, "%.4f" % dz)
        gov = list(self.p.Bodies)
        if gov:
            b.SetBooleanOperationAndTarget(NXOpen.Features.Feature.BooleanType.Unite, gov[0])
        b.CommitFeature()
        b.Destroy()
        return self

    def kure(self, merkez, cap):
        b = self.p.Features.CreateSphereBuilder(NXOpen.Features.Sphere.Null)
        b.Type = NXOpen.Features.SphereBuilder.Types.CenterPointAndDiameter
        b.Diameter.RightHandSide = "%.4f" % cap
        b.CenterPoint = self.p.Points.CreatePoint(
            NXOpen.Point3d(float(merkez[0]), float(merkez[1]), float(merkez[2])))
        self._birlestir(b)
        b.CommitFeature()
        b.Destroy()
        return self

    def yaz(self, yol, kordal=INCE_TOLERANS):
        st = s.DexManager.CreateStlCreator()
        st.OutputFile = yol
        st.OutputType = NXOpen.STLCreator.OutputTypeEnum.Binary
        st.ChordalTol = kordal
        st.AngularTol = 5.0
        st.AutoNormalGen = True
        for b in self.p.Bodies:
            st.ExportSelectionBlock.Add(b)
        st.Commit()
        st.Destroy()
        return len(list(self.p.Bodies))

    def kapat(self):
        self.p.Close(NXOpen.BasePart.CloseWholeTree.TrueValue,
                     NXOpen.BasePart.CloseModified.CloseModified, None)


# ---------------------------------------------------------------- araç aileleri

def roket(g, cap, ld):
    boy = cap * ld
    burun = cap * 3.0
    g.silindir((0, 0, 0), cap, boy - burun)
    g.koni((0, 0, boy - burun), cap, 0.0, burun)


def kanatli_roket(g, cap, ld, kanat_acikligi=0.9):
    roket(g, cap, ld)
    ac, kord, kal = cap * kanat_acikligi, cap * 1.6, cap * 0.07
    g.blok((-ac - cap / 2, -kal / 2, 0), 2 * ac + cap, kal, kord)
    g.blok((-kal / 2, -ac - cap / 2, 0), kal, 2 * ac + cap, kord)


def _ucak_govde(g, boy, cap):
    g.koni((cap * 1.6, 0, 0), cap, 0.0, cap * 1.6, eksen=(-1, 0, 0))
    g.silindir((cap * 1.6, 0, 0), cap, boy - cap * 3.6, eksen=(1, 0, 0))
    g.koni((boy - cap * 2.0, 0, 0), cap, cap * 0.35, cap * 2.0, eksen=(1, 0, 0))


def ucak(g, boy, cap, acik_orani, ok_acikligi=0.0):
    """Gövde X ekseninde uzanır, kanat Y'de açılır, kalınlık Z'de; kök/uç kordu farklı."""
    _ucak_govde(g, boy, cap)
    ac = boy * acik_orani / 2
    kok, uc = boy * 0.20, boy * 0.10
    kal = kok * 0.11
    z0 = boy * 0.42
    n = 4
    for i in range(n):                       # kademeli daralma → gerçek kanat benzeri
        y0 = ac * i / n
        y1 = ac * (i + 1) / n
        t = (i + 0.5) / n
        kord = kok + (uc - kok) * t
        kay = ok_acikligi * (y0 / max(ac, 1e-6)) * boy * 0.12
        g.blok((z0 + kay, y0, -kal / 2), kord, y1 - y0, kal)
        g.blok((z0 + kay, -y1, -kal / 2), kord, y1 - y0, kal)
    kt = boy * 0.085
    g.blok((boy * 0.88, -ac * 0.32, -kal / 2), kt, ac * 0.64, kal)      # yatay kuyruk
    g.blok((boy * 0.88, -kal / 2, 0), kt, kal, boy * 0.10)              # dikey kuyruk


def kaldirici_govde(g, boy, genislik_orani, yukseklik_orani):
    """Gövdenin kendisi kaldırma üretir: geniş, çok yassı, burnu sivri."""
    w, h = boy * genislik_orani, boy * yukseklik_orani
    g.koni((boy * 0.25, 0, 0), h, 0.0, boy * 0.25, eksen=(-1, 0, 0))
    g.blok((boy * 0.22, -w / 2, -h / 2), boy * 0.78, w, h)
    g.blok((boy * 0.80, -w * 0.12, h / 2), boy * 0.20, w * 0.24, h * 0.9)


def multikopter(g, acik, govde_orani, motor_cap):
    """Merkez gövde + çapraz kollar + 4 motor — spoke topolojisi (düşük doluluk)."""
    gv = acik * govde_orani
    kol = acik * 0.06
    g.blok((-gv / 2, -gv / 2, -gv * 0.35), gv, gv, gv * 0.7)
    g.blok((-acik / 2, -kol / 2, -kol / 2), acik, kol, kol)
    g.blok((-kol / 2, -acik / 2, -kol / 2), kol, acik, kol)
    for dx, dy in ((acik / 2, 0), (-acik / 2, 0), (0, acik / 2), (0, -acik / 2)):
        g.silindir((dx, dy, -motor_cap * 0.5), motor_cap, motor_cap * 1.2)


def tilt_rotor(g, boy, cap, acik_orani):
    ucak(g, boy, cap, acik_orani)
    ac = boy * acik_orani / 2
    nas = boy * 0.055
    for y in (ac * 0.94, -ac * 0.94):
        g.silindir((boy * 0.36, y, 0), nas, boy * 0.20, eksen=(1, 0, 0))
        g.koni((boy * 0.36, y, 0), nas, 0.0, boy * 0.06, eksen=(-1, 0, 0))


def kanatli_vtol(g, boy, cap, acik_orani):
    ucak(g, boy, cap, acik_orani)
    ac = boy * acik_orani / 2
    r = boy * 0.022
    for y in (ac * 0.55, -ac * 0.55):
        g.blok((boy * 0.30, y - r, -r), boy * 0.34, 2 * r, 2 * r)
        for zc in (boy * 0.30, boy * 0.62):
            g.silindir((zc, y, 0), r * 2.6, r * 0.8)


def genel_kure(g, cap):
    g.kure((0, 0, 0), cap)


def genel_kup(g, a):
    g.blok((0, 0, 0), a, a, a)


def genel_disk(g, cap, kalinlik):
    g.silindir((0, 0, 0), cap, kalinlik)


# ---------------------------------------------------------------- test ailesi

# ------------------------------------------------- EĞİTİM ailesine özgü şekiller
# Test ailesiyle aynı sınıflar, FARKLI alt-şekiller: kollar radyal (hexa/tri/X),
# uçaklar gövdesiz/çift-kuyruklu, roketler kademeli. Eşik burada kalibre edilir.

def radyal_kopter(g, acik, govde_orani, motor_cap, n_kol):
    """n kollu kopter — kollar keyfi azimutta (X-config, tri, hexa, okto)."""
    gv = acik * govde_orani
    kol_cap = acik * 0.045
    g.silindir((0, 0, -gv * 0.35), gv, gv * 0.7)
    for i in range(n_kol):
        a = 2 * math.pi * i / n_kol + math.pi / n_kol
        ex, ey = math.cos(a), math.sin(a)
        g.silindir((0, 0, 0), kol_cap, acik / 2, eksen=(ex, ey, 0))
        g.silindir((ex * acik / 2, ey * acik / 2, -motor_cap * 0.5), motor_cap,
                   motor_cap * 1.2)


def ucan_kanat(g, acik, kok_kord, ok):
    """Gövdesiz uçan kanat — kaldırıcı gövdeyle karışması beklenen zor vaka."""
    n = 5
    kal = kok_kord * 0.10
    for i in range(n):
        y0, y1 = acik / 2 * i / n, acik / 2 * (i + 1) / n
        t = (i + 0.5) / n
        kord = kok_kord * (1 - 0.62 * t)
        kay = ok * y0
        g.blok((kay, y0, -kal / 2), kord, y1 - y0, kal)
        g.blok((kay, -y1, -kal / 2), kord, y1 - y0, kal)
    g.koni((kok_kord * 0.12, 0, 0), kal * 2.2, 0.0, kok_kord * 0.12, eksen=(-1, 0, 0))


def cift_kuyruklu(g, boy, cap, acik_orani):
    """Çift kuyruk kirişli uçak (twin-boom) — kanat + iki uzun kiriş."""
    ucak(g, boy, cap, acik_orani)
    ac = boy * acik_orani / 2
    r = boy * 0.030
    for y in (ac * 0.45, -ac * 0.45):
        g.silindir((boy * 0.44, y, 0), r, boy * 0.46, eksen=(1, 0, 0))
        g.blok((boy * 0.86, y - r, 0), boy * 0.07, 2 * r, boy * 0.11)


def kademeli_roket(g, cap, ld, ust_orani):
    """İki kademeli roket — alt kademe geniş, üst dar."""
    boy = cap * ld
    alt = boy * 0.55
    ust_cap = cap * ust_orani
    g.silindir((0, 0, 0), cap, alt)
    g.koni((0, 0, alt), cap, ust_cap, cap * 0.6)
    g.silindir((0, 0, alt + cap * 0.6), ust_cap, boy - alt - cap * 0.6 - ust_cap * 2.5)
    g.koni((0, 0, boy - ust_cap * 2.5), ust_cap, 0.0, ust_cap * 2.5)


def takviyeli_roket(g, cap, ld, n_booster):
    """Yan takviyeli roket — radyal ama İNCE (kopterle karışmamalı)."""
    roket(g, cap, ld)
    boy = cap * ld
    bc = cap * 0.42
    for i in range(n_booster):
        a = 2 * math.pi * i / n_booster
        g.silindir((math.cos(a) * cap * 0.68, math.sin(a) * cap * 0.68, 0),
                   bc, boy * 0.42)


def kapsul(g, cap, boy_orani):
    """Kapsül: silindir + iki küre kapak — küt, dönel simetrik."""
    boy = cap * boy_orani
    g.silindir((0, 0, 0), cap, boy)
    g.kure((0, 0, 0), cap)
    g.kure((0, 0, boy), cap)


def dalga_binici(g, boy, genislik_orani):
    """Waverider — çok yassı delta; kaldırıcı gövdenin zor varyantı."""
    w = boy * genislik_orani
    h = boy * 0.075
    n = 6
    for i in range(n):
        # dilimler TEĞET kalırsa NX birleşimi "tool completely outside" der; bindir.
        x0, x1 = boy * i / n, boy * (i + 1) / n
        bind = (x1 - x0) * 0.04
        yw = w / 2 * ((i + 1) / n) ** 0.8
        g.blok((max(x0 - bind, 0.0), -yw, -h / 2), x1 - x0 + bind, 2 * yw, h)
    g.blok((boy * 0.78, -h * 0.5, h / 2), boy * 0.22, h, h * 1.6)


AILE = []


def _ekle(ad, etiket, fn, *a, **kw):
    AILE.append((ad, etiket, fn, a, kw))


if AILE_ADI == "test":
    for i, ld in enumerate((6, 8, 11, 15, 20)):
        _ekle("roket_ld%d" % ld, "roket", roket, 120.0, float(ld))
    for i, ld in enumerate((6, 9, 12, 16)):
        _ekle("kanatliroket_ld%d" % ld, "kanatli_roket", kanatli_roket, 140.0, float(ld))
    for ad, boy, cap, acik in (("kucuk", 1200.0, 130.0, 1.05), ("orta", 2400.0, 240.0, 1.25),
                               ("nakliye", 3600.0, 420.0, 1.45), ("dar", 2000.0, 200.0, 0.75),
                               ("genis", 2000.0, 170.0, 1.70)):
        _ekle("ucak_" + ad, "ucak", ucak, boy, cap, acik)
    _ekle("ucak_okkanat", "ucak", ucak, 2200.0, 220.0, 1.0, 0.9)
    for ad, w, h in (("dar", 0.42, 0.13), ("orta", 0.55, 0.11), ("genis", 0.70, 0.15),
                     ("cokyassi", 0.60, 0.07)):
        _ekle("kaldirici_" + ad, "kaldirici_govde", kaldirici_govde, 1500.0, w, h)
    for ad, acik, gov, mot in (("kucuk", 450.0, 0.30, 40.0), ("orta", 900.0, 0.26, 70.0),
                               ("buyuk", 1600.0, 0.22, 120.0), ("kompakt", 600.0, 0.40, 55.0),
                               ("genisgovde", 1100.0, 0.34, 95.0)):
        _ekle("multikopter_" + ad, "multikopter", multikopter, acik, gov, mot)
    for ad, boy, cap, acik in (("kucuk", 1800.0, 190.0, 1.15), ("orta", 2600.0, 260.0, 1.30),
                               ("darkanat", 2200.0, 230.0, 0.90)):
        _ekle("tiltrotor_" + ad, "tilt_rotor", tilt_rotor, boy, cap, acik)
    for ad, boy, cap, acik in (("kucuk", 1400.0, 150.0, 1.20), ("orta", 2100.0, 210.0, 1.35),
                               ("genis", 2600.0, 230.0, 1.60)):
        _ekle("kanatlivtol_" + ad, "kanatli_vtol", kanatli_vtol, boy, cap, acik)
    for ad, cap in (("kure200", 200.0), ("kure600", 600.0)):
        _ekle("genel_" + ad, "genel", genel_kure, cap)
    _ekle("genel_kup300", "genel", genel_kup, 300.0)
    _ekle("genel_kup800", "genel", genel_kup, 800.0)
    _ekle("genel_disk", "genel", genel_disk, 700.0, 90.0)
else:
    for ld, uo in ((7, 0.55), (10, 0.62), (14, 0.70)):
        _ekle("kademeli_ld%d" % ld, "roket", kademeli_roket, 150.0, float(ld), uo)
    for nb in (2, 4):
        _ekle("takviyeli_b%d" % nb, "roket", takviyeli_roket, 160.0, 9.0, nb)
    for ld, ka in ((7, 1.10), (11, 0.75), (14, 1.30)):
        _ekle("kanatliroket_e%d" % ld, "kanatli_roket", kanatli_roket, 130.0, float(ld), ka)
    for ad, ac, kk, ok in (("dar", 1800.0, 700.0, 0.55), ("genis", 2600.0, 800.0, 0.35),
                           ("keskin", 2000.0, 900.0, 0.80)):
        _ekle("ucankanat_" + ad, "ucak", ucan_kanat, ac, kk, ok)
    for ad, boy, cap, ao in (("kucuk", 1600.0, 175.0, 1.15), ("orta", 2500.0, 255.0, 1.35)):
        _ekle("ciftkuyruk_" + ad, "ucak", cift_kuyruklu, boy, cap, ao)
    for ad, boy, gen in (("dar", 1700.0, 0.50), ("genis", 2100.0, 0.72)):
        _ekle("dalgabinici_" + ad, "kaldirici_govde", dalga_binici, boy, gen)
    for ad, boy, gen, yuk in (("kapsulsu", 1300.0, 0.66, 0.20),):
        _ekle("kaldirici_e_" + ad, "kaldirici_govde", kaldirici_govde, boy, gen, yuk)
    for ad, ac, gv, mot, nk in (("tri", 700.0, 0.28, 62.0, 3), ("xquad", 950.0, 0.25, 78.0, 4),
                                ("hexa", 1250.0, 0.23, 92.0, 6), ("okto", 1500.0, 0.21, 96.0, 8),
                                ("mini_x", 420.0, 0.34, 42.0, 4)):
        _ekle("kopter_" + ad, "multikopter", radyal_kopter, ac, gv, mot, nk)
    for ad, boy, cap, ao in (("e_kucuk", 1500.0, 165.0, 1.05), ("e_genis", 2800.0, 245.0, 1.55)):
        _ekle("tiltrotor_" + ad, "tilt_rotor", tilt_rotor, boy, cap, ao)
    for ad, boy, cap, ao in (("e_orta", 1900.0, 195.0, 1.25),):
        _ekle("kanatlivtol_" + ad, "kanatli_vtol", kanatli_vtol, boy, cap, ao)
    for ad, cap, bo in (("kisa", 400.0, 1.2), ("uzun", 300.0, 2.4)):
        _ekle("genel_kapsul_" + ad, "genel", kapsul, cap, bo)
    _ekle("genel_koni", "genel", lambda g, c, h: g.koni((0, 0, 0), c, 0.0, h), 500.0, 620.0)
    _ekle("genel_kure400", "genel", genel_kure, 400.0)
    _ekle("genel_kup500", "genel", genel_kup, 500.0)

KABA_ORNEK = ({"roket_ld11", "ucak_orta", "multikopter_orta", "kaldirici_orta",
               "tiltrotor_orta", "genel_kup300"} if AILE_ADI == "test" else set())


def main():
    if not os.path.isdir(CIKTI):
        os.makedirs(CIKTI)
    etiketler, hatalar = [], []
    for ad, etiket, fn, a, kw in AILE:
        try:
            g = Parca(ad)
            fn(g, *a, **kw)
            yol = os.path.join(CIKTI, ad + ".stl")
            n_gov = g.yaz(yol, INCE_TOLERANS)
            kayit = {"ad": ad, "etiket": etiket, "stl": ad + ".stl",
                     "govde_nx": n_gov, "kordal_tol": INCE_TOLERANS}
            if ad in KABA_ORNEK:
                kaba = ad + "_kaba.stl"
                g.yaz(os.path.join(CIKTI, kaba), KABA_TOLERANS)
                etiketler.append({"ad": ad + "_kaba", "etiket": etiket, "stl": kaba,
                                  "govde_nx": n_gov, "kordal_tol": KABA_TOLERANS,
                                  "_amac": "tessellation duyarliligi — ayni kati, kaba uçgenleme"})
            etiketler.append(kayit)
            g.kapat()
            lw.WriteLine("OK   %-24s %-16s govde=%d" % (ad, etiket, n_gov))
        except Exception:
            hatalar.append({"ad": ad, "hata": traceback.format_exc()[-400:]})
            lw.WriteLine("HATA %-24s %s" % (ad, traceback.format_exc().strip().splitlines()[-1]))

    with open(os.path.join(CIKTI, "etiketler.json"), "w") as f:
        json.dump({"kaynak": "Siemens NX 2412 — run_journal, analitik katı + boolean",
                   "_neden": ("auto_pilot hafizasi projenin kendi parametrik sekillerinden "
                              "olusuyordu; bu aile BAGIMSIZ ve etiketi insa aninda bilinen "
                              "AYRILMIS TEST SETI'dir."),
                   "adet": len(etiketler), "hata": hatalar, "geometriler": etiketler},
                  f, indent=2)
    lw.WriteLine("\n%d geometri -> %s  (%d hata)" % (len(etiketler), CIKTI, len(hatalar)))


main()
