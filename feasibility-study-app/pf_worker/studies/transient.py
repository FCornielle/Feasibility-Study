"""Transient Stability (pestaña 3) — réplica del estudio Sajoma §9.2 (Cuadro 18 + Figuras 19/29).

  - Corrida BASE sin falla (con planta) a 60 s: muestra tensión, frecuencia y velocidad para ver dónde
    se estabiliza el sistema antes de simular las fallas.
  - Cortocircuito TRIFÁSICO FRANCO en las subestaciones de 1.er/2.º grado más cercanas (una sección por
    barra). Se grafica la tensión de varias barras vecinas (no solo la fallada).
  - TIEMPO CRÍTICO DE DESPEJE (CCT): se BUSCA (búsqueda binaria) el mayor tiempo de despeje que mantiene
    el sincronismo, SIN y CON la planta. No se detiene en un valor fijo.
  - Pérdida de estabilidad = CUALQUIER máquina síncrona del sistema marca la señal nativa de PowerFactory
    s:outofstep (pérdida de paso). Se evalúan TODOS los generadores, no solo los graficados, porque el que
    se desincroniza suele ser una máquina cercana a la falla. (Método del DPL CritClearing.)

Rendimiento: el RMS con falla franca es rápido en horas nocturnas (~3-9 s/corrida) pero en horas de alta
generación solar puede interrumpir el motor; usar una hora nocturna (P20–P05). El worker se reinicia solo.
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
from studies import steady_state as _ss  # barras por grado (reutilizado)  # noqa: E402

STUDY = "transient"
DT = 0.01
FAULT_T = 0.5
TSTOP_CCT = 2.0              # ventana de las corridas de búsqueda (corta: las inestables no se arrastran) [s]
TSTOP_PLOT = 5.0            # ventana de los gráficos de cada falla [s]
TSTOP_BASE = 60.0          # ventana de la corrida base sin falla [s]
# Búsqueda del CCT por bisección exacta hasta CCT_TOL_MS (20 ms): el CCT reportado queda a <=20 ms
# del punto real de pérdida de sincronismo (como el dtmax del DPL), sin disparar demasiadas corridas.
CCT_MIN_MS, CCT_MAX_MS, CCT_TOL_MS = 80, 400, 20
N_FAULT_BUSES = 3           # puntos de falla (una sección c/u)
N_MONITOR_BUSES = 6         # barras cuya tensión se grafica (>5, de 1.er/2.º/3.er grado)
N_MACHINES = 5


def _slack_machine(app):
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
    gens = dynamics.distant_generators(app, pcc, n=N_MACHINES)
    out, seen = [], set()
    for g in [slack] + gens:
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out[:N_MACHINES + 1]


def _display_names():
    """código de subestación -> nombre legible (desde results/substations.json)."""
    import json
    import paths
    out = {}
    try:
        with open(os.path.join(paths.RESULTS_DIR, "substations.json"), encoding="utf-8") as f:
            for s in json.load(f):
                out[s["name"]] = s.get("display_name") or s["name"]
    except Exception:
        pass
    return out


def run(app, sub_name, pv_mw, bess_mw, bess_mwh, bess_mode="discharge", scale_loads=1.0, run_id=None, progress=None):
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda p, q: None)
    data = {"study": STUDY, "run_id": run_id, "substation": sub_name,
            "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode},
            "method": ("Corrida base sin falla (60 s) + cortocircuito trifásico franco en cada barra. Se busca "
                       "el tiempo crítico de despeje (CCT) por búsqueda binaria: el mayor despeje sin que NINGÚN "
                       "generador síncrono del sistema pierda el sincronismo (señal nativa s:outofstep de "
                       "PowerFactory, evaluada en toda la flota). Los gráficos de cada falla se trazan a ese CCT "
                       "y muestran las máquinas más comprometidas. Usar hora nocturna (en horas de alta solar el "
                       "RMS se interrumpe).")}

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

        # Barras vecinas por grado (reutiliza el barrido del Steady State).
        sc = _ss._sc_buses(app, sub, limit=N_MONITOR_BUSES)            # [(term, grado, sub_code)]
        all_buses = [(pcc, 0, sub_name)] + [(t, d, s) for t, d, s in sc if t.GetFullName() != pcc.GetFullName()]
        monitor_buses = [b for b, _, _ in all_buses][:N_MONITOR_BUSES]   # tensión graficada (>5 barras)
        fault_points = all_buses[:N_FAULT_BUSES]                          # puntos de falla (secciones)
        slack = _slack_machine(app)
        machines = _machines(app, pcc, slack)
        # TODOS los generadores síncronos en servicio: el CCT se decide cuando NINGUNO pierde el
        # sincronismo (s:outofstep). El que se desincroniza suele estar cerca de la falla, no en el
        # subconjunto distante que se grafica (por eso antes el CCT salía sobreestimado).
        all_gens = [s for s in app.GetCalcRelevantObjects("*.ElmSym") if s.GetAttribute("outserv") == 0]
        data["reference_machine"] = slack.loc_name
        data["n_generators"] = len(all_gens)

        disp = _display_names()
        bus_labels = {b.GetFullName(): f"{disp.get(s, s)} · {round(b.GetAttribute('uknom'))} kV"
                      for b, d, s in all_buses}

        fault_evt = dynamics.add_event(sb, app, "EvtShc", "fault", 9999.0, target=pcc, i_shc=0)
        clear_evt = dynamics.add_event(sb, app, "EvtShc", "clear", 9999.1, target=pcc, i_shc=4)

        def _ser(res, objs, var, scale=1.0, ref=None, labels=None):
            x0, traces, ry = None, [], None
            if ref is not None:
                _, ry = dynamics.series(app, res, ref, var)
            for o in objs:
                tt, yy = dynamics.series(app, res, o, var)
                if not yy:
                    continue
                if ry is not None:
                    n = min(len(yy), len(ry))
                    yy, tt = [(yy[i] - ry[i]) * scale for i in range(n)], tt[:n]
                elif scale != 1.0:
                    yy = [v * scale for v in yy]
                tx, yx = dynamics.downsample(tt, yy)
                if x0 is None:
                    x0 = tx
                traces.append({"name": (labels or {}).get(o.GetFullName()) or o.loc_name[:18], "y": yx})
            return {"x_label": "t [s]", "x": x0 or [], "traces": traces}

        def _bolted(bus):
            fault_evt.SetAttribute("p_target", bus)
            fault_evt.SetAttribute("R_f", 0.0)
            fault_evt.SetAttribute("X_f", 0.0)
            clear_evt.SetAttribute("p_target", bus)

        def _any_out_of_step(res):
            """True si ALGÚN generador síncrono del sistema marcó la señal nativa s:outofstep (PF)."""
            for g in all_gens:
                _, oos = dynamics.series(app, res, g, "s:outofstep")
                if oos and max(oos) >= 0.5:
                    return True
            return False

        def _stable_at(inc, sim, res, clear_ms, tend):
            """Estable a este despeje, al estilo del DPL CritClearing: (1) si la simulación se detuvo
            antes de tiempo -> inestable; (2) la señal NATIVA s:outofstep de CUALQUIER generador del
            sistema indica pérdida de sincronismo. No basta con mirar el subconjunto graficado: el que
            se desincroniza suele ser una máquina cercana a la falla."""
            clear_evt.SetAttribute("time", FAULT_T + clear_ms / 1000.0)
            dynamics.rms_run(app, inc, sim, tstop=tend, dt=DT)
            t, _ = dynamics.series(app, res, all_gens[0], "s:outofstep")
            if not (t and t[-1] >= tend - 0.6):
                return False                          # la corrida se detuvo antes (divergió)
            return not _any_out_of_step(res)

        def _search_cct(bus):
            """Búsqueda binaria del CCT [ms] = mayor despeje sin que NINGÚN generador pierda el paso."""
            _bolted(bus)
            fault_evt.SetAttribute("time", FAULT_T)
            inc, sim, res = dynamics.rms_prepare(app, [(g, "s:outofstep") for g in all_gens])
            lo, hi = CCT_MIN_MS, CCT_MAX_MS
            if not _stable_at(inc, sim, res, lo, TSTOP_CCT):
                return None, lo                       # inestable aun con el despeje mínimo
            if _stable_at(inc, sim, res, hi, TSTOP_CCT):
                return hi, None                       # estable hasta el máximo explorado (CCT ≥ máx)
            while hi - lo > CCT_TOL_MS:               # bisección exacta hasta la tolerancia
                mid = (lo + hi) // 2
                if _stable_at(inc, sim, res, mid, TSTOP_CCT):
                    lo = mid
                else:
                    hi = mid
            return lo, hi

        def _committed(res, n=N_MACHINES):
            """Las n máquinas MÁS COMPROMETIDAS = mayor excursión del ángulo de rotor relativo al slack
            (las que estuvieron más cerca de perder el sincronismo) + el propio slack de referencia."""
            _, sl = dynamics.series(app, res, slack, "s:firel")
            scored = []
            for g in all_gens:
                if g is slack:
                    continue
                _, a = dynamics.series(app, res, g, "s:firel")
                if not a:
                    continue
                m = min(len(a), len(sl)) if sl else len(a)
                sep = max((abs(a[i] - (sl[i] if sl else 0.0)) for i in range(m)), default=0.0)
                scored.append((sep, g))
            scored.sort(key=lambda x: -x[0])
            return [slack] + [g for _, g in scored[:n]]

        def _capture_run(bus, clear_ms):
            """Corrida a 5 s al despeje dado -> gráficos. Monitorea la tensión de varias barras y el
            ángulo/velocidad de TODOS los generadores, y grafica las máquinas más comprometidas."""
            _bolted(bus)
            fault_evt.SetAttribute("time", FAULT_T)
            clear_evt.SetAttribute("time", FAULT_T + clear_ms / 1000.0)
            inc, sim, res = dynamics.rms_prepare(
                app, [(t, "m:u") for t in monitor_buses]
                + [(g, "s:firel") for g in all_gens] + [(g, "s:xspeed") for g in all_gens])
            dynamics.rms_run(app, inc, sim, tstop=TSTOP_PLOT, dt=DT)
            mach = _committed(res)
            return {"voltages": _ser(res, monitor_buses, "m:u", labels=bus_labels),
                    "angles": _ser(res, mach, "s:firel", scale=1.0 / 180.0, ref=slack),
                    "speeds": _ser(res, mach, "s:xspeed"),
                    "machines": [g.loc_name for g in mach]}

        def _cct_and_graphs(bus):
            """CCT (último despeje sin que NINGÚN generador pierda el paso) + gráficos a 5 s a ESE
            despeje (no a un valor fijo): así el gráfico nunca muestra la oscilación de una máquina
            fuera de paso. Devuelve (cct, upper, side) con side={clearing_ms, machines, voltages,...}."""
            cct, upper = _search_cct(bus)
            clear_ms = cct if cct is not None else CCT_MIN_MS
            side = {"clearing_ms": clear_ms, "stable": cct is not None, **_capture_run(bus, clear_ms)}
            return cct, upper, side

        # ---- CCT + gráficos SIN planta ----
        report("CCT y gráficos sin planta", 8)
        cct_sin, graphs_sin = {}, {}
        for k, (bus, deg, sname) in enumerate(fault_points):
            cct, upper, side = _cct_and_graphs(bus)
            cct_sin[bus.GetFullName()] = (cct, upper)
            graphs_sin[bus.GetFullName()] = side
            report(f"CCT/gráficos sin planta ({k + 1}/{len(fault_points)})", 8 + int(20 * (k + 1) / len(fault_points)))

        # ---- Con planta ----
        report("modelando PV+BESS", 32)
        pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode)
        app.GetFromStudyCase("ComLdf").Execute()

        # ---- Corrida base sin falla (60 s) ----
        report(f"corrida base sin falla ({TSTOP_BASE:.0f} s)", 36)
        fault_evt.SetAttribute("time", 99999.0)
        inc, sim, res = dynamics.rms_prepare(
            app, [(t, "m:u") for t in monitor_buses] + [(t, "m:fehz") for t in monitor_buses]
            + [(g, "s:xspeed") for g in machines])
        dynamics.rms_run(app, inc, sim, tstop=TSTOP_BASE, dt=DT)
        data["baseline"] = {"voltages": _ser(res, monitor_buses, "m:u", labels=bus_labels),
                            "frequency": _ser(res, monitor_buses, "m:fehz", labels=bus_labels),
                            "speeds": _ser(res, machines, "s:xspeed")}

        # ---- CCT + gráficos CON planta; una sección por falla con AMBOS (sin y con planta) ----
        cct_con, cases = {}, []
        for k, (bus, deg, sname) in enumerate(fault_points):
            fn = bus.GetFullName()
            cct, upper, side_con = _cct_and_graphs(bus)
            cct_con[fn] = (cct, upper)
            cases.append({"bus": bus.loc_name, "sub": disp.get(sname, sname), "degree": deg,
                          "kv": round(bus.GetAttribute("uknom"), 1),
                          "sin": graphs_sin.get(fn), "con": side_con})
            report(f"CCT/gráficos con planta ({k + 1}/{len(fault_points)})",
                   40 + int(52 * (k + 1) / len(fault_points)))
        data["cases"] = cases

        rows = []
        for bus, deg, sname in fault_points:
            fn = bus.GetFullName()
            cs, cs_up = cct_sin.get(fn, (None, None))
            cc, cc_up = cct_con.get(fn, (None, None))
            rows.append({"bus": bus.loc_name, "sub": disp.get(sname, sname), "degree": deg,
                         "kv": round(bus.GetAttribute("uknom"), 1),
                         "cct_sin_ms": cs, "cct_sin_upper_ms": cs_up,
                         "cct_con_ms": cc, "cct_con_upper_ms": cc_up,
                         "delta_ms": (cc - cs) if (cs is not None and cc is not None) else None})
        data["cct_table"] = rows

    report("evaluando", 96)
    valid_con = [r["cct_con_ms"] for r in rows if r["cct_con_ms"] is not None]
    data["min_cct_con_ms"] = min(valid_con) if valid_con else None
    no_worse = all((r["cct_sin_ms"] is None or r["cct_con_ms"] is None
                    or r["cct_con_ms"] >= r["cct_sin_ms"] - 2 * CCT_TOL_MS) for r in rows)
    adequate = bool(rows) and all((r["cct_con_ms"] is not None and r["cct_con_ms"] >= 100) for r in rows)
    data["compliance"] = {
        "soporta_despeje_tipico": criteria.verdict(adequate),
        "planta_no_reduce_cct": criteria.verdict(no_worse),
        "overall": criteria.verdict(adequate and no_worse),
    }
    return data
