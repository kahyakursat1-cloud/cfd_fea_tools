"""Başsız REST arayüzü — tarayıcı ön-yüzünü çözücü arka-ucundan ayırır.

CLI ile AYNI `hizmet.analiz_et`'i çağırır. Bu dosyada iş mantığı YOKTUR ve
olmamalıdır: iki arayüz ayrı mantık taşırsa, biri düzeltilirken diğeri
unutulur — bu depoda o kusur üç kez ölçüldü.

    uvicorn api:app --host 0.0.0.0 --port 8000
    curl -X POST localhost:8000/analiz -H "Content-Type: application/json" \
         -d '{"stl":"model.stl","tip":"ucak","hiz":30,"duzeltici":true}'

Analiz UZUN SÜRER (dakikalar). Bu sürüm eşzamanlı (blocking) çalışır; iş
kuyruğuna bağlanması ayrı bir adımdır ve `kuyruk.py` zaten o işi yapıyor.
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from hizmet import SURUM, analiz_et

app = FastAPI(title="AeroSim-Hub çözücü API", version=SURUM)


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
    return {"durum": "ayakta", "surum": SURUM}


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
    is_ = kuyruk.ekle({"stl_path": istek.stl, **_kwargs(istek)})
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
    try:
        return analiz_et(istek.stl, **_kwargs(istek))
    except Exception as e:                                        # noqa: BLE001
        return {"surum": SURUM, "durum": "hata",
                "hata": f"{type(e).__name__}: {e}"}
