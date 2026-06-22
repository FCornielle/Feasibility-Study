"""Modelado de la planta PV + batería (BESS) en el punto de conexión (PCC).

Decisión (punto abierto #3): se **construye desde parámetros** con `ElmGenstat` (clase usada por el
propio modelo: categorías 'Photovoltaic', 'Storage', 'Wind'), no se clona una planta tipo. Esto deja
al usuario fijar MW/MWh y mantiene el modelado autocontenido.

Todo se crea vía `sb.create(...)` para que el sandbox lo rastree y lo borre en el teardown.
"""
from __future__ import annotations


import math


def solar_factor(hour: int) -> float:
    """Factor 0..1 de generación PV por hora (campana de cielo claro, pico ~13h; 0 de noche)."""
    h = hour % 24
    return max(0.0, math.sin(math.pi * (h - 6) / 12)) if 6 <= h <= 18 else 0.0


def bess_factor(hour: int) -> float:
    """Factor del BESS por hora: -1 carga (mediodía, 10-15h), +1 descarga (punta nocturna, 18-23h)."""
    h = hour % 24
    if 10 <= h <= 15:
        return -1.0
    if 18 <= h <= 23:
        return 1.0
    return 0.0


_AUX_KEYS = ("aux", "auxiliar", "servicio propio", "serv propio", "ssaa", "ss aa", "s.a.", "propio")


def _is_aux_load(load) -> bool:
    """¿Es una carga de servicios auxiliares de una planta? (se excluye del escalado de demanda)."""
    nm = (load.loc_name or "").lower()
    return any(k in nm for k in _AUX_KEYS)


def scale_loads(sb, app, factor: float):
    """Aplica un factor de escala a TODAS las cargas en servicio EXCEPTO las auxiliares de plantas.
    Revertible (vía sandbox). Devuelve {scaled, skipped_aux, factor}."""
    if factor is None or abs(factor - 1.0) < 1e-6:
        return {"scaled": 0, "skipped_aux": 0, "factor": 1.0}
    scaled = skipped = 0
    for ld in app.GetCalcRelevantObjects("*.ElmLod"):
        try:
            if ld.GetAttribute("outserv") != 0:
                continue
        except Exception:
            continue
        if _is_aux_load(ld):
            skipped += 1
            continue
        for attr in ("plini", "qlini"):
            try:
                v = ld.GetAttribute(attr)
                if v is not None:
                    sb.set_attr(ld, attr, v * factor)
            except Exception:
                pass
        scaled += 1
    return {"scaled": scaled, "skipped_aux": skipped, "factor": factor}


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
                  bess_mode: str = "discharge", hour: int | None = None):
    """Crea PV + BESS conectados a la barra `pcc`. Devuelve objetos y metadatos.

    Si se da `hour` (la hora del escenario de operación), la salida sigue la regulación: el PV
    genera según el sol y el BESS **carga al mediodía / descarga en la noche** (no inyectan a la
    vez). Si no, se usa `bess_mode` (descarga/carga) con PV a plena potencia.
    """
    grid = grid_of(pcc)
    if grid is None:
        raise RuntimeError(f"No se pudo resolver el ElmNet del PCC '{pcc.loc_name}'.")

    if hour is not None:
        pv_out = round(pv_mw * solar_factor(hour), 3)
        bess_out = round(bess_mw * bess_factor(hour), 3)   # (-) carga, (+) descarga
    else:
        pv_out = pv_mw
        bess_out = bess_mw if bess_mode == "discharge" else -bess_mw

    # --- PV (generador estático fotovoltaico) ---
    cub_pv = sb.create(pcc, "StaCubic", "Cub_PV")
    pv = sb.create(grid, "ElmGenstat", "PV")
    pv.SetAttribute("bus1", cub_pv)
    pv.SetAttribute("cCategory", "Photovoltaic")
    pv.SetAttribute("sgn", max(pv_mw, 0.1))   # MVA nominal (placa)
    pv.SetAttribute("pgini", pv_out)          # MW despachados a esta hora
    pv.SetAttribute("qgini", 0.0)
    pv.SetAttribute("av_mode", "constq")
    pv.SetAttribute("Kfactor", 1.2)            # aporte a cortocircuito (~1.2x corriente nominal, inversor)
    pv.SetAttribute("outserv", 0)

    # --- BESS (generador estático, categoría almacenamiento) ---
    cub_b = sb.create(pcc, "StaCubic", "Cub_BESS")
    bess = sb.create(grid, "ElmGenstat", "BESS")
    bess.SetAttribute("bus1", cub_b)
    bess.SetAttribute("cCategory", "Storage")
    bess.SetAttribute("sgn", max(bess_mw, 0.1))
    bess.SetAttribute("pgini", bess_out)
    bess.SetAttribute("qgini", 0.0)
    bess.SetAttribute("av_mode", "constq")
    bess.SetAttribute("Kfactor", 1.2)
    bess.SetAttribute("outserv", 0)

    return {
        "pcc_name": pcc.loc_name,
        "pcc_kv": pcc.GetAttribute("uknom"),
        "pcc": pcc,
        "grid": grid.loc_name,
        "pv": pv,
        "bess": bess,
        "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode,
                   "hour": hour, "pv_out_mw": pv_out, "bess_out_mw": bess_out},
    }
