"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import {
  createRun, getResult, getSubstations, watchRun,
  RunJob, RunParams, Substation, deriveBess, bessLabel,
} from "@/lib/api";
import PvInput from "@/components/PvInput";
import ComplianceTable from "@/components/ComplianceTable";
import { VoltageRadar } from "@/components/Charts";
import RunProgress from "@/components/RunProgress";
import { ContingencyTable, DispatchPanel, NeighborTable, ShortCircuitSection, SystemPanel } from "@/components/SteadyPanels";
import { getRun, saveRun } from "@/lib/runStore";

const CACHE_KEY = "steady";
const GridMap = dynamic(() => import("@/components/GridMap"), { ssr: false });

const DEFAULT_PARAMS: RunParams = { pv_mw: 50, bess_mw: 25, bess_mwh: 100, bess_mode: "discharge", scale_loads: 1 };
const HOURS = Array.from({ length: 24 }, (_, i) => {
  const n = String(i + 1).padStart(2, "0");
  return { value: `P${n}`, label: `P${n} — ${n}:00` };
});

export default function SteadyState() {
  const cached = getRun(CACHE_KEY);
  const [subs, setSubs] = useState<Substation[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(cached.selected ?? null);
  const [params, setParams] = useState<RunParams>(cached.params ?? DEFAULT_PARAMS);
  const [scenario, setScenario] = useState<string>(cached.scenario ?? ""); // "" = escenario activo
  const [job, setJob] = useState<RunJob | null>(cached.job ?? null);
  const [result, setResult] = useState<any | null>(cached.result ?? null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { getSubstations().then(setSubs).catch((e) => setErr(String(e))); }, []);
  useEffect(() => { saveRun(CACHE_KEY, { selected, scenario, params, job, result }); },
    [selected, scenario, params, job, result]);
  useEffect(() => {
    if (job && (job.status === "queued" || job.status === "running")) {
      const close = watchRun(job.run_id, (j) => {
        setJob(j);
        if (j.status === "done") { getResult(j.run_id).then(setResult).catch(() => {}); close(); }
        if (j.status === "error") close();
      });
      return close;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selSub = subs.find((s) => s.name === selected) || null;
  const subNames = useMemo(
    () => Object.fromEntries(subs.map((s) => [s.name, s.display_name || s.name])),
    [subs]
  );
  const matches = useMemo(
    () => (query
      ? subs.filter((s) => (s.display_name || s.name).toLowerCase().includes(query.toLowerCase())
          || s.name.toLowerCase().includes(query.toLowerCase())).slice(0, 8)
      : []),
    [query, subs]
  );
  const running = job?.status === "queued" || job?.status === "running";

  async function launch() {
    if (!selected) return;
    setErr(null); setResult(null);
    try {
      const created = await createRun({ substation: selected, ...params, scenario: scenario || undefined });
      setJob(created);
      const close = watchRun(created.run_id, (j) => {
        setJob(j);
        if (j.status === "done") { getResult(j.run_id).then(setResult).catch(() => {}); close(); }
        if (j.status === "error") close();
      });
    } catch (e) { setErr(String(e)); }
  }

  return (
    <>
      <div className="grid2">
        {/* Izquierda: mapa + balance */}
        <div>
          <div className="card">
            <h3>Subestación (clic en el mapa o busca)</h3>
            <input placeholder="Buscar subestación…" value={query} onChange={(e) => setQuery(e.target.value)} />
            {matches.length > 0 && (
              <div style={{ marginTop: 6 }}>
                {matches.map((s) => (
                  <div key={s.name} className="selected" style={{ cursor: "pointer", marginTop: 4 }}
                       onClick={() => { setSelected(s.name); setQuery(""); }}>
                    {s.display_name || s.name} · {s.voltages_kv.join("/")} kV
                  </div>
                ))}
              </div>
            )}
            <div style={{ marginTop: 10 }}>
              <GridMap selected={selected} onSelect={setSelected} voltages={result?.substation_voltages} />
            </div>
          </div>
          {result && <SystemPanel base={result.base} plant={result.with_plant}
            scenario={result.scenario} plantDispatch={result.plant_dispatch} />}
        </div>

        {/* Derecha: parámetros, ejecución, despacho */}
        <div>
          <div className="card">
            <h3>Planta a interconectar</h3>
            {selSub ? (
              <div className="selected">Subestación: <b>{selSub.display_name || selSub.name}</b> · {selSub.voltages_kv.join("/")} kV</div>
            ) : (
              <div className="selected">Selecciona una subestación…</div>
            )}
            <div className="row">
              <PvInput value={params.pv_mw} onChange={(pv) => setParams({ ...params, pv_mw: pv, ...deriveBess(pv, "arbitrage") })} />
              <div><label>BESS de arbitraje</label>
                <input type="text" readOnly value={bessLabel(params.pv_mw, "arbitrage")} title="50% de la potencia PV, 4 h de energía (sin BESS si < 20 MWn)" /></div>
            </div>
            <div className="row">
              <div><label>Hora del día (escenario)</label>
                <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
                  <option value="">Auto (escenario activo)</option>
                  {HOURS.map((h) => <option key={h.value} value={h.value}>{h.label}</option>)}
                </select></div>
            </div>
            <div className="row">
              <div><label>Factor de escala de demanda</label>
                <input type="number" step="0.05" min="0.1" value={params.scale_loads ?? 1}
                       onChange={(e) => setParams({ ...params, scale_loads: +e.target.value })} /></div>
              <div style={{ display: "flex", alignItems: "flex-end" }}>
                <span className="phase">Escala todas las cargas (excepto auxiliares de plantas). 1.0 = sin cambio.</span>
              </div>
            </div>
            <button className="run" disabled={!selected || running} onClick={launch}>
              {running ? "Ejecutando…" : "Ejecutar Steady State"}
            </button>
            {job && <RunProgress job={job} />}
            {err && <div className="err">{err}</div>}
            {job?.status === "error" && <div className="err">Error: {job.error}</div>}
          </div>
          {result && <DispatchPanel dispatch={result.dispatch} />}
        </div>
      </div>

      {/* Resultados a ancho completo (la matriz de contingencia necesita espacio) */}
      {result && (
        <>
          <div className="card">
            <h3>Cumplimiento (Código de Conexión)</h3>
            <ComplianceTable compliance={result.compliance} />
            <div className="kpi" style={{ marginTop: 12 }}>
              <div className="item"><div className="v">{result.pcc?.kv} kV</div><div className="l">PCC {result.pcc?.name}</div></div>
              <div className="item"><div className="v">{result.short_circuit_with_plant?.ikss_3ph_ka ?? "—"} kA</div><div className="l">Ikss 3φ</div></div>
              <div className="item"><div className="v">{result.delta?.new_voltage_violations?.length ?? 0}</div><div className="l">nuevas viol. V</div></div>
              <div className="item"><div className="v">{result.delta?.new_overloads?.length ?? 0}</div><div className="l">nuevas sobrecargas</div></div>
              <div className="item"><div className="v">{result.delta?.max_loading_increase_pct}%</div><div className="l">Δ carga máx</div></div>
            </div>
          </div>
          {result.pcc_neighbors?.length > 0 && (
            <div className="card">
              <h3>Barras vecinas al PCC — tensión antes / después</h3>
              <div className="grid2">
                <NeighborTable rows={result.pcc_neighbors} />
                <VoltageRadar neighbors={result.pcc_neighbors} subNames={subNames} />
              </div>
            </div>
          )}
          {result.short_circuit?.length > 0 && (
            <ShortCircuitSection rows={result.short_circuit} subNames={subNames} />
          )}
          {result.contingency && <ContingencyTable contingency={result.contingency} />}
        </>
      )}
    </>
  );
}
