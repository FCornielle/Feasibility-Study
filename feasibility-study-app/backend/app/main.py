"""App FastAPI: estudios de interconexión PV+BESS al SENI (DigSILENT PowerFactory).

Encola corridas hacia el worker persistente de PowerFactory y sirve el modelo (subestaciones/mapa).
Levantar:  uvicorn app.main:app --reload   (desde feasibility-study-app/backend)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import runs, substations

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


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
