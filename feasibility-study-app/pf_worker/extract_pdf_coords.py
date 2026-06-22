"""Extrae coordenadas de subestaciones desde el plano PDF de líneas de transmisión.

El PDF ('Plano RD Lineas Transmision 10062026.pdf') tiene cada subestación como un enlace a Google Maps
con coordenadas en la parte '@lat,lon'. Algunos enlaces traen el NOMBRE legible
(/place/Subestación+<Nombre>/@...); otros solo coordenadas en DMS (sin nombre).

Salida: refdata/pdf_substation_coords.csv  (name, lat, lon)  — solo los enlaces con nombre legible.
El PDF está gitignored; el CSV derivado vive en refdata/ (también gitignored) y se bundlea en el .exe.

Uso:  python pf_worker/extract_pdf_coords.py [ruta_al_pdf]
"""
from __future__ import annotations

import csv
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PDF = os.path.normpath(os.path.join(HERE, "..", "..", "Plano RD Lineas Transmision 10062026.pdf"))
OUT = os.path.join(HERE, "refdata", "pdf_substation_coords.csv")

_COORD = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
_PLACE = re.compile(r"/place/([^/@]+)")
_DMS = re.compile(r"^\d+.*[NSEW]")   # nombre que en realidad es una coordenada DMS (sin nombre legible)


def extract(pdf_path: str) -> dict:
    import pypdf
    reader = pypdf.PdfReader(pdf_path)
    named: dict[str, tuple[float, float]] = {}
    for page in reader.pages:
        for annot in (page.get("/Annots") or []):
            obj = annot.get_object()
            action = obj.get("/A")
            if not (action and action.get("/URI")):
                continue
            uri = urllib.parse.unquote(str(action.get("/URI")))
            mc = _COORD.search(uri)
            mp = _PLACE.search(uri)
            if not (mc and mp):
                continue
            name = mp.group(1).replace("+", " ").strip()
            if not name or _DMS.match(name):
                continue
            named.setdefault(name, (round(float(mc.group(1)), 6), round(float(mc.group(2)), 6)))
    return named


def main():
    pdf = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF
    if not os.path.exists(pdf):
        raise SystemExit(f"No se encontró el PDF: {pdf}")
    named = extract(pdf)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "lat", "lon"])
        for n, (la, lo) in sorted(named.items()):
            w.writerow([n, la, lo])
    print(f"{len(named)} subestaciones nombradas -> {OUT}")


if __name__ == "__main__":
    main()
