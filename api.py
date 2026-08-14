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


@app.post("/analiz")
def analiz(istek: AnalizIstegi) -> dict:
    """Analizi koş ve geçerlilik sınıfıyla BİRLİKTE döndür.

    Hata durumunda da 200 döner ve gövdede `durum: "hata"` bulunur: çözücü
    hatası bir HTTP hatası değildir, ölçülmüş bir sonuçtur ve istemci onu
    ayrıştırabilmelidir.
    """
    try:
        return analiz_et(istek.stl, vehicle_type=istek.tip, velocity=istek.hiz,
                         alpha_deg=istek.alpha, quality=istek.kalite,
                         n_processors=istek.cekirdek, duzeltici=istek.duzeltici,
                         referans_cd=istek.referans_cd)
    except Exception as e:                                        # noqa: BLE001
        return {"surum": SURUM, "durum": "hata",
                "hata": f"{type(e).__name__}: {e}"}
