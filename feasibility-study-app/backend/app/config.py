"""Configuración del backend: rutas compartidas y JobStore (cola hacia el worker)."""
from __future__ import annotations

import os
import sys

# feasibility-study-app/ (dos niveles arriba de backend/app)
APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
RESULTS_DIR = os.path.join(APP_ROOT, "results")

if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from jobstore import JobStore  # noqa: E402  (jobstore.py está en APP_ROOT)

# Única instancia de la cola; el worker (otro proceso) lee/escribe el mismo directorio.
store = JobStore(RESULTS_DIR)
