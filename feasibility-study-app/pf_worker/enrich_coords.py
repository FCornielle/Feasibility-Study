"""Enriquece las coordenadas de subestaciones cruzando el modelo con datos de modom-pypsa.

Fuente de coordenadas (carpeta `refdata/`, derivada del proyecto modom-pypsa):
  - `buses_with_coords.csv`  : bus_id_modom -> lat/lon (resueltos por match SMC del OC).
  - `coordinate_overrides.csv`: overrides manuales confirmados por Fernando (máxima prioridad).
  - `pdd_barras.csv`         : export del modelo PDD 30-09-2025; mapea `subestacion` (código Z) -> `for_name` (código W de barra).

Enlace: `buses_with_coords.bus_id_modom` == `pdd_barras.for_name`. Por membresía de barra se asigna a cada
subestación el centroide de sus barras geolocalizadas. Prioridad: GPS del modelo PF > override manual > SMC modom.

Salida: reescribe `results/substations.json` (añadiendo `coord_source`) y `results/grid_map.geojson`
(puntos de subestación regenerados desde el set enriquecido; las líneas se conservan).
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict

REFDATA = os.path.join(os.path.dirname(__file__), "refdata")
RESULTS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "results"))


def _load_bus_coords() -> dict:
    """bus_id_modom -> (lat, lon, source); overrides manuales pisan a SMC."""
    coords = {}
    with open(os.path.join(REFDATA, "buses_with_coords.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["lat"] and r["lon"]:
                coords[r["bus_id_modom"]] = (float(r["lat"]), float(r["lon"]), r["coord_source"] or "smc_match")
    ov = os.path.join(REFDATA, "coordinate_overrides.csv")
    if os.path.exists(ov):
        with open(ov, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["lat"] and r["lon"]:
                    coords[r["bus_id_modom"]] = (float(r["lat"]), float(r["lon"]), "manual_override")
    return coords


def _substation_to_buscodes() -> dict:
    """código de subestación (Z) -> lista de for_name (W) de sus barras, desde el export del modelo."""
    sub = defaultdict(list)
    with open(os.path.join(REFDATA, "pdd_barras.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["subestacion"] and r["for_name"]:
                sub[r["subestacion"]].append(r["for_name"])
    return sub


def _bus_names() -> dict:
    """bus_id_modom (W) -> nombre legible (bus_name de modom)."""
    out = {}
    with open(os.path.join(REFDATA, "buses_with_coords.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("bus_name", "").strip():
                out[r["bus_id_modom"]] = r["bus_name"].strip()
    return out


def substation_display_names() -> dict:
    """código de subestación (Z) -> nombre legible (el bus_name más común de sus barras)."""
    names = _bus_names()
    sub2bus = _substation_to_buscodes()
    out = {}
    for ssub, codes in sub2bus.items():
        cand = [names[c] for c in codes if c in names]
        if cand:
            out[ssub] = Counter(cand).most_common(1)[0][0]
    return out


def add_display_names(results_dir: str = RESULTS_DIR) -> int:
    """Agrega `display_name` legible a substations.json y grid_map.geojson (idempotente, sin PF)."""
    disp = substation_display_names()
    subs_path = os.path.join(results_dir, "substations.json")
    with open(subs_path, encoding="utf-8") as f:
        subs = json.load(f)
    n = 0
    for s in subs:
        # Relleno: solo si no hay display_name del modelo (o es igual al código).
        if s.get("display_name") and s["display_name"] != s["name"]:
            continue
        name = disp.get(s["name"])
        s["display_name"] = name or s["name"]
        if name:
            n += 1
    with open(subs_path, "w", encoding="utf-8") as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)

    geo_path = os.path.join(results_dir, "grid_map.geojson")
    if os.path.exists(geo_path):
        with open(geo_path, encoding="utf-8") as f:
            fc = json.load(f)
        for ft in fc["features"]:
            if ft["properties"].get("kind") == "substation":
                code = ft["properties"]["name"]
                ft["properties"]["display_name"] = disp.get(code, code)
        with open(geo_path, "w", encoding="utf-8") as f:
            json.dump(fc, f, ensure_ascii=False)
    return n


def substation_coords_from_modom() -> dict:
    """código de subestación -> (lat, lon, source) usando el centroide de sus barras geolocalizadas."""
    bus = _load_bus_coords()
    sub2bus = _substation_to_buscodes()
    out = {}
    for ssub, codes in sub2bus.items():
        pts = [bus[c] for c in codes if c in bus]
        if not pts:
            continue
        lat = sum(p[0] for p in pts) / len(pts)
        lon = sum(p[1] for p in pts) / len(pts)
        src = "manual_override" if any(p[2] == "manual_override" for p in pts) else "modom_smc"
        out[ssub] = (round(lat, 6), round(lon, 6), src)
    return out


def enrich(results_dir: str = RESULTS_DIR) -> dict:
    subs_path = os.path.join(results_dir, "substations.json")
    with open(subs_path, encoding="utf-8") as f:
        subs = json.load(f)

    modom = substation_coords_from_modom()
    stats = {"pf_model": 0, "modom_smc": 0, "manual_override": 0, "none": 0, "unmatched_names": []}

    for s in subs:
        if s.get("has_gps"):  # GPS del propio modelo: prioridad máxima
            s["coord_source"] = "pf_model"
            stats["pf_model"] += 1
            continue
        m = modom.get(s["name"])
        if m:
            s["lat"], s["lon"], s["coord_source"] = m[0], m[1], m[2]
            s["has_gps"] = True
            stats[m[2]] += 1
        else:
            s["coord_source"] = None
            stats["none"] += 1

    with open(subs_path, "w", encoding="utf-8") as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)

    _rebuild_geojson_points(results_dir, subs)
    return stats


def _rebuild_geojson_points(results_dir: str, subs: list) -> None:
    """Regenera los puntos de subestación en el GeoJSON desde el set enriquecido; conserva las líneas."""
    geo_path = os.path.join(results_dir, "grid_map.geojson")
    with open(geo_path, encoding="utf-8") as f:
        fc = json.load(f)
    lines = [ft for ft in fc["features"] if ft["properties"].get("kind") == "line"]
    points = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
            "properties": {
                "kind": "substation",
                "name": s["name"],
                "voltages_kv": s["voltages_kv"],
                "coord_source": s.get("coord_source"),
            },
        }
        for s in subs
        if s.get("has_gps")
    ]
    fc["features"] = points + lines
    with open(geo_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)


if __name__ == "__main__":
    stats = enrich()
    total = sum(v for k, v in stats.items() if k in ("pf_model", "modom_smc", "manual_override"))
    print("Enriquecimiento de coordenadas:")
    print(f"  PF model (GPS propio):   {stats['pf_model']}")
    print(f"  modom SMC (OC):          {stats['modom_smc']}")
    print(f"  override manual:         {stats['manual_override']}")
    print(f"  sin coordenadas:         {stats['none']}")
    print(f"  TOTAL geolocalizadas:    {total}")
