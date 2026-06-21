"""Rutas base, con conciencia de empaquetado (PyInstaller one-folder).

- Desde fuente:  BASE = carpeta del proyecto (feasibility-study-app/).
- Empaquetado:   BASE = carpeta del .exe (dist/...), donde se bundlean frontend/out y results/.
Así la lectura (frontend) y la escritura (results/_jobs) usan una única base coherente y escribible.
"""
from __future__ import annotations

import os
import sys

if getattr(sys, "frozen", False):
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))

RESULTS_DIR = os.path.join(BASE, "results")
FRONTEND_OUT = os.path.join(BASE, "frontend", "out")
