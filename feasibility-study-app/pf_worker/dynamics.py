"""Helpers de simulación dinámica RMS para los estudios de estabilidad (Etapa 6).

Patrón validado contra PDD 30-09-2025:
  inc = ComInc; res = inc.p_resvar ("All calculations"); sim = ComSim.
  res.Clear() + res.AddVariable(obj,var)  ->  inc.Execute()  ->  sim(tstop).Execute()
  lectura: app.ResLoadData(res); GetValue(row,-1)=[ierr,t]; GetValue(row,col)=[ierr,val]; col=FindColumn(obj,var).
  eventos: IntEvt.CreateObject('EvtOutage'|'EvtShc'|'EvtSwitch'); attrs time, p_target.

Nota: ComMod (análisis modal) no converge en este modelo sin configuración especial, por eso el
small-signal se evalúa por amortiguamiento de la oscilación tras un pulso (como en el estudio Sajoma).
"""
from __future__ import annotations

import math

FN = 60.0  # frecuencia nominal del SENI [Hz]


def _gen_rating(s) -> float:
    """Tamaño aproximado de un ElmSym (MW despachado, o sgn del tipo)."""
    for a in ("pgini", "P_max"):
        try:
            v = s.GetAttribute(a)
            if v:
                return abs(v)
        except Exception:
            pass
    typ = s.GetAttribute("typ_id") if hasattr(s, "GetAttribute") else None
    try:
        return abs(typ.GetAttribute("sgn")) if typ else 0.0
    except Exception:
        return 0.0


def reference_generator(app):
    """Mayor generador síncrono en servicio (referencia de frecuencia/oscilación)."""
    syms = [s for s in app.GetCalcRelevantObjects("*.ElmSym") if s.GetAttribute("outserv") == 0]
    if not syms:
        raise RuntimeError("No hay generadores síncronos en servicio.")
    return max(syms, key=_gen_rating)


def rms_prepare(app, monitored):
    """Prepara el RMS: limpia el ElmRes y registra las variables a monitorear (lista de (obj,var))."""
    inc = app.GetFromStudyCase("ComInc")
    res = inc.GetAttribute("p_resvar")
    if res is None:  # study case nuevo (sandbox): crear el ElmRes y enlazarlo
        res = app.GetFromStudyCase("All calculations.ElmRes")
        inc.SetAttribute("p_resvar", res)
    sim = app.GetFromStudyCase("ComSim")
    try:
        res.Clear()
    except Exception:
        pass
    for obj, var in monitored:
        res.AddVariable(obj, var)
    return inc, sim, res


def rms_run(app, inc, sim, tstop: float, dt: float = 0.01):
    inc.SetAttribute("dtgrd", dt)
    if inc.Execute() != 0:
        raise RuntimeError("ComInc (condiciones iniciales RMS) no convergió.")
    sim.SetAttribute("tstop", tstop)
    # ComSim.Execute() devuelve 1 incluso en corridas válidas en este modelo; el éxito real se
    # determina por la presencia de filas en el ElmRes (lo valida el llamador con series()).
    sim.Execute()


def _val(x):
    return x[1] if isinstance(x, (list, tuple)) else x


def series(app, res, obj, var):
    """Devuelve (t[], y[]) de la variable monitoreada tras la corrida RMS."""
    app.ResLoadData(res)
    n = res.GetNumberOfRows()
    col = res.FindColumn(obj, var)
    t, y = [], []
    if col < 0:
        return t, y
    for r in range(n):
        t.append(_val(res.GetValue(r, -1)))
        y.append(_val(res.GetValue(r, col)))
    return t, y


def add_event(sb, app, cls: str, name: str, time: float, target=None, **attrs):
    """Crea un evento en IntEvt vía el sandbox (rastreado y borrado en el teardown)."""
    evtf = app.GetFromStudyCase("IntEvt")
    e = sb.create(evtf, cls, name)
    e.SetAttribute("time", time)
    if target is not None:
        e.SetAttribute("p_target", target)
    for k, v in attrs.items():
        try:
            e.SetAttribute(k, v)
        except Exception:
            pass
    return e


# ---- métricas ----
def nadir(y):
    return min(y) if y else None


def peak(y):
    return max(y) if y else None


def max_rocof(t, y):
    """Máxima |dy/dt| de la serie (y en Hz) -> RoCoF [Hz/s]."""
    m = 0.0
    for i in range(1, len(t)):
        dtv = t[i] - t[i - 1]
        if dtv > 0:
            m = max(m, abs((y[i] - y[i - 1]) / dtv))
    return m


def damping_ratio(y):
    """Razón de amortiguamiento aproximada por decremento logarítmico de picos sucesivos."""
    if len(y) < 5:
        return None
    base = sum(y) / len(y)
    peaks = [abs(y[i] - base) for i in range(1, len(y) - 1) if y[i] > y[i - 1] and y[i] > y[i + 1]]
    peaks = [p for p in peaks if p > 1e-9]
    if len(peaks) < 2:
        return None
    n = len(peaks) - 1
    if peaks[0] <= 0 or peaks[n] <= 0:
        return None
    delta = math.log(peaks[0] / peaks[n]) / n
    return delta / math.sqrt(4 * math.pi ** 2 + delta ** 2)


def _gps_of_term(term):
    ss = term.GetAttribute("cpSubstat") if term is not None else None
    if ss is None:
        return None
    la, lo = ss.GetAttribute("GPSlat"), ss.GetAttribute("GPSlon")
    return (la, lo) if (la and lo) else None


import re as _re
import unicodedata as _ud

_COORDS_CACHE = None


def _norm_name(s: str) -> str:
    """Normaliza un nombre para emparejar generador <-> barra (sin acentos, sin sufijos de unidad/grupo)."""
    s = _ud.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = _re.sub(r"[^a-z0-9 ]", " ", s)
    s = _re.sub(r"\b(grupo|unidad|generador|generadora|gen|tg|tv|tc|ccgt)\d*\b", " ", s)
    s = _re.sub(r"\b\d+\b", " ", s)
    return _re.sub(r"\s+", " ", s).strip()


def _coords_indices():
    """(sub_code -> (lat,lon), nombre_normalizado -> (lat,lon)) desde los datos enriquecidos de modom."""
    global _COORDS_CACHE
    if _COORDS_CACHE is None:
        by_code, by_name = {}, {}
        try:
            import enrich_coords
            for code, c in enrich_coords.substation_coords_from_modom().items():
                by_code[code] = (c[0], c[1])
            names = enrich_coords._bus_names()          # W -> bus_name legible
            bus = enrich_coords._load_bus_coords()       # W -> (lat,lon,src)
            for w, nm in names.items():
                if w in bus:
                    by_name.setdefault(_norm_name(nm), (bus[w][0], bus[w][1]))
        except Exception:
            pass
        _COORDS_CACHE = (by_code, by_name)
    return _COORDS_CACHE


def _gen_coords(s, term, ss):
    """Coordenadas de un generador: GPS del modelo -> coords de su subestación (código) -> match por nombre."""
    g = _gps_of_term(term)
    if g:
        return g
    by_code, by_name = _coords_indices()
    if ss is not None and ss.loc_name in by_code:
        return by_code[ss.loc_name]
    for nm in (s.loc_name, ss.loc_name if ss is not None else ""):
        c = by_name.get(_norm_name(nm))
        if c:
            return c
    return None


def distant_generators(app, pcc, n: int = 6):
    """Generadores síncronos en servicio geográficamente más lejanos del PCC, UNO por subestación
    para dar diversidad (extremos sur/norte/este: hidros remotas como Las Damas, etc.). Son los que
    más participan en los modos inter-área (tienden a perder sincronismo).
    Coordenadas: GPS del modelo (escaso para generadores) + datos enriquecidos de modom por código/nombre."""
    p = _gps_of_term(pcc)
    if not p:
        ss0 = pcc.GetAttribute("cpSubstat")
        by_code, _ = _coords_indices()
        p = by_code.get(ss0.loc_name) if ss0 is not None else None
    by_sub = {}   # subestación -> (coords, mayor unidad)
    for s in app.GetCalcRelevantObjects("*.ElmSym"):
        if s.GetAttribute("outserv") != 0:
            continue
        cub = s.GetAttribute("bus1")
        term = cub.GetAttribute("cterm") if cub is not None else None
        if term is None:
            continue
        ss = term.GetAttribute("cpSubstat")
        g = _gen_coords(s, term, ss)
        if not (p and g):
            continue
        key = ss or term
        cur = by_sub.get(key)
        if cur is None or _gen_rating(s) > _gen_rating(cur[1]):
            by_sub[key] = (g, s)

    # Muestreo de "punto más lejano" (farthest-point sampling) sembrado en el PCC: elige extremos en
    # DIRECCIONES distintas (sur/norte/este), no el cúmulo de plantas más alejado en una sola zona.
    cands = list(by_sub.values())
    anchors = [p] if p else []
    chosen = []
    while cands and anchors and len(chosen) < n:
        g, s = max(cands, key=lambda c: min((c[0][0] - a[0]) ** 2 + (c[0][1] - a[1]) ** 2 for a in anchors))
        chosen.append(s)
        anchors.append(g)
        cands.remove((g, s))

    # Respaldo (sin coordenadas disponibles, p.ej. el .exe sin refdata): completar con los mayores
    # generadores síncronos en servicio, uno por subestación, para SIEMPRE tener señales que monitorear.
    if len(chosen) < n:
        chosen_subs = {(s.GetAttribute("bus1").GetAttribute("cterm").GetAttribute("cpSubstat")
                        if s.GetAttribute("bus1") else None) for s in chosen}
        extra = {}
        for s in app.GetCalcRelevantObjects("*.ElmSym"):
            if s.GetAttribute("outserv") != 0 or s in chosen:
                continue
            cub = s.GetAttribute("bus1")
            term = cub.GetAttribute("cterm") if cub is not None else None
            ss = term.GetAttribute("cpSubstat") if term is not None else None
            if ss in chosen_subs:
                continue
            cur = extra.get(ss)
            if cur is None or _gen_rating(s) > _gen_rating(cur):
                extra[ss] = s
        for s in sorted(extra.values(), key=_gen_rating, reverse=True):
            if len(chosen) >= n:
                break
            chosen.append(s)
    return chosen


def matrix_pencil(y, dt, max_order: int = 16):
    """Extrae los modos (autovalores λ = σ ± jω) de una señal por matrix-pencil/Prony (numpy)."""
    import numpy as np
    y = np.asarray(y, float)
    y = y - y.mean()
    nrm = np.max(np.abs(y)) or 1.0
    y = y / nrm
    N = len(y)
    if N < 30:
        return []
    L = min(N // 2, 120)   # cap para que pinv/eigvals sean rápidos (suficiente para modos lentos)
    H = np.array([y[i:i + L] for i in range(N - L + 1)])   # Hankel (N-L+1) x L
    H1, H2 = H[:-1], H[1:]
    try:
        A = np.linalg.pinv(H1) @ H2
        z = np.linalg.eigvals(A)
    except np.linalg.LinAlgError:
        return []
    z = z[np.abs(z) > 1e-6]
    lam = np.log(z.astype(complex)) / dt
    return [complex(v) for v in lam]


def electromechanical_modes(y, dt, fmin=0.3, fmax=2.5):
    """Modos electromecánicos (0.1–2.5 Hz) de la señal: lista de {real, imag, freq_hz, damping_pct}."""
    import numpy as np
    out, seen = [], set()
    for lam in matrix_pencil(y, dt):
        f = abs(lam.imag) / (2 * np.pi)
        if not (fmin <= f <= fmax):
            continue
        mag = abs(lam) or 1e-9
        zeta = -lam.real / mag * 100.0
        key = (round(f, 2), round(zeta, 1))
        if key in seen:
            continue
        seen.add(key)
        out.append({"real": round(lam.real, 4), "imag": round(abs(lam.imag), 4),
                    "freq_hz": round(f, 3), "damping_pct": round(zeta, 2)})
    out.sort(key=lambda m: m["damping_pct"])   # el crítico (menos amortiguado) primero
    return out


def modes_from_signals(signals, dt, fmin=0.15, fmax=5.0):
    """Modos de oscilación combinando matrix-pencil sobre VARIAS señales (cada generador revela modos
    distintos -> muchos más puntos, como el plano de autovalores de DigSILENT). Agrupa por frecuencia
    los modos vistos por varias señales (mediana robusta). Lista de {real,imag,freq_hz,damping_pct,count}."""
    import numpy as np
    raw = []
    for y in signals:
        if y is None or len(y) < 30:
            continue
        for lam in matrix_pencil(y, dt):
            f = abs(lam.imag) / (2 * np.pi)
            mag = abs(lam) or 1e-9
            zeta = -lam.real / mag * 100.0
            if fmin <= f <= fmax and -10.0 <= zeta <= 40.0:   # banda electromecánica, descarta espurios
                raw.append((f, zeta, lam.real, abs(lam.imag)))
    if not raw:
        return []
    raw.sort()
    clusters = []
    for f, zeta, re, im in raw:
        for c in clusters:
            if abs(c["f"] - f) <= 0.07:        # misma frecuencia vista por otra señal
                c["items"].append((f, zeta, re, im))
                c["f"] = float(np.median([i[0] for i in c["items"]]))
                break
        else:
            clusters.append({"f": f, "items": [(f, zeta, re, im)]})
    out = []
    for c in clusters:
        it = c["items"]
        out.append({
            "real": round(float(np.median([i[2] for i in it])), 4),
            "imag": round(float(np.median([i[3] for i in it])), 4),
            "freq_hz": round(float(np.median([i[0] for i in it])), 3),
            "damping_pct": round(float(np.median([i[1] for i in it])), 2),
            "count": len(it),
        })
    out.sort(key=lambda m: m["damping_pct"])    # el crítico (menos amortiguado) primero
    return out


def downsample(t, y, max_pts: int = 600):
    """Reduce la serie para el frontend conservando la forma."""
    n = len(t)
    if n <= max_pts:
        return [round(v, 4) for v in t], [round(v, 5) for v in y]
    step = n // max_pts
    return ([round(t[i], 4) for i in range(0, n, step)],
            [round(y[i], 5) for i in range(0, n, step)])
