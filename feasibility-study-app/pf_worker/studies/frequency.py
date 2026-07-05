"""Estabilidad de frecuencia (Etapa 6d) — comparación SIN y CON la nueva planta.

Se dispara (desconecta) a los 500 ms una **unidad de generación de tamaño similar a la planta** y se
observa cómo varían la FRECUENCIA del sistema y la VELOCIDAD de los generadores síncronos, primero SIN
la nueva planta y luego CON la planta (PV + BESS de regulación de frecuencia). Así se ve si la planta
—en particular su BESS de regulación— ayuda a arrestar el hundimiento de frecuencia. En un escenario
nocturno la planta es esencialmente la batería, de modo que la comparación equivale a "sin/con batería".

Criterio: el nadir de frecuencia debe mantenerse por encima del PRIMER ESCALÓN del EDAC (59.2 Hz).
La frecuencia del sistema se toma de la velocidad del mayor generador síncrono (f = velocidad * 60).
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

STUDY = "frequency"
TRIP_T = 0.5          # disparo de la unidad a los 500 ms
TSTOP, DT = 60.0, 0.02   # ventana completa de 60 s (dinámica de frecuencia lenta -> paso 0.02 s)
N_SPEED_GENS = 6      # generadores síncronos cuya velocidad se grafica


def _hour_from_scenario(name):
    if not name:
        return None
    return int(re.sub(r"\D", "", name)) if re.search(r"\d", name) else None


def _gen_term(s):
    cub = s.GetAttribute("bus1")
    return cub.GetAttribute("cterm") if cub is not None else None


def _pick_trip_unit(app, target_mw, pcc_term):
    """Generador síncrono en servicio con potencia MÁS PARECIDA a `target_mw` (el que se dispara).
    Se excluye la barra del PCC (no disparar en el mismo nudo que la planta)."""
    pcc_name = pcc_term.GetFullName() if pcc_term is not None else None
    best, best_diff = None, None
    for s in app.GetCalcRelevantObjects("*.ElmSym"):
        if s.GetAttribute("outserv") != 0:
            continue
        term = _gen_term(s)
        if pcc_name is not None and term is not None and term.GetFullName() == pcc_name:
            continue
        rating = dynamics._gen_rating(s)
        if rating <= 0:
            continue
        diff = abs(rating - target_mw)
        if best_diff is None or diff < best_diff:
            best, best_diff = s, diff
    return best


def run(app, sub_name, pv_mw, bess_mw=0.0, bess_mwh=0.0, bess_mode="discharge", scale_loads=1.0,
        run_id=None, progress=None):
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda p, q: None)
    data = {"study": STUDY, "run_id": run_id, "substation": sub_name,
            "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode}}

    with PFRunSandbox(app, run_id=run_id) as sb:
        sub = pv_bess.find_substation(app, sub_name)
        data["load_scaling"] = pv_bess.scale_loads(sb, app, scale_loads)
        report("flujo de carga base", 8)
        if app.GetFromStudyCase("ComLdf").Execute() != 0:
            raise RuntimeError("Flujo de carga base no convergió.")
        pcc = pv_bess.pick_pcc(app, sub, energized=True)
        data["pcc"] = {"name": pcc.loc_name, "kv": round(pcc.GetAttribute("uknom"), 1)}
        scen = app.GetActiveScenario()
        hour = _hour_from_scenario(scen.loc_name if scen else None)
        data["scenario"] = {"name": scen.loc_name if scen else None, "hour": hour}

        # Unidad a disparar: generador síncrono en servicio de tamaño similar a la planta (~pv_mw).
        trip_unit = _pick_trip_unit(app, pv_mw, pcc)
        if trip_unit is None:
            raise RuntimeError("No se encontró un generador síncrono en servicio para el disparo.")
        # Referencia de frecuencia y generadores graficados: los mayores síncronos, excluyendo el disparado.
        syms = [s for s in app.GetCalcRelevantObjects("*.ElmSym")
                if s.GetAttribute("outserv") == 0 and s is not trip_unit]
        syms.sort(key=dynamics._gen_rating, reverse=True)
        ref = syms[0]
        speed_gens = syms[:N_SPEED_GENS]
        data["trip_unit"] = {"name": trip_unit.loc_name, "mw": round(dynamics._gen_rating(trip_unit), 1)}
        data["ref_gen"] = ref.loc_name
        data["monitored_gens"] = [g.loc_name for g in speed_gens]

        # Evento de disparo (persiste para ambas corridas: SIN y CON planta).
        dynamics.add_event(sb, app, "EvtOutage", "trip", TRIP_T, target=trip_unit)
        mon = [(ref, "s:xspeed")] + [(g, "s:xspeed") for g in speed_gens]

        def _capture():
            inc, sim, res = dynamics.rms_prepare(app, mon)
            dynamics.rms_run(app, inc, sim, tstop=TSTOP, dt=DT)
            t, sp = dynamics.series(app, res, ref, "s:xspeed")
            freq = [s * dynamics.FN for s in sp]
            tx, fx = dynamics.downsample(t, freq)
            speeds = {"x_label": "t [s]", "x": tx, "traces": []}
            for g in speed_gens:
                tt, ss = dynamics.series(app, res, g, "s:xspeed")
                if ss:
                    _, yx = dynamics.downsample(tt, ss)
                    speeds["traces"].append({"name": g.loc_name, "y": yx})
            return {
                "frequency": {"x_label": "t [s]", "x": tx, "traces": [{"name": "Frecuencia [Hz]", "y": fx}]},
                "speeds": speeds,
                "nadir_hz": round(dynamics.nadir(freq), 3) if freq else None,
                "peak_hz": round(dynamics.peak(freq), 3) if freq else None,
                "rocof_hz_s": round(dynamics.max_rocof(t, freq), 3) if freq else None,
            }

        # SIN planta
        report("RMS sin planta (disparo de la unidad a 500 ms)", 35)
        sin = _capture()

        # CON planta (despacho coherente con la hora del escenario)
        report("modelando PV+BESS", 55)
        plant = pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mode=bess_mode, hour=hour, bess_role="frequency")
        data["params"].update({"bess_mw": plant["params"]["bess_mw"],
                               "bess_mwh": plant["params"]["bess_mwh"], "bess_role": "frequency"})
        pv_out = plant["params"]["pv_out_mw"]
        bess_out = plant["params"]["bess_out_mw"]
        data["dispatch"] = {"hour": hour, "pv_out_mw": pv_out, "bess_out_mw": bess_out,
                            "battery_scenario": bool(bess_out > 0 and pv_out <= 0)}
        if app.GetFromStudyCase("ComLdf").Execute() != 0:
            raise RuntimeError("Flujo de carga con planta no convergió.")
        report("RMS con planta (disparo de la unidad a 500 ms)", 75)
        con = _capture()

    report("evaluando frecuencia", 92)
    data["frequency"] = {"sin_planta": sin["frequency"], "con_planta": con["frequency"]}
    data["speeds"] = {"sin_planta": sin["speeds"], "con_planta": con["speeds"]}
    data["metrics"] = {
        "nadir_sin_hz": sin["nadir_hz"], "nadir_con_hz": con["nadir_hz"],
        "rocof_sin_hz_s": sin["rocof_hz_s"], "rocof_con_hz_s": con["rocof_hz_s"],
        "edac_first_step_hz": criteria.FREQ_FIRST_EDAC_HZ,
    }
    ok = con["nadir_hz"] is not None and con["nadir_hz"] >= criteria.FREQ_FIRST_EDAC_HZ
    # La planta no debe empeorar el nadir (con batería debería mejorarlo o mantenerlo).
    no_worse = (sin["nadir_hz"] is None or con["nadir_hz"] is None
                or con["nadir_hz"] >= sin["nadir_hz"] - 0.02)
    data["compliance"] = {
        "nadir_sobre_primer_escalon_edac": criteria.verdict(ok),
        "planta_no_empeora_el_nadir": criteria.verdict(no_worse),
        "overall": criteria.verdict(ok and no_worse),
    }
    return data
