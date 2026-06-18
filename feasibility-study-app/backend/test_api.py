"""Test del API con TestClient (SIN PowerFactory): endpoints + encolado + validación."""
from __future__ import annotations

import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fastapi.testclient import TestClient  # noqa: E402

from app.config import RESULTS_DIR  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
results = []


def check(name, cond):
    results.append(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


# health
r = client.get("/api/health")
check("health 200/ok", r.status_code == 200 and r.json()["status"] == "ok")

# substations (lee results/substations.json generado en Etapa 1)
r = client.get("/api/substations")
check("substations 200", r.status_code == 200)
subs = r.json() if r.status_code == 200 else []
check("substations = 217", isinstance(subs, list) and len(subs) == 217)

# grid geojson
r = client.get("/api/grid")
check("grid FeatureCollection", r.status_code == 200 and r.json().get("type") == "FeatureCollection")

# crear corrida
r = client.post("/api/runs", json={"substation": "ZNARAD", "pv_mw": 50, "bess_mw": 20, "bess_mwh": 80})
check("POST /runs 202", r.status_code == 202)
job = r.json() if r.status_code == 202 else {}
rid = job.get("run_id", "")
check("run encolado (queued)", job.get("status") == "queued")
check("params guardados", job.get("params", {}).get("pv_mw") == 50)

# consultar
r = client.get(f"/api/runs/{rid}")
check("GET /runs/{id}", r.status_code == 200 and r.json()["run_id"] == rid)

# inexistente
check("GET inexistente 404", client.get("/api/runs/no_existe").status_code == 404)

# validación pydantic
check("bess_mode inválido 422", client.post("/api/runs", json={"substation": "X", "bess_mode": "bad"}).status_code == 422)
check("pv_mw negativo 422", client.post("/api/runs", json={"substation": "X", "pv_mw": -1}).status_code == 422)

# limpiar jobs de prueba creados
for r2 in client.get("/api/runs").json():
    if r2["substation"] in ("ZNARAD", "X") and r2["status"] == "queued":
        for f in glob.glob(os.path.join(RESULTS_DIR, "_jobs", r2["run_id"] + "*")):
            os.remove(f)

n_fail = sum(1 for c in results if not c)
print(f"\nRESULTADO: {len(results) - n_fail}/{len(results)} PASS")
sys.exit(1 if n_fail else 0)
