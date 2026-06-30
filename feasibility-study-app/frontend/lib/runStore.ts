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
