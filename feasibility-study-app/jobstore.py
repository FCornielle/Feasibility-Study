"""JobStore — cola de trabajos basada en archivos, compartida entre backend y worker.

Por qué archivos: el worker de PowerFactory DEBE ser un proceso aparte (GetApplicationExt una sola
vez por proceso) y usa un intérprete específico; el backend FastAPI corre en su propio proceso. Una
cola en disco los desacopla sin infraestructura extra (Redis/colas) y sobrevive reinicios.

Un job es un JSON en `results/_jobs/<run_id>.json` con el ciclo: queued -> running -> done|error.
Escrituras atómicas (temp + os.replace). Un único worker consume la cola (PF es secuencial).
"""
from __future__ import annotations

import json
import os
import time
import uuid

# Estados terminales
TERMINAL = {"done", "error"}


class JobStore:
    def __init__(self, results_dir: str):
        self.dir = os.path.join(results_dir, "_jobs")
        os.makedirs(self.dir, exist_ok=True)

    # ---- rutas ----
    def _path(self, run_id: str) -> str:
        return os.path.join(self.dir, f"{run_id}.json")

    def _write(self, job: dict) -> None:
        job["updated_at"] = time.time()
        tmp = self._path(job["run_id"]) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._path(job["run_id"]))

    # ---- API backend ----
    def create(self, study: str, substation: str, params: dict) -> dict:
        run_id = time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        job = {
            "run_id": run_id,
            "study": study,
            "substation": substation,
            "params": params,
            "status": "queued",
            "progress": 0,
            "phase": "en cola",
            "result_file": None,
            "compliance": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._write(job)
        return job

    def get(self, run_id: str) -> dict | None:
        p = self._path(run_id)
        if not os.path.exists(p):
            return None
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None  # escritura en curso; el llamador reintenta

    def list(self) -> list[dict]:
        jobs = []
        for fn in os.listdir(self.dir):
            if fn.endswith(".json"):
                j = self.get(fn[:-5])
                if j:
                    jobs.append(j)
        return sorted(jobs, key=lambda j: j["created_at"], reverse=True)

    def update(self, run_id: str, **fields) -> dict | None:
        job = self.get(run_id)
        if job is None:
            return None
        job.update(fields)
        self._write(job)
        return job

    # ---- API worker ----
    def claim_next(self, worker_id: str = "worker") -> dict | None:
        """Toma el job 'queued' más antiguo y lo marca 'running'. Único worker => sin carrera real."""
        queued = [j for j in self.list() if j["status"] == "queued"]
        if not queued:
            return None
        job = min(queued, key=lambda j: j["created_at"])
        job.update(status="running", progress=1, phase="iniciando", worker=worker_id)
        self._write(job)
        return job
