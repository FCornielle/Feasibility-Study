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
  { id: "quasi", label: "Quasi-dinámicas (OC)" },
  { id: "report", label: "📋 Reporte de Interconexión" },
];

// Orden de las secciones en el reporte consolidado.
export const REPORT_ORDER = ["steady_state", "voltage", "small-signal", "transient", "frequency", "quasi"];

// Horas / escenarios de operación P01..P24 (selector compartido).
export const HOURS = Array.from({ length: 24 }, (_, i) => {
  const n = String(i + 1).padStart(2, "0");
  return { value: `P${n}`, label: `P${n} — ${n}:00` };
});

// Pestañas con resultado de serie x/traces (componente DynamicStudy genérico).
export const DYNAMIC_TABS = ["small-signal", "transient", "quasi"];
