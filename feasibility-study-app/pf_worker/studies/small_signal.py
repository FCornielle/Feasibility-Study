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
TSTOP, DT = 6.0, 0.01
N_GENS = 7
MIN_DAMPING = 3.0                    # % amortiguamiento mínimo aceptable (criterio estándar small-signal)
PULSE_T, PULSE_MS = 0.5, 80          # falla en el PCC al inicio -> ventana post-falla larga (>5 s)
FAULT_X_PU = 0.20                    # impedancia de falla (pu sobre Zbase del PCC): dip moderado, RMS converge
PERTURBATION = "Falla trifásica de 80 ms en el PCC (perturbación para excitar los modos)"


def _record(app, res, gens):
    """Velocidad (pu) de cada generador tras la corrida RMS."""
    out = {}
    for g in gens:
        t, sp = dynamics.series(app, res, g, "s:xspeed")
        if sp:
            out[g.loc_name] = (t, sp)
    return out


def _analyze(speeds):
    """Sección B (series) + Sección A (modos). Devuelve (series, modos_plot, crit_damp, crit_freq).

    - modos_plot: extracción MULTI-SEÑAL (la respuesta post-falla de cada generador revela modos
      distintos -> muchos autovalores, como el plano modal de DigSILENT).
    - crit_damp/crit_freq: modo crítico desde el COI (promedio de velocidades). El COI promedia el ruido,
      así que su amortiguamiento es ROBUSTO para el veredicto; las señales individuales lo sesgan a 0.
    """
    if not speeds:
        return None, [], None, None
    any_t = next(iter(speeds.values()))[0]
    n = min(len(v[1]) for v in speeds.values())
    coi = [sum(v[1][i] for v in speeds.values()) / len(speeds) for i in range(n)]
    t0 = PULSE_T + PULSE_MS / 1000.0

    sigs = []
    for (t, sp) in speeds.values():
        post = [sp[i] for i in range(min(len(t), len(sp))) if t[i] > t0]
        if len(post) > 20:
            sigs.append(post)
    modes = dynamics.modes_from_signals(sigs, DT) if sigs else []

    # Veredicto ROBUSTO: amortiguamiento del envolvente de la oscilación dominante del COI por
    # decremento logarítmico (como Sajoma). Tomar el "modo de menor amortiguamiento" del matrix-pencil
    # es frágil: siempre aparecen autovalores espurios cercanos a 0/negativo y el mínimo agarra el peor.
    post_coi = [coi[i] for i in range(n) if any_t[i] > t0]
    dr = dynamics.damping_ratio(post_coi) if len(post_coi) > 20 else None
    crit_damp = round(dr * 100.0, 2) if dr is not None else None
    # Frecuencia del modo dominante = el que más generadores ven (mayor 'count'), banda inter-área primero.
    dom = max(modes, key=lambda m: (m["count"], -m["freq_hz"])) if modes else None
    crit_freq = dom["freq_hz"] if dom else None

    traces = []
    for name, (t, sp) in speeds.items():
        tx, yx = dynamics.downsample(t, sp)
        traces.append({"name": name, "y": yx})
    series = {"x_label": "t [s]", "x": dynamics.downsample(any_t, coi)[0], "traces": traces}
    return series, modes, crit_damp, crit_freq


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

        dgens = dynamics.distant_generators(app, pcc, n=N_GENS)
        data["distant_gens"] = [g.loc_name for g in dgens]

        # Perturbación: falla trifásica breve en el PCC, pero CON impedancia de falla para que la
        # tensión baje de forma moderada (no a 0). Una falla franca colapsa la tensión y satura los
        # inversores -> el RMS diverge y la simulación se corta antes de tiempo (sin oscilación post-falla,
        # sin modos). Con Xf ~ fracción de la Zbase del PCC el dip excita los modos y el RMS converge.
        zbase = (pcc.GetAttribute("uknom") ** 2) / 100.0   # ohm, base 100 MVA
        xf = round(FAULT_X_PU * zbase, 3)
        dynamics.add_event(sb, app, "EvtShc", "fault", PULSE_T, target=pcc, i_shc=0, R_f=0.0, X_f=xf)
        dynamics.add_event(sb, app, "EvtShc", "clear", PULSE_T + PULSE_MS / 1000.0, target=pcc, i_shc=4)

        # SIN planta
        report("RMS sin planta (perturbación pequeña)", 30)
        inc, sim, res = dynamics.rms_prepare(app, [(g, "s:xspeed") for g in dgens])
        dynamics.rms_run(app, inc, sim, tstop=TSTOP, dt=DT)
        series_base, modes_base, crit_base, fcrit_base = _analyze(_record(app, res, dgens))

        # CON planta (despacho coherente con la hora)
        report("modelando PV+BESS", 55)
        pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode, hour=hour)
        app.GetFromStudyCase("ComLdf").Execute()
        report("RMS con planta", 70)
        inc, sim, res = dynamics.rms_prepare(app, [(g, "s:xspeed") for g in dgens])
        dynamics.rms_run(app, inc, sim, tstop=TSTOP, dt=DT)
        series_plant, modes_plant, crit_plant, fcrit_plant = _analyze(_record(app, res, dgens))

    report("evaluando amortiguamiento", 92)
    data["speeds"] = {"sin_planta": series_base, "con_planta": series_plant}
    data["modes"] = {"sin_planta": modes_base, "con_planta": modes_plant}
    data["damping_index"] = {"sin_planta": crit_base, "con_planta": crit_plant}
    data["crit_freq"] = {"sin_planta": fcrit_base, "con_planta": fcrit_plant}

    # Criterio (Código de Conexión / práctica small-signal):
    #  - sistema estable: el modo crítico con planta tiene amortiguamiento > 0 (σ < 0).
    #  - amortiguamiento adecuado: modo crítico con planta >= MIN_DAMPING (bien amortiguado).
    #  - no reduce: tolerante al ruido de la extracción modal de una sola respuesta -> pasa si la caída es
    #    pequeña O si igual queda bien amortiguado (>= MIN_DAMPING).
    stable = (crit_plant is not None) and crit_plant > 0
    well_damped = (crit_plant is not None) and crit_plant >= MIN_DAMPING
    no_worse = (crit_base is None) or (crit_plant is not None and
                                       (crit_plant >= crit_base - 2.0 or crit_plant >= MIN_DAMPING))
    data["min_damping"] = MIN_DAMPING
    data["compliance"] = {
        "sistema_estable": criteria.verdict(stable),
        "amortiguamiento_adecuado": criteria.verdict(well_damped),
        "no_reduce_amortiguamiento": criteria.verdict(no_worse),
        "overall": criteria.verdict(stable and well_damped and no_worse),
    }
    return data
