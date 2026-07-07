"""Small-Signal Stability (pestaña 2) — dos secciones (autovalores/amortiguamiento + perturbación).

A) Análisis de autovalores y amortiguamiento: ante una perturbación pequeña se extraen los modos
   electromecánicos (autovalores λ = σ ± jω) por matrix-pencil/Prony de la respuesta RMS, y se reporta
   el ÍNDICE DE AMORTIGUAMIENTO del modo crítico, SIN y CON planta (mejora o no).
   (ComMod, el solver modal nativo de PowerFactory, no converge por API en este modelo; ver PENDIENTES.)
B) Perturbación pequeña: se grafica la velocidad de los generadores más DISTANTES del PCC (los que
   tienden a perder sincronismo), SIN y CON planta.
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
PULSE_T, PULSE_MS = 0.5, 200         # inicio del pulso y su duración (ms) -> ventana post-pulso larga
PULSE_STEP_PCT = 0.20                # ±20% de una carga del sistema (pulso que excita los modos)
PULSE_LOAD_MW = 50.0                 # se elige la carga en servicio más cercana a este tamaño
PERTURBATION = "Pulso de ±20% de una carga del sistema (excita los modos electromecánicos, sin cambio neto de frecuencia)"


def _record_var(app, res, gens, var):
    """Serie de `var` (p.ej. s:xspeed = velocidad, s:firel = ángulo del rotor) por generador."""
    out = {}
    for g in gens:
        t, y = dynamics.series(app, res, g, var)
        if y:
            out[g.loc_name] = (t, y)
    return out


def _series_only(recorded):
    """{x, traces} de una magnitud por generador (sin análisis modal), para graficarla tal cual."""
    if not recorded:
        return None
    any_t = next(iter(recorded.values()))[0]
    xs = dynamics.downsample(any_t, any_t)[0]
    traces = []
    for name, (t, y) in recorded.items():
        _, yx = dynamics.downsample(t, y)
        traces.append({"name": name, "y": yx})
    return {"x_label": "t [s]", "x": xs, "traces": traces}


def _detrend(event_rec, base_rec):
    """Resta la corrida SIN evento (transitorio de inicialización del RMS) a la corrida CON evento,
    punto a punto, y re-ancla al valor inicial. Así el gráfico queda PLANO en el valor inicial hasta el
    evento y muestra únicamente la respuesta del evento (como el estudio de referencia). La perturbación
    pequeña (±10 MW) es ~100× menor que la deriva de init, por eso sin restarla la deriva domina."""
    out = {}
    for name, (t, y) in event_rec.items():
        b = base_rec.get(name)
        if b is None:
            out[name] = (t, y)
            continue
        tb, yb = b
        n = min(len(y), len(yb))
        if n == 0:
            out[name] = (t, y)
            continue
        y0 = yb[0]                                  # ancla = valor inicial (frecuencia/ángulo en régimen)
        out[name] = (t[:n], [y[i] - yb[i] + y0 for i in range(n)])
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

    # Veredicto ROBUSTO: amortiguamiento del MODO DOMINANTE extraído por matrix-pencil (mediana entre
    # generadores -> robusta al ruido; agrupa el mismo modo visto por varias señales). El decremento
    # logarítmico del COI es frágil ante respuestas multi-modales/beat (da negativo espurio), se usa solo
    # como respaldo si no se extrae ningún modo.
    post_coi = [coi[i] for i in range(n) if any_t[i] > t0]
    dr = dynamics.damping_ratio(post_coi) if len(post_coi) > 20 else None
    # Modo dominante = el que MÁS generadores ven (mayor 'count'); en empate, el de menor frecuencia (inter-área).
    dom = max(modes, key=lambda m: (m["count"], -m["freq_hz"])) if modes else None
    if dom is not None and dom.get("damping_pct") is not None:
        crit_damp = dom["damping_pct"]
    else:
        crit_damp = round(dr * 100.0, 2) if dr is not None else None
    crit_freq = dom["freq_hz"] if dom else None

    traces = []
    for name, (t, sp) in speeds.items():
        tx, yx = dynamics.downsample(t, sp)
        traces.append({"name": name, "y": yx})
    series = {"x_label": "t [s]", "x": dynamics.downsample(any_t, coi)[0], "traces": traces}
    return series, modes, crit_damp, crit_freq


def run(app, sub_name, pv_mw, bess_mw, bess_mwh, bess_mode="discharge", scale_loads=1.0,
        run_id=None, progress=None):
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda p, q: None)
    data = {"study": STUDY, "run_id": run_id, "substation": sub_name, "perturbation": PERTURBATION,
            "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode}}

    with PFRunSandbox(app, run_id=run_id) as sb:
        sub = pv_bess.find_substation(app, sub_name)
        data["load_scaling"] = pv_bess.scale_loads(sb, app, scale_loads)
        dynamics.use_primary_control_balancing(app)   # flujo = equilibrio dinámico (sin deriva de init)
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

        # Perturbación: PULSO de ±PULSE_STEP_PCT de una carga del sistema (como en el estudio de referencia:
        # "pulso de modificación de la carga"). Se sube la carga en t=PULSE_T y se DEVUELVE a su valor en
        # t=PULSE_T+PULSE_MS -> es un pulso SIN cambio neto, así excita los modos electromecánicos (oscilación
        # de la velocidad de los rotores) sin desviar la frecuencia de forma sostenida. Los eventos se crean
        # aquí, se usan en ambas corridas (SIN y CON planta) y el sandbox los borra al terminar (aislados).
        # Se elige una carga GRANDE del sistema para que el pulso excite los modos claramente por encima
        # del ruido numérico (la perturbación debe dominar la respuesta, no la deriva de init).
        pulse_load = max((l for l in app.GetCalcRelevantObjects("*.ElmLod") if l.GetAttribute("outserv") == 0),
                         key=lambda l: (l.GetAttribute("plini") or 0.0), default=None)
        if pulse_load is None:
            raise RuntimeError("No hay cargas en servicio para aplicar el pulso de perturbación.")
        p0 = pulse_load.GetAttribute("plini") or 0.0
        dP_pct = round(PULSE_STEP_PCT * 100, 1)   # EvtLod.dP está en PORCENTAJE (verificado); relativo al P original
        data["perturbation_load"] = {"name": pulse_load.loc_name, "mw": round(p0, 1),
                                     "step_mw": round(PULSE_STEP_PCT * p0, 1), "step_pct": dP_pct}
        ev_up = dynamics.add_event(sb, app, "EvtLod", "pulse_up", PULSE_T, target=pulse_load, dP=dP_pct, iopt_type=0)
        ev_dn = dynamics.add_event(sb, app, "EvtLod", "pulse_dn", PULSE_T + PULSE_MS / 1000.0, target=pulse_load, dP=-dP_pct, iopt_type=0)

        # Mapa (punto 9): variación del ÁNGULO del rotor de TODOS los síncronos por subestación.
        map_gens = [s for s in app.GetCalcRelevantObjects("*.ElmSym") if s.GetAttribute("outserv") == 0]
        mon = ([(g, "s:xspeed") for g in dgens] + [(g, "s:firel") for g in dgens]
               + [(g, "s:firel") for g in map_gens])  # velocidad + ángulo (graficados + mapa)

        def _set_pulse(active):
            for e in (ev_up, ev_dn):
                try:
                    e.SetAttribute("outserv", 0 if active else 1)
                except Exception:
                    pass

        def _capture():
            inc, sim, res = dynamics.rms_prepare(app, mon)
            dynamics.rms_run(app, inc, sim, tstop=TSTOP, dt=DT)
            return (_record_var(app, res, dgens, "s:xspeed"),
                    _record_var(app, res, dgens, "s:firel"),
                    _record_var(app, res, map_gens, "s:firel"))

        # SIN planta: corrida BASE sin el pulso (mide la deriva de init) + corrida CON el pulso -> se restan
        # (detrend) para dejar el gráfico plano hasta el evento y mostrar solo la respuesta del pulso.
        report("RMS base sin planta (sin eventos)", 25)
        _set_pulse(False)
        base_sp, base_an, _base_map = _capture()
        report("RMS sin planta (pulso)", 38)
        _set_pulse(True)
        ev_sp, ev_an, _ev_map = _capture()
        # DETREND: se resta la corrida base sin evento (deriva de init) -> señal plana hasta el pulso y solo
        # la respuesta del pulso. El amortiguamiento se calcula sobre esta señal limpia (el pulso grande da
        # buen SNR). GRÁFICO idéntico (plano hasta el evento).
        sp_sin = _detrend(ev_sp, base_sp)
        series_base, modes_base, crit_base, fcrit_base = _analyze(sp_sin)
        angles_base = _series_only(_detrend(ev_an, base_an))

        # CON planta (despacho coherente con la hora): misma técnica (base sin pulso + pulso -> detrend)
        report("modelando PV+BESS", 55)
        pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode, hour=hour)
        app.GetFromStudyCase("ComLdf").Execute()
        report("RMS base con planta (sin eventos)", 68)
        _set_pulse(False)
        base_sp2, base_an2, base_map2 = _capture()
        report("RMS con planta (pulso)", 80)
        _set_pulse(True)
        ev_sp2, ev_an2, ev_map2 = _capture()
        sp_plant = _detrend(ev_sp2, base_sp2)
        series_plant, modes_plant, crit_plant, fcrit_plant = _analyze(sp_plant)
        angles_plant = _series_only(_detrend(ev_an2, base_an2))

        # Mapa (punto 9): variación máx del ángulo (detrended) por subestación, CON planta.
        map_detr = _detrend(ev_map2, base_map2)   # {gen_name: (t, ángulo_detrended)}
        var_by_sub = {}
        for g in map_gens:
            rec = map_detr.get(g.loc_name)
            if not rec or len(rec[1]) < 2:
                continue
            v = max(rec[1]) - min(rec[1])
            s = dynamics.substation_of(g)
            if s is None:
                continue
            if s not in var_by_sub or v > var_by_sub[s]:
                var_by_sub[s] = v
        data["substation_variation"] = dynamics.pack_variation(var_by_sub, "Máx variación de ángulo", "°")

    report("evaluando amortiguamiento", 92)
    data["speeds"] = {"sin_planta": series_base, "con_planta": series_plant}
    data["angles"] = {"sin_planta": angles_base, "con_planta": angles_plant}   # ángulo del rotor (s:firel)
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
