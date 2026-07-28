"""_wsl_kill KAPSAMI — paralel koşuları öldürmemeli.

ÖLÇÜLDÜ: NACA2412 çapası koşarken paralel başlatılan bir duman testi kendi
temizliğinde `_wsl_kill(["foamRun"])` çağırdı. Eski hâl `pkill -9 -f foamRun`
olduğu için makinedeki HER foamRun öldü — çapanın çözücüsü 1464. iterasyonda
kesildi, log iterasyon ortasında bitti, hiçbir yerde hata görünmedi ve çapa
sessizce yakınsamamış bir sayı üretecekti.
"""
from unittest.mock import patch

import analysis.openfoam_runner as ofr


def _komut(*a, **k):
    """linux_run'ı yakala, üretilen bash komutunu döndür."""
    kayit = {}

    def sahte(cmd, timeout):
        kayit["cmd"] = cmd
        class R:
            stdout = ""
        return R()
    return sahte, kayit


def test_kapsamsiz_cagri_HALA_pkill_kullaniyor():
    """Geriye uyum: dizin verilmezse davranış değişmez."""
    sahte, kayit = _komut()
    with patch.object(ofr, "linux_run", sahte):
        ofr._wsl_kill(["foamRun"])
    assert "pkill -9 -f foamRun" in kayit["cmd"]


def test_dizin_verilince_PKILL_KULLANILMIYOR():
    sahte, kayit = _komut()
    with patch.object(ofr, "linux_run", sahte):
        ofr._wsl_kill(["foamRun"], "/mnt/d/case_a")
    assert "pkill" not in kayit["cmd"], "kapsamli cagri hala global pkill yapiyor"


def test_dizin_verilince_CWD_ile_filtreleniyor():
    sahte, kayit = _komut()
    with patch.object(ofr, "linux_run", sahte):
        ofr._wsl_kill(["foamRun", "mpirun"], "/mnt/d/case_a")
    c = kayit["cmd"]
    assert "/proc/$_p/cwd" in c
    assert '= "/mnt/d/case_a"' in c
    assert "foamRun" in c and "mpirun" in c


def test_bos_desen_hicbir_sey_yapmaz():
    with patch.object(ofr, "linux_run", lambda *a, **k: None):
        assert ofr._wsl_kill([], "/mnt/d/x") is None


def test_kosu_yolu_KAPSAMLI_cagiriyor():
    """run_cfd içindeki üç kill çağrısı da case dizinini geçmeli."""
    import inspect
    src = inspect.getsource(ofr)
    assert "_wsl_kill(bins)" not in src, "kapsamsiz cagri kalmis"
    assert src.count("_wsl_kill(bins, exec_dir)") == 3
