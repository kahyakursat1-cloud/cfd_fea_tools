"""İki-yönlü FSI'nin ÜRETİM GİRİŞİ var mı.

ÖLÇÜLDÜ (2026-08-22): `fsi_surucu` bir vakanın `CFDCase(mesh_motion=True)` ile
kurulmuş olmasını ZORLUYOR --- doğru bir kapı, çünkü hareketsiz bir vakada
çözmek kuplaj turunu sessizce TEK-YÖNLÜ yapardı. Ama depo tarandığında
`mesh_motion=True` diyen tek yer TESTLERDİ. Araç hattı bu bayrağı hiç
geçirmiyordu; elde duran iki FSI vakası da hattan değil, artık var olmayan bir
betikten gelmişti.

Yani savunma doğruydu ve kendisine yem verecek üretim yolu YOKTU. Bu deponun
baskın kusurunun (kapı var, üretim yolu ondan geçmiyor) ters yöndeki biçimi:
kapı var, kapıdan geçebilecek girdiyi üretecek yol yok.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))


def test_arac_hatti_mesh_motion_PARAMETRESI_tasiyor():
    from vehicle_pipeline import run_vehicle_analysis
    p = inspect.signature(run_vehicle_analysis).parameters
    assert "mesh_motion" in p, (
        "araç hattı hareketli ağ kuramıyor — iki-yönlü FSI vakası ÜRETİLEMEZ "
        "ve fsi_surucu'nun kapısı hiçbir zaman beslenemez")
    assert p["mesh_motion"].default is False, (
        "varsayılan True olamaz: hareketli ağ her koşuya maliyet bindirir")


def test_bayrak_CFDCase_e_gercekten_GECIYOR():
    """Parametrenin var olması yetmez; case'e ULAŞMALI.

    Metin araması değil AST: `mesh_motion=mesh_motion` dizisi bir yorumda da
    geçebilir ve bu depoda tam o kusur (kendi açıklayıcı yorumuyla eşleşen
    test) daha önce yaşandı.
    """
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    gecen = []
    for d in ast.walk(ast.parse(src)):
        if not (isinstance(d, ast.Call)
                and getattr(d.func, "id", None) == "CFDCase"):
            continue
        for k in d.keywords:
            if k.arg == "mesh_motion":
                gecen.append(isinstance(k.value, ast.Name)
                             and k.value.id == "mesh_motion")
    assert gecen, "CFDCase çağrısına mesh_motion hiç geçirilmiyor"
    assert any(gecen), "mesh_motion sabitle geçiliyor — çağıranın seçimi ulaşmıyor"


def test_SURUCUNUN_KAPISI_hala_duruyor():
    """Üretim girişi açıldı diye kapı gevşetilmemeli.

    Hareketsiz bir vakayı kuplaj turuna sokmak, turu sessizce tek-yönlü yapar
    ve `fsi_kos` "yakınsadı" der. Kapı bunun tek koruması.
    """
    src = (KOK / "analysis" / "openfoam_runner.py").read_text(encoding="utf-8")
    i = src.index("def run_cfd_yeniden(")
    govde = src[i:i + 4000]
    assert "dynamicMeshDict" in govde and "pointDisplacement" in govde, (
        "ağ hareketi ön koşulu kaldırılmış — kuplaj turu sessizce tek-yönlü "
        "olabilir")
    assert "FileNotFoundError" in govde, "ret SERT olmalı, sessiz dönüş değil"
