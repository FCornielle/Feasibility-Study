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

interface Series { x_label: string; x: number[]; traces: { name: string; y: number[] }[]; }
const PALETTE = ["#2e86ff", "#2ecc71", "#f1c40f", "#e74c3c"];

export function SeriesChart({ series }: { series: Series }) {
  return (
    <Plot
      data={series.traces.map((tr, i) => ({
        x: series.x, y: tr.y, type: "scattergl", mode: "lines", name: tr.name,
        line: { color: PALETTE[i % PALETTE.length], width: 1.6 },
        yaxis: i === 0 ? "y" : "y2",
      }))}
      layout={{
        ...DARK, height: 340,
        legend: { orientation: "h", y: 1.15 },
        xaxis: { title: series.x_label },
        yaxis: { title: series.traces[0]?.name ?? "" },
        yaxis2: series.traces.length > 1
          ? { title: series.traces[1].name, overlaying: "y", side: "right" } : undefined,
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%" }}
    />
  );
}

interface Neighbor { bus: string; sub?: string | null; v_base: number | null; v_plant: number | null; }

export function VoltageRadar({ neighbors }: { neighbors: Neighbor[] }) {
  const pts = neighbors.filter((n) => n.v_base != null && n.v_plant != null);
  if (pts.length < 3) return <div className="phase">Radar requiere ≥3 barras con tensión.</div>;
  const labels = pts.map((n) => `${n.sub ?? ""} ${n.bus}`.trim().slice(0, 22));
  const close = (a: (number | null)[]) => [...a, a[0]];
  return (
    <Plot
      data={[
        { type: "scatterpolar", r: close(pts.map((n) => n.v_base)), theta: [...labels, labels[0]],
          fill: "toself", name: "sin planta", line: { color: "#8aa0b4" }, fillcolor: "rgba(138,160,180,.15)" },
        { type: "scatterpolar", r: close(pts.map((n) => n.v_plant)), theta: [...labels, labels[0]],
          fill: "toself", name: "con planta", line: { color: "#2e86ff" }, fillcolor: "rgba(46,134,255,.2)" },
      ]}
      layout={{
        ...DARK, height: 380,
        polar: {
          radialaxis: { range: [0.85, 1.1], tickfont: { size: 9 }, angle: 90, tickformat: ".2f" },
          bgcolor: "rgba(0,0,0,0)",
        },
        legend: { orientation: "h", y: 1.12 },
        title: "Tensión de barras vecinas (pu) — con vs sin planta",
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
