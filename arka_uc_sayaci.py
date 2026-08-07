"""Arka uç katmanını atlayan çağrıların sayacı — artmasın diye.

NEDEN: `analysis/backend.py` çözücünün nerede koşacağını tek yerden seçer
(WSL ya da Docker konteyneri, `CFD_BACKEND`). Ama kök dizindeki birçok betik
`wsl bash -c` çağrısını ELLE kuruyor ve o katmanı atlıyor. Sonuç sessizdir ve
tehlikelidir: `CFD_BACKEND=docker` ayarlandığında araç hattı konteynere
giderken bu betikler WSL'de kalır — aynı kampanyanın iki yarısı FARKLI
çözücülerde koşabilir ve kanıt dosyaları bunu söylemez. WSL distro seçimi de
atlanır.

DURUM: 36 çağrı / 25 dosya ile başladı, 9 çağrı / 2 dosyaya indi. Taşınanların
hepsinde bash GÖVDESİ aynen korundu; değişen yalnız taşımadır.

KALAN İKİSİ İNCELENDİ VE BEKLETİLDİ (bkz. BEKLEYEN): biri etkileşimli süreç ve
elle süreç-ağacı yoklaması yapıyor, öbürü login kabuk (`bash -lc`) gerektiriyor.
İkisi de taşınabilir ama davranış eşdeğerliği ÖLÇÜLMEDEN değil.

SAYAÇ KALIYOR: yeni kod bu sayıyı ARTIRAMAZ; taşınan her modül tabanı düşürür.
`sessiz_yutma` sayacıyla aynı desen — depo bu mekanizmayı zaten kullanıyor.

    python arka_uc_sayaci.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent

# Tasima katmanini MESRU olarak kuran tek yer; sayilmaz.
MUAF = {"analysis/backend.py", "arka_uc_sayaci.py"}

# INCELENDI VE BEKLETILDI — her birinin gerekcesi ayri. Bu bir muafiyet DEGIL:
# sayaci dusurmezler, sadece "neden hala burada" sorusunun cevabi kodda durur.
# Tasima riskleri olculmemis oldugu icin bekliyorlar, unutuldugu icin degil.
BEKLEYEN = {
    "construct2d_bridge.py": (
        "Etkilesimli surec: printf ile stdin besleniyor ve p3d cikana kadar "
        "`pgrep` ile surec agaci elle yoklaniyor (olculmus yaris durumu: "
        "sarmalayici, construct2d hala kosarken donuyordu ve NACA2412 defalarca "
        "'mesh uretilemedi' raporladi). Tasima, stdin ve surec-gorunurlugu "
        "davranisini degistirebilir; once esdegerlik olculmeli."),
    "xfoil_kesit.py": (
        "`bash -lc` (LOGIN kabuk) kullaniyor: XFOIL yolu kullanicinin profil "
        "dosyalarindan geliyor. linux_argv `bash -c` kurar ve PATH farkli olur — "
        "xfoil 'bulunamadi' diye duserdi. Once backend'e login-kabuk secenegi "
        "eklenmeli, sonra tasinmali."),
}
DESEN = re.compile(r"""wsl["'\s]*bash\s+-c|\[\s*["']wsl["']\s*,""")


def _kaynak_dosyalari() -> list[Path]:
    out = []
    for p in sorted(KOK.rglob("*.py")):
        r = p.relative_to(KOK).as_posix()
        if r.startswith(("tests/", ".venv/", "_")) or "site-packages" in r:
            continue
        out.append(p)
    return out


def _docstring_satirlari(kaynak: str) -> set[int]:
    """Docstring'lerin kapladığı satır numaraları.

    ARACIN KENDI YANLIS POZITIFI: bir modül taşındıktan sonra `wsl bash -c`
    ifadesi yalnız docstring'de kaldı ("eskiden şöyle kuruyordu") ve sayaç onu
    hâlâ atlanan bir çağrı sanıyordu. Gerekçe yazan METIN, kod değildir —
    tersini kabul etmek, aracı memnun etmek için açıklamayı bulanıklaştırmayı
    ödüllendirirdi.
    """
    import ast
    try:
        agac = ast.parse(kaynak)
    except SyntaxError:
        return set()
    satir: set[int] = set()
    for d in ast.walk(agac):
        if (isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant)
                and isinstance(d.value.value, str) and d.end_lineno):
            satir.update(range(d.lineno, d.end_lineno + 1))
    return satir


def tara() -> list[dict]:
    """Arka uç katmanını atlayan her satır (yorum ve docstring HARİÇ)."""
    bulgu = []
    for p in _kaynak_dosyalari():
        rel = p.relative_to(KOK).as_posix()
        if rel in MUAF:
            continue
        kaynak = p.read_text(encoding="utf-8", errors="replace")
        belge = _docstring_satirlari(kaynak)
        for i, satir in enumerate(kaynak.splitlines(), 1):
            if satir.lstrip().startswith("#") or i in belge:
                continue          # gerekçe yazan yorum/docstring sayılmaz
            if DESEN.search(satir):
                bulgu.append({"dosya": rel, "satir": i,
                              "kod": satir.strip()[:100]})
    return bulgu


def ozet() -> dict:
    b = tara()
    dosyalar: dict[str, int] = {}
    for x in b:
        dosyalar[x["dosya"]] = dosyalar.get(x["dosya"], 0) + 1
    return {"toplam": len(b), "dosya_sayisi": len(dosyalar),
            "dosyalar": dict(sorted(dosyalar.items())), "bulgular": b}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    o = ozet()
    print(f"Arka uç katmanını atlayan çağrı: {o['toplam']} satır, "
          f"{o['dosya_sayisi']} dosya\n")
    for d, n in o["dosyalar"].items():
        print(f"  {n:>3}  {d}" + ("   [bekliyor — gerekçe kodda]"
                                     if d in BEKLEYEN else ""))
    print("\nTaşıma: yerel `wsl bash -c` kurulumunu analysis.backend.linux_run "
          "ile değiştirin; bash gövdesi AYNEN kalır, değişen yalnız taşımadır.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
