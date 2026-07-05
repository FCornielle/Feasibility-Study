"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import {
  createRun, getResult, getSubstations, watchRun,
  RunJob, RunParams, Substation, deriveBess, bessLabel,
} from "@/lib/api";
import PvInput from "@/components/PvInput";
import ComplianceTable from "@/components/ComplianceTable";
import { SeriesChart } from "@/components/Charts";
import RunProgress from "@/components/RunProgress";
import { getRun, saveRun } from "@/lib/runStore";

const GridMap = dynamic(() => import("@/components/GridMap"), { ssr: false });
const DEFAULT_PARAMS: RunParams = { pv_mw: 50, bess_mw: 20, bess_mwh: 80, bess_mode: "discharge" };

export default function DynamicStudy({ study }: { study: string }) {
  const cached = getRun(study);
  // El estudio de frecuencia usa el BESS de regulación (10% de la PV); el resto, el de arbitraje (50%, 4 h).
  const bessRole: "arbitrage" | "frequency" = study === "frequency" ? "frequency" : "arbitrage";
  const [subs, setSubs] = useState<Substation[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(cached.selected ?? null);
  const [params, setParams] = useState<RunParams>(cached.params ?? DEFAULT_PARAMS);
  const [job, setJob] = useState<RunJob | null>(cached.job ?? null);
  const [result, setResult] = useState<any | null>(cached.result ?? null);
  const [err, setErr] = useState<string | null>(null);

  // Preserva la última corrida (y selección) por estudio al cambiar de pestaña.
  useEffect(() => { saveRun(study, { selected, params, job, result }); }, [study, selected, params, job, result]);
  useEffect(() => { getSubstations().then(setSubs).catch((e) => setErr(String(e))); }, []);
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
  const matches = useMemo(
    () => (query ? subs.filter((s) => s.name.toLowerCase().includes(query.toLowerCase())).slice(0, 8) : []),
    [query, subs]
  );
  const running = job?.status === "queued" || job?.status === "running";

  async function launch() {
    if (!selected) return;
    setErr(null); setResult(null);
    try {
      const created = await createRun({ substation: selected, study, ...params });
      setJob(created);
      const close = watchRun(created.run_id, (j) => {
        setJob(j);
        if (j.status === "done") { getResult(j.run_id).then(setResult).catch(() => {}); close(); }
        if (j.status === "error") close();
      });
    } catch (e) { setErr(String(e)); }
  }

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
          <h3>Planta a interconectar</h3>
          <div className="selected">
            {selSub ? <>Subestación: <b>{selSub.name}</b> · {selSub.voltages_kv.join("/")} kV</> : "Selecciona una subestación…"}
          </div>
          <div className="row">
            <PvInput value={params.pv_mw} onChange={(pv) => setParams({ ...params, pv_mw: pv, ...deriveBess(pv, bessRole) })} />
            <div><label>{bessRole === "frequency" ? "BESS de frecuencia" : "BESS de arbitraje"}</label>
              <input type="text" readOnly value={bessLabel(params.pv_mw, bessRole)} title={bessRole === "frequency" ? "10% de la PV (regulación primaria + secundaria)" : "50% de la potencia PV, 4 h de energía (sin BESS si < 20 MWn)"} /></div>
          </div>
          <div className="row">
            <div><label>Modo BESS</label>
              <select value={params.bess_mode} onChange={(e) => setParams({ ...params, bess_mode: e.target.value as RunParams["bess_mode"] })}>
                <option value="discharge">Descarga (punta)</option>
                <option value="charge">Carga (mediodía)</option>
              </select></div>
          </div>
          <button className="run" disabled={!selected || running} onClick={launch}>
            {running ? "Ejecutando…" : "Ejecutar estudio"}
          </button>
          {job && <RunProgress job={job} />}
          {err && <div className="err">{err}</div>}
          {job?.status === "error" && <div className="err">Error: {job.error}</div>}
        </div>

        {result && (
          <>
            <div className="card">
              <h3>Cumplimiento</h3>
              <ComplianceTable compliance={result.compliance} />
              <div className="kpi" style={{ marginTop: 12 }}>
                {result.pcc && <div className="item"><div className="v">{result.pcc.kv} kV</div><div className="l">PCC {result.pcc.name}</div></div>}
                {Object.entries(result.metrics || {}).map(([k, v]) => (
                  <div className="item" key={k}><div className="v">{String(v)}</div><div className="l">{k}</div></div>
                ))}
              </div>
            </div>
            {result.series && (
              <div className="card"><h3>Serie</h3><SeriesChart series={result.series} /></div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
