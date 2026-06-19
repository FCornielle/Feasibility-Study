"""Small-Signal Stability (Etapa 6a): amortiguamiento de la oscilación tras un pulso.

ComMod (modal/autovalores) no converge en este modelo sin configuración especial, así que —como en el
estudio Sajoma— se evalúa el amortiguamiento de la oscilación electromecánica tras una perturbación
pequeña (falla trifásica breve), midiendo la razón de amortiguamiento por decremento logarítmico.
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

STUDY = "small-signal"
DAMPING_MIN = 0.03  # umbral práctico (valor exacto pendiente de norma, ver PENDIENTES.md)


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
        report("RMS con pulso (falla breve)", 55)
        inc, sim, res = dynamics.rms_prepare(app, [(ref, "s:xspeed")])
        dynamics.add_event(sb, app, "EvtShc", "fault", 1.0, target=pcc, i_shc=0)      # 3φ
        dynamics.add_event(sb, app, "EvtShc", "clear", 1.06, target=pcc, i_shc=4)     # despeje (60 ms)
        dynamics.rms_run(app, inc, sim, tstop=8.0, dt=0.01)

        report("midiendo amortiguamiento", 85)
        t, speed = dynamics.series(app, res, ref, "s:xspeed")
        freq = [s * dynamics.FN for s in speed]

    post = [f for ti, f in zip(t, freq) if ti > 1.1]  # tras el despeje
    zeta = dynamics.damping_ratio(post)
    tx, fx = dynamics.downsample(t, freq)
    data["metrics"] = {
        "damping_ratio": round(zeta, 4) if zeta is not None else None,
        "damping_min": DAMPING_MIN,
        "ref_gen": ref.loc_name,
    }
    data["series"] = {"x_label": "t [s]", "x": tx, "traces": [{"name": "Frecuencia [Hz]", "y": fx}]}
    stable = zeta is not None and zeta > 0
    damped = zeta is not None and zeta >= DAMPING_MIN
    data["compliance"] = {
        "oscilacion_estable": criteria.verdict(stable),
        "amortiguamiento_suficiente": criteria.verdict(damped),
        "overall": criteria.verdict(stable and damped),
    }
    return data
