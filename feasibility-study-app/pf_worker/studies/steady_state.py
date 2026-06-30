"""Estudio Steady State (Etapa 3): flujo de carga + N-1 + cortocircuito en el PCC.

Patrón de referencia: comparación **sin planta** (caso base) vs **con planta** (PV+BESS),
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


def _neighbor_buses(app, sub, limit: int = 6) -> list:
    """Barras representativas de subestaciones vecinas (1.er, 2.º y 3.er grado si hay pocas) para la
    comparación de tensión antes/después. Reutiliza el barrido por grados del cortocircuito."""
    return [t for t, _deg, _name in _sc_buses(app, sub, limit=limit)]


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


def _branch_terms(app, br):
    """Terminales de una rama (línea o transformador) vía bus1/bus2/bus3."""
    terms = []
    for side in ("bus1", "bus2", "bus3"):
        cub = _attr(br, side)
        ct = _attr(cub, "cterm") if cub is not None else None
        if ct is not None:
            terms.append(ct)
    return terms


def _substation_coords():
    """nombre de subestación -> (lat, lon) desde results/substations.json (para el fallback geográfico)."""
    import json
    import paths
    out = {}
    try:
        with open(os.path.join(paths.RESULTS_DIR, "substations.json"), encoding="utf-8") as f:
            for s in json.load(f):
                if s.get("lat") and s.get("lon"):
                    out[s["name"]] = (s["lat"], s["lon"])
    except Exception:
        pass
    return out


def _local_branches_by_degree(app, sub, min_count: int = 5, max_degree: int = 5):
    """Ramas (LÍNEAS y TRANSFORMADORES) por GRADO de conexión desde la subestación de la planta.

    BFS a NIVEL DE TERMINAL: el grado = nº de subestaciones cruzadas (los puntos de derivación/tap, sin
    subestación, se atraviesan sin sumar grado; los acoples conectan barras dentro de una subestación).
    Así una subestación radial de 69 kV que se conecta por un tap a una línea, o por un trafo a 138 kV,
    sí alcanza a sus vecinas. SIEMPRE se analizan ≥ min_count subestaciones/líneas: se sube de grado
    (1.º, 2.º, 3.º…) hasta alcanzarlas. Devuelve [(rama, grado, es_linea)] (acoples sólo para atravesar)."""
    from collections import deque

    def subname(t):
        ss = t.GetAttribute("cpSubstat")
        return ss.loc_name if ss is not None else None

    adj = {}            # fullname terminal -> [(term_vecino, es_nueva_sub)]
    reportable = []     # ramas a clasificar (líneas y trafos)
    for cls, is_line, rep in (("*.ElmLne", True, True), ("*.ElmTr2", False, True),
                              ("*.ElmTr3", False, True), ("*.ElmCoup", False, False)):
        for br in app.GetCalcRelevantObjects(cls):
            try:
                if br.GetAttribute("outserv") != 0:
                    continue
            except Exception:
                pass
            ts = _branch_terms(app, br)
            for i in range(len(ts)):
                for j in range(len(ts)):
                    if i != j:
                        adj.setdefault(ts[i].GetFullName(), []).append(ts[j])
            if rep:
                reportable.append((br, is_line, ts))

    # 1) BFS: distancia en SUBESTACIONES cruzadas (los taps, sin subestación, se atraviesan sin sumar).
    plant_terms = pv_bess.substation_terminals(app, sub)
    dist = {t.GetFullName(): 0 for t in plant_terms}
    sub_dist = {sub.loc_name: 0}
    q = deque(plant_terms)
    while q:
        u = q.popleft()
        du, usub = dist[u.GetFullName()], subname(u)
        for v in adj.get(u.GetFullName(), []):
            vsub = subname(v)
            dv = du + (1 if (vsub and vsub != usub) else 0)
            if dv > max_degree:
                continue
            vfn = v.GetFullName()
            if vfn not in dist or dv < dist[vfn]:
                dist[vfn] = dv
                if vsub is not None and (vsub not in sub_dist or dv < sub_dist[vsub]):
                    sub_dist[vsub] = dv
                q.append(v)

    # 2) grado de cada rama = (distancia de la subestación más cercana que toca) + 1.
    #    Una derivación que sólo toca una subestación vecina (a 1 sub) -> grado 2, no 1.
    out = []
    for br, is_line, ts in reportable:
        subs = {s for s in (subname(t) for t in ts) if s is not None}
        ds = [sub_dist[s] for s in subs if s in sub_dist]
        if not ds:   # rama sólo entre taps -> usar la distancia de sus terminales
            ds = [dist[t.GetFullName()] for t in ts if t.GetFullName() in dist]
            if not ds:
                continue
        deg = min(ds) + 1
        if not (1 <= deg <= max_degree):
            continue
        kv = max((t.GetAttribute("uknom") for t in ts), default=0.0)
        out.append((br, deg, is_line, kv))

    # Cutoff: subir de grado hasta analizar ≥ min_count SUBESTACIONES vecinas y ≥ min_count LÍNEAS
    # (siempre ≥ 2.º grado). Así una subestación radial se estudia hasta el 3.er, 4.º… grado.
    plant_kv = max((t.GetAttribute("uknom") for t in plant_terms), default=0.0)
    neigh_degs = sorted(d for s, d in sub_dist.items() if d >= 1)        # grados de subestaciones vecinas
    line_degs = sorted(d for _, d, il, _ in out if il)

    def _kth(degs, k):
        return degs[k - 1] if len(degs) >= k else (degs[-1] if degs else 2)

    cutoff = min(max_degree, max(2, _kth(neigh_degs, min_count), _kth(line_degs, min_count)))
    local = sorted([b for b in out if b[1] <= cutoff], key=lambda x: (x[1], -x[3]))
    # En barras de baja tensión, incluir además las líneas de MAYOR tensión cercanas (aunque queden fuera del cutoff).
    hv = sorted([b for b in out if b[3] > plant_kv + 1.0 and b[1] > cutoff], key=lambda x: (x[1], -x[3]))
    chosen = hv[:8] + local

    # Garantizar ≥ min_count subestaciones vecinas: si la topología (fragmentada por la conmutación
    # detallada de interruptores) alcanza menos, completar con las subestaciones MÁS CERCANAS por
    # coordenadas, en grados sucesivos. Así una barra radial igual se estudia con ≥5 subestaciones.
    covered = {s for br, d, il, kv in chosen for s in (subname(t) for t in _branch_terms(app, br))
               if s and s != sub.loc_name}
    if len(covered) < min_count:
        coords = _substation_coords()
        p = coords.get(sub.loc_name)
        if p:
            lines_by_sub = {}
            for ln in app.GetCalcRelevantObjects("*.ElmLne"):
                try:
                    if ln.GetAttribute("outserv") != 0:
                        continue
                except Exception:
                    pass
                for t in _branch_terms(app, ln):
                    s = subname(t)
                    if s:
                        lines_by_sub.setdefault(s, []).append(ln)
            nearest = sorted((((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2) ** 0.5, name)
                             for name, c in coords.items()
                             if name != sub.loc_name and name not in covered and name in lines_by_sub)
            deg = max((d for _, d, _, _ in chosen), default=2) + 1
            for _dist, name in nearest:
                if len(covered) >= min_count:
                    break
                ln = max(lines_by_sub[name],
                         key=lambda l: max((t.GetAttribute("uknom") for t in _branch_terms(app, l)), default=0))
                kv = max((t.GetAttribute("uknom") for t in _branch_terms(app, ln)), default=0.0)
                chosen.append((ln, deg, True, kv))
                covered.add(name)
                deg += 1

    return [(br, deg, is_line) for br, deg, is_line, kv in chosen]


def _local_lines_by_degree(app, sub, min_count: int = 5, max_degree: int = 5):
    """Solo las LÍNEAS por grado (para N-1; el barrido cruza trafos para alcanzar líneas lejanas)."""
    return [(b, d) for b, d, is_line in _local_branches_by_degree(app, sub, min_count, max_degree) if is_line]


def _local_lines(app, sub):
    """(compat) Líneas de 1.er y 2.º grado como dos listas; extiende al 3.er grado si hay pocas."""
    by_deg = _local_lines_by_degree(app, sub)
    first = [ln for ln, d in by_deg if d == 1]
    rest = [ln for ln, d in by_deg if d >= 2]   # 2.º (y 3.er grado si se incluyó)
    return first, rest


def _contingency_matrix(app, sub, max_lines: int = 14) -> dict:
    """Matriz N-1: cargabilidad de cada línea local bajo la salida de cada línea local."""
    by_deg = _local_lines_by_degree(app, sub)[:max_lines]
    monitored = [ln for ln, _ in by_deg]
    meta = [{"name": ln.loc_name, "degree": d} for ln, d in by_deg]
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
    """Una barra representativa por subestación vecina (1.er, 2.º y, si hay pocas, 3.er grado).
    Cruza líneas Y transformadores (alcanza las barras de 138/345 kV vecinas)."""
    by_deg = _local_branches_by_degree(app, sub)
    by_sub = {}  # sub_name -> (term, degree)

    def consider(br, degree):
        for t in _branch_terms(app, br):
            ss = t.GetAttribute("cpSubstat")
            if ss is None or ss.loc_name == sub.loc_name:
                continue
            cur = by_sub.get(ss.loc_name)
            if cur is None or degree < cur[1] or (degree == cur[1] and t.GetAttribute("uknom") > cur[0].GetAttribute("uknom")):
                by_sub[ss.loc_name] = (t, degree)

    for br, d, _is_line in by_deg:
        consider(br, d)
    items = sorted(by_sub.items(), key=lambda kv: (kv[1][1], -kv[1][0].GetAttribute("uknom")))[:limit]
    return [(t, deg, name) for name, (t, deg) in items]


def _sc_metrics_at(app, terms):
    """Métricas de cortocircuito IEC 60909 por terminal:
    Ikss 3φ y 1φ (kA), Sk" (MVA), corriente pico ip (kA) y relación X/R. Devuelve {fullname: {...}}."""
    def _r(v, n=3):
        return round(v, n) if isinstance(v, (int, float)) and v else None

    shc = app.GetFromStudyCase("ComShc")
    out = {}
    for t in terms:
        m = {"ikss_3ph": None, "skss_mva": None, "ip_3ph": None, "ikss_1ph": None, "xr": None}
        try:
            shc.SetAttribute("iopt_mde", 0)
            shc.SetAttribute("iopt_allbus", 0)
            shc.SetAttribute("iopt_shc", "3psc")
            shc.SetAttribute("shcobj", t)
            if shc.Execute() == 0:
                m["ikss_3ph"] = _r(_attr(t, "m:Ikss"))
                m["skss_mva"] = _r(_attr(t, "m:Skss"), 1)
                m["ip_3ph"] = _r(_attr(t, "m:ip"))
                rtox = _attr(t, "m:rtox")          # R/X -> reportamos X/R = 1/(R/X)
                if isinstance(rtox, (int, float)) and rtox > 1e-6:
                    m["xr"] = round(1.0 / rtox, 2)
                else:                              # fallback: X/R desde m:X y m:R
                    rr, xx = _attr(t, "m:R"), _attr(t, "m:X")
                    if isinstance(rr, (int, float)) and isinstance(xx, (int, float)) and abs(rr) > 1e-9:
                        m["xr"] = round(abs(xx / rr), 2)
        except Exception:
            pass
        try:
            shc.SetAttribute("iopt_shc", "spgf")   # falla monofásica a tierra (SLG)
            shc.SetAttribute("shcobj", t)
            if shc.Execute() == 0:
                m["ikss_1ph"] = _r(_attr(t, "m:Ikss"))
        except Exception:
            pass
        out[t.GetFullName()] = m
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
        sc_base = _sc_metrics_at(app, sc_terms)

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
        sc_plant = _sc_metrics_at(app, sc_terms)
        sc_rows = []
        for t, deg, sname2 in sc_buses:
            fn = t.GetFullName()
            b, p = sc_base.get(fn, {}), sc_plant.get(fn, {})
            ik_b, ik_p = b.get("ikss_3ph"), p.get("ikss_3ph")
            delta = round(ik_p - ik_b, 3) if (ik_b is not None and ik_p is not None) else None
            sc_rows.append({"bus": t.loc_name, "sub": sname2, "degree": deg,
                            "kv": round(t.GetAttribute("uknom"), 1),
                            "ikss_base": ik_b, "ikss_plant": ik_p, "delta": delta,
                            "skss_mva": p.get("skss_mva"), "ip_ka": p.get("ip_3ph"),
                            "ikss_1ph": p.get("ikss_1ph"), "xr": p.get("xr")})
        data["short_circuit"] = sc_rows
        pcc_p = sc_plant.get(pcc.GetFullName(), {})
        data["short_circuit_with_plant"] = {
            "ikss_3ph_ka": pcc_p.get("ikss_3ph"), "ikss_1ph_ka": pcc_p.get("ikss_1ph"),
            "skss_mva": pcc_p.get("skss_mva"), "ip_ka": pcc_p.get("ip_3ph"), "xr": pcc_p.get("xr")}

        # 4) Análisis de contingencia (N-1) sobre las líneas locales (1.er y 2.º grado)
        report("análisis de contingencia (N-1)", 70)
        data["contingency"] = _contingency_matrix(app, sub)
        report("evaluando criterios", 90)

    # --- veredicto por DELTA: la planta no debe INTRODUCIR ni EMPEORAR violaciones ---
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
