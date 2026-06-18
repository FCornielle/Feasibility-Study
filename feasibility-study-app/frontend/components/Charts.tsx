"use client";
import dynamic from "next/dynamic";

// react-plotly.js importa plotly.js (necesita window) -> solo cliente.
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as any;

const DARK = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#8aa0b4", size: 11 },
  margin: { l: 45, r: 15, t: 30, b: 40 },
};

interface Bus { bus: string; kv: number; u_pu: number; }
interface Branch { elem: string; type: string; loading_pct: number; }

export function VoltageChart({ base, plant }: { base: Bus[]; plant: Bus[] }) {
  const idx = plant.map((_, i) => i);
  return (
    <Plot
      data={[
        { x: idx, y: base.map((b) => b.u_pu), mode: "markers", type: "scattergl", name: "sin planta",
          marker: { size: 3, color: "#8aa0b4" } },
        { x: idx, y: plant.map((b) => b.u_pu), mode: "markers", type: "scattergl", name: "con planta",
          marker: { size: 3, color: "#2e86ff" } },
      ]}
      layout={{
        ...DARK, height: 280, title: "Perfil de tensión por barra (pu)",
        shapes: [
          { type: "line", x0: 0, x1: idx.length, y0: 1.05, y1: 1.05, line: { color: "#e74c3c", dash: "dot", width: 1 } },
          { type: "line", x0: 0, x1: idx.length, y0: 0.95, y1: 0.95, line: { color: "#e74c3c", dash: "dot", width: 1 } },
        ],
        legend: { orientation: "h", y: 1.15 },
        yaxis: { title: "u [pu]" }, xaxis: { title: "barra (índice)" },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%" }}
    />
  );
}

export function LoadingChart({ branches }: { branches: Branch[] }) {
  const top = [...branches].sort((a, b) => b.loading_pct - a.loading_pct).slice(0, 15).reverse();
  return (
    <Plot
      data={[
        { x: top.map((b) => b.loading_pct), y: top.map((b) => b.elem), type: "bar", orientation: "h",
          marker: { color: top.map((b) => (b.loading_pct > 100 ? "#e74c3c" : "#2ecc71")) } },
      ]}
      layout={{
        ...DARK, height: 320, title: "Cargabilidad — top 15 ramas (%)",
        margin: { l: 160, r: 15, t: 30, b: 40 },
        shapes: [{ type: "line", x0: 100, x1: 100, y0: -0.5, y1: top.length - 0.5, line: { color: "#f1c40f", dash: "dot", width: 1 } }],
        xaxis: { title: "% del límite" },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%" }}
    />
  );
}
