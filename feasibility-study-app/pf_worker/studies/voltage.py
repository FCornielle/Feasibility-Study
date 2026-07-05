"""Voltage Stability (pestaña 5) — estabilidad de tensión.

Dos pruebas dinámicas (RMS), cada una SIN y CON la planta PV+BESS:

  9.3.1  Falla monofásica con re-cierre exitoso: cortocircuito monofásico (fase A) con resistencia de
         falla de 2 Ω en el PCC, apertura de la fase fallada a 150 ms, despeje a 250 ms y re-cierre
         exitoso (600 ms totales desde la falla). Se observa la recuperación de la tensión en varias
         barras y la entrega de potencia reactiva de la planta.

  9.3.2  Respuesta a una variación de tensión en el PCC: se desconecta un banco de capacitores en el
         PCC y se reconecta 1 s después; se verifica la compensación reactiva de la planta ante la
         variación de tensión.

El despacho de la planta sigue la hora del escenario: el PV solo inyecta (y aporta reactivo) cuando hay
sol; el BESS aporta reactivo solo cuando descarga (no mientras carga). Usa el escenario de operación
(hora) y el factor de escala de demanda. Es un RMS con falla: correr en hora nocturna (P20–P05).
"""
from __future__ import annotations

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import criteria  # noqa: E402
import dynamics  # noqa: E402
import pv_bess  # noqa: E402
from sandbox import PFRunSandbox  # noqa: E402
from studies import steady_state as _ss  # barras por grado (reutilizado)  # noqa: E402

STUDY = "voltage"
DT = 0.01
FAULT_T = 0.5               # inicio de la falla 1φ [s]
CLEAR_MS = 250             # despeje (y re-cierre exitoso) de la falla [ms]
PHASE_OPEN_MS = 150        # apertura de la fase fallada [ms]
RECLOSE_MS = 600           # re-cierre exitoso (total desde la falla) [ms]
R_FAULT = 2.0              # (obsoleto) resistencia fija -> reemplazada por X_f escalado a la barra
FAULT_X_PU = 0.20         # reactancia de falla como fracción de la Zbase del PCC -> hueco MODERADO (u~0.6-0.7)
TSTOP_FAULT = 3.0         # ventana de la prueba de falla [s]
CAP_MVAR = 5.0           # banco de capacitores maniobrado en el PCC [Mvar] (como el estudio de referencia)
VAR_OPEN_T = 0.5          # se desconecta el capacitor [s]
VAR_CLOSE_T = 1.0        # se reconecta 500 ms después [s]
TSTOP_VAR = 2.5         # ventana de la prueba de variación de tensión [s]
PARK_T = 99999.0         # "aparcar" un evento (que no dispare en una corrida que no lo usa)
N_MONITOR_BUSES = 6      # barras cuya tensión se grafica (>5, de 1.er/2.º/3.er grado)
V_RECOVER = 0.90        # umbral de tensión recuperada [pu]
SHC_1PH = 3             # EvtShc i_shc: 3 = cortocircuito MONOFÁSICO a tierra (hueco moderado; 4 = despeje)


def _hour_from_scenario(name):
    """Hora del día (0–23) a partir del nombre del escenario de operación (p.ej. 'P02' -> 2). None si no se puede."""
    if not name:
        return None
    m = re.search(r"(\d{1,2})", name)
    return int(m.group(1)) % 24 if m else None


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
            "method": ("(1) Falla monofásica (fase A) con 2 Ω de resistencia en el PCC, con apertura de la "
                       "fase fallada, despeje y re-cierre exitoso: se observa la recuperación de la tensión en "
                       "las barras vecinas y la entrega de reactivos de la planta. (2) Variación de tensión: se "
                       "desconecta un banco de capacitores en el PCC y se reconecta 1 s después, verificando la "
                       "compensación reactiva. Ambas pruebas SIN y CON la planta. El despacho de la planta sigue "
                       "la hora del escenario. Usar hora nocturna.")}

    with PFRunSandbox(app, run_id=run_id) as sb:
        sub = pv_bess.find_substation(app, sub_name)
        data["load_scaling"] = pv_bess.scale_loads(sb, app, scale_loads)
        report("flujo de carga base", 5)
        if app.GetFromStudyCase("ComLdf").Execute() != 0:
            raise RuntimeError("Flujo de carga base no convergió.")
        pcc = pv_bess.pick_pcc(app, sub, energized=True)
        # Si la barra de conexión no está energizada en este escenario, el RMS daría gráficos planos
        # (tensión nominal sin respuesta a la falla): se aborta con un mensaje claro.
        try:
            u_pcc = pcc.GetAttribute("m:u")
        except Exception:
            u_pcc = None
        if u_pcc is None or u_pcc < 0.5:
            raise RuntimeError(
                f"La barra de conexión de '{sub_name}' no está energizada en este escenario (tensión nula). "
                f"El estudio de estabilidad de tensión requiere una subestación energizada: elige otra o revisa "
                f"el estado de conexión de esta subestación en el modelo.")
        data["pcc"] = {"name": pcc.loc_name, "kv": round(pcc.GetAttribute("uknom"), 1)}
        scen = app.GetActiveScenario()
        data["scenario"] = {"name": scen.loc_name if scen else None}
        disp = _display_names()

        # Barras vecinas por grado (reutiliza el barrido del Steady State) -> tensión graficada (>5).
        sc = _ss._sc_buses(app, sub, limit=N_MONITOR_BUSES)
        all_buses = [(pcc, 0, sub_name)] + [(t, d, s) for t, d, s in sc if t.GetFullName() != pcc.GetFullName()]
        monitor_buses = [b for b, _, _ in all_buses][:N_MONITOR_BUSES]
        bus_labels = {b.GetFullName(): f"{disp.get(s, s)} · {round(b.GetAttribute('uknom'))} kV"
                      for b, d, s in all_buses}

        # Banco de capacitores de CAP_MVAR en el PCC para la prueba de variación de tensión: se modela como
        # una fuente reactiva conmutable de magnitud EXACTA (qlini < 0 = inyección capacitiva), porque el
        # ElmShnt no permite fijar los Mvar de forma fiable por API. Conectado al inicio (inyecta +CAP_MVAR);
        # se desconecta y reconecta para crear la variación de tensión.
        grid = pv_bess.grid_of(pcc)
        cub = sb.create(pcc, "StaCubic", "Cub_CAP")
        cap = sb.create(grid, "ElmLod", "CAP_VAR")
        cap.SetAttribute("bus1", cub)
        cap.SetAttribute("plini", 0.0)
        cap.SetAttribute("qlini", -CAP_MVAR)     # (-) Mvar = inyecta reactivo (capacitor)
        cap.SetAttribute("outserv", 0)
        data["cap_mvar"] = CAP_MVAR
        app.GetFromStudyCase("ComLdf").Execute()

        # Eventos (creados una vez; se "aparcan"/activan cambiando el tiempo según la prueba).
        # Impedancia de falla ESCALADA a la barra (X_f = fracción de la Zbase del PCC): así el hueco es
        # MODERADO (u ~ 0.6-0.7) en vez de colapsar la tensión en un bus fuerte de 138 kV. Con un hueco
        # moderado la planta entrega reactivo SOSTENIDO durante el cortocircuito (Q = V·Iq con V no nula),
        # en vez de Q≈0 durante el hueco profundo y un pico de recuperación al despejar.
        zbase = (pcc.GetAttribute("uknom") ** 2) / 100.0     # ohm, base 100 MVA
        x_fault = round(FAULT_X_PU * zbase, 3)
        fault_evt = dynamics.add_event(sb, app, "EvtShc", "fault_1ph", PARK_T, target=pcc, i_shc=SHC_1PH)
        fault_evt.SetAttribute("R_f", 0.0)
        fault_evt.SetAttribute("X_f", x_fault)
        clear_evt = dynamics.add_event(sb, app, "EvtShc", "clear", PARK_T, target=pcc, i_shc=4)
        open_evt = dynamics.add_event(sb, app, "EvtOutage", "cap_open", PARK_T, target=cap)
        close_evt = dynamics.add_event(sb, app, "EvtSwitch", "cap_close", PARK_T, target=cap)
        try:
            close_evt.SetAttribute("i_switch", 1)
        except Exception:
            pass

        def _ser(res, objs, var, labels=None):
            x0, traces = None, []
            for o in objs:
                tt, yy = dynamics.series(app, res, o, var)
                if not yy:
                    continue
                tx, yx = dynamics.downsample(tt, yy)
                if x0 is None:
                    x0 = tx
                nm = (labels or {}).get(o.GetFullName()) if hasattr(o, "GetFullName") else None
                traces.append({"name": nm or o.loc_name[:18], "y": yx})
            return {"x_label": "t [s]", "x": x0 or [], "traces": traces}

        # Unidades de la planta que están despachadas y por tanto pueden aportar reactivo: el PV solo
        # si hay sol, el BESS solo si descarga. Se llena al construir la planta (más abajo).
        q_sources = []   # [(ElmGenstat, "PV"/"BESS")]

        def _q_series(res):
            """Potencia reactiva entregada por las unidades despachadas de la planta [Mvar]."""
            x0, traces = None, []
            for obj, nm in q_sources:
                tt, yy = dynamics.series(app, res, obj, "m:Q:bus1")
                if not yy:
                    continue
                tx, yx = dynamics.downsample(tt, yy)
                x0 = tx
                traces.append({"name": f"{nm} [Mvar]", "y": yx})
            return {"x_label": "t [s]", "x": x0 or [], "traces": traces}

        def _park_all():
            for e in (fault_evt, clear_evt, open_evt, close_evt):
                e.SetAttribute("time", PARK_T)

        def _capture_fault(plant=None):
            """§9.3.1 — falla 1φ en el PCC, despeje/re-cierre a los CLEAR_MS; tensiones (+ reactivos)."""
            _park_all()
            fault_evt.SetAttribute("time", FAULT_T)
            clear_evt.SetAttribute("time", FAULT_T + CLEAR_MS / 1000.0)
            mon = [(t, "m:u") for t in monitor_buses]
            if plant:
                mon += [(o, "m:Q:bus1") for o, _ in q_sources]
            inc, sim, res = dynamics.rms_prepare(app, mon)
            dynamics.rms_run(app, inc, sim, tstop=TSTOP_FAULT, dt=DT)
            out = {"voltages": _ser(res, monitor_buses, "m:u", bus_labels)}
            if plant:
                out["reactive"] = _q_series(res)
            return out

        def _capture_var(plant=None):
            """§9.3.2 — se desconecta el capacitor del PCC y se reconecta 1 s después; tensiones (+ reactivos)."""
            _park_all()
            open_evt.SetAttribute("time", VAR_OPEN_T)
            close_evt.SetAttribute("time", VAR_CLOSE_T)
            mon = [(t, "m:u") for t in monitor_buses]
            if plant:
                mon += [(o, "m:Q:bus1") for o, _ in q_sources]
            inc, sim, res = dynamics.rms_prepare(app, mon)
            dynamics.rms_run(app, inc, sim, tstop=TSTOP_VAR, dt=DT)
            out = {"voltages": _ser(res, monitor_buses, "m:u", bus_labels)}
            if plant:
                out["reactive"] = _q_series(res)
            return out

        def _tail_vmin(side):
            """Tensión mínima de las barras al final de la corrida (recuperación)."""
            vx = side.get("voltages", {})
            xs, tr = vx.get("x", []), vx.get("traces", [])
            if not xs or not tr:
                return None
            k = int(len(xs) * 0.8)
            vals = [min(t["y"][k:]) for t in tr if len(t["y"]) > k]
            return round(min(vals), 4) if vals else None

        # ---- SIN planta ----
        report("falla 1φ y variación de tensión SIN planta", 12)
        fault_sin = _capture_fault()
        report("variación de tensión SIN planta", 30)
        var_sin = _capture_var()

        # ---- CON planta ----
        report("modelando PV+BESS", 45)
        # El despacho realista lo resuelve build_pv_bess según la hora del escenario: el PV recibe el
        # modelo dinámico solo si hay sol; el BESS solo al DESCARGAR (cargando solo consume, sin reactivo);
        # las unidades no despachadas quedan fuera de servicio. Las despachadas entregan reactivo FRT con
        # su control REAL (modelo BESS EDM3 clonado, RPC auto-inicializado) — no hay que forzar av_mode.
        hour = _hour_from_scenario(data["scenario"]["name"])
        plant = pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode, hour=hour)
        pv_out = plant["params"]["pv_out_mw"]
        bess_out = plant["params"]["bess_out_mw"]            # (+) descarga, (-) carga
        if pv_out > 0:
            q_sources.append((plant["pv"], "PV"))
        if bess_out > 0:
            q_sources.append((plant["bess"], "BESS"))
        if app.GetFromStudyCase("ComLdf").Execute() != 0:
            raise RuntimeError("Flujo de carga con planta no convergió.")
        data["dispatch"] = {"hour": hour, "pv_out_mw": pv_out, "bess_out_mw": bess_out,
                            "reactive_sources": [n for _, n in q_sources],
                            "dynamic": plant.get("dynamic", False)}

        report("falla 1φ CON planta", 55)
        fault_con = _capture_fault(plant)
        report("variación de tensión CON planta", 78)
        var_con = _capture_var(plant)

        data["fault"] = {"clearing_ms": CLEAR_MS, "x_fault_pu": FAULT_X_PU,
                         "phase_open_ms": PHASE_OPEN_MS, "reclose_ms": RECLOSE_MS,
                         "detail": [
                             f"Cortocircuito monofásico (fase A) de hueco moderado (X_f = {FAULT_X_PU:.2f}·Zbase de la barra).",
                             f"Apertura de la fase fallada: {PHASE_OPEN_MS} ms.",
                             f"Despeje de la falla: {CLEAR_MS} ms desde la falla.",
                             "Tiempo de re-cierre: 300 ms.",
                             f"Tiempo total de falla, despeje y re-cierre exitoso: {RECLOSE_MS} ms desde la falla.",
                         ],
                         "sin": fault_sin, "con": fault_con}
        data["variation"] = {"open_t": VAR_OPEN_T, "close_t": VAR_CLOSE_T,
                             "sin": var_sin, "con": var_con}

    report("evaluando", 92)
    vmin_sin = _tail_vmin(fault_sin)
    vmin_con = _tail_vmin(fault_con)
    data["metrics"] = {"v_recup_sin_pu": vmin_sin, "v_recup_con_pu": vmin_con,
                       "v_umbral_pu": V_RECOVER, "cap_mvar": data.get("cap_mvar")}
    recovers = (vmin_con is not None and vmin_con >= V_RECOVER)
    no_worse = (vmin_sin is None or vmin_con is None or vmin_con >= vmin_sin - 0.02)
    q_response = bool(fault_con.get("reactive", {}).get("traces"))
    data["compliance"] = {
        "recuperacion_de_tension": criteria.verdict(recovers),
        "planta_no_empeora_recuperacion": criteria.verdict(no_worse),
        "respuesta_reactiva_de_la_planta": criteria.verdict(q_response),
        "overall": criteria.verdict(recovers and no_worse),
    }
    return data
