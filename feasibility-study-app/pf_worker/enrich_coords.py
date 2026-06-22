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
if not os.path.isdir(REFDATA):  # empaquetado (.exe): refdata se bundlea bajo RESOURCE/pf_worker/refdata
    try:
        import paths
        _r = os.path.join(paths.RESOURCE, "pf_worker", "refdata")
        if os.path.isdir(_r):
            REFDATA = _r
    except Exception:
        pass
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

    # El geojson usa el MISMO nombre final de substations.json (modelo + respaldo modom) -> consistencia.
    name_map = {s["name"]: s.get("display_name") or s["name"] for s in subs}
    geo_path = os.path.join(results_dir, "grid_map.geojson")
    if os.path.exists(geo_path):
        with open(geo_path, encoding="utf-8") as f:
            fc = json.load(f)
        for ft in fc["features"]:
            if ft["properties"].get("kind") == "substation":
                code = ft["properties"]["name"]
                ft["properties"]["display_name"] = name_map.get(code, code)
        with open(geo_path, "w", encoding="utf-8") as f:
            json.dump(fc, f, ensure_ascii=False)
    return n


def _norm_name(s: str) -> str:
    """Normaliza un nombre de subestación para emparejar (sin acentos, abreviaturas ni palabras genéricas)."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\bzf\b", "zona franca", s)        # abreviatura común en el modelo
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    # palabras genéricas/sufijos (Bp/Bt = barra/breaker, Terminal/Gen/Grupo/Vapor = terminales de planta)
    s = re.sub(r"\b(subestacion|subestaciones|electrica|electricas|hidroelectrica|central|planta|terminal|"
               r"gen|grupo|vapor|parque|eolico|fotovoltaico|psfv|pfv|kv|eted|ede|edenorte|edesur|eg|"
               r"bp|bt|bg|kps|de|del|la|el|los|las|ii|i|km|kilometro)\b", " ", s)
    s = re.sub(r"\b\d+\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def pdf_coord_index() -> dict:
    """nombre_normalizado -> (lat, lon) desde el plano PDF (refdata/pdf_substation_coords.csv)."""
    path = os.path.join(REFDATA, "pdf_substation_coords.csv")
    if not os.path.exists(path):
        return {}
    idx = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("lat") and r.get("lon"):
                key = _norm_name(r["name"])
                if key and key not in idx:
                    idx[key] = (float(r["lat"]), float(r["lon"]))
    return idx


def _pdf_match(idx: dict, *names) -> tuple | None:
    """Busca en el índice del PDF por cualquiera de los nombres dados (normalizados)."""
    for nm in names:
        c = idx.get(_norm_name(nm or ""))
        if c:
            return c
    return None


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
    pdf_idx = pdf_coord_index()
    modom_names = substation_display_names()    # code -> nombre legible (para intentar más variantes)
    stats = {"pf_model": 0, "modom_smc": 0, "manual_override": 0, "pdf": 0, "none": 0, "unmatched_names": []}

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
            # respaldo: plano PDF, emparejando por nombre legible (display del modelo, código, o nombre modom)
            p = _pdf_match(pdf_idx, s.get("display_name"), s["name"], modom_names.get(s["name"]))
            if p:
                s["lat"], s["lon"], s["coord_source"] = round(p[0], 6), round(p[1], 6), "pdf"
                s["has_gps"] = True
                stats["pdf"] += 1
            else:
                s["coord_source"] = None
                stats["none"] += 1

    with open(subs_path, "w", encoding="utf-8") as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)

    _rebuild_geojson_points(results_dir, subs)
    return stats


def _rebuild_geojson_points(results_dir: str, subs: list) -> None:
    """Regenera los puntos de subestación desde el set enriquecido y dibuja como RECTA (entre las dos
    subestaciones extremas) las líneas sin ruta GPS, usando las coordenadas enriquecidas."""
    geo_path = os.path.join(results_dir, "grid_map.geojson")
    with open(geo_path, encoding="utf-8") as f:
        fc = json.load(f)
    coord = {s["name"]: [s["lon"], s["lat"]] for s in subs if s.get("has_gps")}
    lines = []
    for ft in fc["features"]:
        if ft["properties"].get("kind") != "line":
            continue
        if ft.get("geometry") is None:           # línea sin ruta -> recta entre subestaciones
            p = ft["properties"]
            a, b = coord.get(p.get("sub1")), coord.get(p.get("sub2"))
            if a and b:
                ft["geometry"] = {"type": "LineString", "coordinates": [a, b]}
                ft["properties"]["straight"] = True
                lines.append(ft)
            # si falta alguna coordenada del extremo, no se puede dibujar -> se omite
        else:
            lines.append(ft)
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
