"use client";
import { useEffect, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip } from "react-leaflet";
import { getGrid, GridFeature } from "@/lib/api";

// Color por nivel de tensión nominal (modo por defecto, sin resultados).
function levelColor(kvs: number[] = []): string {
  const kv = Math.max(0, ...kvs);
  if (kv >= 230) return "#e74c3c";
  if (kv >= 138) return "#2e86ff";
  if (kv >= 69) return "#2ecc71";
  return "#8aa0b4";
}

// Heatmap de tensión (pu): AZUL (baja) → blanco angosto (~1.0) → NARANJA → ROJO (alta).
function heatColor(u: number): string {
  const lo = 0.93, hi = 1.07, mid = 1.0;
  const lerp = (a: number, b: number, t: number) => Math.round(a + (b - a) * t);
  const cl = (x: number) => Math.max(0, Math.min(1, x));
  if (u <= mid) {
    // azul → blanco; t^1.6 mantiene el azul hasta cerca de 1.0 (poco blanco)
    const t = Math.pow(cl((u - lo) / (mid - lo)), 1.6);
    return `rgb(${lerp(46, 240, t)},${lerp(134, 240, t)},${lerp(255, 240, t)})`;
  }
  // blanco → naranja → rojo; t^0.7 sale rápido del blanco
  const t = Math.pow(cl((u - mid) / (hi - mid)), 0.7);
  if (t < 0.5) {
    const k = t / 0.5;
    return `rgb(${lerp(240, 243, k)},${lerp(240, 156, k)},${lerp(240, 18, k)})`;   // blanco→naranja
  }
  const k = (t - 0.5) / 0.5;
  return `rgb(${lerp(243, 231, k)},${lerp(156, 76, k)},${lerp(18, 60, k)})`;        // naranja→rojo
}

// Heatmap de VARIACIÓN (ángulo/velocidad/tensión durante el evento): mínimo → máximo.
// VERDE (poca variación) → AMARILLO → ROJO (mayor variación). Escala de máx a mín como el steady state.
function varColor(t: number): string {
  const lerp = (a: number, b: number, k: number) => Math.round(a + (b - a) * k);
  const cl = (x: number) => Math.max(0, Math.min(1, x));
  t = cl(t);
  if (t < 0.5) {
    const k = t / 0.5;                                     // verde → amarillo
    return `rgb(${lerp(46, 243, k)},${lerp(204, 200, k)},${lerp(113, 18, k)})`;
  }
  const k = (t - 0.5) / 0.5;                               // amarillo → rojo
  return `rgb(${lerp(243, 231, k)},${lerp(200, 76, k)},${lerp(18, 60, k)})`;
}

export interface VariationMap {
  values: Record<string, number>;
  min: number | null;
  max: number | null;
  label?: string;
  unit?: string;
}

export default function GridMap({
  selected,
  onSelect,
  voltages,
  variation,
}: {
  selected: string | null;
  onSelect: (name: string) => void;
  voltages?: Record<string, number> | null;
  variation?: VariationMap | null;
}) {
  const [feats, setFeats] = useState<GridFeature[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getGrid().then((g) => setFeats(g.features)).catch((e) => setErr(String(e)));
  }, []);

  const subs = feats.filter((f) => f.properties.kind === "substation");
  const lines = feats.filter((f) => f.properties.kind === "line");
  const heat = !!voltages && Object.keys(voltages).length > 0;
  const vmap = !heat && !!variation && Object.keys(variation.values || {}).length > 0 ? variation : null;
  const vmin = vmap?.min ?? 0;
  const vspan = vmap && vmap.max != null && vmap.min != null && vmap.max > vmap.min ? vmap.max - vmap.min : 1;

  if (err) return <div className="err">No se pudo cargar el mapa: {err}</div>;

  return (
    <div className="map">
      <MapContainer center={[18.75, -70.25]} zoom={8} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution="&copy; OpenStreetMap"
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        {lines.filter((f) => f.geometry).map((f, i) => {
          const coords = (f.geometry.coordinates as number[][]).map((c) => [c[1], c[0]] as [number, number]);
          const straight = f.properties.straight;   // línea aproximada (recta entre subestaciones)
          return <Polyline key={`l${i}`} positions={coords}
            pathOptions={{ color: straight ? "#3a4f63" : "#33506b", weight: straight ? 1 : 1.2,
                           dashArray: straight ? "4 5" : undefined, opacity: straight ? 0.65 : 1 }} />;
        })}
        {subs.map((f, i) => {
          const [lon, lat] = f.geometry.coordinates as number[];
          const isSel = f.properties.name === selected;
          const u = heat ? voltages![f.properties.name] : undefined;
          const vv = vmap ? vmap.values[f.properties.name] : undefined;
          const color = u != null ? heatColor(u)
            : vv != null ? varColor((vv - vmin) / vspan)
            : levelColor(f.properties.voltages_kv);
          const active = u != null || vv != null;
          const label = f.properties.display_name || f.properties.name;
          return (
            <CircleMarker
              key={`s${i}`}
              center={[lat, lon]}
              radius={isSel ? 9 : active ? 6 : 5}
              pathOptions={{
                color: isSel ? "#fff" : color,
                fillColor: color,
                fillOpacity: active ? 0.95 : 0.85,
                weight: isSel ? 3 : 1,
              }}
              eventHandlers={{ click: () => onSelect(f.properties.name) }}
            >
              <Tooltip>
                {label} · {(f.properties.voltages_kv || []).join("/")} kV
                {u != null && <> · {u.toFixed(3)} pu</>}
                {vv != null && <> · {vv.toFixed(4)} {vmap?.unit || ""}</>}
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
      {heat && (
        <div className="legend">
          <span>0.93</span>
          <i style={{ background: "linear-gradient(90deg,#2e86ff,#f0f0f0 50%,#f39c12 78%,#e74c3c)" }} />
          <span>1.07 pu</span>
        </div>
      )}
      {vmap && (
        <div className="legend">
          <span>{vmap.label || "variación"}: {vmap.min?.toFixed?.(3) ?? vmap.min}</span>
          <i style={{ background: "linear-gradient(90deg,#2ecc71,#f3c812 50%,#e74c3c)" }} />
          <span>{vmap.max?.toFixed?.(3) ?? vmap.max} {vmap.unit || ""}</span>
        </div>
      )}
    </div>
  );
}
