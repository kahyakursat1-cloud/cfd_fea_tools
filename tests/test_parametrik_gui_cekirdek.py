"""Parametrik arayüz ORTAK ÇEKİRDEĞİ sürüyor mu, kendi analiz yolunu mu kuruyor?

ÖLÇÜLEN GEÇMİŞ (2026-08-02): bu ekranın analiz sekmeleri çözücüyü HİÇ
çağırmıyordu. `_start_simulation` `runner.run_simulation(job)` satırını yorumda
bırakıp 101 adımlık `time.sleep` döngüsü koşuyor ve "✅ Simülasyon tamamlandı!"
yazıyordu; FEA sekmesi gerilmeyi `yük/100×2.5` ile uydurup ondan "GÜVENLİ"
hükmü veriyordu. Yollar o gün gerekçeli redde çevrildi.

Şimdi CFD yolu geri bağlandı --- ama YENİ BİR ANALİZ YOLU YAZILARAK DEĞİL,
`hizmet.analiz_et` çağrılarak. Ayrım önemli: bu depoda üç giriş noktasının ayrı
yol tutması ölçülmüş bir kusurdur (bir düzeltme seçeneği yalnız düğme yoluna
eklenmiş, kuyruk yolunda yok sayılmıştı). Bu test o ayrışmanın geri gelmesini
engeller.

FEA sekmesi hâlâ reddediyor ve bu BİLİNÇLİ: `hizmet.analiz_et` bir CFD
sözleşmesi döndürür, yapısal yol ayrıdır (`app_analyzer.py`).
"""
import ast
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

KAYNAK = (KOK / "app_parametric.py").read_text(encoding="utf-8")
AGAC = ast.parse(KAYNAK)


def _cagrilan_adlar() -> set[str]:
    adlar = set()
    for n in ast.walk(AGAC):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                adlar.add(f.id)
            elif isinstance(f, ast.Attribute):
                adlar.add(f.attr)
    return adlar


def test_analiz_ORTAK_CEKIRDEKTEN_cagriliyor():
    assert "analiz_et" in _cagrilan_adlar(), (
        "arayüz `hizmet.analiz_et` çağırmıyor — kendi analiz yolunu kuruyorsa "
        "CLI/REST ile ayrışır")


def test_KENDI_hattini_kurmuyor():
    """`run_vehicle_analysis`ı doğrudan çağırmak, çekirdeği ATLAMAK demektir.

    Çekirdek yalnız hattı sürmez: sonucu sınıflandırır, fizik kapısını uygular
    ve sözleşmeyi kurar. Doğrudan hat çağrısı bu katmanı sessizce atlar ve
    arayüz sınıfsız bir sayı gösterir.
    """
    assert "run_vehicle_analysis" not in _cagrilan_adlar()


def test_SAHTE_ilerleme_dongusu_geri_gelmedi():
    """`time.sleep` ile doldurulan ilerleme çubuğu bu dosyanın özgün kusuruydu.

    Tarama AST üzerinden yapılır, ham metin üzerinden DEĞİL: modül başlığı o
    kusuru ölçümüyle birlikte ANLATIYOR ve metin taraması açıklamayı kusurun
    kendisi sanıp yanlış pozitif üretiyordu. Yanlış pozitif üreten denetim
    kullanılmaz hale gelir, üstelik gerçek kusuru da gizler.
    """
    uykular = [n for n in ast.walk(AGAC)
               if isinstance(n, ast.Call) and (
                   (isinstance(n.func, ast.Attribute) and n.func.attr == "sleep")
                   or (isinstance(n.func, ast.Name) and n.func.id == "sleep"))]
    assert not uykular, (
        f"{len(uykular)} adet sleep() çağrısı — ilerleme çubuğunu doldurmak "
        "analiz yapmak değildir")


def test_sonuc_SINIFIYLA_birlikte_gosteriliyor():
    """Sayı sınıfsız gösterilirse sözleşme arayüzde kırılır."""
    assert "gecerlilik" in KAYNAK, "geçerlilik sınıfı arayüze taşınmıyor"
    assert "tasarimda_kullanilir" in KAYNAK, (
        "niceliğin tasarımda kullanılıp kullanılamayacağı gösterilmiyor")


def test_FEA_yolu_HALA_reddediyor():
    """Kapsam kaydı: CFD bağlandı, FEA bağlanmadı --- ve bu görünür olmalı."""
    assert "_run_fea_analysis" in KAYNAK
    assert "DEMO_RET_METNI" in KAYNAK, "FEA reddi kaldırılmış ama yerine ne kondu?"


def test_tip_eslemesi_TEK_yerde():
    """aircraft_geometry tipleri ile hattın araç tipleri ayrı sözlüklerdir."""
    import re
    assert KAYNAK.count("_ARAC_TIPI = {") == 1
    esleme = re.search(r"_ARAC_TIPI = \{(.*?)\}", KAYNAK, re.S).group(1)
    from auto_pilot import TIPLER
    for hedef in re.findall(r':\s*"([a-z_]+)"', esleme):
        assert hedef in TIPLER, f"'{hedef}' hattın tanıdığı bir araç tipi değil"
