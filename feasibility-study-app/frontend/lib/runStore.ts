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
