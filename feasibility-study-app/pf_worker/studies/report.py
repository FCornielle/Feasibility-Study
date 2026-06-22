"""Reporte de Interconexión (Etapa 8): corre TODOS los estudios de interconexión y los ensambla.

Realiza la visión central: dada una subestación + planta PV+BESS, ejecuta en serie los 6 estudios
(steady, small-signal, transient, voltage, frequency, quasi) y produce un informe consolidado al
estilo del *Estudio de Acceso al SENI* (Sajoma), con la matriz de cumplimiento del Código de Conexión.

Cada sub-estudio corre en su propio sandbox (no destructivo); si uno falla, el reporte continúa y lo marca.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studies import frequency, quasi_dynamic, small_signal, steady_state, transient, voltage  # noqa: E402

STUDY = "report"

# (clave, etiqueta, función). Orden del reporte estilo Sajoma.
SUBSTUDIES = [
    ("steady_state", "Comportamiento estático (flujo, N-1, cortocircuito)", steady_state.run),
    ("voltage", "Estabilidad de tensión", voltage.run),
    ("small-signal", "Estabilidad de pequeña señal (amortiguamiento)", small_signal.run),
    ("transient", "Estabilidad transitoria", transient.run),
    ("frequency", "Estabilidad de frecuencia", frequency.run),
    ("quasi", "Quasi-dinámico 24 h (OC)", quasi_dynamic.run),
]


def run(app, sub_name, pv_mw, bess_mw, bess_mwh, bess_mode="discharge", scale_loads=1.0, run_id=None, progress=None):
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda p, q: None)
    data = {
        "study": STUDY, "run_id": run_id, "substation": sub_name,
        "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode},
        "studies": {}, "labels": {}, "compliance_summary": {},
    }
    n = len(SUBSTUDIES)
    for i, (key, label, fn) in enumerate(SUBSTUDIES):
        data["labels"][key] = label
        report(f"{label}", int(100 * i / n))
        try:
            d = fn(app, sub_name, pv_mw, bess_mw, bess_mwh, bess_mode, scale_loads=scale_loads, run_id=f"{run_id}_{key}")
            data["studies"][key] = d
            data["compliance_summary"][key] = (d.get("compliance") or {}).get("overall", "-")
            if "pcc" in d and "pcc" not in data:
                data["pcc"] = d["pcc"]
        except Exception as e:  # un fallo no detiene el reporte
            data["studies"][key] = {"error": str(e)}
            data["compliance_summary"][key] = "ERROR"

    verdicts = list(data["compliance_summary"].values())
    data["overall"] = "PASA" if verdicts and all(v == "PASA" for v in verdicts) else "FALLA"
    data["compliance"] = {"overall": data["overall"]}  # para la cola/tabla genérica
    report("reporte completo", 100)
    return data
