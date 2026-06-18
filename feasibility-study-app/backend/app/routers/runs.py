"""Endpoints de corridas: encolar estudios, consultar estado y progreso (WebSocket)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ..config import store
from ..models import RunRequest

# TERMINAL importado desde el módulo compartido jobstore (config ya puso APP_ROOT en el path).
from jobstore import TERMINAL  # noqa: E402

router = APIRouter(prefix="/api", tags=["runs"])


@router.post("/runs", status_code=202)
def create_run(req: RunRequest):
    """Encola un estudio. El worker (proceso aparte) lo tomará y ejecutará en PowerFactory."""
    job = store.create(req.study, req.substation, req.to_params())
    return job


@router.get("/runs")
def list_runs():
    return store.list()


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    job = store.get(run_id)
    if job is None:
        raise HTTPException(404, "run no encontrado")
    return job


@router.websocket("/ws/runs/{run_id}")
async def ws_run(ws: WebSocket, run_id: str):
    """Emite el estado del run cada vez que cambia, hasta llegar a un estado terminal."""
    await ws.accept()
    last = None
    try:
        while True:
            job = store.get(run_id)
            if job is None:
                await ws.send_json({"error": "run no encontrado", "run_id": run_id})
                break
            snap = (job["status"], job["progress"], job["phase"])
            if snap != last:
                await ws.send_json(job)
                last = snap
            if job["status"] in TERMINAL:
                break
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
