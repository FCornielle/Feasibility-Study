"""Extracción geográfica del modelo de PowerFactory -> GeoJSON.

Construye `results/grid_map.geojson` con:
  - Puntos (Point) por subestación con GPS (GPSlat/GPSlon).
  - Líneas (LineString) por línea con ruta GPS (ElmLne.GPScoords).

Nota de formato: PowerFactory entrega coordenadas como [lat, lon]; GeoJSON exige [lon, lat],
por lo que se invierte el orden al exportar.
"""
from __future__ import annotations

import json
import os

import connect
from substations import _voltages_by_substation

RESULTS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "results"))


def _substation_features(app) -> list[dict]:
    volt = _voltages_by_substation(app)
    feats = []
    for s in app.GetCalcRelevantObjects("*.ElmSubstat"):
        lat, lon = s.GetAttribute("GPSlat"), s.GetAttribute("GPSlon")
        if not (lat and lon):
            continue
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "kind": "substation",
                    "name": s.loc_name,
                    "voltages_kv": sorted(volt.get(s, [])),
                },
            }
        )
    return feats


def _line_features(app) -> list[dict]:
    feats = []
    for l in app.GetCalcRelevantObjects("*.ElmLne"):
        gc = l.GetAttribute("GPScoords")
        if not (isinstance(gc, list) and len(gc) >= 2):
            continue
        # gc: filas [lat, lon] -> GeoJSON [lon, lat]
        coords = [[row[1], row[0]] for row in gc if isinstance(row, list) and len(row) >= 2]
        if len(coords) < 2:
            continue
        try:
            kv = round(float(l.GetAttribute("bus1").GetAttribute("uknom")), 1)
        except Exception:
            kv = None
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {"kind": "line", "name": l.loc_name, "kv": kv},
            }
        )
    return feats


def build_grid_geojson(app) -> dict:
    return {
        "type": "FeatureCollection",
        "features": _substation_features(app) + _line_features(app),
    }


def write_grid_geojson(app, path: str | None = None) -> str:
    path = path or os.path.join(RESULTS_DIR, "grid_map.geojson")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fc = build_grid_geojson(app)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    return path


if __name__ == "__main__":
    app = connect.get_app()
    fc = build_grid_geojson(app)
    n_sub = sum(1 for f in fc["features"] if f["properties"]["kind"] == "substation")
    n_line = sum(1 for f in fc["features"] if f["properties"]["kind"] == "line")
    path = write_grid_geojson(app)
    print(f"GeoJSON: {n_sub} subestaciones + {n_line} líneas")
    print(f"Escrito: {path}")
