"""Estabilidad de frecuencia (Etapa 6d): RMS ante desconexión de la planta PV+BESS.

Criterio: el nadir de frecuencia debe mantenerse por encima del PRIMER ESCALÓN del EDAC = 59.2 Hz
(ver criteria.py / docs). Se monitorea la velocidad del mayor generador síncrono como proxy de la
frecuencia del sistema (f = velocidad * 60).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import criteria  # noqa: E402
import dynamics  # noqa: E402
import pv_bess  # noqa: E402
from sandbox import PFRunSandbox  # noqa: E402

STUDY = "frequency"


def run(app, sub_name, pv_mw, bess_mw, bess_mwh, bess_mode="discharge", scale_loads=1.0, run_id=None, progress=None):
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda p, q: None)
    data = {"study": STUDY, "run_id": run_id, "substation": sub_name,
            "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode}}

    with PFRunSandbox(app, run_id=run_id) as sb:
        sub = pv_bess.find_substation(app, sub_name)
        report("flujo de carga base", 10)
        if app.GetFromStudyCase("ComLdf").Execute() != 0:
            raise RuntimeError("Flujo de carga base no convergió.")
        pcc = pv_bess.pick_pcc(app, sub, energized=True)
        data["pcc"] = {"name": pcc.loc_name, "kv": round(pcc.GetAttribute("uknom"), 1)}

        report("modelando PV+BESS", 30)
        # Estudio de regulación de frecuencia -> BESS de regulación primaria+secundaria (10% de la PV).
        plant = pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mode=bess_mode, bess_role="frequency")
        data["params"].update({"bess_mw": plant["params"]["bess_mw"],       # tamaño real (derivado de la PV)
                               "bess_mwh": plant["params"]["bess_mwh"], "bess_role": "frequency"})
        if app.GetFromStudyCase("ComLdf").Execute() != 0:
            raise RuntimeError("Flujo de carga con planta no convergió.")

        ref = dynamics.reference_generator(app)
        report("simulación RMS (desconexión de la planta)", 55)
        inc, sim, res = dynamics.rms_prepare(app, [(ref, "s:xspeed")])
        # Evento: desconectar la planta PV+BESS en t=1.0 s
        dynamics.add_event(sb, app, "EvtOutage", "trip_pv", 1.0, target=plant["pv"])
        dynamics.add_event(sb, app, "EvtOutage", "trip_bess", 1.0, target=plant["bess"])
        dynamics.rms_run(app, inc, sim, tstop=15.0, dt=0.01)

        report("evaluando frecuencia", 85)
        t, speed = dynamics.series(app, res, ref, "s:xspeed")
        freq = [s * dynamics.FN for s in speed]

    nadir_hz = dynamics.nadir(freq)
    rocof = dynamics.max_rocof(t, freq)
    tx, fx = dynamics.downsample(t, freq)
    data["metrics"] = {
        "nadir_hz": round(nadir_hz, 3) if nadir_hz else None,
        "peak_hz": round(dynamics.peak(freq), 3) if freq else None,
        "rocof_hz_s": round(rocof, 3),
        "edac_first_step_hz": criteria.FREQ_FIRST_EDAC_HZ,
        "ref_gen": ref.loc_name,
    }
    data["series"] = {"x_label": "t [s]", "x": tx,
                      "traces": [{"name": "Frecuencia [Hz]", "y": fx}]}
    ok = nadir_hz is not None and nadir_hz >= criteria.FREQ_FIRST_EDAC_HZ
    data["compliance"] = {"nadir_sobre_primer_escalon_edac": criteria.verdict(ok), "overall": criteria.verdict(ok)}
    return data
