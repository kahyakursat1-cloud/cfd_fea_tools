"""Başsız REST arayüzü — tarayıcı ön-yüzünü çözücü arka-ucundan ayırır.

CLI ile AYNI `hizmet.analiz_et`'i çağırır. Bu dosyada iş mantığı YOKTUR ve
olmamalıdır: iki arayüz ayrı mantık taşırsa, biri düzeltilirken diğeri
unutulur — bu depoda o kusur üç kez ölçüldü.

    uvicorn api:app --host 0.0.0.0 --port 8000

Tipik akış (tarayıcı ön-yüzü):
    1. POST /yukle?ad=kanat.stl   --data-binary @kanat.stl   → {"stl": "<id>.stl"}
    2. POST /analiz               {"stl":"<id>.stl","tip":"ucak","hiz":30}
                                                             → {"is_id": "..."}
    3. GET  /is/{is_id}           → durum; bittiğinde tam sonuç

Analiz DAKİKALAR sürer, o yüzden varsayılan yol kuyruktur. `/analiz/senkron`
betikler ve kısa koşular için durur ve aynı sözleşmeyi döndürür.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from hizmet import SURUM, analiz_et

app = FastAPI(title="AeroSim-Hub çözücü API", version=SURUM)

# ── Dosya sınırı ─────────────────────────────────────────────────────────────
# API, SUNUCUDAKİ HERHANGİ BİR YOLU kabul etmemelidir. Önceki sürümde `stl`
# alanı doğrudan çözücüye gidiyordu; bir istemci `../../etc/passwd` ya da başka
# bir kullanıcının geometrisini verebilirdi. Analiz o dosyayı okur ve sonucu
# (hacim, alan, kütle merkezi) döndürür — yani dolaylı bir okuma kanalı.
#
# Bu sınır YALNIZ API içindir. `cli.py` kullanıcının kendi hesabında koşar ve
# kendi dosyalarına zaten erişebilir; oraya aynı kısıtı koymak, yerel kullanımı
# gereksiz yere sakatlardı.
VERI_KOK = Path(os.environ.get("AEROSIM_VERI", "veri")).resolve()
UZANTILAR = {".stl", ".obj", ".step", ".stp"}


def _guvenli_yol(s: str) -> str:
    """Verilen yol VERI_KOK içinde mi? Değilse istek REDDEDİLİR.

    `resolve()` sembolik bağları ve `..` parçalarını çözer; karşılaştırma
    çözülmüş yollar arasında yapılır, aksi halde `veri/../../gizli` geçerdi.
    """
    VERI_KOK.mkdir(parents=True, exist_ok=True)
    p = (VERI_KOK / s).resolve() if not Path(s).is_absolute() else Path(s).resolve()
    if not p.is_relative_to(VERI_KOK):
        raise HTTPException(400, f"yol veri kökü dışında: {s} (kök: {VERI_KOK})")
    if p.suffix.lower() not in UZANTILAR:
        raise HTTPException(400, f"desteklenmeyen uzantı: {p.suffix}")
    if not p.exists():
        raise HTTPException(404, f"dosya yok: {s}")
    return str(p)


class AnalizIstegi(BaseModel):
    stl: str = Field(..., description="geometri dosyası yolu (.stl)")
    tip: str = "ucak"
    hiz: float = 30.0
    alpha: float = 0.0
    kalite: str = "standart"
    cekirdek: int = 0
    duzeltici: bool = False
    referans_cd: float | None = None


@app.get("/saglik")
def saglik() -> dict:
    return {"durum": "ayakta", "surum": SURUM, "veri_kok": str(VERI_KOK)}


@app.post("/yukle")
async def yukle(istek: Request, ad: str = "model.stl") -> dict:
    """Geometriyi HAM GÖVDE olarak al, veri köküne yaz, kimliğini döndür.

    Çok-parçalı (multipart) form yerine ham gövde kullanılır: `python-multipart`
    bağımlılığı gerektirmez ve `curl --data-binary @model.stl` ile çalışır.

        curl -X POST "localhost:8000/yukle?ad=kanat.stl" --data-binary @kanat.stl

    Dönen `stl` alanı doğrudan `/analiz`'e verilebilir. İstemcinin sunucu
    dosya sistemini bilmesi gerekmez ve zaten bilmemelidir.
    """
    uz = Path(ad).suffix.lower()
    if uz not in UZANTILAR:
        raise HTTPException(400, f"desteklenmeyen uzantı: {uz}")
    govde = await istek.body()
    if not govde:
        raise HTTPException(400, "boş gövde — geometri gönderilmedi")
    VERI_KOK.mkdir(parents=True, exist_ok=True)
    # Kullanıcının verdiği ad DOSYA ADI OLARAK KULLANILMAZ; yalnız uzantısı
    # alınır. Aksi halde "../../x.stl" gibi bir ad veri kökünden çıkardı.
    hedef = VERI_KOK / f"{uuid.uuid4().hex[:12]}{uz}"
    hedef.write_bytes(govde)
    return {"surum": SURUM, "durum": "yuklendi", "stl": hedef.name,
            "bayt": len(govde), "ozgun_ad": ad}


def _kwargs(istek: AnalizIstegi) -> dict:
    return {"vehicle_type": istek.tip, "velocity": istek.hiz,
            "alpha_deg": istek.alpha, "quality": istek.kalite,
            "n_processors": istek.cekirdek, "duzeltici": istek.duzeltici,
            "referans_cd": istek.referans_cd}


@app.post("/analiz")
def analiz_kuyruga(istek: AnalizIstegi) -> dict:
    """İşi KUYRUĞA al ve iş kimliği döndür (varsayılan yol).

    Gerçek bir analiz dakikalar sürer; eşzamanlı yanıt beklemek tarayıcıyı
    zaman aşımına uğratır. Kuyruk zaten sıra, kilit ve yarım-iş kurtarma
    mantığını taşıyor, o yüzden API kendi zamanlayıcısını KURMUYOR.

    Not: işi koşan `kuyruk.calis()` worker'ıdır ve AYRI bir süreçtir. API
    yalnız işi kaydeder; worker koşmuyorsa iş "bekliyor" durumunda kalır ve
    `/is/{id}` bunu açıkça söyler.
    """
    import kuyruk
    is_ = kuyruk.ekle({"stl_path": _guvenli_yol(istek.stl), **_kwargs(istek)})
    return {"surum": SURUM, "durum": "kuyrukta", "is_id": is_["id"],
            "durum_ucu": f"/is/{is_['id']}"}


@app.get("/is/{is_id}")
def is_durumu(is_id: str) -> dict:
    """Kuyruktaki bir işin durumu; bittiyse TAM sözleşme `sonuc` altındadır.

    `sonuc.tam`, `/analiz/senkron`'un döndürdüğünün AYNISIDIR — istemci işin
    hangi yoldan geldiğine göre farklı ayrıştırıcı yazmak zorunda kalmamalı.
    """
    import kuyruk
    for i in kuyruk.listele():
        if i["id"] == is_id:
            son = i.get("sonuc") or {}
            return {"surum": SURUM, "is_id": is_id, "durum": i["durum"],
                    "eklendi": i.get("ts"), "sonuc": son.get("tam") or son or None}
    return {"surum": SURUM, "is_id": is_id, "durum": "yok",
            "hata": "böyle bir iş kaydı bulunamadı"}


@app.get("/isler")
def isler() -> dict:
    import kuyruk
    return {"surum": SURUM,
            "isler": [{"is_id": i["id"], "durum": i["durum"], "eklendi": i.get("ts"),
                       "stl": i["params"].get("stl_path")} for i in kuyruk.listele()]}


@app.post("/analiz/senkron")
def analiz(istek: AnalizIstegi) -> dict:
    """Analizi ŞİMDİ koş ve geçerlilik sınıfıyla birlikte döndür.

    Betikler ve kısa koşular için; tarayıcı ön-yüzü `/analiz` kullanmalıdır.
    Hata durumunda da 200 döner ve gövdede `durum: "hata"` bulunur: çözücü
    hatası bir HTTP hatası değildir, ölçülmüş bir sonuçtur ve istemci onu
    ayrıştırabilmelidir.
    """
    yol = _guvenli_yol(istek.stl)     # HTTPException DIŞARIDA: yol reddi bir
    #                                   istemci hatasıdır (400/404), çözücü
    #                                   sonucu değil. Aşağıdaki geniş `except`
    #                                   içine alınırsa 200 + "durum: hata"
    #                                   dönerdi ve istemci reddi göremezdi.
    try:
        return analiz_et(yol, **_kwargs(istek))
    except Exception as e:                                        # noqa: BLE001
        return {"surum": SURUM, "durum": "hata",
                "hata": f"{type(e).__name__}: {e}"}
