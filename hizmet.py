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


def _verdict_dict(v, dil: str = "tr") -> dict:
    """Hükmü sözleşmeye çevir.

    `kod` HER ZAMAN döner ve dile bağlı DEĞİLDİR: çeviri eksik olsa bile
    tüketici hükmü makine düzeyinde ayırt edebilsin diye. Serbest metin
    (`gerekce`) ile sınıf adı (`sinif_metni`) sunumdur ve dile göre değişir;
    `sinif` alanı ise anahtar olarak kalır --- eski tüketiciler kırılmaz.
    """
    from mesajlar import KULLANIM, NICELIK, SINIF, cevir, dil_dogrula, gerekce_metni
    d = dil_dogrula(dil)
    kod = getattr(v, "kod", "") or ""
    gerekce = (gerekce_metni(kod, d, **getattr(v, "parametreler", {}) or {})
               if kod else v.message)
    return {"nicelik": v.quantity, "nicelik_metni": cevir(NICELIK, v.quantity, d),
            "sinif": v.klass, "sinif_metni": cevir(SINIF, v.klass, d),
            "tasarimda_kullanilir": bool(v.design_safe),
            "kullanim_metni": KULLANIM[bool(v.design_safe)][d],
            "kod": kod, "gerekce": gerekce}


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


def vlm_analiz_et(aircraft, *, alpha_deg: float = 0.0, mach: float = 0.05,
                  panel_bandi_pct: float | None = None, dil: str = "tr",
                  vehicle_type: str = "ucak",
                  output_dir: str = "./vspaero_results") -> dict[str, Any]:
    """VSPAERO (VLM) hızlı çözücüsü --- CFD ile AYNI çıktı sözleşmesi.

    NEDEN AYNI SÖZLEŞME: VLM bu depoda vardı ama `pipeline`/`openvsp_bridge`
    üzerinden, karar katmanına HİÇ uğramadan çıkıyordu. Yani hızlı yolun sayısı
    sınıfsız geliyordu ve CLAUDE.md'nin uyardığı iki-hızlılık tam olarak buydu.
    Bu işlev VLM'i ortak sözleşmeye bağlar; motoru değiştirmez.

    NEDEN STL ALMIYOR: VLM taşıyıcı-yüzey parametrizasyonu ister (kanat, veter,
    açıklık, profil), keyfî bir üçgen ağı değil. `analiz_et`'e `cozucu="vlm"`
    diye bir bayrak koyup STL kabul etmek, çözülemeyecek bir girdiyi kabul
    ediyormuş gibi yapmak olurdu. Parametrik yolun elinde `aircraft` ZATEN var;
    STL'i o üretiyor.
    """
    from mesajlar import SINIF as _SINIF
    from mesajlar import cevir as _cevir
    from mesajlar import dil_dogrula
    from validity_envelope import classify_vlm, overall_class
    _dil = dil_dogrula(dil)

    from openvsp_bridge import run_vspaero
    r = run_vspaero(aircraft, alpha_deg=alpha_deg, mach=mach,
                    output_dir=output_dir)
    if str(r.get("status", "")).upper() == "FAILED":
        return {"surum": SURUM, "durum": "hata", "cozucu": "vlm",
                "hata": r.get("hata") or "VSPAERO koşusu başarısız"}
    # IRAKSAMA KAPISI (`openvsp_bridge` uygular, tanımı zarf katmanında):
    # ıraksamış bir koşuyu sınıflandırmak, saçma bir sayıya hüküm yazmak olurdu.
    if r.get("kabul_edilemez"):
        return {"surum": SURUM, "durum": "hata", "cozucu": "vlm",
                "hata": f"VLM çözümü kabul edilemez: {r['kabul_edilemez']}"}

    cl, cdi = r.get("Cl"), r.get("Cd_i")
    e = _span_verimi(cl, cdi, _en_boy_orani(aircraft))
    v = classify_vlm(alpha_deg, mach, Cl=cl, CDi=cdi, e_span=e,
                     panel_bandi_pct=panel_bandi_pct, vehicle_type=vehicle_type)

    return {
        "surum": SURUM,
        "durum": "ok",
        # ÇÖZÜCÜ ÇIKTIDA YAZILI: bir tüketici elindeki sayının hangi denklem
        # takımından geldiğini sonuçtan bilmelidir. CFD yolu da bunu yazar.
        "cozucu": "vlm",
        "girdi": {"tip": vehicle_type, "alpha_deg": alpha_deg, "mach": mach},
        # `cd` ANAHTARI YOK. VLM toplam sürükleme üretmez; boş ya da 0 bir `cd`
        # koymak tüketiciyi yanıltırdı. Yerine indüklenen bileşen kendi adıyla.
        "sonuc": {"cl": cl, "cd_i": cdi, "span_verimi": e},
        "dil": _dil,
        "gecerlilik": {"genel": overall_class(v),
                       "genel_metni": _cevir(_SINIF, overall_class(v), _dil),
                       "nicelikler": [_verdict_dict(x, _dil) for x in v]},
        "panel": {"band_pct": panel_bandi_pct},
    }


def _en_boy_orani(aircraft):
    """AR = b²/S --- ÇÖZÜCÜ SONUCUNDAN DEĞİL, geometriden.

    İlk sürüm `r.get("AR")` deniyordu ama çözücü sonucu AR taşımıyor; sonuç
    daima None oluyordu ve açıklık-verimi kapısı bu yüzden HİÇ çalışmıyordu
    (ölçüldü, ilk uçtan uca koşu). Çapa betiği aynı hesabı zaten geometriden
    yapıyor; tek doğru kaynak orası.
    """
    try:
        k = aircraft.wing
        b, s = float(k.span), float(k.area)
        return (b * b / s) if (b > 0 and s > 0) else None
    # sessiz-yutma: kabul — geometri okunamazsa AR yoktur ve None DÖNMEK
    # kapıyı açmaz, KAPATIR: `classify_vlm` e=None'ı "fizik kontrolü
    # sınanmadı" sayıp CDi'yi eğilime indirir (VLM_SPAN_OLCULMEDI). Yani
    # sebebin yutulması burada hükmü gevşetmiyor, sıkılaştırıyor.
    except (AttributeError, TypeError, ValueError):
        return None


def _span_verimi(cl, cdi, ar):
    """e = CL²/(π·AR·CDi). Eksik girdide None --- uydurulmuş bir e, kapıyı
    sessizce açardı."""
    import math
    if not cl or not cdi or not ar or cdi <= 0 or ar <= 0:
        return None
    return (cl * cl) / (math.pi * ar * cdi)


def analiz_et(stl_path: str, *, duzeltici: bool = False,
              referans_cd: float | None = None, dil: str = "tr",
              **kw) -> dict[str, Any]:
    """Bir araç analizi koş ve JSON'a hazır sonuç döndür.

    `duzeltici=True` ise kurulum kusurları onarılıp yeniden koşulur; hangi
    müdahalelerin yapıldığı ve hangilerinin YAPILAMADIĞI çıktıdadır.

    `dil` yalnız SUNUM katmanını etkiler (tr|en): sınıf adları, nicelik adları
    ve hüküm gerekçeleri çevrilir. Sözleşme anahtarları (`sinif`, `kod`,
    `tasarimda_kullanilir`) DEĞİŞMEZ --- bir tüketici dili değiştirdiğinde
    kodunun kırılmaması gerekir. Tanısal uyarılar (`uyarilar`) şimdilik yalnız
    Türkçedir ve bu çıktıda AÇIKÇA işaretlenir; yarım çevrilmiş bir arayüzü
    tam gibi göstermek, aracın geri kalanının duruşuyla çelişirdi.
    """
    from mesajlar import SINIF as _SINIF
    from mesajlar import cevir as _cevir
    from mesajlar import dil_dogrula
    _dil = dil_dogrula(dil)
    from validity_envelope import (
        MACH_INCOMP,
        apply_ince_ozellik_gate,
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
        # Referans BORU HATTINA da gider: raporu orası üretiyor ve hükmü
        # servisle AYNI kurabilmesi için beyanı görmesi gerekir.
        r = run_vehicle_analysis(stl_path, referans_cd=referans_cd, **kw)

    if r.status != "ok":
        return {"surum": SURUM, "durum": "hata",
                "hata": r.error or "bilinmeyen", "case_dir": r.case_dir}

    ma = (r.velocity or 0.0) / 340.0
    mds = getattr(r, "mesh_duyarlilik", None) or {}
    gci_ok = bool(mds.get("gci")) and str(mds.get("verdikt", "")).startswith("✅")
    # BEYAN EDİLEN REFERANS HÜKME DE GİRER. `referans_cd` bu katmanda vardı ama
    # YALNIZ düzelticiye gidiyordu: kullanıcı "referansım şu" dediğinde araç
    # onu düzeltme için kullanıp hüküm verirken görmezden geliyordu, yani %40
    # sapan bir koşu yine DOĞRULANMIŞ alabiliyordu. Referans beyan etmek,
    # ölçülmeyi istemektir.
    #
    # VARSAYILAN DAVRANIŞ DEĞİŞMEZ: `referans_cd` None ise (CLI/REST
    # varsayılanı) kapı hiç çalışmaz ve sınıflandırma birebir eskisi gibidir.
    ref_hata = None
    if referans_cd and r.cd is not None:
        ref_hata = abs(r.cd - referans_cd) / abs(referans_cd) * 100.0
    # SAPMA, BEYAN EDİLEN BÜTÇEYE karşı sınanır --- düz bir yüzdeye karşı
    # değil. Koşunun kendi u_val'i varsa (sayısal ⊕ model-form ⊕ referans) kapı
    # onu kullanır: bütçenin İÇİNDE kalan bir sapma, açıklanmamış bir
    # tutarsızlık değildir (ASME V&V 20, R_E≤1). Bütçe yoksa düz eşiğe düşülür.
    u_val = (r.belirsizlik or {}).get("u_toplam_pct") if r.belirsizlik else None
    v = classify_cfd(r.vehicle_type, r.alpha_deg, ma, has_gci_band=gci_ok,
                     band_pct=mds.get("fark_pct"), Cl=r.cl, Cd=r.cd,
                     referans_hata_pct=ref_hata, u_val_pct=u_val)
    v = apply_physics_gate(v, getattr(r, "fizik_kabul", None) or {})
    v = apply_ince_ozellik_gate(
        v, ((getattr(r, "sinir_tabaka", None) or {})
            .get("yuzey_cozunurlugu") or {}).get("geometri_goreli"))

    return {
        "surum": SURUM,
        "durum": "ok",
        "cozucu": "cfd",
        "girdi": {"stl": str(stl_path), "tip": r.vehicle_type,
                  "hiz_ms": r.velocity, "alpha_deg": r.alpha_deg,
                  "mach": round(ma, 4), "sikisabilir": ma >= MACH_INCOMP},
        # HÜKMÜ VEREN SAYI ÇIKTIDA DURUR: referans beyan edildiyse sapma da
        # görünür olmalı, aksi halde hüküm denetlenemez. Beyan yoksa None.
        "referans": ({"cd": referans_cd, "hata_pct": round(ref_hata, 3)}
                     if ref_hata is not None else None),
        "sonuc": {"cd": r.cd, "cl": r.cl, "ld": r.ld, "aref_m2": r.aref_m2,
                  "surukleme_N": r.drag_N},
        # SINIF SAYIYLA BIRLIKTE GIDER. Çıplak bir Cd döndürmek, bu aracın
        # varlık nedenine aykırıdır: istemci hangi sayının tasarım kararında
        # kullanılabileceğini çıktının kendisinden bilmelidir.
        "dil": _dil,
        "gecerlilik": {"genel": overall_class(v),
                       "genel_metni": _cevir(_SINIF, overall_class(v), _dil),
                       "nicelikler": [_verdict_dict(x, _dil) for x in v]},
        "belirsizlik": r.belirsizlik,
        "mesh": r.mesh,
        "yakinsama": r.convergence,
        "duzeltici": _duzeltici_dict(duz),
        "uyarilar": list(getattr(r, "uyarilar", None) or []),
        "case_dir": r.case_dir,
        "rapor": r.report,
    }
