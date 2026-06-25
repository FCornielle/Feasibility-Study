"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { createRun, getResult, getSubstations, watchRun, RunJob, RunParams, Substation } from "@/lib/api";
import RunProgress from "@/components/RunProgress";
import ReportView from "@/components/ReportView";

const GridMap = dynamic(() => import("@/components/GridMap"), { ssr: false });
const DEFAULT_PARAMS: RunParams = { pv_mw: 50, bess_mw: 20, bess_mwh: 80, bess_mode: "discharge" };

export default function ReportRunner() {
  const [subs, setSubs] = useState<Substation[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [params, setParams] = useState<RunParams>(DEFAULT_PARAMS);
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
      const created = await createRun({ substation: selected, study: "report", ...params });
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
            <div><label>PV (MW)</label><input type="number" value={params.pv_mw} onChange={(e) => setParams({ ...params, pv_mw: +e.target.value })} /></div>
            <div><label>BESS (MW)</label><input type="number" value={params.bess_mw} onChange={(e) => setParams({ ...params, bess_mw: +e.target.value })} /></div>
          </div>
          <div className="row">
            <div><label>BESS (MWh)</label><input type="number" value={params.bess_mwh} onChange={(e) => setParams({ ...params, bess_mwh: +e.target.value })} /></div>
            <div><label>Modo BESS</label>
              <select value={params.bess_mode} onChange={(e) => setParams({ ...params, bess_mode: e.target.value as RunParams["bess_mode"] })}>
                <option value="discharge">Descarga (punta)</option>
                <option value="charge">Carga (mediodía)</option>
              </select></div>
          </div>
          <button className="run" disabled={!selected || running} onClick={launch}>
            {running ? "Ejecutando todos los estudios…" : "Generar reporte (corre los 6 estudios)"}
          </button>
          <p className="phase" style={{ marginTop: 8 }}>Ejecuta steady + 4 dinámicos + quasi en serie (~varios minutos).</p>
          {job && <RunProgress job={job} />}
          {err && <div className="err">{err}</div>}
          {job?.status === "error" && <div className="err">Error: {job.error}</div>}
        </div>
      </div>
    </div>
  );
}
