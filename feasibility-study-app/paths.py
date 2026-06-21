"""Rutas base, con conciencia de empaquetado (PyInstaller one-folder, v6 = datos en _internal/).

- Desde fuente:  RESOURCE = DATA = carpeta del proyecto (feasibility-study-app/).
- Empaquetado:   RESOURCE = sys._MEIPASS (datos bundleados, solo lectura: frontend/out, modelo)
                 DATA     = carpeta del .exe (escribible: results/_jobs).
En el primer arranque se siembran los artefactos del modelo (substations.json, grid_map.geojson)
desde RESOURCE hacia la carpeta escribible para que el backend los encuentre y los estudios escriban ahí.
"""
from __future__ import annotations

import os
import shutil
import sys

if getattr(sys, "frozen", False):
    RESOURCE = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    DATA = os.path.dirname(sys.executable)
else:
    RESOURCE = os.path.dirname(os.path.abspath(__file__))
    DATA = RESOURCE

FRONTEND_OUT = os.path.join(RESOURCE, "frontend", "out")
RESULTS_DIR = os.path.join(DATA, "results")

os.makedirs(RESULTS_DIR, exist_ok=True)
for _fn in ("substations.json", "grid_map.geojson"):
    _dst = os.path.join(RESULTS_DIR, _fn)
    _src = os.path.join(RESOURCE, "results", _fn)
    if not os.path.exists(_dst) and os.path.exists(_src):
        try:
            shutil.copy2(_src, _dst)
        except OSError:
            pass
