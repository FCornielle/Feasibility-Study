"""Transient Stability (Etapa 6b): RMS ante falla severa (3φ) en el PCC con despeje.

Verifica que el sistema mantiene sincronismo y la tensión se recupera tras una falla trifásica
despejada por protecciones. Monitorea la tensión del PCC y el ángulo de rotor del generador de referencia.
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

STUDY = "transient"
FAULT_T = 1.0
CLEAR_MS = 150  # tiempo de despeje [ms]


def run(app, sub_name, pv_mw, bess_mw, bess_mwh, bess_mode="discharge", run_id=None, progress=None):
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
        plant = pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode)
        app.GetFromStudyCase("ComLdf").Execute()

        ref = dynamics.reference_generator(app)
        report(f"RMS falla 3φ {CLEAR_MS} ms en el PCC", 55)
        inc, sim, res = dynamics.rms_prepare(app, [(pcc, "m:u"), (ref, "s:firel")])
        dynamics.add_event(sb, app, "EvtShc", "fault", FAULT_T, target=pcc, i_shc=0)
        dynamics.add_event(sb, app, "EvtShc", "clear", FAULT_T + CLEAR_MS / 1000.0, target=pcc, i_shc=4)
        dynamics.rms_run(app, inc, sim, tstop=5.0, dt=0.01)

        report("evaluando estabilidad", 85)
        t, u = dynamics.series(app, res, pcc, "m:u")
        _, ang = dynamics.series(app, res, ref, "s:firel")

    u_pre = next((v for ti, v in zip(t, u) if ti < FAULT_T), None)
    u_min = dynamics.nadir(u)
    u_final = u[-1] if u else None
    ang0 = ang[0] if ang else 0.0
    ang_max = max((abs(a - ang0) for a in ang), default=None)
    tx, ux = dynamics.downsample(t, u)
    traces = [{"name": "Tensión PCC [pu]", "y": ux}]
    if ang:
        _, ax = dynamics.downsample(t, ang)
        traces.append({"name": "Ángulo rotor [°]", "y": ax})
    data["metrics"] = {
        "u_pre_pu": round(u_pre, 4) if u_pre else None,
        "u_min_pu": round(u_min, 4) if u_min is not None else None,
        "u_final_pu": round(u_final, 4) if u_final is not None else None,
        "rotor_angle_swing_deg": round(ang_max, 1) if ang_max is not None else None,
    }
    data["series"] = {"x_label": "t [s]", "x": tx, "traces": traces}
    recovers = u_final is not None and 0.90 <= u_final <= 1.10
    synchronism = ang_max is None or ang_max < 180.0   # sin pole slip
    data["compliance"] = {
        "tension_se_recupera": criteria.verdict(recovers),
        "mantiene_sincronismo": criteria.verdict(synchronism),
        "overall": criteria.verdict(recovers and synchronism),
    }
    return data
