

def test_CONDA_RUN_oneki_taniniyor():
    """OpenVSP/XFOIL kanıtları ayrı bir conda ortamından üretiliyor ve komut o
    önekle KAYITLI. Önek tanınmayınca YENİDEN ÜRETİLEBİLİR bir kanıt
    "komut kayıtlı değil" diye raporlanıyordu (ölçüldü: vlm_capa,
    vlm_panel_yakinsamasi, vlm_iki_yonlu_yakinsama — 13 uyarıdan 3'ü)."""
    import kanit
    d = {"_uretim": "Üretim: conda run -n openvsp python experiments/vlm_capa.py"}
    k = kanit._uretim_komutu(d)
    assert k, "conda run öneki tanınmıyor"
    assert "vlm_capa.py" in k
    # Duz komut da calismaya devam etmeli.
    assert "zarf.py" in kanit._uretim_komutu({"_u": "Üretim: python zarf.py --yaz"})
