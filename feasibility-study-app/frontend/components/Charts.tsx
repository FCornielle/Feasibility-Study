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
        { x: idx, y: base.map((b) => b.u_pu), mode: "markers", type: "scatter", name: "sin planta",
          marker: { size: 3, color: "#8aa0b4" } },
        { x: idx, y: plant.map((b) => b.u_pu), mode: "markers", type: "scatter", name: "con planta",
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
        x: series.x, y: tr.y, type: "scatter", mode: "lines", name: tr.name,
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

export function VoltageRadar({ neighbors, subNames }: { neighbors: Neighbor[]; subNames?: Record<string, string> }) {
  const pts = neighbors.filter((n) => n.v_base != null && n.v_plant != null);
  if (pts.length < 3) return <div className="phase">Radar requiere ≥3 barras con tensión.</div>;
  const labels = pts.map((n) => (subNames?.[n.sub ?? ""] || n.sub || n.bus).slice(0, 18));
  const close = (a: (number | null)[]) => [...a, a[0]];
  // Escala = rango real de las tensiones (min..max de las barras), con un pequeño margen.
  const vals = pts.flatMap((n) => [n.v_base!, n.v_plant!]);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = Math.max((hi - lo) * 0.15, 0.002);
  const range: [number, number] = [+(lo - pad).toFixed(4), +(hi + pad).toFixed(4)];
  return (
    <Plot
      data={[
        { type: "scatterpolar", r: close(pts.map((n) => n.v_base)), theta: [...labels, labels[0]],
          name: "sin planta", mode: "lines+markers", line: { color: "#f1c40f", dash: "dash", width: 2 },
          marker: { size: 6, color: "#f1c40f" } },
        { type: "scatterpolar", r: close(pts.map((n) => n.v_plant)), theta: [...labels, labels[0]],
          fill: "toself", name: "con planta", mode: "lines+markers", line: { color: "#2e86ff", width: 2 },
          marker: { size: 5, color: "#2e86ff" }, fillcolor: "rgba(46,134,255,.12)" },
      ]}
      layout={{
        ...DARK, height: 380,
        polar: {
          radialaxis: { range, tickfont: { size: 9 }, angle: 90, tickformat: ".3f" },
          bgcolor: "rgba(0,0,0,0)",
        },
        legend: { orientation: "h", y: 1.12 },
        title: "Tensión de barras vecinas (pu) — con vs sin planta · (scroll para zoom)",
      }}
      config={{ displayModeBar: false, responsive: true, scrollZoom: true }}
      style={{ width: "100%" }}
    />
  );
}

export function LoadingChart({ branches, title }: { branches: Branch[]; title?: string }) {
  const top = [...branches].filter((b) => b.loading_pct != null)
    .sort((a, b) => b.loading_pct - a.loading_pct).slice(0, 15).reverse();
  return (
    <Plot
      data={[
        { x: top.map((b) => b.loading_pct), y: top.map((b) => b.elem), type: "bar", orientation: "h",
          marker: { color: top.map((b) => (b.loading_pct > 100 ? "#e74c3c" : "#2ecc71")) } },
      ]}
      layout={{
        ...DARK, height: Math.max(280, top.length * 22 + 60),
        title: title ?? "Cargabilidad de ramas (%)",
        margin: { l: 240, r: 15, t: 34, b: 40 },
        yaxis: { automargin: true, tickfont: { size: 10 } },
        shapes: [{ type: "line", x0: 100, x1: 100, y0: -0.5, y1: top.length - 0.5, line: { color: "#f1c40f", dash: "dot", width: 1 } }],
        xaxis: { title: "% del límite" },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%" }}
    />
  );
}

interface Mode { real: number; imag: number; freq_hz: number; damping_pct: number; }
function ChartFailBox({ children }: { children: any }) {
  return (
    <div style={{
      height: 340, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      gap: 8, border: "1px dashed var(--bad)", borderRadius: 8, background: "rgba(231,76,60,0.07)",
      color: "var(--bad)", textAlign: "center", padding: 20,
    }}>
      <div style={{ fontSize: 30 }}>⚠</div>
      <div style={{ fontWeight: 700 }}>Simulación sin datos</div>
      <div style={{ color: "var(--text)", fontSize: 13, maxWidth: 420 }}>{children}</div>
    </div>
  );
}

export function EigenvalueChart({ sin, con }: { sin: Mode[]; con: Mode[] }) {
  if (!sin.length && !con.length)
    return <ChartFailBox>No se extrajeron modos: el RMS no convergió o no se monitorearon generadores. Prueba otra hora (nocturna) o revisa que el escenario sea válido.</ChartFailBox>;
  return (
    <Plot
      data={[
        { x: sin.map((m) => m.real), y: sin.map((m) => m.imag), mode: "markers", type: "scatter",
          name: "sin planta", marker: { symbol: "circle-open", color: "#f1c40f", size: 11, line: { width: 2 } } },
        { x: con.map((m) => m.real), y: con.map((m) => m.imag), mode: "markers", type: "scatter",
          name: "con planta", marker: { symbol: "x", color: "#2e86ff", size: 10 } },
      ]}
      layout={{
        ...DARK, height: 360, title: "Autovalores (plano complejo) — modos electromecánicos · (scroll = zoom)",
        legend: { orientation: "h", y: 1.15 },
        xaxis: { title: "σ parte real [1/s]  ·  estable ← | → inestable", zeroline: false },
        yaxis: { title: "ω parte imaginaria [rad/s]" },
        shapes: [{ type: "line", x0: 0, x1: 0, yref: "paper", y0: 0, y1: 1, line: { color: "#e74c3c", dash: "dash", width: 1 } }],
      }}
      config={{ displayModeBar: false, responsive: true, scrollZoom: true }}
      style={{ width: "100%" }}
    />
  );
}

export function SpeedChart({ series, title }: { series: any; title?: string }) {
  if (!series?.traces?.length)
    return <ChartFailBox>Sin datos de velocidad: el RMS no produjo resultados (no convergió o sin generadores monitoreados).</ChartFailBox>;
  return (
    <Plot
      data={series.traces.map((tr: any) => ({
        x: series.x, y: tr.y, type: "scatter", mode: "lines", name: tr.name, line: { width: 1 },
      }))}
      layout={{
        ...DARK, height: 340, title: title ?? "Velocidad de generadores [pu]",
        legend: { orientation: "h", y: -0.25, font: { size: 9 } },
        xaxis: { title: series.x_label }, yaxis: { title: "velocidad [pu]" }, margin: { l: 55, r: 15, t: 34, b: 70 },
      }}
      config={{ displayModeBar: false, responsive: true, scrollZoom: true }}
      style={{ width: "100%" }}
    />
  );
}

interface ScRow { bus: string; sub?: string | null; ikss_base: number | null; ikss_plant: number | null; }
export function ShortCircuitChart({ rows, subNames }: { rows: ScRow[]; subNames?: Record<string, string> }) {
  const r = rows.filter((x) => x.ikss_base != null || x.ikss_plant != null);
  if (!r.length) return null;
  const labels = r.map((x) => (subNames?.[x.sub ?? ""] || x.sub || x.bus).slice(0, 16));
  return (
    <Plot
      data={[
        { x: labels, y: r.map((x) => x.ikss_base), type: "bar", name: "sin planta", marker: { color: "#8aa0b4" } },
        { x: labels, y: r.map((x) => x.ikss_plant), type: "bar", name: "con planta", marker: { color: "#2e86ff" } },
      ]}
      layout={{
        ...DARK, height: 320, barmode: "group", title: "Ikss en barras seleccionadas [kA] — con vs sin planta",
        legend: { orientation: "h", y: 1.15 }, xaxis: { tickangle: -35, tickfont: { size: 9 } },
        yaxis: { title: "Ikss [kA]" }, margin: { l: 45, r: 15, t: 40, b: 90 },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%" }}
    />
  );
}
