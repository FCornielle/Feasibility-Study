"""Worker persistente de PowerFactory: consume la cola de trabajos y corre los estudios.

Proceso de larga vida que llama `GetApplicationExt()` UNA sola vez (restricción del engine) y
atiende muchas corridas en serie (PF no es thread-safe). Lee jobs de `JobStore`, ejecuta el estudio
con reportes de progreso y escribe el resultado.

Uso:
    python worker.py            # bucle infinito (producción)
    python worker.py --once     # procesa un solo job y termina (para pruebas)
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))      # pf_worker/
APP_ROOT = os.path.dirname(HERE)                         # feasibility-study-app/
for _p in (HERE, APP_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import connect  # noqa: E402
import export  # noqa: E402
import paths  # noqa: E402
from jobstore import JobStore  # noqa: E402
from sandbox import PFRunSandbox  # noqa: E402
from studies import (  # noqa: E402
    frequency, quasi_dynamic, report, small_signal, steady_state, transient, voltage,
)

RESULTS_DIR = paths.RESULTS_DIR

# Registro de estudios disponibles (clave = id que envía el frontend).
STUDIES = {
    "steady_state": steady_state.run,
    "small-signal": small_signal.run,
    "transient": transient.run,
    "voltage": voltage.run,
    "frequency": frequency.run,
    "quasi": quasi_dynamic.run,
    "report": report.run,
}


def process_one(app, store: JobStore) -> bool:
    job = store.claim_next()
    if job is None:
        return False
    rid, study, sub, params = job["run_id"], job["study"], job["substation"], job["params"]
    print(f"[{rid}] {study} sub={sub} params={params}")
    try:
        runner = STUDIES.get(study)
        if runner is None:
            raise ValueError(f"Estudio desconocido: {study!r}")

        def progress(phase, pct, _rid=rid):
            store.update(_rid, phase=phase, progress=pct)

        data = runner(app, sub, run_id=rid, progress=progress, **params)
        path = export.write_results(rid, study, data)
        store.update(rid, status="done", progress=100, phase="completado",
                     result_file=os.path.relpath(path, APP_ROOT),
                     compliance=data.get("compliance"))
        print(f"[{rid}] done -> {path}")
    except Exception as e:  # nunca tumbar el worker por un job
        store.update(rid, status="error", phase="error", error=str(e))
        print(f"[{rid}] ERROR: {e}")
    return True


def main():
    once = "--once" in sys.argv
    print("Conectando a PowerFactory...")
    app = connect.get_app()
    print("Proyecto activo:", app.GetActiveProject().loc_name)
    swept = PFRunSandbox.sweep_orphans(app)
    if swept:
        print(f"Barridos {swept} objetos huérfanos de corridas previas.")
    store = JobStore(RESULTS_DIR)
    print(f"Worker listo (once={once}). Esperando trabajos en {store.dir}")
    while True:
        did = process_one(app, store)
        if once and did:
            break
        if not did:
            time.sleep(1.0)


if __name__ == "__main__":
    main()
