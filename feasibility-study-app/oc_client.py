"""Cliente del API del OC SENI (WSDL/JSON) — basado en OC_API.txt.

Usa solo stdlib (urllib) para funcionar igual en el backend y en el Python de PowerFactory.
Base: https://apps.oc.org.do/wsOCWebsiteChart/Service.asmx  (HTTP GET -> JSON).
Normaliza fechas probando varios formatos (MM/DD/YYYY, YYYY-MM-DDT00:00:00, YYYY-MM-DD).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime

BASE = "https://apps.oc.org.do/wsOCWebsiteChart/Service.asmx"
UA = "Feasibility-OC-Client/1.0"
DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%dT00:00:00", "%Y-%m-%d")
DATE_KEYS = ("Fecha", "Desde", "Hasta")


def _get(operation: str, params: dict, timeout: int):
    url = f"{BASE}/{operation}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _unwrap(data):
    """Las respuestas vienen como {'GetXxx': [...]}; devuelve el valor interno."""
    if isinstance(data, dict) and len(data) == 1:
        return next(iter(data.values()))
    return data


def call(operation: str, params: dict | None = None, timeout: int = 25):
    """Llama una operación del WSDL. Si hay fechas, prueba formatos hasta obtener datos."""
    params = dict(params or {})
    date_keys = [k for k in params if k in DATE_KEYS]
    if not date_keys:
        return _unwrap(_get(operation, params, timeout))
    data = None
    for fmt in DATE_FORMATS:
        p = dict(params)
        for k in date_keys:
            v = params[k]
            if isinstance(v, (date, datetime)):
                p[k] = v.strftime(fmt)
        data = _get(operation, p, timeout)
        inner = _unwrap(data)
        if inner not in (None, [], {}):
            return inner
    return _unwrap(data)


# ---- helpers temáticos (ver OC_API.txt) ----
def generacion_demanda(fecha):
    """Generación vs demanda del día -> GetGeneracionDemandaJSon."""
    return call("GetGeneracionDemandaJSon", {"Fecha": fecha})


def post_despacho(fecha):
    return call("GetPostDespachoJSon", {"Fecha": fecha})


def predespacho(fecha):
    return call("GetPredespachoJSon", {"Fecha": fecha})


def potencia_programada(fecha):
    return call("GetPotenciaProgramadaJSon", {"Fecha": fecha})


def programa_operativo():
    return call("GetProgramaOperativoJSon")


def generacion_actual(tipo: str = "ALL"):
    return call("GetGeneracionActualJSon", {"Tipo": tipo})
