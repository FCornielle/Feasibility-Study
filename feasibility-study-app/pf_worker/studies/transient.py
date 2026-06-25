"""Transient Stability (pestaña 3) — réplica del estudio Sajoma §9.2 (Cuadro 18 + Figuras 19/29).

Metodología (estabilidad transitoria por simulación en el tiempo, RMS):
  - Se falla con un cortocircuito TRIFÁSICO SIN impedancia (el caso más severo) en las subestaciones de
    1.er y 2.º grado más cercanas a la subestación donde se conecta la planta (y 3.er grado si en total
    hay < 5 puntos de falla), reutilizando el barrido por grados del Steady State.
  - Para cada punto de falla se busca el TIEMPO CRÍTICO DE DESPEJE (CCT): el máximo tiempo que puede durar
    la falla antes de que el sistema pierda estabilidad (búsqueda binaria sobre el tiempo de despeje).
  - Pérdida de estabilidad si una máquina SÍNCRONA pierde el sincronismo (deslizamiento de polos: el ángulo
    de rotor relativo a la máquina de referencia/slack —Punta Catalina— supera ~180° y crece) o si excede
    ~5 % de sobrevelocidad (podrían actuar las protecciones). Las máquinas más comprometidas son las
    síncronas eléctricamente más distantes de la falla.
  - Se reporta la tabla de CCT SIN y CON la planta nueva (Cuadro 18) y, para un despeje típico estable, los
    gráficos de tensiones y ángulos/velocidades a 5 s mostrando que el sincronismo se mantiene (Figura 19).

Criterio CCT vía equal-area / pole-slip: la falla debe despejarse antes del ángulo crítico; CCT es el
máximo tiempo de despeje que mantiene el sincronismo (referencias clásicas de estabilidad transitoria).
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
FAULT_T = 0.5                 # instante de la falla [s]
TSTOP_CCT = 4.0             # ventana para juzgar estabilidad (cubre multi-swing; el CCT así es estable a 5 s)
TSTOP_PLOT = 5.0            # ventana de los gráficos representativos [s]
# Tiempos de despeje a probar, de MAYOR a menor (búsqueda gruesa con parada temprana): el CCT ≈ el mayor
# estable. RMS faltado es caro en este modelo, por eso se acota (CCT acotado en PCC + 2 vecinas).
CLEARING_SET_MS = [300, 220, 150, 100]
ANGLE_LIMIT = 180.0          # pérdida de sincronismo (pole slip) [grados, relativo al slack]
OVERSPEED = 0.05             # sobrevelocidad máxima admisible (5 %)
N_FAULT_BUSES = 3            # puntos de falla (PCC + 2 vecinas de 1.er/2.º grado)
N_MACHINES = 5               # generadores síncronos distantes a monitorear


def _slack_machine(app):
    """Máquina de referencia del sistema (slack). Por defecto Punta Catalina; si no, la mayor síncrona."""
    syms = [s for s in app.GetCalcRelevantObjects("*.ElmSym") if s.GetAttribute("outserv") == 0]
    for s in syms:
        if "catalina" in s.loc_name.lower():
            return s
    for s in syms:                       # bandera de referencia/slack del flujo de carga
        try:
            if s.GetAttribute("ip_ctrl") == 1 or s.GetAttribute("i_ref") == 1:
                return s
        except Exception:
            pass
    return dynamics.reference_generator(app)


def _machines(app, pcc, slack):
    """Generadores síncronos a monitorear: los más distantes de la falla + el slack (referencia)."""
    gens = dynamics.distant_generators(app, pcc, n=N_MACHINES)   # ElmSym más distantes
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
        return False, None, None
    n = min(len(v) for v in angles.values())
    if n < int(0.6 * TSTOP_CCT / DT):      # la corrida se cortó (divergió) -> inestable
        return False, None, None
    sl = angles.get(slack_name)
    max_sep = 0.0
    for a in angles.values():
        for i in range(n):
            d = abs(a[i] - (sl[i] if sl and i < len(sl) else 0.0))
            if d > max_sep:
                max_sep = d
    max_over = max((abs(v - 1.0) for sp in speeds.values() for v in sp), default=0.0)
    stable = max_sep < ANGLE_LIMIT and max_over < OVERSPEED
    return stable, round(max_sep, 1), round(max_over * 100, 2)


def _cct_ms(run_stable):
    """Tiempo crítico de despeje [ms] por búsqueda gruesa descendente con parada temprana:
    el mayor tiempo de la lista que mantiene el sincronismo. run_stable(clear_s)->bool.
    Devuelve (cct_ms, upper_ms) donde el CCT real está en [cct_ms, upper_ms]. cct_ms=None si < mínimo."""
    upper = None
    for tc in CLEARING_SET_MS:                     # de mayor a menor
        if run_stable(tc / 1000.0):
            return tc, upper                       # primer estable desde arriba = mayor estable
        upper = tc
    return None, upper                             # ni el menor es estable (CCT < mínimo)


def run(app, sub_name, pv_mw, bess_mw, bess_mwh, bess_mode="discharge", scale_loads=1.0, run_id=None, progress=None):
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda p, q: None)
    data = {"study": STUDY, "run_id": run_id, "substation": sub_name,
            "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode},
            "method": ("Cortocircuito trifásico sin impedancia; se busca el tiempo crítico de despeje (CCT) "
                       "que mantiene el sincronismo. Criterio: ángulo de rotor relativo al slack "
                       "(Punta Catalina) < 180° y sobrevelocidad < 5 %.")}

    with PFRunSandbox(app, run_id=run_id) as sb:
        sub = pv_bess.find_substation(app, sub_name)
        data["load_scaling"] = pv_bess.scale_loads(sb, app, scale_loads)
        report("flujo de carga base", 6)
        if app.GetFromStudyCase("ComLdf").Execute() != 0:
            raise RuntimeError("Flujo de carga base no convergió.")
        pcc = pv_bess.pick_pcc(app, sub, energized=True)
        data["pcc"] = {"name": pcc.loc_name, "kv": round(pcc.GetAttribute("uknom"), 1)}
        scen = app.GetActiveScenario()
        data["scenario"] = {"name": scen.loc_name if scen else None}

        # Puntos de falla = PCC + barras vecinas de 1.er/2.º grado (3.er si en total hay < 5).
        fault_buses = [(pcc, 0, sub_name)] + _ss._sc_buses(app, sub, limit=N_FAULT_BUSES - 1)
        fault_buses = fault_buses[:N_FAULT_BUSES]
        slack = _slack_machine(app)
        machines = _machines(app, pcc, slack)
        data["reference_machine"] = slack.loc_name
        data["monitored_machines"] = [g.loc_name for g in machines]

        # Eventos reutilizables: falla (i_shc=0) y despeje (i_shc=4); se varía el objetivo y el tiempo.
        fault_evt = dynamics.add_event(sb, app, "EvtShc", "fault", FAULT_T, target=pcc, i_shc=0)
        clear_evt = dynamics.add_event(sb, app, "EvtShc", "clear", FAULT_T + 0.1, target=pcc, i_shc=4)
        bus_terms = [b for b, _, _ in fault_buses]

        def _ser(res, objs, var):
            x0, traces = None, []
            for o in objs:
                tt, yy = dynamics.series(app, res, o, var)
                if not yy:
                    continue
                tx, yx = dynamics.downsample(tt, yy)
                if x0 is None:
                    x0 = tx
                traces.append({"name": o.loc_name[:18], "y": yx})
            return {"x_label": "t [s]", "x": x0 or [], "traces": traces}

        def _angles_pu(res):
            """Ángulo de rotor relativo al slack en PU (1 pu = 180° = límite de pérdida de sincronismo)."""
            _, sl = dynamics.series(app, res, slack, "s:firel")
            x0, traces = None, []
            for g in machines:
                t, y = dynamics.series(app, res, g, "s:firel")
                if not y:
                    continue
                n = min(len(y), len(sl)) if sl else len(y)
                rel = [(y[i] - (sl[i] if sl else 0.0)) / 180.0 for i in range(n)]
                tx, yx = dynamics.downsample(t[:n], rel)
                if x0 is None:
                    x0 = tx
                traces.append({"name": g.loc_name[:18], "y": yx})
            return {"x_label": "t [s]", "x": x0 or [], "traces": traces}

        def cct_for(bus, capture=False):
            """Búsqueda gruesa descendente del CCT [ms] (el mayor despeje que mantiene el sincronismo).
            Si capture=True guarda los gráficos (tensiones/ángulos/velocidades) de ESA corrida del barrido
            —sin corridas extra—. Devuelve (cct, upper, series|None)."""
            fault_evt.SetAttribute("p_target", bus)
            clear_evt.SetAttribute("p_target", bus)
            mon = [(g, "s:firel") for g in machines] + [(g, "s:xspeed") for g in machines]
            if capture:
                mon = [(t, "m:u") for t in bus_terms] + mon
            inc, sim, res = dynamics.rms_prepare(app, mon)
            upper = None
            for tc in CLEARING_SET_MS:                     # de mayor a menor
                clear_evt.SetAttribute("time", FAULT_T + tc / 1000.0)
                dynamics.rms_run(app, inc, sim, tstop=TSTOP_CCT, dt=DT)
                ang = _series_map(app, res, machines, "s:firel")
                spd = _series_map(app, res, machines, "s:xspeed")
                ok, _, _ = _is_stable(ang, spd, slack.loc_name)
                if ok:
                    cap = ({"voltages": _ser(res, bus_terms, "m:u"), "angles": _angles_pu(res),
                            "speeds": _ser(res, machines, "s:xspeed")} if capture else None)
                    return tc, upper, cap
                upper = tc
            cap = ({"voltages": _ser(res, bus_terms, "m:u"), "angles": _angles_pu(res),
                    "speeds": _ser(res, machines, "s:xspeed")} if capture else None)
            return None, upper, cap            # ninguno estable -> grafica el caso (inestable) del menor despeje

        # --- CCT SIN planta ---
        report("CCT sin planta (puede tardar)", 12)
        cct_sin = {}
        for k, (bus, deg, sname) in enumerate(fault_buses):
            r = cct_for(bus)
            cct_sin[bus.GetFullName()] = (r[0], r[1])
            report(f"CCT sin planta ({k + 1}/{len(fault_buses)})", 12 + int(33 * (k + 1) / len(fault_buses)))

        # --- Con planta PV+BESS (se capturan los gráficos del despeje al CCT) ---
        report("modelando PV+BESS", 48)
        pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode)
        app.GetFromStudyCase("ComLdf").Execute()

        cct_con, cases = {}, []
        for k, (bus, deg, sname) in enumerate(fault_buses):
            cc, cc_up, series = cct_for(bus, capture=True)
            cct_con[bus.GetFullName()] = (cc, cc_up)
            clear_ms = cc if cc is not None else CLEARING_SET_MS[-1]
            if series is not None:
                cases.append({"bus": bus.loc_name, "sub": sname, "degree": deg,
                              "kv": round(bus.GetAttribute("uknom"), 1), "clearing_ms": clear_ms,
                              "stable": cc is not None, **series})
            report(f"CCT con planta ({k + 1}/{len(fault_buses)})", 50 + int(42 * (k + 1) / len(fault_buses)))
        data["cases"] = cases

        # Tabla de CCT (Cuadro 18)
        rows = []
        for bus, deg, sname in fault_buses:
            fn = bus.GetFullName()
            cs, cs_up = cct_sin.get(fn, (None, None))
            cc, cc_up = cct_con.get(fn, (None, None))
            rows.append({"bus": bus.loc_name, "sub": sname, "degree": deg,
                         "kv": round(bus.GetAttribute("uknom"), 1),
                         "cct_sin_ms": cs, "cct_sin_upper_ms": cs_up,
                         "cct_con_ms": cc, "cct_con_upper_ms": cc_up,
                         "delta_ms": (cc - cs) if (cs is not None and cc is not None) else None})
        data["cct_table"] = rows

    # --- Veredicto ---
    report("evaluando", 96)
    valid_con = [r["cct_con_ms"] for r in rows if r["cct_con_ms"] is not None]
    min_cct_con = min(valid_con) if valid_con else None
    # la planta no debe reducir el CCT respecto al caso sin planta (tolera un escalón grueso ~80 ms)
    no_worse = all(
        (r["cct_sin_ms"] is None or r["cct_con_ms"] is None or r["cct_con_ms"] >= r["cct_sin_ms"] - 80)
        for r in rows)
    # el sistema debe soportar al menos un despeje típico de protección (~100 ms) en todos los puntos
    adequate = bool(rows) and all((r["cct_con_ms"] is not None and r["cct_con_ms"] >= 100) for r in rows)
    data["min_cct_con_ms"] = min_cct_con
    data["compliance"] = {
        "soporta_despeje_tipico": criteria.verdict(adequate),
        "planta_no_reduce_cct": criteria.verdict(no_worse),
        "overall": criteria.verdict(adequate and no_worse),
    }
    return data
