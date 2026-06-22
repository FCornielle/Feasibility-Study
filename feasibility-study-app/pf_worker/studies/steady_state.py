"""Estudio Steady State (Etapa 3): flujo de carga + N-1 + cortocircuito en el PCC.

Patrón del Estudio Sajoma: comparación **sin planta** (caso base) vs **con planta** (PV+BESS),
emitiendo PASA/FALLA contra los criterios del Código de Conexión (ver criteria.py / docs).

Corre dentro de `PFRunSandbox`, por lo que todo lo creado/modificado se revierte y el proyecto
queda idéntico al terminar.
"""
from __future__ import annotations

import os
import re
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


def _attr(o, a, default=None):
    try:
        return o.GetAttribute(a)
    except Exception:
        return default


def _system_totals(app) -> dict:
    """Demanda, generación y pérdidas del sistema tras un LDF (P en MW, Q en Mvar)."""
    dp = dq = 0.0
    for ld in app.GetCalcRelevantObjects("*.ElmLod"):
        if ld.GetAttribute("outserv") == 0:
            dp += _attr(ld, "m:P:bus1", 0.0) or 0.0
            dq += _attr(ld, "m:Q:bus1", 0.0) or 0.0
    gp = gq = 0.0
    for cls in ("*.ElmSym", "*.ElmGenstat"):
        for g in app.GetCalcRelevantObjects(cls):
            if g.GetAttribute("outserv") == 0:
                gp += _attr(g, "m:P:bus1", 0.0) or 0.0
                gq += _attr(g, "m:Q:bus1", 0.0) or 0.0
    return {"demand_mw": round(dp, 1), "demand_mvar": round(dq, 1),
            "generation_mw": round(gp, 1), "generation_mvar": round(gq, 1),
            "losses_mw": round(gp - dp, 1)}


def _tech(g) -> str:
    c = _attr(g, "cCategory")
    if c:
        return str(c)
    return "Síncrono" if g.GetClassName() == "ElmSym" else "Otro"


def _dispatch(app) -> dict:
    """Generadores despachados agrupados por tecnología, con P y Q, ordenados de mayor a menor."""
    by = {}
    for cls in ("*.ElmSym", "*.ElmGenstat"):
        for g in app.GetCalcRelevantObjects(cls):
            if g.GetAttribute("outserv") != 0:
                continue
            p, q = _attr(g, "m:P:bus1"), _attr(g, "m:Q:bus1")
            if p is None:   # incluir unidades en servicio aunque despachen 0 (p.ej. solar de noche)
                continue
            t = by.setdefault(_tech(g), {"tech": _tech(g), "p_mw": 0.0, "q_mvar": 0.0, "units": []})
            t["p_mw"] += p
            t["q_mvar"] += q or 0.0
            t["units"].append({"name": g.loc_name, "p_mw": round(p, 2), "q_mvar": round(q or 0.0, 2)})
    techs = []
    for t in by.values():
        t["units"].sort(key=lambda x: x["p_mw"], reverse=True)
        t["p_mw"], t["q_mvar"] = round(t["p_mw"], 1), round(t["q_mvar"], 1)
        techs.append(t)
    techs.sort(key=lambda x: x["p_mw"], reverse=True)
    return {"technologies": techs,
            "total_p_mw": round(sum(t["p_mw"] for t in techs), 1),
            "total_q_mvar": round(sum(t["q_mvar"] for t in techs), 1)}


def _substation_voltages(app) -> dict:
    """código de subestación -> tensión (pu) de su barra energizada de mayor tensión (para el heatmap)."""
    best = {}
    for t in app.GetCalcRelevantObjects("*.ElmTerm"):
        ss = t.GetAttribute("cpSubstat")
        if ss is None or t.GetAttribute("outserv") != 0:
            continue
        u = _attr(t, "m:u")
        if not u or u <= 0.01:
            continue
        kv = t.GetAttribute("uknom")
        cur = best.get(ss.loc_name)
        if cur is None or kv > cur[0]:
            best[ss.loc_name] = (kv, round(u, 4))
    return {k: v[1] for k, v in best.items()}


def _neighbor_buses(app, sub, limit: int = 5) -> list:
    """Barras de subestaciones VECINAS conectadas por una línea/trafo a la subestación de la planta."""
    sub_terms = {t.GetFullName() for t in pv_bess.substation_terminals(app, sub)}
    out, seen = [], set()
    for cls in ("*.ElmLne", "*.ElmTr2", "*.ElmTr3"):
        for br in app.GetCalcRelevantObjects(cls):
            if br.GetAttribute("outserv") != 0:
                continue
            terms = []
            for side in ("bus1", "bus2", "bus3"):
                cub = _attr(br, side)
                ct = _attr(cub, "cterm") if cub is not None else None
                if ct is not None:
                    terms.append(ct)
            names = [t.GetFullName() for t in terms]
            if not any(n in sub_terms for n in names):
                continue
            for t in terms:
                fn = t.GetFullName()
                ss = t.GetAttribute("cpSubstat")
                if fn in sub_terms or fn in seen or ss is None or ss.loc_name == sub.loc_name:
                    continue
                seen.add(fn)
                out.append(t)
    return out[:limit]


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


def _line_terms(app, ln):
    out = []
    for side in ("bus1", "bus2"):
        cub = _attr(ln, side)
        ct = _attr(cub, "cterm") if cub is not None else None
        if ct is not None:
            out.append(ct)
    return out


def _local_lines(app, sub):
    """Líneas de 1.er grado (conectadas directo a la subestación de la planta) y de 2.º grado
    (conectadas a una subestación vecina a la de la planta)."""
    sub_terms = {t.GetFullName() for t in pv_bess.substation_terminals(app, sub)}
    lines = [l for l in app.GetCalcRelevantObjects("*.ElmLne") if l.GetAttribute("outserv") == 0]
    first, first_names, neigh_subs = [], set(), set()
    for ln in lines:
        terms = _line_terms(app, ln)
        if any(t.GetFullName() in sub_terms for t in terms):
            first.append(ln)
            first_names.add(ln.GetFullName())
            for t in terms:
                ss = t.GetAttribute("cpSubstat")
                if ss is not None and ss.loc_name != sub.loc_name:
                    neigh_subs.add(ss.loc_name)
    second = []
    for ln in lines:
        if ln.GetFullName() in first_names:
            continue
        for t in _line_terms(app, ln):
            ss = t.GetAttribute("cpSubstat")
            if ss is not None and ss.loc_name in neigh_subs:
                second.append(ln)
                break
    return first, second


def _contingency_matrix(app, sub, max_lines: int = 14) -> dict:
    """Matriz N-1 estilo Sajoma: cargabilidad de cada línea local bajo la salida de cada línea local."""
    first, second = _local_lines(app, sub)
    monitored = (first + second)[:max_lines]
    meta = [{"name": ln.loc_name, "degree": 1 if ln in first else 2} for ln in monitored]
    _run_ldf(app)
    base_load = [round(_attr(ln, "m:loading") or 0.0, 1) for ln in monitored]

    saved = {ln.GetFullName(): ln.GetAttribute("outserv") for ln in monitored}
    per_cont = []  # per_cont[j][i] = cargabilidad de la línea i con la contingencia j fuera
    try:
        for cln in monitored:
            cln.SetAttribute("outserv", 1)
            ierr = _run_ldf(app)
            if ierr != 0:
                per_cont.append([None] * len(monitored))
            else:
                per_cont.append([
                    (round(_attr(ln, "m:loading") or 0.0, 1) if ln.GetFullName() != cln.GetFullName() else None)
                    for ln in monitored
                ])
            cln.SetAttribute("outserv", saved[cln.GetFullName()])
    finally:
        for ln in monitored:
            ln.SetAttribute("outserv", saved[ln.GetFullName()])
        _run_ldf(app)

    matrix = [[per_cont[j][i] for j in range(len(monitored))] for i in range(len(monitored))]
    worst = max((v for col in per_cont for v in col if v is not None), default=None)
    return {"lines": meta, "contingencies": [m["name"] for m in meta],
            "base_loading": base_load, "matrix": matrix,
            "worst_loading_pct": round(worst, 1) if worst is not None else None}


def _sc_buses(app, sub, limit: int = 8):
    """Una barra representativa por subestación vecina (1.er y 2.º grado) para el cortocircuito."""
    first, second = _local_lines(app, sub)
    by_sub = {}  # sub_name -> (term, degree)

    def consider(ln, degree):
        for t in _line_terms(app, ln):
            ss = t.GetAttribute("cpSubstat")
            if ss is None or ss.loc_name == sub.loc_name:
                continue
            cur = by_sub.get(ss.loc_name)
            if cur is None or degree < cur[1] or (degree == cur[1] and t.GetAttribute("uknom") > cur[0].GetAttribute("uknom")):
                by_sub[ss.loc_name] = (t, degree)

    for ln in first:
        consider(ln, 1)
    for ln in second:
        consider(ln, 2)
    items = sorted(by_sub.items(), key=lambda kv: (kv[1][1], -kv[1][0].GetAttribute("uknom")))[:limit]
    return [(t, deg, name) for name, (t, deg) in items]


def _ikss_at(app, terms):
    """Ikss 3φ (kA) en cada terminal (IEC 60909). Devuelve {fullname: ikss}."""
    shc = app.GetFromStudyCase("ComShc")
    out = {}
    for t in terms:
        try:
            shc.SetAttribute("iopt_mde", 0)
            shc.SetAttribute("iopt_allbus", 0)
            shc.SetAttribute("iopt_shc", "3psc")
            shc.SetAttribute("shcobj", t)
            out[t.GetFullName()] = round(_attr(t, "m:Ikss") or 0.0, 3) if shc.Execute() == 0 else None
        except Exception:
            out[t.GetFullName()] = None
    return out


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
        bess_mode: str = "discharge", scale_loads: float = 1.0,
        run_id: str | None = None, progress=None) -> dict:
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda phase, pct: None)
    data = {"study": "steady_state", "run_id": run_id, "substation": sub_name,
            "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode}}

    with PFRunSandbox(app, run_id=run_id) as sb:
        sub = pv_bess.find_substation(app, sub_name)
        data["load_scaling"] = pv_bess.scale_loads(sb, app, scale_loads)

        # 1) Caso base (sin planta) — necesario antes de elegir el PCC energizado
        report("flujo de carga base", 10)
        if _run_ldf(app) != 0:
            raise RuntimeError("El flujo de carga base no convergió.")
        data["base"] = _capture(app)
        data["base"]["system"] = _system_totals(app)
        sv_base = _substation_voltages(app)

        # Escenario de operación activo (P01..P24 = la hora del flujo de carga)
        scen = app.GetActiveScenario()
        sname = scen.loc_name if scen is not None else None
        hour = int(re.sub(r"\D", "", sname)) if sname and re.search(r"\d", sname) else None
        data["scenario"] = {"name": sname, "hour": hour}

        # PCC = barra de mayor tensión ENERGIZADA de la subestación (evita barras muertas/spare)
        pcc = pv_bess.pick_pcc(app, sub, energized=True)
        data["pcc"] = {"name": pcc.loc_name, "kv": round(pcc.GetAttribute("uknom"), 1)}

        # Barras de subestaciones vecinas + sus tensiones SIN planta (para la comparación antes/después).
        neighbors = _neighbor_buses(app, sub)
        nb_base = {}
        for t in neighbors:
            ss = t.GetAttribute("cpSubstat")
            nb_base[t.GetFullName()] = (t.loc_name, round(t.GetAttribute("uknom"), 1),
                                        _attr(t, "m:u"), ss.loc_name if ss else None)
        pcc_v_base = _attr(pcc, "m:u")

        # Cortocircuito SIN planta en el PCC + barras aledañas (1.er/2.º grado)
        report("cortocircuito (sin planta)", 30)
        sc_buses = [(pcc, 0, sub_name)] + _sc_buses(app, sub)
        sc_terms = [t for t, _, _ in sc_buses]
        ikss_base = _ikss_at(app, sc_terms)

        # 2) Con planta PV+BESS (despacho coherente con la hora del escenario)
        report("modelando PV+BESS y flujo con planta", 45)
        plant = pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode, hour=hour)
        data["plant_dispatch"] = {"pv_out_mw": plant["params"]["pv_out_mw"],
                                  "bess_out_mw": plant["params"]["bess_out_mw"], "hour": hour}
        if _run_ldf(app) != 0:
            raise RuntimeError("El flujo de carga con planta no convergió.")
        data["with_plant"] = _capture(app)
        data["with_plant"]["system"] = _system_totals(app)
        data["substation_voltages"] = _substation_voltages(app)      # con planta -> heatmap
        data["substation_voltages_base"] = sv_base
        data["dispatch"] = _dispatch(app)

        # Tensiones de las barras vecinas al PCC, antes vs después (incluye el PCC).
        def _vu(t):
            u = _attr(t, "m:u")
            return round(u, 4) if u else None

        rows = [{"bus": pcc.loc_name, "sub": sub_name, "kv": data["pcc"]["kv"], "is_pcc": True,
                 "v_base": round(pcc_v_base, 4) if pcc_v_base else None, "v_plant": _vu(pcc)}]
        for t in neighbors:
            b = nb_base.get(t.GetFullName())
            rows.append({"bus": t.loc_name, "sub": b[3] if b else None, "kv": b[1] if b else None,
                         "is_pcc": False, "v_base": round(b[2], 4) if b and b[2] else None,
                         "v_plant": _vu(t)})
        data["pcc_neighbors"] = rows

        # 3) Cortocircuito CON planta en las mismas barras -> sección comparativa con/sin planta
        report("cortocircuito (con planta)", 55)
        ikss_plant = _ikss_at(app, sc_terms)
        sc_rows = []
        for t, deg, sname2 in sc_buses:
            fn = t.GetFullName()
            sc_rows.append({"bus": t.loc_name, "sub": sname2, "degree": deg,
                            "kv": round(t.GetAttribute("uknom"), 1),
                            "ikss_base": ikss_base.get(fn), "ikss_plant": ikss_plant.get(fn)})
        data["short_circuit"] = sc_rows
        pcc_ik = ikss_plant.get(pcc.GetFullName())
        data["short_circuit_with_plant"] = {"ikss_3ph_ka": pcc_ik}

        # 4) Análisis de contingencia (N-1) sobre las líneas locales (1.er y 2.º grado)
        report("análisis de contingencia (N-1)", 70)
        data["contingency"] = _contingency_matrix(app, sub)
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
    ct = data["contingency"]
    print(f"  Contingencia: {len(ct['lines'])} líneas locales, peor carga={ct['worst_loading_pct']}%")
    print(f"  sistema: demanda={data['with_plant']['system']['demand_mw']}MW gen={data['with_plant']['system']['generation_mw']}MW pérdidas={data['with_plant']['system']['losses_mw']}MW")
    print(f"  CUMPLIMIENTO: {c}")
    print(f"  -> {path}")


if __name__ == "__main__":
    main()
