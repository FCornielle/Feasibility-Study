"""Endpoints del modelo: subestaciones y mapa (alimentan el selector/mapa del frontend)."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException

from ..config import RESULTS_DIR

router = APIRouter(prefix="/api", tags=["model"])


def _load(name: str):
    path = os.path.join(RESULTS_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(503, f"{name} no generado. Corre pf_worker/substations.py y geo.py + enrich_coords.py.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@router.get("/substations")
def substations():
    """Lista de subestaciones (nombre, tensiones kV, coordenadas)."""
    return _load("substations.json")


@router.get("/grid")
def grid():
    """GeoJSON de subestaciones (puntos) y líneas (rutas) para el mapa."""
    return _load("grid_map.geojson")
