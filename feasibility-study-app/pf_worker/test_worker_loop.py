"""Test del bucle del worker SIN PowerFactory: inyecta un estudio simulado.

Valida cola -> claim -> progreso -> done, y el camino de error. No llama a GetApplicationExt.
"""
from __future__ import annotations

import glob
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
for _p in (HERE, APP_ROOT):
    sys.path.insert(0, _p)

import worker  # noqa: E402  (importa connect pero NO conecta)
from jobstore import JobStore  # noqa: E402

RESULTS = os.path.join(APP_ROOT, "results")
store = JobStore(RESULTS)
results = []


def check(name, cond):
    results.append(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def cleanup(rid):
    for f in glob.glob(os.path.join(RESULTS, "_jobs", rid + "*")):
        os.remove(f)
    d = os.path.join(RESULTS, rid)
    if os.path.isdir(d):
        shutil.rmtree(d)


# --- camino feliz con estudio simulado ---
seen = []


def fake_run(app, sub, run_id=None, progress=None, **params):
    progress("fase simulada", 50)
    seen.append((sub, params))
    return {"study": "steady_state", "run_id": run_id, "compliance": {"overall": "PASA"}}


worker.STUDIES["steady_state"] = fake_run
job = store.create("steady_state", "ZTEST", {"pv_mw": 10, "bess_mw": 0, "bess_mwh": 0, "bess_mode": "discharge"})
rid = job["run_id"]
did = worker.process_one(None, store)
j = store.get(rid)
check("procesa un job de la cola", did)
check("status -> done", j["status"] == "done")
check("progress -> 100", j["progress"] == 100)
check("compliance propagado", j["compliance"] == {"overall": "PASA"})
check("result_file escrito", bool(j["result_file"]) and os.path.exists(os.path.join(APP_ROOT, j["result_file"])))
check("runner recibió sub y params", seen == [("ZTEST", {"pv_mw": 10, "bess_mw": 0, "bess_mwh": 0, "bess_mode": "discharge"})])

# --- camino de error: el worker no debe caer ---
def boom(app, sub, run_id=None, progress=None, **params):
    raise RuntimeError("kaboom")


worker.STUDIES["steady_state"] = boom
job2 = store.create("steady_state", "ZERR", {"pv_mw": 1, "bess_mw": 0, "bess_mwh": 0, "bess_mode": "discharge"})
worker.process_one(None, store)
j2 = store.get(job2["run_id"])
check("status -> error", j2["status"] == "error")
check("mensaje de error guardado", j2["error"] and "kaboom" in j2["error"])

# --- cola vacía ---
# limpiar antes de probar vacío
cleanup(rid)
cleanup(job2["run_id"])
check("cola vacía -> process_one False", worker.process_one(None, store) is False)

n_fail = sum(1 for c in results if not c)
print(f"\nRESULTADO: {len(results) - n_fail}/{len(results)} PASS")
sys.exit(1 if n_fail else 0)
