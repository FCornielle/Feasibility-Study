"""Estudio Steady State (Etapa 3): flujo de carga + N-1 + cortocircuito en el PCC.

Patrón del Estudio Sajoma: comparación **sin planta** (caso base) vs **con planta** (PV+BESS),
emitiendo PASA/FALLA contra los criterios del Código de Conexión (ver criteria.py / docs).

Corre dentro de `PFRunSandbox`, por lo que todo lo creado/modificado se revierte y el proyecto
queda idéntico al terminar.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # pf_worker en el path

import connect  # noqa: E402
import criteria  # noqa: E402
import export  # noqa: E402
import pv_bess  # noqa: E402
from sandbox import PFRunSandbox  # noqa: E402

MIN_KV = 69.0  # nivel desde el cual se evalúan tensiones (transmisión)


# --------------------------------------------------------------------------- helpers PF
def _run_ldf(app) -> int:
    return app.GetFromStudyCase("ComLdf").Execute()


def _branches(app):
    return (app.GetCalcRelevantObjects("*.ElmLne")
            + app.GetCalcRelevantObjects("*.ElmTr2")
            + app.GetCalcRelevantObjects("*.ElmTr3"))


def _capture(app) -> dict:
    """Tensiones de barras de transmisión y cargabilidad de ramas tras un LDF exitoso."""
    volt, deenerg = [], 0
    for t in app.GetCalcRelevantObjects("*.ElmTerm"):
        if t.GetAttribute("outserv") != 0 or t.GetAttribute("uknom") < MIN_KV:
            continue
        try:
            u = t.GetAttribute("m:u")
        except Exception:
            continue
        if u <= 0.01:   # barra no energizada (spare/islada): no entra en estadísticas de tensión
            deenerg += 1
            continue
        volt.append({"bus": t.loc_name, "kv": round(t.GetAttribute("uknom"), 1), "u_pu": round(u, 4)})
    load = []
    for b in _branches(app):
        if b.GetAttribute("outserv") != 0:
            continue
        try:
            ld = b.GetAttribute("m:loading")
        except Exception:
            continue
        load.append({"elem": b.loc_name, "type": b.GetClassName(), "loading_pct": round(ld, 1)})
    v_viol = [v for v in volt if not criteria.voltage_ok(v["u_pu"])]
    l_over = [x for x in load if not criteria.loading_ok(x["loading_pct"])]
    return {
        "n_buses": len(volt),
        "n_deenergized": deenerg,
        "v_min": min((v["u_pu"] for v in volt), default=None),
        "v_max": max((v["u_pu"] for v in volt), default=None),
        "voltage_violations": v_viol,
        "max_loading_pct": max((x["loading_pct"] for x in load), default=None),
        "overloads": l_over,
        "buses": volt,
        "branches": load,
    }


def _short_circuit(app, pcc) -> dict:
    """Ikss 3φ y 1φ en el PCC (IEC 60909)."""
    out = {}
    shc = app.GetFromStudyCase("ComShc")
    for tag, mode in (("ikss_3ph_ka", "3psc"), ("ikss_1ph_ka", "spgf")):
        try:
            shc.SetAttribute("iopt_mde", 0)       # método IEC 60909
            shc.SetAttribute("iopt_allbus", 0)    # falla solo en el objeto seleccionado
            shc.SetAttribute("iopt_shc", mode)
            shc.SetAttribute("shcobj", pcc)
            ierr = shc.Execute()
            val = None
            if ierr == 0:
                for a in ("m:Ikss", "m:ikss", "m:Ikss:A"):
                    try:
                        v = pcc.GetAttribute(a)
                        if v:
                            val = round(v, 3)
                            break
                    except Exception:
                        continue
            out[tag] = val
        except Exception as e:
            out[tag] = None
            out.setdefault("errors", []).append(f"{tag}: {e}")
    return out


def _n1(app, pcc, contingency_lines, max_n=25) -> dict:
    """N-1 sobre las líneas de evacuación del PCC: por cada salida, LDF y peor cargabilidad/tensión."""
    results = []
    for ln in contingency_lines[:max_n]:
        old = ln.GetAttribute("outserv")
        try:
            ln.SetAttribute("outserv", 1)
            ierr = _run_ldf(app)
            if ierr != 0:
                results.append({"contingency": ln.loc_name, "converged": False})
                continue
            cap = _capture(app)
            results.append({
                "contingency": ln.loc_name,
                "converged": True,
                "max_loading_pct": cap["max_loading_pct"],
                "v_min": cap["v_min"], "v_max": cap["v_max"],
                "n_overloads": len(cap["overloads"]),
                "n_voltage_violations": len(cap["voltage_violations"]),
            })
        finally:
            ln.SetAttribute("outserv", old)  # restaurar SIEMPRE (solo una contingencia a la vez)
    worst = max((r["max_loading_pct"] for r in results if r.get("converged") and r["max_loading_pct"]), default=None)
    return {"n_contingencies": len(results), "worst_loading_pct": worst, "cases": results}


def _evacuation_lines(app, sub):
    """Líneas conectadas a las barras de la subestación (circuitos de evacuación)."""
    term_names = {t.GetFullName() for t in pv_bess.substation_terminals(app, sub)}
    out = []
    for ln in app.GetCalcRelevantObjects("*.ElmLne"):
        for side in ("bus1", "bus2"):
            cub = ln.GetAttribute(side)
            if cub is not None:
                ct = cub.GetAttribute("cterm")
                if ct is not None and ct.GetFullName() in term_names:
                    out.append(ln)
                    break
    return out


# --------------------------------------------------------------------------- estudio
def run(app, sub_name: str, pv_mw: float, bess_mw: float, bess_mwh: float,
        bess_mode: str = "discharge", run_id: str | None = None, progress=None) -> dict:
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda phase, pct: None)
    data = {"study": "steady_state", "run_id": run_id, "substation": sub_name,
            "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode}}

    with PFRunSandbox(app, run_id=run_id) as sb:
        sub = pv_bess.find_substation(app, sub_name)

        # 1) Caso base (sin planta) — necesario antes de elegir el PCC energizado
        report("flujo de carga base", 10)
        if _run_ldf(app) != 0:
            raise RuntimeError("El flujo de carga base no convergió.")
        data["base"] = _capture(app)

        # PCC = barra de mayor tensión ENERGIZADA de la subestación (evita barras muertas/spare)
        pcc = pv_bess.pick_pcc(app, sub, energized=True)
        data["pcc"] = {"name": pcc.loc_name, "kv": round(pcc.GetAttribute("uknom"), 1)}

        # 2) Con planta PV+BESS
        report("modelando PV+BESS y flujo con planta", 35)
        plant = pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode)
        if _run_ldf(app) != 0:
            raise RuntimeError("El flujo de carga con planta no convergió.")
        data["with_plant"] = _capture(app)

        # 3) Cortocircuito en el PCC (con planta)
        report("cortocircuito en el PCC", 55)
        data["short_circuit_with_plant"] = _short_circuit(app, plant["pcc"])

        # 4) N-1 sobre líneas de evacuación (con planta)
        report("análisis N-1", 70)
        evac = _evacuation_lines(app, sub)
        data["evacuation_lines"] = [l.loc_name for l in evac]
        data["n1_with_plant"] = _n1(app, plant["pcc"], evac)
        report("evaluando criterios", 90)

    # --- veredicto por DELTA: la planta no debe INTRODUCIR ni EMPEORAR violaciones (criterio Sajoma) ---
    base, wp = data["base"], data["with_plant"]
    base_v = {v["bus"] for v in base["voltage_violations"]}
    base_o = {o["elem"] for o in base["overloads"]}
    new_v = [v for v in wp["voltage_violations"] if v["bus"] not in base_v]
    new_o = [o for o in wp["overloads"] if o["elem"] not in base_o]
    base_max = base["max_loading_pct"] or 0
    wp_max = wp["max_loading_pct"] or 0
    data["delta"] = {
        "new_voltage_violations": new_v,
        "new_overloads": new_o,
        "max_loading_increase_pct": round(wp_max - base_max, 2),
        "preexisting_voltage_violations": len(base_v),
        "preexisting_overloads": len(base_o),
    }
    checks = {
        "no_new_voltage_violation": len(new_v) == 0,
        "no_new_overload": len(new_o) == 0,
        "no_loading_worsening_over_limit": not (wp_max > criteria.LOADING_MAX_PCT and wp_max > base_max + 0.5),
    }
    checks["overall"] = all(checks.values())
    data["compliance"] = {k: criteria.verdict(v) for k, v in checks.items()}
    return data


def main():
    sub = sys.argv[1] if len(sys.argv) > 1 else "ZNARAD"
    pv = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0
    bess = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
    bess_mwh = float(sys.argv[4]) if len(sys.argv) > 4 else 80.0
    app = connect.get_app()
    data = run(app, sub, pv, bess, bess_mwh)
    path = export.write_results(data["run_id"], "steady_state", data)
    c = data["compliance"]
    d = data["delta"]
    print(f"Subestación {sub} | PCC {data['pcc']['name']} ({data['pcc']['kv']} kV)")
    print(f"  base:   v[{data['base']['v_min']}..{data['base']['v_max']}] maxload={data['base']['max_loading_pct']}% "
          f"(violaciones preexistentes: V={d['preexisting_voltage_violations']} sobrecargas={d['preexisting_overloads']})")
    print(f"  planta: v[{data['with_plant']['v_min']}..{data['with_plant']['v_max']}] maxload={data['with_plant']['max_loading_pct']}%")
    print(f"  DELTA:  nuevas violaciones V={len(d['new_voltage_violations'])} sobrecargas={len(d['new_overloads'])} "
          f"d_maxload={d['max_loading_increase_pct']}%")
    print(f"  CC PCC: {data['short_circuit_with_plant']}")
    print(f"  N-1:    {data['n1_with_plant']['n_contingencies']} cont., peor carga={data['n1_with_plant']['worst_loading_pct']}%")
    print(f"  CUMPLIMIENTO: {c}")
    print(f"  -> {path}")


if __name__ == "__main__":
    main()
