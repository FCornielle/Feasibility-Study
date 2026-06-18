"""Exportación de resultados de estudios a `results/<run_id>/<study>.json`."""
from __future__ import annotations

import json
import os

RESULTS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "results"))


def write_results(run_id: str, study: str, data: dict) -> str:
    run_dir = os.path.join(RESULTS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, f"{study}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path
