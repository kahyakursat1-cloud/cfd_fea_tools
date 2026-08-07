# AeroSim-Hub cozucu konteyneri: OpenFOAM 11 (Foundation) + CalculiX ccx.
# Python/GUI HOST'ta kalir; konteyner yalniz cozucudur (CFD_BACKEND=docker ile
# analysis/backend.py ayni bash komutlarini burada kosar).
#
# Insa:      docker build -t aerosim-hub .
# Baslatma:  docker run -d --name aerosim -v D:\:/mnt/d aerosim-hub sleep infinity
#            (bind-mount, host suruculerini WSL ile AYNI /mnt/<x> yoluna koyar —
#             windows_to_wsl_path degismeden calisir)
# Kullanim:  $env:CFD_BACKEND="docker"  (istege: CFD_DOCKER_CONTAINER=aerosim)
# TABAN IMAJ DIGEST'E SABIT. `:latest` DEGISTIRILEBILIR bir etikettir: ayni
# Dockerfile yarin baska bir OpenFOAM derlemesi cekebilir ve yayimlanmis bir
# GCI bandi sessizce gecersizlesir. Digest icerik-adresli, yani bu satir
# degismedikce imaj da degismez.
#
# Digest ÖLÇÜLDÜ (2026-08-08), elle yazilmadi:
#   docker buildx imagetools inspect openfoam/openfoam11-paraview510
# Guncellemek icin ayni komutu kosun ve cikan Digest'i buraya yazin — ama
# guncelleme BILINCLI bir karardir: cozucu degisirse kanitlar yeniden
# uretilmelidir (bkz. ortam.py, kanit.py --ortam).
FROM openfoam/openfoam11-paraview510@sha256:fd10956e0b1eb70f9808baf2857e4baf846a0f6f272f73b6d00546eae96be181

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends calculix-ccx \
    && rm -rf /var/lib/apt/lists/*
