"""Configuración del backend: rutas compartidas y JobStore (cola hacia el worker)."""
from __future__ import annotations

import os
import sys

# feasibility-study-app/ (dos niveles arriba de backend/app)
APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
PF_WORKER = os.path.join(APP_ROOT, "pf_worker")
for _p in (APP_ROOT, PF_WORKER):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import paths  # noqa: E402

# Rutas con conciencia de empaquetado (frozen): results escribible + frontend estático.
RESULTS_DIR = paths.RESULTS_DIR
FRONTEND_OUT = paths.FRONTEND_OUT

from jobstore import JobStore  # noqa: E402  (jobstore.py está en APP_ROOT)

# Única instancia de la cola; el worker (otro proceso) lee/escribe el mismo directorio.
store = JobStore(RESULTS_DIR)
