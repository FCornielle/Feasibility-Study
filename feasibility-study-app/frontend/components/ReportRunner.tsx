"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { createRun, getResult, getSubstations, watchRun, RunJob, RunParams, Substation, deriveBess, bessLabel } from "@/lib/api";
import PvInput from "@/components/PvInput";
import ScaleLoadsInput from "@/components/ScaleLoadsInput";
import RunProgress from "@/components/RunProgress";
import ReportView from "@/components/ReportView";
import { HOURS } from "@/lib/tabs";

const GridMap = dynamic(() => import("@/components/GridMap"), { ssr: false });
const DEFAULT_PARAMS: RunParams = { pv_mw: 50, bess_mw: 25, bess_mwh: 100, bess_mode: "discharge", scale_loads: 1 };

export default function ReportRunner() {
  const [subs, setSubs] = useState<Substation[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [params, setParams] = useState<RunParams>(DEFAULT_PARAMS);
  const [scenario, setScenario] = useState<string>("");
  const [job, setJob] = useState<RunJob | null>(null);
  const [result, setResult] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { getSubstations().then(setSubs).catch((e) => setErr(String(e))); }, []);
  const selSub = subs.find((s) => s.name === selected) || null;
  const matches = useMemo(
    () => (query ? subs.filter((s) => s.name.toLowerCase().includes(query.toLowerCase())).slice(0, 8) : []),
    [query, subs]
  );
  const running = job?.status === "queued" || job?.status === "running";

  async function launch() {
    if (!selected) return;
    setErr(null); setResult(null);
    try {
      const created = await createRun({ substation: selected, study: "report", ...params, scenario: scenario || undefined });
      setJob(created);
      const close = watchRun(created.run_id, (j) => {
        setJob(j);
        if (j.status === "done") { getResult(j.run_id).then(setResult).catch(() => {}); close(); }
        if (j.status === "error") close();
      });
    } catch (e) { setErr(String(e)); }
  }

  if (result) return <ReportView result={result} />;

  return (
    <div className="grid2">
      <div>
        <div className="card">
          <h3>Subestación (clic en el mapa o busca)</h3>
          <input placeholder="Buscar subestación…" value={query} onChange={(e) => setQuery(e.target.value)} />
          {matches.length > 0 && (
            <div style={{ marginTop: 6 }}>
              {matches.map((s) => (
                <div key={s.name} className="selected" style={{ cursor: "pointer", marginTop: 4 }}
                     onClick={() => { setSelected(s.name); setQuery(""); }}>
                  {s.name} · {s.voltages_kv.join("/")} kV
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: 10 }}><GridMap selected={selected} onSelect={setSelected} /></div>
        </div>
      </div>

      <div>
        <div className="card">
          <h3>Reporte completo de interconexión</h3>
          <div className="selected">
            {selSub ? <>Subestación: <b>{selSub.name}</b> · {selSub.voltages_kv.join("/")} kV</> : "Selecciona una subestación…"}
          </div>
          <div className="row">
            <PvInput value={params.pv_mw} onChange={(pv) => setParams({ ...params, pv_mw: pv, ...deriveBess(pv, "arbitrage") })} />
            <div><label>BESS (derivado de la PV)</label>
              <input type="text" readOnly value={bessLabel(params.pv_mw, "arbitrage")} title="Arbitraje 50%/4 h; en el estudio de frecuencia se usa el BESS de regulación (5%, 1 h). Sin BESS si < 20 MWn." /></div>
          </div>
          <div className="row">
            <div><label>Hora del día (escenario)</label>
              <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
                <option value="">Auto (escenario activo)</option>
                {HOURS.map((h) => <option key={h.value} value={h.value}>{h.label}</option>)}
              </select></div>
            <div />
          </div>
          <div className="row">
            <ScaleLoadsInput value={params.scale_loads ?? 1} onChange={(v) => setParams({ ...params, scale_loads: v })} />
          </div>
          <button className="run" disabled={!selected || running} onClick={launch}>
            {running ? "Ejecutando todos los estudios…" : "Generar reporte (corre los 5 estudios)"}
          </button>
          <p className="phase" style={{ marginTop: 8 }}>Ejecuta steady + 4 dinámicos (tensión, pequeña señal, transitoria, frecuencia) en serie (~varios minutos).</p>
          {job && <RunProgress job={job} />}
          {err && <div className="err">{err}</div>}
          {job?.status === "error" && <div className="err">Error: {job.error}</div>}
        </div>
      </div>
    </div>
  );
}
