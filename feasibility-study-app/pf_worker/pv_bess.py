"""Modelado de la planta PV + batería (BESS) en el punto de conexión (PCC).

Decisión (punto abierto #3): se **construye desde parámetros** con `ElmGenstat` (clase usada por el
propio modelo: categorías 'Photovoltaic', 'Storage', 'Wind'), no se clona una planta tipo. Esto deja
al usuario fijar MW/MWh y mantiene el modelado autocontenido.

Todo se crea vía `sb.create(...)` para que el sandbox lo rastree y lo borre en el teardown.
"""
from __future__ import annotations


def grid_of(term):
    """ElmNet que contiene al terminal (subiendo por los padres)."""
    o = term
    while o is not None:
        if o.GetClassName() == "ElmNet":
            return o
        o = o.GetParent()
    return None


def find_substation(app, name: str):
    for s in app.GetCalcRelevantObjects("*.ElmSubstat"):
        if s.loc_name == name:
            return s
    raise ValueError(f"Subestación '{name}' no encontrada en el modelo.")


def substation_terminals(app, sub):
    """Terminales en servicio de una subestación (vía cpSubstat)."""
    out = []
    for t in app.GetCalcRelevantObjects("*.ElmTerm"):
        ss = t.GetAttribute("cpSubstat")
        if ss is not None and ss.loc_name == sub.loc_name and t.GetAttribute("outserv") == 0:
            out.append(t)
    return out


def pick_pcc(app, sub, energized: bool = False):
    """Barra de mayor tensión nominal de la subestación = punto de conexión (PCC).

    energized=True (recomendado): solo considera barras energizadas (requiere un LDF previo),
    evitando elegir una barra muerta/spare donde la planta no tendría efecto.
    """
    terms = substation_terminals(app, sub)
    if not terms:
        raise ValueError(f"La subestación '{sub.loc_name}' no tiene terminales en servicio.")
    if energized:
        en = []
        for t in terms:
            try:
                if t.GetAttribute("m:u") > 0.5:
                    en.append(t)
            except Exception:
                pass
        if en:
            terms = en
    return max(terms, key=lambda t: t.GetAttribute("uknom"))


def build_pv_bess(sb, app, pcc, pv_mw: float, bess_mw: float, bess_mwh: float,
                  bess_mode: str = "discharge"):
    """Crea PV + BESS conectados a la barra `pcc` (ya seleccionada). Devuelve objetos y metadatos.

    bess_mode: 'discharge' (entrega potencia, horas de punta) o 'charge' (absorbe, mediodía).
    """
    grid = grid_of(pcc)
    if grid is None:
        raise RuntimeError(f"No se pudo resolver el ElmNet del PCC '{pcc.loc_name}'.")

    # --- PV (generador estático fotovoltaico) ---
    cub_pv = sb.create(pcc, "StaCubic", "Cub_PV")
    pv = sb.create(grid, "ElmGenstat", "PV")
    pv.SetAttribute("bus1", cub_pv)
    pv.SetAttribute("cCategory", "Photovoltaic")
    pv.SetAttribute("sgn", max(pv_mw, 0.1))   # MVA nominal (~unidad de pf)
    pv.SetAttribute("pgini", pv_mw)            # MW
    pv.SetAttribute("qgini", 0.0)
    pv.SetAttribute("av_mode", "constq")       # PQ (control de tensión/reactivo = refinamiento Etapa posterior)
    pv.SetAttribute("outserv", 0)

    # --- BESS (generador estático, categoría almacenamiento) ---
    p_bess = bess_mw if bess_mode == "discharge" else -bess_mw
    cub_b = sb.create(pcc, "StaCubic", "Cub_BESS")
    bess = sb.create(grid, "ElmGenstat", "BESS")
    bess.SetAttribute("bus1", cub_b)
    bess.SetAttribute("cCategory", "Storage")
    bess.SetAttribute("sgn", max(bess_mw, 0.1))
    bess.SetAttribute("pgini", p_bess)
    bess.SetAttribute("qgini", 0.0)
    bess.SetAttribute("av_mode", "constq")
    bess.SetAttribute("outserv", 0)

    return {
        "pcc_name": pcc.loc_name,
        "pcc_kv": pcc.GetAttribute("uknom"),
        "pcc": pcc,
        "grid": grid.loc_name,
        "pv": pv,
        "bess": bess,
        "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode},
    }
