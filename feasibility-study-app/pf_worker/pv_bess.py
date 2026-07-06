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


# --- Dimensionamiento del BESS según su ROL (función de la potencia de la planta PV) --------------
# El BESS no se ingresa a mano: su tamaño se deriva de la PV y del tipo de estudio.
#   arbitraje  (por defecto, todos los estudios salvo el de frecuencia):
#              50% de la potencia PV y 4 h de energía  (ej.: PV 100 MW -> BESS 50 MW / 200 MWh).
#   frecuencia (solo el estudio de regulación de frecuencia):
#              5% de la potencia PV (regulación primaria) y 1 h de energía.
ARBITRAGE_MW_FRAC = 0.50
ARBITRAGE_HOURS = 4.0
FREQREG_MW_FRAC = 0.05          # 5% de la PV para regulación primaria de frecuencia
FREQREG_HOURS = 1.0           # energía equivalente a 1 hora
BESS_MIN_PV_MW = 20.0         # plantas PV < 20 MWn NO requieren sistema de almacenamiento
RPC_KVI = 30.0               # ganancia integral de tensión del RPC clonado (de fábrica 10): con 30 el
                             # reactivo VUELVE A CERO ~1 s tras despejar la falla (antes tardaba ~6 s),
                             # manteniendo el aporte pleno durante el cortocircuito.


def bess_sizing(pv_mw: float, role: str = "arbitrage") -> tuple[float, float]:
    """Devuelve (bess_mw, bess_mwh) según el rol del BESS y la potencia de la planta PV.
    Plantas PV de menos de 20 MWn no requieren almacenamiento -> (0, 0)."""
    if pv_mw < BESS_MIN_PV_MW:
        return 0.0, 0.0
    if role == "frequency":
        mw = round(FREQREG_MW_FRAC * pv_mw, 3)
        return mw, round(mw * FREQREG_HOURS, 3)
    mw = round(ARBITRAGE_MW_FRAC * pv_mw, 3)     # arbitraje
    return mw, round(mw * ARBITRAGE_HOURS, 3)


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


def find_dynamic_ref(app):
    """Modelo dinámico de referencia a clonar para dar reactivo FRT a la planta sintética.

    Se usa el modelo de la BESS EDM3 del PDD: sus 4 DSL (APC, RPC, BSM, Control Flags) NO están
    encriptados y el control de reactivo (RPC) AUTO-INICIALIZA limpio (`inc(Vref)=Vt`), por lo que
    el modelo compuesto converge en ComInc a cualquier tensión de PCC. Devuelve el ElmComp de
    referencia, o None si el proyecto no lo trae (entonces la planta cae a genstat estático)."""
    comps = app.GetCalcRelevantObjects("*.ElmComp")
    for c in comps:
        if c.loc_name in ("BESS 1_EDM3", "BESS 2_EDM3"):
            return c
    for c in comps:  # cualquier planta cuyo frame sea 'BESS' con DSL editables
        t = c.GetAttribute("typ_id")
        if t is not None and t.loc_name == "BESS":
            return c
    return None


def attach_dynamic_model(sb, app, grid, pcc_term, cub, sgn, pgini, category, name, ref_comp):
    """Clona el modelo dinámico de referencia (BESS EDM3) sobre un generador nuevo en `cub`.

    `AddCopy` del generador (hereda su configuración RMS de fuente de corriente) + `AddCopy` del
    ElmComp (trae los 4 DSL y los medidores StaVmea/StaPqmea/PLL); se reapuntan los medidores al
    PCC y se re-arma `pelm` con el generador nuevo en el slot Converter. Rastreado por el sandbox.
    Devuelve (gen, comp)."""
    ref_pelm = list(ref_comp.GetAttribute("pelm"))
    ref_gen = next(e for e in ref_pelm if e is not None and e.GetClassName() == "ElmGenstat")
    gen = sb.track(grid.AddCopy(ref_gen, name))
    gen.SetAttribute("bus1", cub)
    gen.SetAttribute("sgn", max(sgn, 0.1))
    gen.SetAttribute("pgini", pgini)
    gen.SetAttribute("qgini", 0.0)
    gen.SetAttribute("cCategory", category)
    gen.SetAttribute("av_mode", "constq")   # LDF a Q=0; el modelo RMS gobierna el reactivo dinámico
    gen.SetAttribute("outserv", 0)
    try:
        gen.SetAttribute("Kfactor", 1.2)
    except Exception:
        pass
    comp = sb.track(grid.AddCopy(ref_comp, name + "_ctrl"))
    kids = {k.loc_name: k for k in comp.GetContents()}
    for k in comp.GetContents():         # medidores del comp -> reapuntar al PCC
        cn = k.GetClassName()
        if cn in ("StaVmea", "StaVt", "ElmPhi__pll"):
            if k.HasAttribute("pbusbar"):
                k.SetAttribute("pbusbar", pcc_term)
        elif cn == "StaPqmea":
            if k.HasAttribute("pcubic"):
                k.SetAttribute("pcubic", cub)
    new_pelm = [(gen if e is ref_gen else (None if e is None else kids.get(e.loc_name)))
                for e in ref_pelm]
    comp.SetAttribute("pelm", new_pelm)
    # Afinar el control de reactivo (RPC): subir Kvi para que el reactivo VUELVA A CERO rápido al despejar
    # la falla (con el valor de fábrica la cola de retorno era de ~6 s), sin perder el aporte durante el CC.
    for k in comp.GetContents():
        typ = k.GetAttribute("typ_id") if hasattr(k, "GetAttribute") else None
        if typ is not None and getattr(typ, "loc_name", "") == "RPC":
            try:
                pars = list(k.GetAttribute("params"))     # [Kqp, Kqi, Kvp, Kvi]
                if len(pars) >= 4:
                    pars[3] = RPC_KVI
                    k.SetAttribute("params", pars)
            except Exception:
                pass
            break
    return gen, comp


def _make_unit(sb, app, grid, pcc, cub, mw, out, category, name, ref_comp):
    """Crea un generador de la planta. Si está DESPACHADO para inyectar (out>0) y hay modelo de
    referencia, clona el modelo dinámico (reactivo FRT real); si no (sin sol / cargando / sin
    modelo), genstat estático (fuera de servicio si no hay despacho)."""
    dispatched = out is not None and out > 0.05
    if dispatched and ref_comp is not None:
        return attach_dynamic_model(sb, app, grid, pcc, cub, mw, out, category, name, ref_comp)
    gen = sb.create(grid, "ElmGenstat", name)
    gen.SetAttribute("bus1", cub)
    gen.SetAttribute("cCategory", category)
    gen.SetAttribute("sgn", max(mw, 0.1))
    gen.SetAttribute("pgini", out or 0.0)
    gen.SetAttribute("qgini", 0.0)
    gen.SetAttribute("av_mode", "constq")
    gen.SetAttribute("Kfactor", 1.2)
    gen.SetAttribute("outserv", 0 if (out is not None and abs(out) > 0.05) else 1)
    return gen, None


def build_pv_bess(sb, app, pcc, pv_mw: float, bess_mw: float = 0.0, bess_mwh: float = 0.0,
                  bess_mode: str = "discharge", hour: int | None = None, bess_role: str = "arbitrage"):
    """Crea PV + BESS conectados a la barra `pcc`. Devuelve objetos y metadatos.

    El BESS se DIMENSIONA a partir de la potencia PV y su ROL (los `bess_mw`/`bess_mwh` que llegan
    se ignoran): `arbitrage` = 50% de la PV y 4 h (todos los estudios salvo frecuencia); `frequency`
    = 10% de la PV (5% primaria + 5% secundaria, solo el estudio de regulación de frecuencia).

    Si se da `hour` (la hora del escenario de operación), la salida sigue la regulación: el PV
    genera según el sol y el BESS **carga al mediodía / descarga en la noche** (no inyectan a la
    vez). Si no, se usa `bess_mode` (descarga/carga) con PV a plena potencia.
    """
    grid = grid_of(pcc)
    if grid is None:
        raise RuntimeError(f"No se pudo resolver el ElmNet del PCC '{pcc.loc_name}'.")

    bess_mw, bess_mwh = bess_sizing(pv_mw, bess_role)   # el BESS se deriva de la PV según el rol

    if hour is not None:
        pv_out = round(pv_mw * solar_factor(hour), 3)
        bess_out = round(bess_mw * bess_factor(hour), 3)   # (-) carga, (+) descarga
    else:
        pv_out = pv_mw
        bess_out = bess_mw if bess_mode == "discharge" else -bess_mw

    # Modelo dinámico de referencia (BESS EDM3, DSL editables + auto-init). Si el proyecto lo trae,
    # el/los generador(es) despachados reciben control de reactivo FRT real; si no, genstat estático.
    ref = find_dynamic_ref(app)

    # --- PV: dinámico si hay sol (pv_out>0), estático/fuera de servicio si es de noche ---
    cub_pv = sb.create(pcc, "StaCubic", "Cub_PV")
    pv, pv_ctrl = _make_unit(sb, app, grid, pcc, cub_pv, pv_mw, pv_out, "Photovoltaic", "PV", ref)

    # --- BESS: dinámico al DESCARGAR (bess_out>0); estático/consumiendo al cargar; sin aporte si ocioso ---
    cub_b = sb.create(pcc, "StaCubic", "Cub_BESS")
    bess, bess_ctrl = _make_unit(sb, app, grid, pcc, cub_b, bess_mw, bess_out, "Storage", "BESS", ref)

    return {
        "pcc_name": pcc.loc_name,
        "pcc_kv": pcc.GetAttribute("uknom"),
        "pcc": pcc,
        "grid": grid.loc_name,
        "pv": pv,
        "bess": bess,
        "pv_ctrl": pv_ctrl,       # ElmComp dinámico (o None si estático)
        "bess_ctrl": bess_ctrl,
        "dynamic": ref is not None,
        "params": {"pv_mw": pv_mw, "bess_mw": bess_mw, "bess_mwh": bess_mwh, "bess_mode": bess_mode,
                   "bess_role": bess_role, "hour": hour, "pv_out_mw": pv_out, "bess_out_mw": bess_out},
    }
