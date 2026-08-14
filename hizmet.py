"""Başsız hizmet katmanı — CLI ve REST'in ORTAK çekirdeği.

NEDEN TEK İŞLEV: bu depoda "aynı motorun iki kullanıcısı farklı yetenek alıyor"
kusuru üç kez ölçüldü (`ref_bump` beş çağıranın birine ulaşmıştı; `duzeltici`
ANALİZ ET düğmesine eklenip kuyruğa eklenmemişti; `app_parametric` çözücüyü hiç
çağırmadan "tamamlandı" yazıyordu). CLI ile REST ayrı ayrı yazılırsa aynı şey
dördüncü kez olur. İkisi de `analiz_et`'i çağırır; başka yol yoktur.

ÇIKTI SÖZLEŞMESİ: dönen sözlük JSON-serileştirilebilir olmalıdır. Karar
katmanının nesneleri (Verdict, DuzelticiSonuc) burada düz veriye çevrilir —
tarayıcı ya da başka bir dil onları göremez.

Kullanım:
    python cli.py --stl model.stl --tip ucak --hiz 30 --duzeltici
    uvicorn api:app        (POST /analiz)
"""
from __future__ import annotations

from typing import Any

SURUM = "1.0"


def _verdict_dict(v) -> dict:
    return {"nicelik": v.quantity, "sinif": v.klass,
            "tasarimda_kullanilir": bool(v.design_safe), "gerekce": v.message}


def _duzeltici_dict(s) -> dict | None:
    """DuzelticiSonuc → düz veri. None ise düzeltici kapalıydı."""
    if s is None:
        return None
    return {
        "sinif": s.sinif,
        "verdikt": s.verdikt,
        "etkisiz_sayisi": s.etkisiz_sayisi,
        "mudahaleler": [
            {"duzeltme": m.duzeltme, "degisiklik": m.degisiklik,
             "onceki_hata_pct": m.onceki_hata_pct,
             "sonraki_hata_pct": m.sonraki_hata_pct,
             "ise_yaradi": m.ise_yaradi, "yan_etki": m.yan_etki}
            for m in s.mudahaleler],
        # Tespit edilip düzeltilemeyenler ÇIKTIDA kalır: bir istemci "kusur yok"
        # ile "kusur var ama elimden gelmedi"yi ayırt edebilmelidir.
        "engellenenler": [{"duzeltme": ad, "neden": neden}
                          for ad, neden in s.engellenenler],
    }


def analiz_et(stl_path: str, *, duzeltici: bool = False,
              referans_cd: float | None = None, **kw) -> dict[str, Any]:
    """Bir araç analizi koş ve JSON'a hazır sonuç döndür.

    `duzeltici=True` ise kurulum kusurları onarılıp yeniden koşulur; hangi
    müdahalelerin yapıldığı ve hangilerinin YAPILAMADIĞI çıktıdadır.
    """
    from validity_envelope import (
        MACH_INCOMP,
        apply_physics_gate,
        classify_cfd,
        overall_class,
    )

    duz = None
    if duzeltici:
        from duzeltici_adaptor import duzelterek_analiz
        r, duz = duzelterek_analiz(stl_path, referans=referans_cd, **kw)
    else:
        from vehicle_pipeline import run_vehicle_analysis
        r = run_vehicle_analysis(stl_path, **kw)

    if r.status != "ok":
        return {"surum": SURUM, "durum": "hata",
                "hata": r.error or "bilinmeyen", "case_dir": r.case_dir}

    ma = (r.velocity or 0.0) / 340.0
    mds = getattr(r, "mesh_duyarlilik", None) or {}
    gci_ok = bool(mds.get("gci")) and str(mds.get("verdikt", "")).startswith("✅")
    v = classify_cfd(r.vehicle_type, r.alpha_deg, ma, has_gci_band=gci_ok,
                     band_pct=mds.get("fark_pct"), Cl=r.cl, Cd=r.cd)
    v = apply_physics_gate(v, getattr(r, "fizik_kabul", None) or {})

    return {
        "surum": SURUM,
        "durum": "ok",
        "girdi": {"stl": str(stl_path), "tip": r.vehicle_type,
                  "hiz_ms": r.velocity, "alpha_deg": r.alpha_deg,
                  "mach": round(ma, 4), "sikisabilir": ma >= MACH_INCOMP},
        "sonuc": {"cd": r.cd, "cl": r.cl, "ld": r.ld, "aref_m2": r.aref_m2,
                  "surukleme_N": r.drag_N},
        # SINIF SAYIYLA BIRLIKTE GIDER. Çıplak bir Cd döndürmek, bu aracın
        # varlık nedenine aykırıdır: istemci hangi sayının tasarım kararında
        # kullanılabileceğini çıktının kendisinden bilmelidir.
        "gecerlilik": {"genel": overall_class(v),
                       "nicelikler": [_verdict_dict(x) for x in v]},
        "belirsizlik": r.belirsizlik,
        "mesh": r.mesh,
        "yakinsama": r.convergence,
        "duzeltici": _duzeltici_dict(duz),
        "uyarilar": list(getattr(r, "uyarilar", None) or []),
        "case_dir": r.case_dir,
        "rapor": r.report,
    }
