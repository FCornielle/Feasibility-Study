"""Endpoints del OC SENI (curva de demanda horaria) para el estudio quasi-dinámico."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..config import APP_ROOT  # noqa: F401  (asegura APP_ROOT en sys.path para importar oc_client)

import oc_client  # noqa: E402

router = APIRouter(prefix="/api/oc", tags=["oc"])


@router.get("/demand")
def demand(fecha: Optional[str] = None):
    """Demanda y generación horaria del SENI (GetGeneracionDemandaJSon)."""
    day = fecha or (date.today() - timedelta(days=4)).isoformat()
    try:
        rows = oc_client.generacion_demanda(day)
    except Exception as e:
        raise HTTPException(502, f"OC no disponible: {e}")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(502, "Respuesta del OC inesperada o vacía")
    return {
        "fecha": day,
        "horas": [
            {"periodo": int(r["PERIODO"]), "demanda_mw": r.get("DEMANDA"), "generacion_mw": r.get("GENERACION")}
            for r in rows if r.get("PERIODO") is not None
        ],
    }
