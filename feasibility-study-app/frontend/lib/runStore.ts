// Cache en memoria de la última corrida por pestaña, para que NO se pierda al cambiar de pestaña.
// Persiste mientras la app esté cargada (no sobrevive un refresh completo del navegador).
export interface RunCache {
  selected?: string | null;
  scenario?: string;
  params?: any;
  job?: any;
  result?: any;
}

const store: Record<string, RunCache> = {};

export const getRun = (key: string): RunCache => store[key] ?? {};
export const saveRun = (key: string, v: RunCache): void => { store[key] = { ...store[key], ...v }; };

// Parámetros COMPARTIDOS entre pestañas: la subestación, la potencia PV, la hora/escenario y el factor
// de escala asignados en cualquier pestaña se usan como valores por defecto en las demás (ítem 4). El
// BESS lo deriva cada pestaña de la PV según su rol (arbitraje / frecuencia).
export interface CommonParams {
  selected?: string | null;
  scenario?: string;
  pv_mw?: number;
  scale_loads?: number;
}

let common: CommonParams = {};
export const getCommon = (): CommonParams => ({ ...common });
export const saveCommon = (v: CommonParams): void => {
  common = { ...common, ...v };
};

// Cronómetro por corrida (persiste al cambiar de pestaña, para que el conteo NO se reinicie al volver).
const runTimes: Record<string, { t0: number; t1: number | null }> = {};
export const runStart = (id: string): number => {
  if (!runTimes[id]) runTimes[id] = { t0: Date.now(), t1: null };
  return runTimes[id].t0;
};
export const runEnd = (id: string, ended: boolean): number | null => {
  const r = runTimes[id] ?? (runTimes[id] = { t0: Date.now(), t1: null });
  if (ended && r.t1 == null) r.t1 = Date.now();
  return r.t1;
};
