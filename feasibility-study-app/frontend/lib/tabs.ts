export interface Tab {
  id: string;
  label: string;
  stub?: boolean;
}

// Orden de la barra lateral (según el plan). El id de las pestañas dinámicas == clave del estudio
// en el worker (steady usa "steady_state"; ver STUDY_KEY).
export const TABS: Tab[] = [
  { id: "recurso", label: "Estudio de Recurso", stub: true },
  { id: "steady", label: "Steady State" },
  { id: "small-signal", label: "Small Signal Stability" },
  { id: "transient", label: "Transient Stability" },
  { id: "voltage", label: "Voltage Stability" },
  { id: "frequency", label: "Frequency Stability" },
  { id: "quasi", label: "Quasi-dinámicas (OC)", stub: true },
];

// Pestañas dinámicas (resultado con serie x/traces); el resto se maneja aparte.
export const DYNAMIC_TABS = ["small-signal", "transient", "voltage", "frequency"];
