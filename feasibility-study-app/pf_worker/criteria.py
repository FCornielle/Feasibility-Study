"""Umbrales de aceptación normativos (ver docs/criteria.md).

Centraliza los criterios del Código de Conexión del SENI para que los estudios solo emitan PASA/FALLA.
Valores numéricos pendientes de OCR (FRT, RoCoF, damping) se cierran en docs/PENDIENTES.md.
"""
from __future__ import annotations

# Estado estacionario
VOLT_PU_MIN = 0.95          # ±5% en barras de generadores y 69/138/345 kV (Sajoma §3.1.1.a, §3.6)
VOLT_PU_MAX = 1.05
LOADING_MAX_PCT = 100.0     # sin sobrecarga en operación normal y N-1 (§3.1.1.a, §10.2.g)

# Frecuencia
FREQ_FIRST_EDAC_HZ = 59.2   # nadir debe mantenerse por encima del 1.er escalón del EDAC del SENI


def voltage_ok(u_pu: float) -> bool:
    return VOLT_PU_MIN <= u_pu <= VOLT_PU_MAX


def loading_ok(loading_pct: float) -> bool:
    return loading_pct <= LOADING_MAX_PCT


def verdict(passed: bool) -> str:
    return "PASA" if passed else "FALLA"
