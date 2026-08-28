"""İki-hızlı katman ölçeri: aynı sözleşmeyi paylaşan yollar ayrışıyor mu.

NEDEN. 2026-08-28'de araç yolunda ölçülmüş bir yük kusuru bulundu: yüzey
normalleri YÜZ BAŞINA ters çevriliyordu ve yapıya aerodinamik yükün dörtte
biri uygulanıyordu. Kusurun teknik açıklaması var, ama HAYATTA KALMA
sebebi yapısal: FSI sürücüsünün eşleme modülü aynı ölçütü çoktan
çürütmüştü ve gerekçesini kendi gövdesine yazmıştı. İki yol yan yana
duruyordu; biri dersi öğrenmiş, öteki hiç duymamıştı.

CLAUDE.md bu riski "iki-hızlı uyarı" diye zaten sayıyordu. Bu ölçer onu
varsayımdan ÖLÇÜME çevirir. Sorduğu soru bir düzeltme yapıldığında
sorulması gereken sorudur: *aynı kusur hangi ÖTEKİ yolda duruyor.*

ÖLÇER İKİ AYRI ŞEY YAPAR VE İKİNCİSİ ASIL DEĞERİ TAŞIR:

  1. KAYITLI uygulamaları paylaştıkları sözleşmeye karşı DAVRANIŞLA sınar.
     Bu, bilinen yolların ayrışmadığını gösterir.
  2. KAYITSIZ ADAYLARI tarar: sözleşmenin konusu olan işi yapan ama
     kayıtta bulunmayan kod. Bugünkü kusuru yakalayacak olan BUDUR ---
     birinci madde `vehicle_fea`'yı hiç görmezdi, çünkü orada sözleşmeyi
     tutan bir fonksiyon YOKTU, ham bir maske ataması vardı.

KAPSAM SINIRI. Bu bir kod-klonu dedektörü DEĞİLDİR ve "aynı işi yapan her
şeyi" bulmaz. Sözleşmeler ELLE bildirilir; ölçer yalnız bildirilen
sözleşmenin ihlallerini arar. Yeni bir fizik yolu eklendiğinde sözleşmesi
de eklenmelidir --- ölçer bunu kendiliğinden bilemez ve bilir gibi
yapmaz.

    python iki_hiz.py
Çıktı: iki_hiz.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "iki_hiz.json"

ATLA = (".venv", "build", "__pycache__", ".git", "tests")


# ══════════════════════════════ SOZLESME 1 ══════════════════════════════
# YONLENDIRME BUTUNSELDIR. Bir yuzeyin sarimi tutarliysa yonlendirme ya
# HICBIR yuze dokunur ya da HEPSINI cevirir. Bir ALT KUMEYI cevirmek
# yuzeyin tutarliligini bozar --- ve olculen kusur tam olarak buydu
# (A320'de 335.156 yuzun 176.031'i).

def _kup(ters: bool = False):
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
    tris = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                     [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
                     [1, 2, 6], [1, 6, 5], [0, 4, 7], [0, 7, 3]])
    if ters:
        tris = tris[:, ::-1]
    v1, v2 = P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]]
    cr = np.cross(v1, v2)
    A = 0.5 * np.linalg.norm(cr, axis=1)
    n = cr / (2 * A[:, None] + 1e-30)
    return P, tris, n, A, P[tris].mean(axis=1)


def _iki_ayrik_kup(ters: bool = False):
    """DISBUKEY OLMAYAN govde --- kusuru ORTAYA CIKARAN sinav.

    Dısbukey bir kutuda "merkezden disari" olcutu ZATEN dogrudur, yani
    kusuru gostermez. Iki ayrik kupte agirlik merkezi aradaki bosluga
    duser ve sol kupun +x yuzunun dis normali merkeze DOGRU bakar.
    """
    P0, t0, _, _, _ = _kup(ters)
    P = np.vstack([P0, P0 + np.array([3.0, 0, 0])])
    tris = np.vstack([t0, t0 + len(P0)])
    v1, v2 = P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]]
    cr = np.cross(v1, v2)
    A = 0.5 * np.linalg.norm(cr, axis=1)
    n = cr / (2 * A[:, None] + 1e-30)
    return P, tris, n, A, P[tris].mean(axis=1)


def _sozlesme_butunsel(uygula) -> dict:
    """`uygula(P, tris, n, A, c) -> yeni_n` bütünsel mi."""
    kusur = []
    for ad, kur in (("kup", _kup), ("kup_ters", lambda: _kup(True)),
                    ("iki_ayrik_kup", _iki_ayrik_kup),
                    ("iki_ayrik_kup_ters", lambda: _iki_ayrik_kup(True))):
        P, tris, n, A, c = kur()
        try:
            yeni = np.asarray(uygula(P, tris, n.copy(), A, c), float)
        except Exception as e:                              # noqa: BLE001
            kusur.append(f"{ad}: {type(e).__name__}: {e}"[:120])
            continue
        if yeni.shape != n.shape:
            kusur.append(f"{ad}: şekil {yeni.shape} ≠ {n.shape}")
            continue
        if not (np.allclose(yeni, n) or np.allclose(yeni, -n)):
            kaç = int((~np.isclose(yeni, n).all(axis=1)).sum())
            kusur.append(f"{ad}: {kaç}/{len(n)} yüz ayrı çevrilmiş "
                         "— yönlendirme BÜTÜNSEL değil")
    return {"tutuyor": not kusur, "kusurlar": kusur}


def _u_vehicle(P, tris, n, A, c):
    from vehicle_fea import _disa_yonlendir
    return _disa_yonlendir(P, tris, n, A, c)[0]


def _u_fsi(P, tris, n, A, c):
    from fsi_korunumlu_esleme import disa_yonlendir
    # Bu uygulama BIR REFERANSA hizalar; sozlesme yine de ayni: ya hepsi
    # ya hicbiri. Referans olarak yuzeyin KENDI normalleri verilir.
    return disa_yonlendir(c, n, c, n)[0]


def _u_alici(P, tris, n, A, c):
    sys.path.insert(0, str(KOK / "experiments"))
    from alici_yuzey_yeterliligi import _kuresel_yonlendir
    return _kuresel_yonlendir(c, n, A)


# ══════════════════════════════ SOZLESME 2 ══════════════════════════════
# YUK AKTARIMI KORUNUMLUDUR. Bir yuzey kuvveti alici duguMlere dagitilirken
# TOPLAM degismez: sum F_dugum == sum dF_yuz, makine hassasiyetinde. Bu bir
# yaklasim degil KIMLIKTIR --- agirliklar 1'e toplanir.
#
# ESKI SEMA BUNU TUTMUYORDU: basinci tasiyip kuvveti ALICI yuzeyde yeniden
# integre ediyordu ve alanlar farkliysa toplam da farkli cikiyordu
# (olculdu: aerodinamik kuvvetten medyan %9,5 sapma, 23 kosu).

def _bozuk_alanli():
    """Üçgen alanları BİRBİRİNDEN FARKLI bir yüzey --- sınavın can alıcı
    parçası.

    Küpün on iki üçgeni EŞİT alanlıdır ve alan-farkı etkisi orada yok
    olur: eski (korunumsuz) şema bile küpte korunum sınavını GEÇTİ. Yani
    sınav bir şey sınamıyordu. Bu, aynı oturumda ikinci kez yapılan hata
    --- yönlendirme sınavında da dışbükey bir kutu seçilmiş ve eski ölçütü
    kırmamıştı. Sınav geometrisi kusuru İŞLETMELİDİR.

    Köşeler rastgele kaydırılır; kapalılık ve sarım korunur, yalnız alanlar
    dağılır.
    """
    P, tris, _, _, _ = _kup()
    P = P + np.random.default_rng(3).normal(0, 0.22, P.shape)
    v1, v2 = P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]]
    cr = np.cross(v1, v2)
    A = 0.5 * np.linalg.norm(cr, axis=1)
    n = cr / (2 * A[:, None] + 1e-30)
    return P, tris, n, A, P[tris].mean(axis=1)


def _sozlesme_korunumlu(dagit) -> dict:
    """`dagit(dF_cfd, cfd_merkez, dugumler, yuzler, yuz_merkez) -> F_dugum`
    toplami koruyor mu."""
    rng = np.random.default_rng(7)
    kusur = []
    for ad, kur in (("kup", _kup), ("kup_ters", lambda: _kup(True)),
                    ("bozuk_alanli", _bozuk_alanli)):
        P, tris, n, A, c = kur()
        # CFD yuzleri: alici ucgenlerin merkezlerinden RASTGELE kaydirilmis
        # noktalar --- birebir ortusme OLMASIN ki kimlik gercekten sinansin.
        cfd_c = c + rng.normal(0, 0.05, c.shape)
        dF = rng.normal(0, 1.0, cfd_c.shape)
        try:
            F = np.asarray(dagit(dF, cfd_c, P, tris, c), float)
        except Exception as e:                              # noqa: BLE001
            kusur.append(f"{ad}: {type(e).__name__}: {e}"[:120])
            continue
        artik = float(np.linalg.norm(F.sum(axis=0) - dF.sum(axis=0))
                      / (np.linalg.norm(dF.sum(axis=0)) + 1e-30))
        if artik > 1e-10:
            kusur.append(f"{ad}: korunum artığı {artik:.3e} — toplam kuvvet "
                         "KORUNMUYOR")
    return {"tutuyor": not kusur, "kusurlar": kusur}


def _d_korunumlu(dF, cfd_c, P, tris, c):
    from fsi_korunumlu_esleme import korunumlu_dagit
    return korunumlu_dagit(dF, cfd_c, P, tris, c)[0]


def _d_t6(dF, cfd_c, P, tris, c):
    """Araç yolunun T6 dağıtımı --- kuadratik şekil fonksiyonlarıyla.

    Korunum T6'da da KİMLİKTİR: şekil fonksiyonları 1'e toplanır. Sınav
    burada lineer üçgen kullandığı için düğüm listesi köşelerden kurulur;
    ölçülen şey ağırlıkların toplamıdır, eleman tipi değil.
    """
    from fsi_korunumlu_esleme import esleme_kur
    from vehicle_fea import t6_sekil
    esleme = esleme_kur(cfd_c, P, tris, c)
    w, ucgen = esleme["agirlik"], esleme["ucgen"]
    N = t6_sekil(w)
    F = np.zeros_like(P, dtype=float)
    # T6 sekil fonksiyonlarinin KOSE bileseni + kenar-orta bileseni; sinav
    # agi lineer oldugundan kenar-orta paylari kose dugumlerine BOLUNUR.
    # (Toplami degistirmez --- sinanan sey zaten toplam.)
    for k in range(3):
        np.add.at(F, ucgen[:, k], N[:, k:k + 1] * dF)
    for k, (i, j) in enumerate(((0, 1), (1, 2), (2, 0))):
        np.add.at(F, ucgen[:, i], 0.5 * N[:, 3 + k:4 + k] * dF)
        np.add.at(F, ucgen[:, j], 0.5 * N[:, 3 + k:4 + k] * dF)
    return F


SOZLESMELER = [
    {
        "ad": "yuk_aktarimi_korunumlu",
        "soru": "yüzey kuvveti düğümlere dağıtılırken toplam korunuyor mu",
        "sinav": _sozlesme_korunumlu,
        "uygulamalar": [
            ("fsi_korunumlu_esleme.korunumlu_dagit", _d_korunumlu),
            ("vehicle_fea.t6_sekil (araç yolu dağıtımı)", _d_t6),
        ],
        "aday_imzasi": "korunumsuz_yeniden_integrasyon",
    },
    {
        "ad": "yonlendirme_butunsel",
        "soru": "yüzey yönlendirmesi hepsi-ya-hiçbiri mi",
        "sinav": _sozlesme_butunsel,
        "uygulamalar": [
            ("vehicle_fea._disa_yonlendir", _u_vehicle),
            ("fsi_korunumlu_esleme.disa_yonlendir", _u_fsi),
            ("experiments/alici_yuzey_yeterliligi._kuresel_yonlendir",
             _u_alici),
        ],
        # KAYITSIZ ADAY IMZASI: normal dizisine MASKEYLE/INDEKSLE atama.
        # Bugunku kusurun sozdizimi tam buydu:
        #     flip = np.einsum(...) < 0
        #     normals[flip] *= -1
        "aday_imzasi": "normal_maskeli_atama",
    },
]


# ═══════════════════════ KAYITSIZ ADAY TARAMASI ═════════════════════════

def _kayitli_konumlar() -> set[str]:
    return {ad.split(".")[-1] for s in SOZLESMELER
            for ad, _ in s["uygulamalar"]}


def _isaret_cevirme(dugum) -> bool:
    """Bu atama bir İŞARET ÇEVİRME mi --- yoksa dizi DOLDURMA mı.

    ÖLÇÜT İLK YAZIMDA FAZLA GENİŞTİ ve üç yanlış pozitif üretti:
    `normals[idx] = nrm/|nrm|` (döngüde dizi doldurma),
    `normals[nid] += fn` (düğüm normali toplama) ve
    `normal[argmin(ext)] = 1.0` (birim vektör kurma). Üçü de meşru.

    Kusurun imzası doldurma DEĞİL, YÖN DEĞİŞTİRMEDİR:
        normals[flip] *= -1      ya da      normals[flip] = -normals[flip]
    Ölçüt bu yüzden İŞLEME bağlanır: negatif bir çarpan ya da tekli eksi.
    """
    if isinstance(dugum, ast.AugAssign):
        if not isinstance(dugum.op, (ast.Mult, ast.Div)):
            return False
        v = dugum.value
        return (isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.USub)) or (
            isinstance(v, ast.Constant)
            and isinstance(v.value, (int, float)) and v.value < 0)
    v = dugum.value
    return isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.USub)


def _normal_maskeli_atama(agac: ast.AST) -> list[tuple[str, int]]:
    """Normal dizisinin bir ALT KÜMESİNİN işaretini çeviren atama.

    İki koşul birlikte aranır: (a) indeks sabit ya da dilim DEĞİL --- yani
    bir maske/indeks dizisi, yüz-başına karar; (b) işlem bir İŞARET
    ÇEVİRME. İkisi ayrı ayrı masumdur; kusuru yapan bileşimleridir.
    """
    bulgu = []
    for d in ast.walk(agac):
        if not isinstance(d, (ast.Assign, ast.AugAssign)):
            continue
        if not _isaret_cevirme(d):
            continue
        hedefler = d.targets if isinstance(d, ast.Assign) else [d.target]
        for h in hedefler:
            if not isinstance(h, ast.Subscript):
                continue
            taban = h.value
            if not isinstance(taban, ast.Name):
                continue
            if "normal" not in taban.id.lower():
                continue
            idx = h.slice
            if isinstance(idx, (ast.Slice, ast.Constant, ast.Tuple)):
                continue                     # n[:, 2] gibi bilesen yazimi
            bulgu.append((taban.id, d.lineno))
    return bulgu


def _kaynaklar():
    for p in sorted(KOK.rglob("*.py")):
        s = p.relative_to(KOK).as_posix()
        if any(a in Path(s).parts for a in ATLA):
            continue
        if p.name == "iki_hiz.py":
            continue                          # kendi ornekleri sayilmaz
        yield s, p


def aday_tara() -> list[dict]:
    kayitli = _kayitli_konumlar()
    adaylar = []
    for s, p in _kaynaklar():
        try:
            agac = ast.parse(p.read_text(encoding="utf-8"))
        # sessiz-yutma: kabul — ayristirilamayan dosya ADIYLA listelenir
        except (OSError, SyntaxError) as e:
            adaylar.append({"dosya": s, "satir": 0,
                            "neden": f"ayrıştırılamadı: {type(e).__name__}"})
            continue
        for fn in ast.walk(agac):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for ad, satir in _normal_maskeli_atama(fn):
                if fn.name in kayitli:
                    continue                  # kayitli uygulama — sozlesme
                adaylar.append({"dosya": s, "fonksiyon": fn.name,
                                "satir": satir, "dizi": ad,
                                "imza": "normal_maskeli_atama"})
    return adaylar


def olc() -> dict:
    sonuc = []
    for s in SOZLESMELER:
        uyg = []
        for ad, fn in s["uygulamalar"]:
            r = s["sinav"](fn)
            uyg.append({"uygulama": ad, **r})
        sonuc.append({"sozlesme": s["ad"], "soru": s["soru"],
                      "uygulamalar": uyg,
                      "ayrisan": [u["uygulama"] for u in uyg
                                  if not u["tutuyor"]]})
    adaylar = aday_tara()
    return {
        "vaka": "İki-hızlı katman — aynı sözleşmeyi paylaşan yollar ayrışıyor mu",
        "_neden": ("2026-08-28: arac yolunda yuzey normalleri YUZ BASINA "
                   "ters ceviriliyordu ve yapiya yukun dortte biri "
                   "uygulaniyordu. FSI yolu ayni olcutu coktan curutmustu. "
                   "Ders bir yolda ogrenilmis, otekine tasinmamisti."),
        "sozlesmeler": sonuc,
        "kayitsiz_adaylar": adaylar,
        "verdikt": _hukum(sonuc, adaylar),
        "_kisit": (
            "Kod-klonu dedektoru DEGILDIR. Sozlesmeler ELLE bildirilir ve "
            "olcer yalniz bildirilenin ihlalini arar; yeni bir fizik yolu "
            "eklendiginde sozlesmesi de eklenmelidir. Aday taramasi da tek "
            "bir SOZDIZIMI imzasina bakar --- ayni kusurun baska bir "
            "yazilisi bu imzaya girmeyebilir."),
        "_uretim": "Üretim: python iki_hiz.py",
    }


def _hukum(sonuc: list[dict], adaylar: list[dict]) -> str:
    ayrisan = [a for s in sonuc for a in s["ayrisan"]]
    n_uyg = sum(len(s["uygulamalar"]) for s in sonuc)
    if ayrisan:
        return (f"AYRIŞMA VAR: {len(ayrisan)}/{n_uyg} uygulama paylaştığı "
                f"sözleşmeyi tutmuyor — {', '.join(ayrisan)}.")
    if adaylar:
        ad = ", ".join(f"{a['dosya']}:{a.get('satir')}" for a in adaylar[:4])
        return (f"{n_uyg}/{n_uyg} kayıtlı uygulama sözleşmesini tutuyor, ama "
                f"{len(adaylar)} KAYITSIZ ADAY var: {ad}. Aday, sözleşmenin "
                f"konusu olan işi yapıp kayıtta bulunmayan koddur; bugünkü "
                f"kusur tam bu durumdaydı.")
    return (f"{n_uyg}/{n_uyg} kayıtlı uygulama paylaştığı sözleşmeyi "
            f"tutuyor ve kayıtsız aday yok. Bu bir AYRIŞMA hükmüdür — "
            f"bildirilmemiş bir sözleşme varsa ölçer onu göremez.")


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    o = olc()
    CIKTI.write_text(json.dumps(o, indent=2, ensure_ascii=False),
                     encoding="utf-8")
    for s in o["sozlesmeler"]:
        print(f"sözleşme: {s['sozlesme']} — {s['soru']}")
        for u in s["uygulamalar"]:
            im = "✅" if u["tutuyor"] else "❌"
            print(f"  {im} {u['uygulama']}")
            for k in u["kusurlar"]:
                print(f"       {k}")
    if o["kayitsiz_adaylar"]:
        print("\nkayıtsız adaylar:")
        for a in o["kayitsiz_adaylar"]:
            print(f"  {a['dosya']}:{a.get('satir')} "
                  f"{a.get('fonksiyon', '')} ({a.get('imza', a.get('neden'))})")
    print()
    print(o["verdikt"])
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
