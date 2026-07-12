# AeroSim-Hub cozucu konteyneri: OpenFOAM 11 (Foundation) + CalculiX ccx.
# Python/GUI HOST'ta kalir; konteyner yalniz cozucudur (CFD_BACKEND=docker ile
# analysis/backend.py ayni bash komutlarini burada kosar).
#
# Insa:      docker build -t aerosim-hub .
# Baslatma:  docker run -d --name aerosim -v D:\:/mnt/d aerosim-hub sleep infinity
#            (bind-mount, host suruculerini WSL ile AYNI /mnt/<x> yoluna koyar —
#             windows_to_wsl_path degismeden calisir)
# Kullanim:  $env:CFD_BACKEND="docker"  (istege: CFD_DOCKER_CONTAINER=aerosim)
FROM openfoam/openfoam11-paraview510

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends calculix-ccx \
    && rm -rf /var/lib/apt/lists/*
