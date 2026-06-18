"use client";
import { useEffect, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip } from "react-leaflet";
import { getGrid, GridFeature } from "@/lib/api";

// Color por nivel de tensión más alto de la subestación.
function voltColor(kvs: number[] = []): string {
  const kv = Math.max(0, ...kvs);
  if (kv >= 230) return "#e74c3c";
  if (kv >= 138) return "#2e86ff";
  if (kv >= 69) return "#2ecc71";
  return "#8aa0b4";
}

export default function GridMap({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (name: string) => void;
}) {
  const [feats, setFeats] = useState<GridFeature[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getGrid()
      .then((g) => setFeats(g.features))
      .catch((e) => setErr(String(e)));
  }, []);

  const subs = feats.filter((f) => f.properties.kind === "substation");
  const lines = feats.filter((f) => f.properties.kind === "line");

  if (err) return <div className="err">No se pudo cargar el mapa: {err}</div>;

  return (
    <div className="map">
      <MapContainer center={[18.75, -70.25]} zoom={8} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; OpenStreetMap'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        {lines.map((f, i) => {
          const coords = (f.geometry.coordinates as number[][]).map(
            (c) => [c[1], c[0]] as [number, number]
          );
          return <Polyline key={`l${i}`} positions={coords} pathOptions={{ color: "#33506b", weight: 1.2 }} />;
        })}
        {subs.map((f, i) => {
          const [lon, lat] = f.geometry.coordinates as number[];
          const isSel = f.properties.name === selected;
          return (
            <CircleMarker
              key={`s${i}`}
              center={[lat, lon]}
              radius={isSel ? 9 : 5}
              pathOptions={{
                color: isSel ? "#fff" : voltColor(f.properties.voltages_kv),
                fillColor: voltColor(f.properties.voltages_kv),
                fillOpacity: 0.9,
                weight: isSel ? 3 : 1,
              }}
              eventHandlers={{ click: () => onSelect(f.properties.name) }}
            >
              <Tooltip>
                {f.properties.name} · {(f.properties.voltages_kv || []).join("/")} kV
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
