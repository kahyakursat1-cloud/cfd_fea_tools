"""CalculiX düğüm numarası KONUMA göre mi bağlanıyor, indise göre mi?

ÖLÇÜLEN KUSUR (2026-08-26): `cfd_pressure_to_fea_loads` düğüm anahtarını STL
köşe İNDİSİNDEN üretiyor (`i+1`) ve `write_cload` onu doğrudan CalculiX düğüm
numarası olarak yazıyordu. Bu, iki ağın düğümleri AYNI SIRADA yazdığını
varsayar --- ve varsayım YANLIŞ:

    beş FSI vakasının HEPSİNDE ilk 8 düğüm STL'in 8 köşesinin ta kendisi
    ama SIRALARI FARKLI; köşe 4 ile 7 yer değişmiş.

Yani iki köşenin yükü YANLIŞ KONUMA biniyordu. Ölçülen etki o vakalarda
küçüktü (moment hatası %0,010; kayan iki köşe birbirine yakın ve yükleri
benzer) ve bu ABARTILMAMALI --- ama bir tesadüftür, güvence değil: köşe sayısı
arttıkça permütasyon keyfîleşir ve etki ölçülmemiştir.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from coupling_fsi import dugum_eslemesi  # noqa: E402


def _inp(tmp: Path, koor: list[tuple[int, tuple]]) -> Path:
    s = ["*NODE, NSET=NALL"]
    s += [f"{n}, {x:.9e}, {y:.9e}, {z:.9e}" for n, (x, y, z) in koor]
    s.append("*ELEMENT, TYPE=C3D10, ELSET=EALL")
    p = tmp / "d.inp"
    p.write_text("\n".join(s))
    return p


def test_PERMUTE_edilmis_siralama_dogru_cozuluyor(tmp_path):
    """Testin var oluş sebebi: sıra farklıysa indis bağlaması yanlış düğüme
    yazar. Konum bağlaması permütasyonu çözmeli."""
    v = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])
    # inp'te 2. ve 4. dugum YER DEGISMIS
    p = _inp(tmp_path, [(1, (0, 0, 0)), (2, (0, 0, 1)),
                        (3, (0, 1, 0)), (4, (1, 0, 0))])
    m = dugum_eslemesi(v, str(p))
    assert m == {1: 1, 2: 4, 3: 3, 4: 2}, m
    assert sum(1 for a, b in m.items() if a != b) == 2


def test_ozdes_siralamada_KIMLIK(tmp_path):
    v = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]])
    p = _inp(tmp_path, [(1, (0, 0, 0)), (2, (1, 0, 0)), (3, (0, 1, 0))])
    assert dugum_eslemesi(v, str(p)) == {1: 1, 2: 2, 3: 3}


def test_ESLESMEYEN_kose_SESSIZCE_atlanmiyor(tmp_path):
    """Sözlükte yoksa çağıran görür; uydurulmuş bir eşleşme, yükü rastgele
    bir düğüme bindirirdi."""
    v = np.array([[0.0, 0, 0], [99.0, 99, 99]])
    p = _inp(tmp_path, [(1, (0, 0, 0)), (2, (1, 0, 0))])
    m = dugum_eslemesi(v, str(p))
    assert 1 in m and 2 not in m, m


def test_TOLERANS_agin_olceginden(tmp_path):
    """Mutlak bir metre değeri, milimetrik modelde her şeyi eşleştirir,
    metrelik modelde hiçbir şeyi."""
    v = np.array([[0.0, 0, 0], [1e-3, 0, 0]])
    p = _inp(tmp_path, [(1, (0, 0, 0)), (2, (1e-3, 0, 0))])
    assert len(dugum_eslemesi(v, str(p))) == 2


def test_URETIM_YOLU_konuma_gore_bagliyor():
    src = (KOK / "fsi_surucu.py").read_text(encoding="utf-8")
    assert "dugum_eslemesi(" in src, "sürücü konum eşlemesini çağırmıyor"
    i = src.index("dugum_eslemesi(")
    blok = src[i - 300:i + 600]
    assert "write_cload" in blok, "eşleme cload yazımından ÖNCE uygulanmıyor"
    assert "dugum_eslemesi" in src[:src.index("def fsi_kos")], "ithal edilmemiş"


def test_gercek_vakalarda_KAYMA_var():
    """Bulgunun dayanağı arşivden okunur; arşiv yoksa iddia da yok."""
    import trimesh
    bulunan = 0
    for inp_p in sorted((KOK / "vehicle_runs").glob("*/fea/*.inp")):
        sj = inp_p.parent.parent / "sonuc.json"
        if not sj.exists():
            continue
        d = json.loads(sj.read_text(encoding="utf-8"))
        stl = d.get("stl")
        if not stl or not Path(stl).exists():
            continue
        v = np.asarray(trimesh.load(stl, force="mesh").vertices)
        m = dugum_eslemesi(v, str(inp_p))
        if m:
            bulunan += 1
            assert len(m) == len(v), f"{inp_p}: {len(m)}/{len(v)} eşleşti"
    if bulunan == 0:
        pytest.skip("FEA girdisi olan vaka yok (gitignore)")
