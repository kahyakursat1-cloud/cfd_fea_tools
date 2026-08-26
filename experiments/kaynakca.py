r"""Kaynakça — KANITTAN üretilir, elle yazılmaz.

Rapor onlarca literatür kaynağı kullanıyor (Ladson, Driver \& Seegmiller,
Achenbach, Roshko, Norberg, Williamson, Hoerner, Celik ve ark., Eça \&
Hoekstra, Svanberg, ASME V\&V 20) ama ayrı bir kaynakça bölümü YOKTU. Dış
inceleme bunu yakaladı ve haklıydı: dahili bir geliştirme raporu için tolere
edilebilir, akademik çıktı ya da proje kanıtı olarak kullanılacaksa şart.

NEDEN ÜRETİCİ, NEDEN ELLE DEĞİL: kaynaklar zaten yapısal olarak duruyor ---
çapa kayıtlarının `kaynak` alanlarında ve kod sabitlerinde (`*_KAYNAK`). Elle
bir liste yazmak, raporun kendi avladığı kusuru işlemek olurdu: sabit metin,
değişen veri. Bir çapa yeni bir referansa taşındığında liste sessizce eskirdi.

NE YAPMAZ: DOI uydurmaz. Kayıtta ne varsa onu basar; eksik künye eksik
görünür ve bu KASITLIDIR --- tamamlanmış gibi görünen bir kaynakça,
tamamlanmamış olandan daha tehlikelidir.

    python experiments/kaynakca.py
Çıktı: docs/kaynakca.tex  (rapor \input eder) + kaynakca.json
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

TEX = KOK / "docs" / "kaynakca.tex"
CIKTI = KOK / "kaynakca.json"

# LITERATUR MU, SUREC NOTU MU? Kanit dosyalarindaki `kaynak` alanlari ikisini
# de tasiyor: "Roshko, J. Fluid Mech. 10 (1961)" literaturdur,
# "--oku: mevcut case'ten okundu" degildir. Ayirt edici: bir YIL ve bir
# kaynak-gostergesi (dergi/rapor kisaltmasi ya da yazar-virgul deseni).
_YIL = re.compile(r"\b(1[89]\d{2}|20[0-2]\d)\b")
_GOSTERGE = re.compile(
    r"J\. Fluid Mech|AIAA|NACA|NASA|ASME|Phys\. Fluids|Int\. J\.|J\. Fluids|"
    r"KSME|Theor\. Comput|Struct\. Multidisc|Comput\. Methods|Heat Fluid Flow|"
    r"Fluid-Dynamic Drag|Theory of Wing Sections|Trans\.|Rep\.|TM-|TN-|TR-")
_SUREC = re.compile(r"^--|mevcut case|yeniden üretilmedi|YENIDEN|okundu$|"
                    r"^GCI |^LSR |^ölçülen |^OpenFOAM \d")


def _literatur_mu(s: str) -> bool:
    s = s.strip()
    if len(s) < 20 or _SUREC.search(s):
        return False
    return bool(_YIL.search(s) and _GOSTERGE.search(s))


def topla(atlanan: list[str] | None = None) -> dict[str, set[str]]:
    """Kaynakları kanıt dosyalarından VE kod sabitlerinden topla.

    ATLANAN DOSYA SESSIZCE KAYBOLMAZ. Okunamayan ya da ayrıştırılamayan bir
    dosya, İÇİNDEKİ KAYNAKLARIN da kaybolması demektir; sebep `atlanan`
    listesine yazılır ve kanıt dosyasına geçer. ``Kaç kaynak bulundu''
    sorusunun yanında ``kaç dosya okunamadı'' durmazsa, eksik bir kaynakça
    tam görünür.
    """
    atlanan = [] if atlanan is None else atlanan
    bulunan: dict[str, set[str]] = {}
    kalip = re.compile(
        r'"(?:kaynak|kunye|referans|referans_kaynak|_kaynak|ref_kaynak|'
        r'span_kaynak|kaynak_adaylari|CD_KAYNAK|ST_KAYNAK)"'
        r'\s*:\s*"([^"]{20,})"')
    for p in KOK.glob("*.json"):
        # URETICI KENDI CIKTISINI KAYNAK YERI SAYMAZ: kaynakca.json
        # her kunyeyi zaten tasir ve her satirin yaninda kendi adi
        # cikardi --- bilgi tasimayan bir kendine-atif.
        if p.name == CIKTI.name:
            continue
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            atlanan.append(f"{p.name}: okunamadı ({type(e).__name__})")
            continue
        for m in kalip.findall(t):
            if _literatur_mu(m):
                bulunan.setdefault(m.strip(), set()).add(p.name)

    for d in (KOK, KOK / "experiments", KOK / "analysis"):
        for p in d.glob("*.py"):
            try:
                agac = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            except (SyntaxError, OSError) as e:
                atlanan.append(f"{p.name}: ayrıştırılamadı ({type(e).__name__})")
                continue
            for n in ast.walk(agac):
                if not isinstance(n, ast.Assign):
                    continue
                for hedef in n.targets:
                    if not (isinstance(hedef, ast.Name)
                            and hedef.id.endswith("KAYNAK")):
                        continue
                    try:
                        v = ast.literal_eval(n.value)
                    # sessiz-yutma: kabul — istisna BURADA eleme kriterinin
                    # kendisidir. `X_KAYNAK = f(...)` gibi HESAPLANAN bir deger
                    # sabit degildir ve kunye olamaz; "ayristirilamadi" diye
                    # kaydetmek, olmayan bir kusuru rapor etmek olurdu. Bilgi
                    # kaybi yok: aranan sey zaten yalnizca sabit dizgilerdir.
                    except (ValueError, SyntaxError):
                        continue
                    if isinstance(v, str) and _literatur_mu(v):
                        bulunan.setdefault(v.strip(), set()).add(
                            f"{p.name}:{hedef.id}")
    return bulunan


def _kacir(s: str) -> str:
    """LaTeX'e girecek metni kaçır — kaynak metni SERBEST yazılmıştır.

    Künyeler kanıt dosyalarından geldiği için matematik sembolü (π, ≈, ×)
    ve tipografik tırnak taşıyabilir; ilk sürüm bunları geçirdi ve derleme
    ``Unicode character π'' hatası verdi. Üretilen bir dosyanın derlenmemesi,
    üretilmemiş olmasıyla aynı kapıya çıkar.
    """
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                 ("_", r"\_"), ("#", r"\#"), ("$", r"\$"), ("{", r"\{"),
                 ("}", r"\}"), ("~", r"\textasciitilde{}"),
                 ("^", r"\textasciicircum{}")):
        s = s.replace(a, b)
    for a, b in (("π", r"$\pi$"), ("≈", r"$\approx$"), ("×", r"$\times$"),
                 ("≤", r"$\leq$"), ("≥", r"$\geq$"), ("−", "--"),
                 ("’", "'"), ("‘", "'"), ("“", "``"), ("”", "''"),
                 ("σ", r"$\sigma$"), ("Δ", r"$\Delta$"), ("δ", r"$\delta$"),
                 ("α", r"$\alpha$"), ("θ", r"$\theta$"), ("μ", r"$\mu$"),
                 ("±", r"$\pm$"), ("→", r"$\rightarrow$"), ("…", "\\dots")):
        s = s.replace(a, b)
    return s


def _sirala(s: str) -> tuple:
    """Yazar soyadına göre sırala; bulunamazsa metnin kendisi."""
    m = re.match(r"([A-ZÇĞİÖŞÜ][\w'’-]+)", s.strip())
    return (m.group(1).lower() if m else s.lower(), s.lower())


def _anahtar(s: str) -> str:
    """Mükerrer künyeleri birleştirmek için imza: ilk yazar + ilk yıl.

    Aynı kaynak iki kanıt dosyasında biraz farklı yazılmış olabilir
    (``Hoerner 1965, Fluid-Dynamic Drag'' ve aynısının ``; Re>1e4...''
    ekli hâli). İkisini ayrı kaynak saymak, kaynakçayı olduğundan
    kalabalık gösterirdi.
    """
    m = re.match(r"([A-ZÇĞİÖŞÜ][\w'’-]+)", s.strip())
    y = _YIL.search(s)
    return f"{(m.group(1).lower() if m else s[:12].lower())}|{y.group(1) if y else ''}"


def uret() -> dict:
    atlanan: list[str] = []
    ham = topla(atlanan)
    b: dict[str, set[str]] = {}
    _imza: dict[str, str] = {}
    for k in sorted(ham, key=len, reverse=True):
        a = _anahtar(k)
        if a in _imza:
            b[_imza[a]] |= ham[k]      # kisa varyanti UZUN kunyeye kat
        else:
            _imza[a] = k
            b[k] = set(ham[k])
    kayitlar = sorted(b, key=_sirala)
    satirlar = [
        "% ÜRETİLMİŞTİR — elle düzenlemeyin.",
        "% Üretim: python experiments/kaynakca.py",
        "% Kaynaklar çapa kayıtlarının `kaynak` alanlarından ve kod",
        "% sabitlerinden (*_KAYNAK) toplanır; elle yazılan bir liste,",
        "% bir çapa yeni referansa taşındığında sessizce eskirdi.",
        "\\begin{thebibliography}{99}",
    ]
    for i, k in enumerate(kayitlar, 1):
        nerede = ", ".join(sorted(b[k])[:3])
        satirlar.append(f"\\bibitem{{kaynak{i}}} {_kacir(k)}"
                        f"\\quad{{\\scriptsize[{_kacir(nerede)}]}}")
    satirlar.append("\\end{thebibliography}")
    TEX.write_text("\n".join(satirlar) + "\n", encoding="utf-8")

    kayit = {
        "vaka": "Kaynakça — kanıt kayıtlarından ve kod sabitlerinden üretildi",
        "_neden": ("Rapor onlarca literatur kaynagi kullaniyordu ama ayri bir "
                   "kaynakca bolumu YOKTU (dis inceleme yakaladi). Elle liste "
                   "yazmak, raporun kendi avladigi kusuru islemek olurdu: "
                   "sabit metin, degisen veri."),
        "kaynak_sayisi": len(kayitlar),
        "atlanan_dosya": atlanan or None,
        "verdikt": (
            f"{len(kayitlar)} kaynak üretildi ve rapora bağlandı. Künyeler "
            f"çapa kayıtlarının `kaynak` alanlarından ve kod sabitlerinden "
            f"gelir; elle yazılmış bir liste, bir çapa yeni referansa "
            f"taşındığında sessizce eskirdi. DOI TAMAMLANMAMIŞTIR ve bu "
            f"kasıtlıdır --- yayına giderken her künye birincil kaynaktan "
            f"doğrulanmalıdır."),
        "kaynaklar": [{"kunye": k, "gectigi_yer": sorted(b[k])} for k in kayitlar],
        "_kisit": ("DOI UYDURULMAZ: kayitta ne varsa o basilir. Eksik kunye "
                   "EKSIK GORUNUR ve bu kasitlidir --- tamamlanmis gibi "
                   "gorunen bir kaynakca, tamamlanmamis olandan tehlikelidir. "
                   "Yayina giderken her kunye birincil kaynaktan (Crossref) "
                   "dogrulanmalidir."),
        "_uretim": "Üretim: python experiments/kaynakca.py",
    }
    import ortam
    ortam.damgala(kayit)
    CIKTI.write_text(json.dumps(kayit, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    return kayit


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = uret()
    print(f"{r['kaynak_sayisi']} kaynak -> {TEX.name}, {CIKTI.name}")
    for k in r["kaynaklar"]:
        print("  ", k["kunye"][:95])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
