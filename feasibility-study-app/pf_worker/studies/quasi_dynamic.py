"""Estudio Quasi-dinámico (Etapa 7): perfil horario de 24 h con datos del OC.

Toma la curva de demanda horaria del OC SENI (GetGeneracionDemandaJSon), escala la carga del
modelo a cada hora, aplica un perfil solar a la PV y un perfil de carga/descarga al BESS
(desplazar energía del mediodía a las horas de punta), corre flujo de carga por hora y registra
el perfil de tensión del PCC y la cargabilidad máxima de transmisión.

Es un quasi-dynamic simplificado (serie de soluciones estáticas), basado en el flujo de carga ya
validado; la integración con ComStatsim/características de PF queda para el barrido.
"""
from __future__ import annotations

import math
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # pf_worker
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))  # app root (oc_client)

import criteria  # noqa: E402
import oc_client  # noqa: E402
import pv_bess  # noqa: E402
from sandbox import PFRunSandbox  # noqa: E402

STUDY = "quasi"
MIN_KV = 69.0


def solar_profile(h: int) -> float:
    """Factor 0..1 de generación solar por hora (campana de cielo claro, pico ~13h)."""
    if 6 <= h <= 18:
        return max(0.0, math.sin(math.pi * (h - 6) / 12))
    return 0.0


def bess_profile(h: int) -> float:
    """Factor -1..1 del BESS: carga (-) al mediodía, descarga (+) en punta."""
    if h in (10, 11, 12, 13, 14):
        return -1.0          # carga (absorbe excedente solar)
    if h in (18, 19, 20, 21):
        return 1.0           # descarga (horas de punta)
    return 0.0


def _oc_demand(progress):
    """Curva de demanda horaria del OC para una fecha reciente; fallback sintético si no hay red."""
    d = date.today() - timedelta(days=4)
    try:
        rows = oc_client.generacion_demanda(d)
        if isinstance(rows, list) and rows:
            by_h = {int(r["PERIODO"]): float(r["DEMANDA"]) for r in rows if r.get("DEMANDA")}
            dem = [by_h.get(h, None) for h in range(1, 25)]
            if all(v is not None for v in dem):
                return d.isoformat(), dem, "OC"
    except Exception:
        pass
    # Fallback: curva típica diaria (valle de madrugada, punta nocturna)
    base = [0.78, 0.74, 0.72, 0.71, 0.72, 0.76, 0.82, 0.88, 0.92, 0.95, 0.97, 0.98,
            0.97, 0.96, 0.95, 0.95, 0.96, 0.99, 1.00, 1.00, 0.97, 0.92, 0.86, 0.81]
    return d.isoformat(), [b * 3700 for b in base], "sintético"


def run(app, sub_name, pv_mw, bess_mw, bess_mwh, bess_mode="discharge", run_id=None, progress=None):
    import time
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda p, q: None)
    data = {"study": STUDY, "run_id": run_id, "substation": sub_name,
            "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode}}

    report("consultando demanda del OC", 8)
    fecha, demand, src = _oc_demand(report)
    data["oc"] = {"fecha": fecha, "fuente": src, "demanda_pico_mw": round(max(demand), 1)}

    with PFRunSandbox(app, run_id=run_id) as sb:
        ldf = app.GetFromStudyCase("ComLdf")
        sub = pv_bess.find_substation(app, sub_name)
        if ldf.Execute() != 0:
            raise RuntimeError("Flujo de carga base no convergió.")
        pcc = pv_bess.pick_pcc(app, sub, energized=True)
        data["pcc"] = {"name": pcc.loc_name, "kv": round(pcc.GetAttribute("uknom"), 1)}
        plant = pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode)
        pv, bess = plant["pv"], plant["bess"]

        loads = [l for l in app.GetCalcRelevantObjects("*.ElmLod") if l.GetAttribute("outserv") == 0]
        orig = {l: (l.GetAttribute("plini"), l.GetAttribute("qlini")) for l in loads}
        base_dem = sum(p for p, _ in orig.values()) or 1.0

        hourly = []
        try:
            for i, h in enumerate(range(1, 25)):
                scale = demand[h - 1] / base_dem
                for l in loads:
                    p0, q0 = orig[l]
                    l.SetAttribute("plini", p0 * scale)
                    l.SetAttribute("qlini", q0 * scale)
                pv.SetAttribute("pgini", pv_mw * solar_profile(h))
                bess.SetAttribute("pgini", bess_mw * bess_profile(h))
                report(f"hora {h}/24", 15 + int(75 * i / 24))
                if ldf.Execute() != 0:
                    hourly.append({"period": h, "converged": False})
                    continue
                vs = []
                for tt in app.GetCalcRelevantObjects("*.ElmTerm"):
                    if tt.GetAttribute("outserv") != 0 or tt.GetAttribute("uknom") < MIN_KV:
                        continue
                    try:
                        u = tt.GetAttribute("m:u")
                    except Exception:
                        continue
                    if u > 0.01:
                        vs.append(u)
                loadings = []
                for b in app.GetCalcRelevantObjects("*.ElmLne") + app.GetCalcRelevantObjects("*.ElmTr2"):
                    if b.GetAttribute("outserv") != 0:
                        continue
                    try:
                        loadings.append(b.GetAttribute("m:loading"))
                    except Exception:
                        pass
                hourly.append({
                    "period": h, "converged": True,
                    "demand_mw": round(demand[h - 1], 1),
                    "pcc_v_pu": round(pcc.GetAttribute("m:u"), 4),
                    "v_min": round(min(vs), 4) if vs else None,
                    "v_max": round(max(vs), 4) if vs else None,
                    "max_loading_pct": round(max(loadings), 1) if loadings else None,
                    "pv_mw": round(pv_mw * solar_profile(h), 1),
                    "bess_mw": round(bess_mw * bess_profile(h), 1),
                })
        finally:
            for l in loads:
                p0, q0 = orig[l]
                l.SetAttribute("plini", p0)
                l.SetAttribute("qlini", q0)

    ok_hours = [r for r in hourly if r.get("converged")]
    pcc_v = [r["pcc_v_pu"] for r in ok_hours]
    loadings = [r["max_loading_pct"] for r in ok_hours if r["max_loading_pct"] is not None]
    data["hourly"] = hourly
    data["metrics"] = {
        "fecha_oc": fecha,
        "demanda_pico_mw": round(max(demand), 1),
        "pcc_v_min": round(min(pcc_v), 4) if pcc_v else None,
        "pcc_v_max": round(max(pcc_v), 4) if pcc_v else None,
        "max_loading_pct": round(max(loadings), 1) if loadings else None,
        "horas_convergidas": len(ok_hours),
    }
    data["series"] = {
        "x_label": "hora",
        "x": [r["period"] for r in ok_hours],
        "traces": [
            {"name": "Tensión PCC [pu]", "y": pcc_v},
            {"name": "Cargabilidad máx [%]", "y": loadings},
        ],
    }
    within = all(criteria.voltage_ok(v) for v in pcc_v) if pcc_v else False
    data["compliance"] = {
        "pcc_tension_dentro_de_banda": criteria.verdict(within),
        "overall": criteria.verdict(within),
    }
    return data
