export interface Tab {
  id: string;
  label: string;
  stub?: boolean;
}

// Orden de la barra lateral (según el plan). Solo "steady" está implementado en el MVP.
export const TABS: Tab[] = [
  { id: "recurso", label: "Estudio de Recurso", stub: true },
  { id: "steady", label: "Steady State" },
  { id: "small-signal", label: "Small Signal Stability", stub: true },
  { id: "transient", label: "Transient Stability", stub: true },
  { id: "voltage", label: "Voltage Stability", stub: true },
  { id: "frequency", label: "Frequency Stability", stub: true },
  { id: "quasi", label: "Quasi-dinámicas (OC)", stub: true },
];
