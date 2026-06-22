"""Esquemas de request/response del API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    substation: str = Field(..., description="Nombre de la subestación (código del modelo PF)")
    study: str = Field("steady_state", description="Estudio a ejecutar")
    pv_mw: float = Field(50.0, ge=0, description="Potencia PV (MW)")
    bess_mw: float = Field(0.0, ge=0, description="Potencia BESS (MW)")
    bess_mwh: float = Field(0.0, ge=0, description="Energía BESS (MWh)")
    bess_mode: str = Field("discharge", pattern="^(discharge|charge)$",
                           description="Modo del BESS: 'discharge' (punta) o 'charge' (mediodía)")
    scenario: Optional[str] = Field(None, description="Escenario de operación / hora (P01..P24); None = el activo")
    scale_loads: float = Field(1.0, gt=0, description="Factor de escala de demanda (a todas las cargas no auxiliares)")

    def to_params(self) -> dict:
        return {"pv_mw": self.pv_mw, "bess_mw": self.bess_mw,
                "bess_mwh": self.bess_mwh, "bess_mode": self.bess_mode,
                "scenario": self.scenario, "scale_loads": self.scale_loads}
