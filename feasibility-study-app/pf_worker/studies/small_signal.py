"""Small-Signal Stability (pestaña 2) — dos secciones, como el estudio Sajoma §9.1.

A) Análisis de autovalores y amortiguamiento: ante una perturbación pequeña se extraen los modos
   electromecánicos (autovalores λ = σ ± jω) por matrix-pencil/Prony de la respuesta RMS, y se reporta
   el ÍNDICE DE AMORTIGUAMIENTO del modo crítico, SIN y CON planta (mejora o no).
   (ComMod, el solver modal nativo de PowerFactory, no converge por API en este modelo; ver PENDIENTES.)
B) Perturbación pequeña: se grafica la velocidad de los generadores más DISTANTES del PCC (los que
   tienden a perder sincronismo), SIN y CON planta (estilo Figura 17 de Sajoma).
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
TSTOP, DT = 8.0, 0.01
FAULT_T, CLEAR_MS = 1.0, 60          # perturbación: falla trifásica breve en el PCC
PERTURBATION = "Falla trifásica de 60 ms en el PCC (perturbación pequeña para excitar los modos)"


def _record(app, res, gens):
    """Velocidad (pu) de cada generador tras la corrida RMS."""
    out = {}
    for g in gens:
        t, sp = dynamics.series(app, res, g, "s:xspeed")
        if sp:
            out[g.loc_name] = (t, sp)
    return out


def _analyze(speeds):
    """Sección B (series) + Sección A (modos) a partir de las velocidades de los gens distantes."""
    if not speeds:
        return None, [], None
    # COI = promedio de las velocidades (modo inter-área dominante)
    any_t = next(iter(speeds.values()))[0]
    n = min(len(v[1]) for v in speeds.values())
    coi = [sum(v[1][i] for v in speeds.values()) / len(speeds) for i in range(n)]
    post = [(any_t[i], coi[i]) for i in range(n) if any_t[i] > FAULT_T + CLEAR_MS / 1000.0]
    modes = dynamics.electromechanical_modes([p[1] for p in post], DT) if len(post) > 20 else []
    crit = modes[0]["damping_pct"] if modes else None        # modo crítico (menos amortiguado)
    # series para el frontend (downsampled)
    traces = []
    for name, (t, sp) in speeds.items():
        tx, yx = dynamics.downsample(t, sp)
        traces.append({"name": name, "y": yx})
    series = {"x_label": "t [s]", "x": dynamics.downsample(any_t, coi)[0], "traces": traces}
    return series, modes, crit


def run(app, sub_name, pv_mw, bess_mw, bess_mwh, bess_mode="discharge", run_id=None, progress=None):
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda p, q: None)
    data = {"study": STUDY, "run_id": run_id, "substation": sub_name, "perturbation": PERTURBATION,
            "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode}}

    with PFRunSandbox(app, run_id=run_id) as sb:
        sub = pv_bess.find_substation(app, sub_name)
        report("flujo de carga base", 8)
        if app.GetFromStudyCase("ComLdf").Execute() != 0:
            raise RuntimeError("Flujo de carga base no convergió.")
        pcc = pv_bess.pick_pcc(app, sub, energized=True)
        data["pcc"] = {"name": pcc.loc_name, "kv": round(pcc.GetAttribute("uknom"), 1)}
        scen = app.GetActiveScenario()
        hour = None
        if scen is not None:
            import re
            hour = int(re.sub(r"\D", "", scen.loc_name)) if re.search(r"\d", scen.loc_name) else None
        data["scenario"] = {"name": scen.loc_name if scen else None, "hour": hour}

        dgens = dynamics.distant_generators(app, pcc)
        data["distant_gens"] = [g.loc_name for g in dgens]

        # Perturbación (creada una vez; vale para ambas corridas)
        dynamics.add_event(sb, app, "EvtShc", "fault", FAULT_T, target=pcc, i_shc=0)
        dynamics.add_event(sb, app, "EvtShc", "clear", FAULT_T + CLEAR_MS / 1000.0, target=pcc, i_shc=4)

        # SIN planta
        report("RMS sin planta (perturbación pequeña)", 30)
        inc, sim, res = dynamics.rms_prepare(app, [(g, "s:xspeed") for g in dgens])
        dynamics.rms_run(app, inc, sim, tstop=TSTOP, dt=DT)
        series_base, modes_base, crit_base = _analyze(_record(app, res, dgens))

        # CON planta (despacho coherente con la hora)
        report("modelando PV+BESS", 55)
        pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode, hour=hour)
        app.GetFromStudyCase("ComLdf").Execute()
        report("RMS con planta", 70)
        inc, sim, res = dynamics.rms_prepare(app, [(g, "s:xspeed") for g in dgens])
        dynamics.rms_run(app, inc, sim, tstop=TSTOP, dt=DT)
        series_plant, modes_plant, crit_plant = _analyze(_record(app, res, dgens))

    report("evaluando amortiguamiento", 92)
    data["speeds"] = {"sin_planta": series_base, "con_planta": series_plant}
    data["modes"] = {"sin_planta": modes_base, "con_planta": modes_plant}
    data["damping_index"] = {"sin_planta": crit_base, "con_planta": crit_plant}

    stable = (crit_plant is not None) and crit_plant > 0
    no_worse = (crit_base is None) or (crit_plant is not None and crit_plant >= crit_base - 0.1)
    data["compliance"] = {
        "sistema_estable": criteria.verdict(stable),
        "no_reduce_amortiguamiento": criteria.verdict(no_worse),
        "overall": criteria.verdict(stable and no_worse),
    }
    return data
