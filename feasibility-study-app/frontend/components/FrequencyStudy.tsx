"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { createRun, getResult, getSubstations, watchRun, RunJob, RunParams, Substation, deriveBess, bessLabel } from "@/lib/api";
import PvInput from "@/components/PvInput";
import ScaleLoadsInput from "@/components/ScaleLoadsInput";
import ComplianceTable from "@/components/ComplianceTable";
import { SpeedChart } from "@/components/Charts";
import RunProgress from "@/components/RunProgress";
import { HOURS } from "@/lib/tabs";
import { getRun, saveRun } from "@/lib/runStore";

const CACHE_KEY = "frequency";
const GridMap = dynamic(() => import("@/components/GridMap"), { ssr: false });
const DEFAULT_PARAMS: RunParams = { pv_mw: 50, bess_mw: 5, bess_mwh: 2.5, bess_mode: "discharge", scale_loads: 1 };

export default function FrequencyStudy() {
  const cached = getRun(CACHE_KEY);
  const [subs, setSubs] = useState<Substation[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(cached.selected ?? null);
  const [params, setParams] = useState<RunParams>(cached.params ?? DEFAULT_PARAMS);
  const [scenario, setScenario] = useState<string>(cached.scenario ?? "");
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
  const matches = useMemo(
    () => (query ? subs.filter((s) => (s.display_name || s.name).toLowerCase().includes(query.toLowerCase())).slice(0, 8) : []),
    [query, subs]
  );
  const running = job?.status === "queued" || job?.status === "running";

  async function launch() {
    if (!selected) return;
    setErr(null); setResult(null);
    try {
      const created = await createRun({ substation: selected, study: "frequency", ...params, scenario: scenario || undefined });
      setJob(created);
      const close = watchRun(created.run_id, (j) => {
        setJob(j);
        if (j.status === "done") { getResult(j.run_id).then(setResult).catch(() => {}); close(); }
        if (j.status === "error") close();
      });
    } catch (e) { setErr(String(e)); }
  }

  const m = result?.metrics;
  // Frecuencia: superponer SIN vs CON en un solo gráfico (mismo largo de simulación => misma base x).
  const freqCompare = result?.frequency ? {
    x_label: "t [s]",
    x: result.frequency.con_planta?.x ?? result.frequency.sin_planta?.x ?? [],
    traces: [
      { name: "SIN planta", y: result.frequency.sin_planta?.traces?.[0]?.y ?? [] },
      { name: "CON planta", y: result.frequency.con_planta?.traces?.[0]?.y ?? [] },
    ],
  } : null;
  const battery = result?.dispatch?.battery_scenario;

  return (
    <>
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
                    {s.display_name || s.name} · {s.voltages_kv.join("/")} kV
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
            <div className="selected">{selSub ? <>Subestación: <b>{selSub.display_name || selSub.name}</b></> : "Selecciona una subestación…"}</div>
            <div className="row">
              <PvInput value={params.pv_mw} onChange={(pv) => setParams({ ...params, pv_mw: pv, ...deriveBess(pv, "frequency") })} />
              <div><label>BESS de regulación de frecuencia</label><input type="text" readOnly value={bessLabel(params.pv_mw, "frequency")} title="5% de la potencia PV (regulación primaria), 1 h de energía; sin BESS si < 20 MWn" /></div>
            </div>
            <div className="row">
              <div><label>Hora del día</label>
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
              {running ? "Ejecutando…" : "Ejecutar Frequency Stability"}
            </button>
            <p className="phase" style={{ marginTop: 8, color: "var(--warn)" }}>
              ⚠ Cálculo RMS (60 s). Se dispara a los 500 ms una unidad de generación de tamaño similar a la
              planta y se compara la frecuencia SIN y CON la planta. Usa <b>horas nocturnas</b> para ver el
              aporte de la batería (regulación de frecuencia).
            </p>
            {job && <RunProgress job={job} />}
            {err && <div className="err">{err}</div>}
            {job?.status === "error" && <div className="err">Error: {job.error}</div>}
          </div>
        </div>
      </div>

      {result && (
        <>
          <div className="card">
            <h3>Estabilidad de frecuencia — disparo de una unidad similar a la planta</h3>
            <ComplianceTable compliance={result.compliance} />
            <div className="kpi" style={{ margin: "10px 0" }}>
              <div className="item"><div className="v">{m?.nadir_sin_hz ?? "—"}</div><div className="l">nadir SIN planta [Hz]</div></div>
              <div className="item"><div className="v">{m?.nadir_con_hz ?? "—"}</div><div className="l">nadir CON planta [Hz]</div></div>
              <div className="item"><div className="v">{m?.edac_first_step_hz ?? "—"}</div><div className="l">1.er escalón EDAC [Hz]</div></div>
              <div className="item"><div className="v">{m?.rocof_con_hz_s ?? "—"}</div><div className="l">RoCoF CON planta [Hz/s]</div></div>
            </div>
            <p className="phase">
              Se dispara (desconecta) a los 500 ms la unidad <b>{result.trip_unit?.name}</b>
              {result.trip_unit?.mw ? ` (~${result.trip_unit.mw} MW, similar a la planta)` : ""} y se observa cómo
              varía la frecuencia y la velocidad de los generadores síncronos, SIN y CON la nueva planta.
              {battery ? " En este escenario nocturno la planta es esencialmente la batería, por lo que la comparación equivale a sin/con batería." : ""}
            </p>
          </div>

          <div className="card">
            <h3>Frecuencia del sistema — SIN vs CON planta</h3>
            <SpeedChart series={freqCompare} title="Frecuencia del sistema" yLabel="f [Hz]" />
            <p className="phase" style={{ marginTop: 8 }}>
              El nadir de frecuencia con la planta debe mantenerse por encima del primer escalón del EDAC
              (59.2 Hz). Si la batería está despachada, ayuda a arrestar el hundimiento (mejor nadir / menor RoCoF).
            </p>
          </div>

          <div className="card">
            <h3>Velocidad de los generadores síncronos</h3>
            <div className="grid2">
              <div>
                <h4 style={{ margin: "0 0 6px", color: "var(--warn)" }}>● SIN planta</h4>
                <SpeedChart series={result.speeds?.sin_planta} title="Velocidad de rotores" yLabel="ω [pu]" />
              </div>
              <div>
                <h4 style={{ margin: "0 0 6px", color: "var(--accent)" }}>✚ CON planta</h4>
                <SpeedChart series={result.speeds?.con_planta} title="Velocidad de rotores" yLabel="ω [pu]" />
              </div>
            </div>
            <p className="phase" style={{ marginTop: 8 }}>
              Frecuencia tomada de la velocidad del mayor generador síncrono ({result.ref_gen}). Generadores
              monitoreados: {(result.monitored_gens ?? []).join(", ")}.
            </p>
          </div>
        </>
      )}
    </>
  );
}
