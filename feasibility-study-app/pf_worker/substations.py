"""Enumeración de subestaciones del proyecto activo de PowerFactory.

Produce `results/substations.json`: lista de subestaciones con sus niveles de tensión
(derivados de los terminales contenidos) y coordenadas GPS cuando existen. Alimenta el
autocompletar y el mapa de selección del frontend (Etapa 5).
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

import connect

RESULTS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "results"))


def _voltages_by_substation(app) -> dict:
    """Tensiones nominales (kV) presentes en cada subestación, vía `cpSubstat` de los terminales."""
    volt = defaultdict(set)
    for t in app.GetCalcRelevantObjects("*.ElmTerm"):
        ss = t.GetAttribute("cpSubstat")
        if ss is None:
            continue
        try:
            volt[ss].add(round(float(t.GetAttribute("uknom")), 1))
        except Exception:
            pass
    return volt


def enumerate_substations(app) -> list[dict]:
    """Lista de subestaciones con nombre, tensiones (kV), lat/lon y bandera de GPS."""
    volt = _voltages_by_substation(app)
    out = []
    for s in app.GetCalcRelevantObjects("*.ElmSubstat"):
        lat = s.GetAttribute("GPSlat")
        lon = s.GetAttribute("GPSlon")
        has_gps = bool(lat) and bool(lon)
        out.append(
            {
                "name": s.loc_name,
                "voltages_kv": sorted(volt.get(s, [])),
                "lat": lat if has_gps else None,
                "lon": lon if has_gps else None,
                "has_gps": has_gps,
            }
        )
    out.sort(key=lambda d: d["name"])
    return out


def write_substations_json(app, path: str | None = None) -> str:
    path = path or os.path.join(RESULTS_DIR, "substations.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = enumerate_substations(app)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    app = connect.get_app()
    data = enumerate_substations(app)
    path = write_substations_json(app)
    with_gps = sum(1 for d in data if d["has_gps"])
    print(f"Subestaciones: {len(data)}  (con GPS: {with_gps})")
    print(f"Escrito: {path}")
    for d in data[:5]:
        print(" ", d["name"], d["voltages_kv"], "GPS" if d["has_gps"] else "-")
