"""Korumasız ithal edilen her paket `pyproject.toml`'da İLAN EDİLMİŞ olmalı.

NEDEN VAR: `meshio` (analysis/tet_mesher.py) ve `vtk` (farfield_drag.py) çekirdek
yollarda korumasız ithal ediliyordu ama bağımlılık listesinde YOKTU. Geliştirme
makinesinde ikisi de kurulu olduğu için hiçbir test bunu göremedi; kusur ancak
konteyner temiz-odasında ortaya çıktı (2026-08-15) ve o da inşa sırasında değil,
worker gerçek bir iş koşarken.

Bu testin yakaladığı kusur sınıfı şudur: YEREL ORTAM, EKSİK BEYANI MASKELER.
Temiz bir `pip install .` yapan herkeste (konteyner, CI, yeni geliştirici) yol
kırık gelir ve hata mesajı kaynağı göstermez.

Korumalı (try/except ImportError) ithaller kapsam dışıdır: onlar bilinçli olarak
isteğe bağlıdır ve modül eksikliğinde kendi yedeğine düşer.
"""
import ast
import sys
import tomllib
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def _taranacak() -> list[Path]:
    """Yalnız GIT'IN IZLEDIGI .py dosyaları taranır.

    Çalışma dizininde başka projelere ait, `.gitignore`'da olan betikler
    bulunabiliyor (ör. `revise_1001_panel.py` -> `docx`). Onların bağımlılığı
    bu projenin beyanına girmez; taramaya dahil etmek yanlış pozitif üretir ve
    yanlış pozitif üreten denetim kullanılmaz hale gelir.
    """
    import subprocess
    r = subprocess.run(["git", "-C", str(KOK), "ls-files", ":(glob)*.py",
                        ":(glob)analysis/*.py"], capture_output=True, text=True)
    if r.returncode != 0:                     # git yoksa: tüm dosyalara düş
        return list(KOK.glob("*.py")) + list((KOK / "analysis").glob("*.py"))
    return [KOK / s for s in r.stdout.split() if (KOK / s).exists()]


def _yerel_modul_adlari() -> set[str]:
    """Depodaki HER .py'nin kök adı yerel modüldür (experiments/, tests/ dahil).

    Yalnız kök dizine bakmak yetmiyordu: `experiments/` içindeki modüller
    birbirini ithal ediyor ve tarama onları "beyan edilmemiş paket" sanıyordu.
    """
    return ({p.stem for p in KOK.rglob("*.py")}
            | {"analysis", "solvers", "post_processing", "tests", "experiments"})

# Yalnız KÖPRÜ modülleri tarafından ithal edilen dış araçlar. Başsız yol bunlara
# dokunmaz; kuran kullanıcı o köprüyü bilerek kullanır. Beyan zorunlu değil ama
# liste BURADA tutulur ki "unuttuk" ile "bilerek dışarıda" ayrılabilsin.
KOPRU_ARACLARI = {
    "NXOpen":   "Siemens NX içinde çalışır; pip paketi değildir",
    "openvsp":  "OpenVSP kurulumuyla gelir (openvsp_bridge.py)",
    "orhelper": "OpenRocket/JPype köprüsü (openrocket_bridge.py)",
    "pyvista":  "yalnız masaüstü sonuç görüntüleyici (result_viewer.py)",
}
# matplotlib'in parçası; ayrı paket değil.
IC_PAKETLER = {"mpl_toolkits"}


def _ilan_edilenler() -> set[str]:
    pp = tomllib.loads((KOK / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    ham = list(pp["dependencies"])
    for v in pp.get("optional-dependencies", {}).values():
        ham += v
    ad = set()
    for d in ham:
        k = d.split(">")[0].split("=")[0].split("[")[0].strip().lower().replace("-", "_")
        ad.add(k)
    # Dağıtım adı ile ithal adı ayrışan paketler.
    ad |= {"yaml", "pil"}          # pyyaml, Pillow
    return ad


def _korumasiz_ithaller(dosya: Path) -> set[str]:
    """Modül düzeyinde ve try/except DIŞINDA ithal edilen kök paket adları."""
    # BOM'lu dosyalar var (revise_1001_panel.py gibi); utf-8-sig okuması
    # BOM'u düşürür, aksi halde ast.parse "U+FEFF" ile patlar.
    agac = ast.parse(dosya.read_text(encoding="utf-8-sig"))
    korumali: set[str] = set()
    for n in ast.walk(agac):
        if isinstance(n, ast.Try):
            for c in ast.walk(n):
                if isinstance(c, ast.Import):
                    korumali |= {a.name.split(".")[0] for a in c.names}
                elif isinstance(c, ast.ImportFrom) and c.level == 0:
                    korumali.add((c.module or "").split(".")[0])
    bulunan: set[str] = set()
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            bulunan |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0:
            bulunan.add((n.module or "").split(".")[0])
    return bulunan - korumali


def test_korumasiz_ithaller_PYPROJECT_te_ILAN_EDILMIS():
    std = set(sys.stdlib_module_names)
    ilan = _ilan_edilenler()
    yerel = _yerel_modul_adlari()

    eksik: dict[str, set[str]] = {}
    for f in _taranacak():
        for a in _korumasiz_ithaller(f):
            k = a.lower().replace("-", "_")
            if (not a or k in std or k in yerel or k in ilan
                    or a in KOPRU_ARACLARI or a in IC_PAKETLER):
                continue
            eksik.setdefault(a, set()).add(f.name)

    assert not eksik, (
        "korumasız ithal edilen ama pyproject'te İLAN EDİLMEYEN paket(ler): "
        + "; ".join(f"{k} <- {sorted(v)}" for k, v in sorted(eksik.items()))
        + ". Ya bağımlılık listesine ekleyin, ya try/except ile isteğe bağlı "
          "yapın, ya da köprü aracıysa KOPRU_ARACLARI'na gerekçesiyle yazın.")


def test_KOPRU_listesi_GERCEKTEN_kullanilmayanlari_tasimasin():
    """Liste bir çöplük olmamalı: artık ithal edilmeyen bir ad burada kalırsa,
    gelecekte gerçek bir eksik beyanı maskeleyebilir."""
    # Canlılık kontrolü TÜM izlenen dosyalara bakar, yalnız taranan alt kümeye
    # değil: köprü araçları `experiments/` altında da ithal ediliyor (NXOpen ->
    # experiments/nx_geometri_uret.py) ve dar kapsam onu "ölü" sanıyordu.
    import subprocess
    r = subprocess.run(["git", "-C", str(KOK), "ls-files", ":(glob)**/*.py"],
                       capture_output=True, text=True)
    dosyalar = ([KOK / s for s in r.stdout.split() if (KOK / s).exists()]
                if r.returncode == 0 else list(KOK.rglob("*.py")))
    tum: set[str] = set()
    for f in dosyalar:
        tum |= _korumasiz_ithaller(f)
    olu = set(KOPRU_ARACLARI) - tum
    assert not olu, f"KOPRU_ARACLARI'nda artık ithal edilmeyen ad(lar): {sorted(olu)}"
