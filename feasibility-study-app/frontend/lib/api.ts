// Cliente del backend FastAPI. En dev, /api se reescribe a http://localhost:8000 (ver next.config).
// El WebSocket se conecta directo al backend (las reescrituras de Next no proxean WS de forma fiable).

export const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE ?? "ws://localhost:8000";

export interface Substation {
  name: string;
  voltages_kv: number[];
  lat: number | null;
  lon: number | null;
  has_gps: boolean;
  coord_source?: string | null;
}

export interface RunParams {
  pv_mw: number;
  bess_mw: number;
  bess_mwh: number;
  bess_mode: "discharge" | "charge";
}

export interface RunJob {
  run_id: string;
  study: string;
  substation: string;
  params: RunParams;
  status: "queued" | "running" | "done" | "error";
  progress: number;
  phase: string;
  result_file: string | null;
  compliance: Record<string, string> | null;
  error: string | null;
}

export interface RunRequest extends RunParams {
  substation: string;
  study?: string;
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export interface GridFeature {
  type: "Feature";
  geometry: { type: "Point" | "LineString"; coordinates: number[] | number[][] };
  properties: { kind: "substation" | "line"; name: string; voltages_kv?: number[]; kv?: number; coord_source?: string };
}
export interface GridGeoJSON {
  type: "FeatureCollection";
  features: GridFeature[];
}

export const getSubstations = () => jget<Substation[]>("/api/substations");
export const getGrid = () => jget<GridGeoJSON>("/api/grid");
export const getRun = (id: string) => jget<RunJob>(`/api/runs/${id}`);
// El resultado completo del estudio (steady_state.json) vive aparte del job.
export const getResult = (id: string) => jget<any>(`/api/runs/${id}/result`);

export async function createRun(req: RunRequest): Promise<RunJob> {
  const r = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ study: "steady_state", ...req }),
  });
  if (!r.ok) throw new Error(`POST /api/runs -> ${r.status}`);
  return r.json();
}

// Suscribe al progreso del run; devuelve una función para cerrar el socket.
export function watchRun(id: string, onUpdate: (job: RunJob) => void): () => void {
  const ws = new WebSocket(`${WS_BASE}/api/ws/runs/${id}`);
  ws.onmessage = (ev) => {
    try {
      onUpdate(JSON.parse(ev.data));
    } catch {
      /* ignora frames no-JSON */
    }
  };
  return () => ws.close();
}
