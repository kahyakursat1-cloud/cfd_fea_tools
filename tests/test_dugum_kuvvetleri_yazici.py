"""Üretilen `.inp` ELLE DÜZENLENMEZ --- yükler yazıcının kendi yolundan.

BU KUSUR SESSİZDİ VE PATLAMASI AN MESELESİYDİ. Üç yer üretilen girdi
metnini düzenliyordu:

    txt.replace("*STATIC", "*STATIC\\n" + cload, 1)

Lineer bir adımda `*STATIC` tek satırdır ve enjeksiyon çalışır. NLGEOM ya
da DYNAMIC açıldığında ise `*STATIC` bir ARTIM SATIRI taşır (``0.1, 1.0'')
ve enjeksiyon onu CLOAD bloğunun içine iter; CalculiX girdiyi reddeder.
Turek--Hron CSM1'de tam bu oldu ve ders oradan geldi --- ama aynı desen
üretim yolunda (`vehicle_fea`) da duruyordu, yani NLGEOM'un GUI'ye
taşındığı gün patlayacaktı.

KÖK SEBEP BİR EKSİK YETENEKTİ: `ForceLoad` bir TOPLAM kuvveti tek yönde
düğümlere eşit dağıtır; FSI aktarımının ürettiği yük ise düğüm başına ayrı
ve üç bileşenlidir. O sınıfla ifade edilemediği için herkes metni
düzenliyordu. `FEACase.dugum_kuvvetleri` bu boşluğu kapatır.

Testler HEM yeteneği HEM de eski desenin geri gelmemesini bağlar.
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from analysis.calculix_writer import (  # noqa: E402
    FEACase,
    FEAMaterial,
    FixedBC,
    write_inp,
)


def _mesh():
    from turek_hron_fsi1 import _bayrak_agi
    return _bayrak_agi()


def _yaz(nlgeom: bool, yuk: dict) -> str:
    mesh = _mesh()
    case = FEACase(
        name="t", mesh=mesh,
        material=FEAMaterial(name="m", youngs_modulus_pa=1.4e6,
                             poisson_ratio=0.4, density_kg_m3=1000.0),
        fixed_bcs=[FixedBC(node_ids=np.array([1, 2, 3]))],
        dugum_kuvvetleri=yuk, nlgeom=nlgeom, max_artim_sayisi=20)
    with tempfile.TemporaryDirectory() as d:
        return write_inp(case, Path(d)).read_text(encoding="utf-8")


def test_DUGUM_KUVVETLERI_CLOAD_OLARAK_YAZILIYOR():
    t = _yaz(False, {5: (1.0, -2.0, 0.0), 9: (0.0, 3.0, 0.0)})
    assert "*CLOAD" in t
    for satir in ("5, 1, 1.000000e+00", "5, 2, -2.000000e+00",
                  "9, 2, 3.000000e+00"):
        assert satir in t, f"{satir} yazılmamış"
    # SIFIR BILESEN YAZILMAZ --- gereksiz satir, ama daha onemlisi
    # "0 kuvvet uygulandi" ile "kuvvet uygulanmadi" ayni gorunmesin.
    assert "9, 1," not in t


def test_NLGEOM_ARTIM_SATIRI_BOZULMUYOR():
    """ASIL KUSURUN TESTİ. `*STATIC`'in artım satırı yerinde kalmalı ve
    yük blokları ONDAN SONRA gelmeli; ters sırada CalculiX girdiyi
    reddeder."""
    t = _yaz(True, {5: (1.0, 0.0, 0.0)})
    i_static = t.index("*STATIC")
    i_artim = t.index("0.1, 1.0")
    i_cload = t.index("*CLOAD")
    assert i_static < i_artim < i_cload, (
        "artım satırı `*STATIC` ile yük bloğunun ARASINDA olmalı; "
        f"sıra {i_static} / {i_artim} / {i_cload}")
    # Ve artim satiri BASKA bir blogun verisi gibi gorunmemeli.
    arasi = t[i_artim:i_cload]
    assert "*BOUNDARY" not in arasi.split("\n")[0]


def test_LINEER_ADIMDA_ARTIM_SATIRI_YOK():
    """Ölçütün yanlış-pozitif tarafı: lineer adımda artım satırı zaten
    yoktur ve bu bir kusur değildir."""
    t = _yaz(False, {5: (1.0, 0.0, 0.0)})
    i = t.index("*STATIC")
    assert t[i:i + 40].split("\n")[1].startswith("*"), (
        "lineer `*STATIC` altında veri satırı olmamalı")


def test_URETILEN_INP_ELLE_DUZENLENMIYOR():
    """Eski desenin geri gelmemesi. Ölçüt METNE değil MEKANİZMAYA
    bağlanır: `write_inp`'ten doğan yola geri yazan bir çağrı olmamalı.

    (Bu ölçüt bu depoda bir kez fazla geniş kuruldu --- kaynakta
    `"*BOUNDARY"` geçmesin denmiş ve kendi açıklama satırını suçlamıştı.
    Bu yüzden AST kullanılıyor.)
    """
    for ad in ("vehicle_fea.py", "experiments/turek_hron_fsi1.py",
               "experiments/turek_hron_csm1.py",
               "experiments/turek_hron_csm3.py"):
        yol = KOK / ad
        if not yol.exists():
            continue
        agac = ast.parse(yol.read_text(encoding="utf-8"))
        inp_adlari = {
            t.id for n in ast.walk(agac) if isinstance(n, ast.Assign)
            for t in n.targets if isinstance(t, ast.Name)
            if isinstance(n.value, ast.Call)
            and getattr(n.value.func, "id", "") == "write_inp"}
        kirli = [n for n in ast.walk(agac)
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr in ("write_text", "read_text")
                 and getattr(n.func.value, "id", None) in inp_adlari]
        assert not kirli, (
            f"{ad}: üretilen .inp'ye geri yazılıyor/okunuyor --- NLGEOM ya "
            "da DYNAMIC açıldığında `*STATIC` artım satırını bozar")


def test_DUZLEM_GERINIM_de_YAZICI_YOLUYLA():
    """FSI1'in z kısıtı da elle enjekte ediliyordu; artık FixedBC."""
    src = (KOK / "experiments" / "turek_hron_fsi1.py").read_text(
        encoding="utf-8")
    assert 'name="ZDUZLEM"' in src and "dof_start=3" in src


def test_BOS_YUK_SOZLUGU_CLOAD_URETMIYOR():
    """`0.0` yük ile 'yük yok' ayrı kalmalı: boş sözlükte CLOAD bloğu hiç
    olmamalı, yoksa okur yükün uygulandığını sanır."""
    t = _yaz(False, {})
    assert "*CLOAD" not in t
