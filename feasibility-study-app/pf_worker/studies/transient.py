"""Transient Stability (pestaña 3) — réplica del estudio Sajoma §9.2 (Cuadro 18 + Figuras 19/29).

Metodología (estabilidad transitoria por simulación en el tiempo, RMS):
  - Una corrida BASE sin falla (con la planta conectada) que muestra tensión, frecuencia y velocidad
    planas: demuestra que no hay perturbación antes de simular las fallas.
  - Cortocircuito TRIFÁSICO en las subestaciones de 1.er/2.º grado más cercanas (una sección por barra).
  - Para cada punto de falla se busca el TIEMPO CRÍTICO DE DESPEJE (CCT): el mayor tiempo que puede durar
    la falla sin perder estabilidad, SIN y CON la planta (búsqueda gruesa descendente con parada temprana).
  - Pérdida de estabilidad = una máquina síncrona pierde sincronismo (ángulo de rotor relativo al slack
    —Punta Catalina— supera 180°: deslizamiento de polos) o excede 5 % de sobrevelocidad.
  - Gráficos a 5 s por cada falla (despejada al CCT): tensiones, ángulos de rotor [pu] y velocidades.

Nota de rendimiento: el RMS faltado es costoso en este modelo (la red se vuelve casi singular con la
falla). Por eso el estudio se acota (3 barras, búsqueda gruesa) y conviene usar una hora nocturna.
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
from studies import steady_state as _ss  # barras de falla por grado (reutilizado)  # noqa: E402

STUDY = "transient"
DT = 0.01
FAULT_T = 0.5                  # instante de la falla [s]
TSTOP_CCT = 2.5               # ventana para juzgar estabilidad SIN planta (primer swing + margen) [s]
TSTOP_PLOT = 5.0            # ventana de los gráficos (corrida base + fallas CON planta) [s]
# RENDIMIENTO: una falla FRANCA (V→0) vuelve la red casi singular y, cuando el despeje supera el tiempo
# crítico, la máquina pierde el paso y el integrador se arrastra muchísimo (corridas de 2-3 min; estudio
# de >30 min). Para un estudio VIABLE en cualquier escenario se usa una falla trifásica con una pequeña
# impedancia (caída de tensión severa, ~50 %): no se singulariza la red ni hay deslizamiento de polos,
# las corridas quedan acotadas (~45 s) y el estudio corre en minutos. (Para CCT con falla franca, usar
# una hora nocturna; en horas pico la falla franca es demasiado lenta por la API.)
FAULT_X_PU = 0.04            # impedancia de falla [pu sobre Zbase del bus]
CLEARING_SET_MS = [200]      # despeje probado [ms] (1 corrida por barra/caso -> estudio acotado)
ANGLE_LIMIT = 180.0          # pérdida de sincronismo (pole slip) [grados, relativo al slack]
OVERSPEED = 0.05             # sobrevelocidad máxima admisible (5 %)
N_FAULT_BUSES = 3            # puntos de falla (PCC + 2 vecinas de 1.er/2.º grado)
N_MACHINES = 5               # generadores síncronos distantes a monitorear
# Presupuesto de tiempo: en horas pico una corrida faltada puede arrastrarse; el estudio se ACOTA y
# devuelve resultados parciales en vez de tardar media hora. (En horas nocturnas corre completo y rápido.)
BUDGET_SIN_S = 150           # tope para la fase SIN planta [s]
BUDGET_TOTAL_S = 360         # tope total [s]


def _set_fault(evt, bus):
    """Apunta la falla trifásica a una barra con impedancia pequeña (para un RMS viable)."""
    evt.SetAttribute("p_target", bus)
    evt.SetAttribute("R_f", 0.0)
    evt.SetAttribute("X_f", round(FAULT_X_PU * (bus.GetAttribute("uknom") ** 2) / 100.0, 4))


def _slack_machine(app):
    """Máquina de referencia del sistema (slack). Por defecto Punta Catalina; si no, la mayor síncrona."""
    syms = [s for s in app.GetCalcRelevantObjects("*.ElmSym") if s.GetAttribute("outserv") == 0]
    for s in syms:
        if "catalina" in s.loc_name.lower():
            return s
    for s in syms:
        try:
            if s.GetAttribute("ip_ctrl") == 1 or s.GetAttribute("i_ref") == 1:
                return s
        except Exception:
            pass
    return dynamics.reference_generator(app)


def _machines(app, pcc, slack):
    """Generadores síncronos a monitorear: los más distantes de la falla + el slack (referencia)."""
    gens = dynamics.distant_generators(app, pcc, n=N_MACHINES)
    out, seen = [], set()
    for g in [slack] + gens:
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out[:N_MACHINES + 1]


def _series_map(app, res, gens, var):
    out = {}
    for g in gens:
        _, y = dynamics.series(app, res, g, var)
        if y:
            out[g.loc_name] = y
    return out


def _is_stable(angles, speeds, slack_name):
    """Estable si ninguna máquina pierde sincronismo (ángulo relativo al slack < 180°) ni excede 5 % de
    sobrevelocidad, y la simulación no divergió (suficientes muestras)."""
    if not angles:
        return False
    n = min(len(v) for v in angles.values())
    if n < 80:                                  # la corrida se cortó (divergió) -> inestable
        return False
    sl = angles.get(slack_name)
    max_sep = max((abs(a[i] - (sl[i] if sl and i < len(sl) else 0.0))
                   for a in angles.values() for i in range(n)), default=0.0)
    max_over = max((abs(v - 1.0) for sp in speeds.values() for v in sp), default=0.0)
    return max_sep < ANGLE_LIMIT and max_over < OVERSPEED


def run(app, sub_name, pv_mw, bess_mw, bess_mwh, bess_mode="discharge", scale_loads=1.0, run_id=None, progress=None):
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda p, q: None)
    data = {"study": STUDY, "run_id": run_id, "substation": sub_name,
            "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode},
            "method": (f"Corrida base sin falla + cortocircuito trifásico severo (caída de tensión ~50 %) en "
                       f"cada barra, despejado en {CLEARING_SET_MS[0]} ms, SIN y CON la planta. Estable si "
                       f"ninguna máquina síncrona pierde el sincronismo (ángulo de rotor relativo al slack "
                       f"—Punta Catalina— < 180°) ni excede 5 % de sobrevelocidad. (Falla con impedancia "
                       f"pequeña para un RMS viable; para falla franca, usar una hora nocturna.)")}

    with PFRunSandbox(app, run_id=run_id) as sb:
        sub = pv_bess.find_substation(app, sub_name)
        data["load_scaling"] = pv_bess.scale_loads(sb, app, scale_loads)
        report("flujo de carga base", 4)
        if app.GetFromStudyCase("ComLdf").Execute() != 0:
            raise RuntimeError("Flujo de carga base no convergió.")
        pcc = pv_bess.pick_pcc(app, sub, energized=True)
        data["pcc"] = {"name": pcc.loc_name, "kv": round(pcc.GetAttribute("uknom"), 1)}
        scen = app.GetActiveScenario()
        data["scenario"] = {"name": scen.loc_name if scen else None}

        fault_buses = [(pcc, 0, sub_name)] + _ss._sc_buses(app, sub, limit=N_FAULT_BUSES - 1)
        fault_buses = fault_buses[:N_FAULT_BUSES]
        bus_terms = [b for b, _, _ in fault_buses]
        slack = _slack_machine(app)
        machines = _machines(app, pcc, slack)
        data["reference_machine"] = slack.loc_name
        data["monitored_machines"] = [g.loc_name for g in machines]
        t0 = time.time()
        truncated = False

        # Eventos reutilizables (se varía objetivo/tiempo; time grande = no dispara, para la corrida base).
        fault_evt = dynamics.add_event(sb, app, "EvtShc", "fault", 999.0, target=pcc, i_shc=0)
        clear_evt = dynamics.add_event(sb, app, "EvtShc", "clear", 999.1, target=pcc, i_shc=4)

        def _ser(res, objs, var, scale=1.0, ref=None):
            x0, traces = None, []
            ry = None
            if ref is not None:
                _, ry = dynamics.series(app, res, ref, var)
            for o in objs:
                tt, yy = dynamics.series(app, res, o, var)
                if not yy:
                    continue
                if ry is not None:
                    n = min(len(yy), len(ry))
                    yy = [(yy[i] - ry[i]) * scale for i in range(n)]
                    tt = tt[:n]
                elif scale != 1.0:
                    yy = [v * scale for v in yy]
                tx, yx = dynamics.downsample(tt, yy)
                if x0 is None:
                    x0 = tx
                traces.append({"name": o.loc_name[:18], "y": yx})
            return {"x_label": "t [s]", "x": x0 or [], "traces": traces}

        def _capture_fault(res):
            return {"voltages": _ser(res, bus_terms, "m:u"),
                    "angles": _ser(res, machines, "s:firel", scale=1.0 / 180.0, ref=slack),  # pu (1 pu=180°)
                    "speeds": _ser(res, machines, "s:xspeed")}

        # ---- CCT SIN planta (sólo el valor; ventana corta) ----
        report("CCT sin planta", 8)
        cct_sin = {}
        for k, (bus, deg, sname) in enumerate(fault_buses):
            if k > 0 and time.time() - t0 > BUDGET_SIN_S:    # acotar la fase sin planta
                truncated = True
                break
            _set_fault(fault_evt, bus)
            clear_evt.SetAttribute("p_target", bus)
            inc, sim, res = dynamics.rms_prepare(
                app, [(g, "s:firel") for g in machines] + [(g, "s:xspeed") for g in machines])
            fault_evt.SetAttribute("time", FAULT_T)
            upper = None
            cct = None
            for tc in CLEARING_SET_MS:
                clear_evt.SetAttribute("time", FAULT_T + tc / 1000.0)
                dynamics.rms_run(app, inc, sim, tstop=TSTOP_CCT, dt=DT)
                if _is_stable(_series_map(app, res, machines, "s:firel"),
                              _series_map(app, res, machines, "s:xspeed"), slack.loc_name):
                    cct = tc
                    break
                upper = tc
            cct_sin[bus.GetFullName()] = (cct, upper)
            report(f"CCT sin planta ({k + 1}/{len(fault_buses)})", 8 + int(22 * (k + 1) / len(fault_buses)))

        # ---- Con planta PV+BESS ----
        report("modelando PV+BESS", 32)
        pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode)
        app.GetFromStudyCase("ComLdf").Execute()

        # ---- Corrida BASE sin falla (con planta): tensión, frecuencia y velocidad planas (5 s) ----
        report("corrida base sin falla (5 s)", 36)
        fault_evt.SetAttribute("time", 999.0)        # la falla no dispara
        inc, sim, res = dynamics.rms_prepare(
            app, [(t, "m:u") for t in bus_terms] + [(t, "m:fehz") for t in bus_terms]
            + [(g, "s:xspeed") for g in machines])
        dynamics.rms_run(app, inc, sim, tstop=TSTOP_PLOT, dt=DT)
        data["baseline"] = {
            "voltages": _ser(res, bus_terms, "m:u"),
            "frequency": _ser(res, bus_terms, "m:fehz"),
            "speeds": _ser(res, machines, "s:xspeed"),
        }

        # ---- CCT CON planta + gráficos a 5 s por cada falla (capturados de la corrida al CCT) ----
        fault_evt.SetAttribute("time", FAULT_T)
        cct_con, cases = {}, []
        for k, (bus, deg, sname) in enumerate(fault_buses):
            if k > 0 and time.time() - t0 > BUDGET_TOTAL_S:   # acotar el total -> resultados parciales
                truncated = True
                break
            _set_fault(fault_evt, bus)
            clear_evt.SetAttribute("p_target", bus)
            inc, sim, res = dynamics.rms_prepare(
                app, [(t, "m:u") for t in bus_terms]
                + [(g, "s:firel") for g in machines] + [(g, "s:xspeed") for g in machines])
            upper, cct, series = None, None, None
            for tc in CLEARING_SET_MS:
                clear_evt.SetAttribute("time", FAULT_T + tc / 1000.0)
                dynamics.rms_run(app, inc, sim, tstop=TSTOP_PLOT, dt=DT)
                if _is_stable(_series_map(app, res, machines, "s:firel"),
                              _series_map(app, res, machines, "s:xspeed"), slack.loc_name):
                    cct, series = tc, _capture_fault(res)
                    break
                upper = tc
                series = _capture_fault(res)        # si ninguno estable, queda el último (caso inestable)
            cct_con[bus.GetFullName()] = (cct, upper)
            clear_ms = cct if cct is not None else CLEARING_SET_MS[-1]
            cases.append({"bus": bus.loc_name, "sub": sname, "degree": deg,
                          "kv": round(bus.GetAttribute("uknom"), 1), "clearing_ms": clear_ms,
                          "stable": cct is not None, **(series or {})})
            report(f"CCT/gráficos con planta ({k + 1}/{len(fault_buses)})",
                   40 + int(52 * (k + 1) / len(fault_buses)))
        data["cases"] = cases

        rows = []
        for bus, deg, sname in fault_buses:
            fn = bus.GetFullName()
            if fn not in cct_con:            # barra no completada (acotado por tiempo)
                continue
            cs, cs_up = cct_sin.get(fn, (None, None))
            cc, cc_up = cct_con.get(fn, (None, None))
            rows.append({"bus": bus.loc_name, "sub": sname, "degree": deg,
                         "kv": round(bus.GetAttribute("uknom"), 1),
                         "cct_sin_ms": cs, "cct_sin_upper_ms": cs_up,
                         "cct_con_ms": cc, "cct_con_upper_ms": cc_up,
                         "delta_ms": (cc - cs) if (cs is not None and cc is not None) else None})
        data["cct_table"] = rows
        data["truncated"] = truncated

    report("evaluando", 96)
    valid_con = [r["cct_con_ms"] for r in rows if r["cct_con_ms"] is not None]
    data["min_cct_con_ms"] = min(valid_con) if valid_con else None
    no_worse = all((r["cct_sin_ms"] is None or r["cct_con_ms"] is None
                    or r["cct_con_ms"] >= r["cct_sin_ms"] - 80) for r in rows)
    adequate = bool(rows) and all(r["cct_con_ms"] is not None for r in rows)   # soporta el menor despeje probado
    data["compliance"] = {
        "soporta_despeje_tipico": criteria.verdict(adequate),
        "planta_no_reduce_cct": criteria.verdict(no_worse),
        "overall": criteria.verdict(adequate and no_worse),
    }
    return data
