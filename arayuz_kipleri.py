"""Arayüz kipleri — aynı yapılandırmanın üç yüzü.

TEMEL KURAL: kipler farklı yazılım YOLU üretmez. Üçü de aynı
`analysis/` çekirdeğine ve AYNI koşu-yapılandırmasına gider; değişen yalnız
neyin görünür, neyin düzenlenebilir olduğudur. Aksi hâlde "Otopilot sonucu"
ile "Mühendis sonucu" aynı problem için farklı case kurabilirdi ve bu, tek
kanonik çekirdek ilkesine doğrudan aykırı olurdu.

  otopilot   STL → amaç → önerilen plan → çalıştır → hüküm.
             Kritik ayarlar otomatik seçilir; gizlenir ama KULLANILMAYA devam
             eder ve "neden bu ayar?" ile gerekçesi görülebilir.
  muhendis   Aynı akış; mesh, y⁺, sınır tabaka, çözücü bütçesi ve yapısal
             kontrol düzenlenebilir.
  arastirma  Hepsi + V&V/UQ katmanı: mesh-duyarlılık ailesi, kanıt gezgini,
             ortam parmak izi.

GİZLEMEK SIFIRLAMAK DEĞİLDİR. Bir alan gizlendiğinde değeri korunur ve
çözücüye aynen gider; görünürlük yalnız sunum katmanıdır. Bunu bozmak,
kullanıcının göremediği bir ayarın sessizce değişmesi demek olurdu --- bu
deponun avladığı kusur sınıfının ta kendisi.
"""
from __future__ import annotations

KIPLER = ("otopilot", "muhendis", "arastirma")
KIP_ETIKET = {
    "otopilot": "🤖 Otopilot — kararları sistem verir",
    "muhendis": "🛠 Mühendis — ayarlar düzenlenebilir",
    "arastirma": "🔬 Araştırma — V&V/UQ ve kanıt katmanı açık",
}
KIP_ACIKLAMA = {
    "otopilot": ("Ayarlar otomatik seçilir ve gizlenir — ama SİLİNMEZ: çözücüye "
                 "aynen gider. Gerekçelerini 'Planı göster' ile okuyabilirsiniz."),
    "muhendis": ("Mesh, y⁺, sınır tabaka, çözücü bütçesi ve yapısal kontrol "
                 "düzenlenebilir. Otomatik öneriler başlangıç değeri olarak durur."),
    "arastirma": ("Mesh-duyarlılık aileleri, kanıt dosyaları ve ortam parmak izi "
                  "açık. Yayımlanacak bir sayı üretiyorsanız bu kip."),
}

# Alan → GÖRÜNDÜĞÜ EN DÜŞÜK kip indeksi. Burada olmayan her şey her kipte görünür.
# Ölçüt: "bu ayarı yanlış vermek sonucu bozar mı, ve otopilot onu güvenilir
# biçimde seçebiliyor mu?" İkisi de evetse otopilotta gizlenir.
GORUNURLUK: dict[str, int] = {
    # — Mühendis ve üstü —
    "cmb_rejim": 1,       # akış rejimi: otopilot Mach'tan çıkarır
    "spn_mach": 1,
    "cmb_quality": 1,     # mesh kalitesi: otopilot geometriden seçer
    "cmb_nose": 1,        # eksenler: geometri kapısı zaten denetliyor
    "cmb_up": 1,
    "spn_proc": 1,        # işlemci: otopilot çekirdek sayısından
    "spn_layers": 1,      # sınır tabaka katmanı
    "spn_yplus": 1,       # hedef y⁺
    "btn_queue_add": 1,
    "gb_polar": 1,
    "gb_fea": 1,
    # Düzeltici HER KİPTE görünür (0) ve bu bilinçli bir karardır. Ek koşu
    # maliyeti getirdiği için `chk_sens` gibi araştırma kipine çekilebilirdi;
    # ama en çok otopilot kullanıcısının işine yarar: y⁺ uyumsuzluğunu ya da
    # duvar işleminin ağa uymadığını kendi teşhis edemeyecek olan odur.
    # Varsayılan KAPALI olduğu için kimseye sürpriz maliyet çıkarmaz.
    "chk_duzeltici": 0,
    # — Yalnız araştırma —
    "chk_sens": 2,        # mesh-duyarlılık bandı (ek koşu maliyeti)
    "spn_seviye": 2,
    "btn_kanit": 2,       # kanıt gezgini
}


def gorunur_mu(alan: str, kip: str) -> bool:
    """`alan` bu kipte görünmeli mi? Bilinmeyen alan HER kipte görünür —
    varsayılan gizlemek değil GÖSTERMEKTİR: yeni bir ayar eklendiğinde
    sessizce kaybolmasın."""
    return KIPLER.index(kip) >= GORUNURLUK.get(alan, 0)


def kip_dogrula(kip: str | None) -> str:
    return kip if kip in KIPLER else "muhendis"
