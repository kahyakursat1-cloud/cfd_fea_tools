"""YARIŞ DURUMU: `wsl bash -c` sarmalayıcısı, çözücü hâlâ koşarken dönebiliyor.

Bu depoda `construct2d_bridge.run_construct2d` içinde belgelenmiş ve orada
çözülmüştü — ama KANONİK koşucuda (analysis/openfoam_runner) yoktu. İki-hızlı
ayrışmanın bir örneği daha.

ÖLÇÜLDÜ (gripen_AB_Right, güvenilirlik taraması):
    sonuc.json yazildi        13:51
    log.foamRun "End"         13:59   (800 iterasyon, TEMIZ bitti, oldurulmedi)
    boru hattinin gordugu     213 kayit   (nihai 801'in dortte biri)

Çökme üretmediği, MAKUL GÖRÜNEN kısmi bir sonuç ürettiği için yıllarca fark
edilmedi. Sonucu: salınım hükmü koşudan koşuya değişiyordu (aynı geometri, aynı
ayar → geçiş sayısı 3 ↔ 12), yani V&V aracının hükmü TEKRARLANABİLİR DEĞİLDİ.
Cd %1 içinde tekrarlanabiliyordu çünkü kuyruk ortalaması kısmi tarihçede de yakın
çıkıyor — bu da hatayı gizleyen ikinci katmandı.
"""
from unittest.mock import patch

import analysis.openfoam_runner as ofr


def _sahte_linux_run(cikti):
    def f(cmd, timeout):
        class R:
            stdout = cikti
        return R()
    return f


def test_yasayan_cozucu_tespit_ediliyor():
    with patch.object(ofr, "linux_run", _sahte_linux_run("VAR\n")):
        assert ofr._cozucu_yasiyor(["foamRun"], "/mnt/d/case") is True


def test_biten_cozucu_tespit_ediliyor():
    with patch.object(ofr, "linux_run", _sahte_linux_run("")):
        assert ofr._cozucu_yasiyor(["foamRun"], "/mnt/d/case") is False


def test_sorgu_KAPSAMLI_cwd_ile():
    """Kapsamsız bir sorgu başka bir koşunun çözücüsünü 'yaşıyor' sayardı."""
    yakalanan = {}

    def f(cmd, timeout):
        yakalanan["cmd"] = cmd
        class R:
            stdout = ""
        return R()
    with patch.object(ofr, "linux_run", f):
        ofr._cozucu_yasiyor(["foamRun", "mpirun"], "/mnt/d/case_a")
    c = yakalanan["cmd"]
    assert "/proc/$_p/cwd" in c
    assert '= "/mnt/d/case_a"' in c
    assert "foamRun" in c and "mpirun" in c


def test_bos_desende_beklemez():
    assert ofr._cozucu_yasiyor([], "/mnt/d/case") is False


def test_bekleme_cozucu_bitince_DONUYOR():
    with patch.object(ofr, "linux_run", _sahte_linux_run("")):
        ofr._cozucu_bitmesini_bekle(["foamRun"], "/mnt/d/case", tmo=5, adim=1)


def test_bekleme_TIMEOUT_ile_sinirli():
    """Asla süresiz kilitlenmemeli — en kötü hâl eski davranıştır."""
    import time
    with patch.object(ofr, "linux_run", _sahte_linux_run("VAR\n")):
        t0 = time.time()
        ofr._cozucu_bitmesini_bekle(["foamRun"], "/mnt/d/case", tmo=2, adim=1)
        assert time.time() - t0 < 6


def test_sorgu_DUSERSE_kilitlenmiyor():
    """Sorgulanamıyorsa 'yaşamıyor' varsayılır — yeni bir asılma riski getirmez."""
    def patlat(cmd, timeout):
        raise RuntimeError("wsl yok")
    with patch.object(ofr, "linux_run", patlat):
        assert ofr._cozucu_yasiyor(["foamRun"], "/mnt/d/c") is False


def test_kosucu_BEKLEMEYI_cagiriyor():
    """Ölçüm tüketilmezse yine sessiz kalır — bu oturumun tekrarlayan deseni."""
    import inspect
    src = inspect.getsource(ofr.run_cfd)
    assert "_cozucu_bitmesini_bekle" in src
    # erken-durdurmada beklenmemeli (zaten kasitli oldurduk)
    i = src.index("_cozucu_bitmesini_bekle")
    assert "if not early:" in src[max(0, i - 120):i]
