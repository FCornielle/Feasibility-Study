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


def distant_generators(app, pcc, n: int = 7):
    """Generadores síncronos en servicio más LEJANOS (geográficamente) del PCC.
    Son los que tienden a perder sincronismo en una oscilación inter-área."""
    p = _gps_of_term(pcc)
    scored = []
    for s in app.GetCalcRelevantObjects("*.ElmSym"):
        if s.GetAttribute("outserv") != 0:
            continue
        cub = s.GetAttribute("bus1")
        term = cub.GetAttribute("cterm") if cub is not None else None
        g = _gps_of_term(term)
        d = ((p[0] - g[0]) ** 2 + (p[1] - g[1]) ** 2) ** 0.5 if (p and g) else -1.0
        scored.append((d, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:n]]


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


def electromechanical_modes(y, dt, fmin=0.1, fmax=2.5):
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


def downsample(t, y, max_pts: int = 600):
    """Reduce la serie para el frontend conservando la forma."""
    n = len(t)
    if n <= max_pts:
        return [round(v, 4) for v in t], [round(v, 5) for v in y]
    step = n // max_pts
    return ([round(t[i], 4) for i in range(0, n, step)],
            [round(y[i], 5) for i in range(0, n, step)])
