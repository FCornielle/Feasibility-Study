"""Voltage Stability (Etapa 6c): curva P-V por escalamiento de demanda.

Aumenta la demanda del sistema en pasos, corre flujo de carga en cada paso y registra la tensión
mínima de transmisión hasta la no-convergencia (colapso). El margen es el % de carga adicional
soportado. Estudio basado en flujo de carga (no RMS). Restaura la demanda original al terminar.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import criteria  # noqa: E402
import pv_bess  # noqa: E402
from sandbox import PFRunSandbox  # noqa: E402

STUDY = "voltage"
MIN_KV = 69.0
MARGIN_MIN_PCT = 5.0          # margen mínimo aceptable (umbral práctico, ver PENDIENTES.md)
SCALES = [1.0 + 0.05 * i for i in range(0, 13)]  # 1.00 .. 1.60


def _min_transmission_v(app):
    vs = []
    for tt in app.GetCalcRelevantObjects("*.ElmTerm"):
        if tt.GetAttribute("outserv") == 0 and tt.GetAttribute("uknom") >= MIN_KV:
            try:
                u = tt.GetAttribute("m:u")
                if u > 0.01:
                    vs.append(u)
            except Exception:
                pass
    return min(vs) if vs else None


def run(app, sub_name, pv_mw, bess_mw, bess_mwh, bess_mode="discharge", run_id=None, progress=None):
    run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
    report = progress or (lambda p, q: None)
    data = {"study": STUDY, "run_id": run_id, "substation": sub_name,
            "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode}}

    with PFRunSandbox(app, run_id=run_id) as sb:
        # ComLdf debe obtenerse DENTRO del sandbox (pertenece al Study Case activo del run).
        ldf = app.GetFromStudyCase("ComLdf")
        sub = pv_bess.find_substation(app, sub_name)
        report("flujo de carga base", 10)
        if ldf.Execute() != 0:
            raise RuntimeError("Flujo de carga base no convergió.")
        pcc = pv_bess.pick_pcc(app, sub, energized=True)
        data["pcc"] = {"name": pcc.loc_name, "kv": round(pcc.GetAttribute("uknom"), 1)}
        pv_bess.build_pv_bess(sb, app, pcc, pv_mw, bess_mw, bess_mwh, bess_mode)

        loads = [l for l in app.GetCalcRelevantObjects("*.ElmLod") if l.GetAttribute("outserv") == 0]
        orig = {l: (l.GetAttribute("plini"), l.GetAttribute("qlini")) for l in loads}
        curve, last_ok = [], 1.0
        try:
            for k, sc in enumerate(SCALES):
                for l in loads:
                    p0, q0 = orig[l]
                    l.SetAttribute("plini", p0 * sc)
                    l.SetAttribute("qlini", q0 * sc)
                report(f"curva P-V (carga x{sc:.2f})", 20 + int(60 * k / len(SCALES)))
                if ldf.Execute() != 0:
                    break  # colapso: no converge
                vmin = _min_transmission_v(app)
                curve.append({"scale": round(sc, 3), "v_min_pu": round(vmin, 4) if vmin else None})
                last_ok = sc
        finally:
            for l in loads:
                p0, q0 = orig[l]
                l.SetAttribute("plini", p0)
                l.SetAttribute("qlini", q0)

    margin = round((last_ok - 1.0) * 100, 1)
    data["metrics"] = {"margin_pct": margin, "margin_min_pct": MARGIN_MIN_PCT,
                       "collapse_scale": round(last_ok, 2), "n_loads": len(loads)}
    data["series"] = {
        "x_label": "factor de carga",
        "x": [c["scale"] for c in curve],
        "traces": [{"name": "V mín transmisión [pu]", "y": [c["v_min_pu"] for c in curve]}],
    }
    ok = margin >= MARGIN_MIN_PCT
    data["compliance"] = {"margen_de_tension_suficiente": criteria.verdict(ok), "overall": criteria.verdict(ok)}
    return data
