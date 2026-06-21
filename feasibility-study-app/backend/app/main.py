"""App FastAPI: estudios de interconexión PV+BESS al SENI (DigSILENT PowerFactory).

Encola corridas hacia el worker persistente de PowerFactory y sirve el modelo (subestaciones/mapa).
Levantar:  uvicorn app.main:app --reload   (desde feasibility-study-app/backend)
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_OUT
from .routers import oc, runs, substations

app = FastAPI(title="Estudios de Interconexión PV+BESS (SENI/DigSILENT)", version="0.1.0")

# CORS abierto para el frontend React/Next en desarrollo (Etapa 5).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(substations.router)
app.include_router(runs.router)
app.include_router(oc.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/api/environment", tags=["environment"])
def environment():
    """Versiones de PowerFactory instaladas + selección activa (para los selectores de inicio)."""
    import connect  # import perezoso; no conecta al motor

    return {
        "pf_versions": connect.detect_pf_versions(),
        "active_version": os.environ.get("PF_VERSION", connect.DEFAULT_VERSION),
        "active_project": os.environ.get("PF_PROJECT", connect.DEFAULT_PROJECT),
    }


# La app de escritorio sirve el frontend exportado (frontend/out) desde el mismo origen que la API.
# Debe montarse AL FINAL para no tapar las rutas /api.
if os.path.isdir(FRONTEND_OUT):
    app.mount("/", StaticFiles(directory=FRONTEND_OUT, html=True), name="frontend")
