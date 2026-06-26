"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { createRun, getResult, getSubstations, watchRun, RunJob, RunParams, Substation } from "@/lib/api";
import ComplianceTable from "@/components/ComplianceTable";
import { EigenvalueChart, SpeedChart } from "@/components/Charts";
import RunProgress from "@/components/RunProgress";
import { HOURS } from "@/lib/tabs";

const GridMap = dynamic(() => import("@/components/GridMap"), { ssr: false });
const DEFAULT_PARAMS: RunParams = { pv_mw: 50, bess_mw: 20, bess_mwh: 80, bess_mode: "discharge", scale_loads: 1 };

function ModesTable({ modes }: { modes: any[] }) {
  if (!modes?.length) return <div className="phase">Sin modos electromecánicos extraídos.</div>;
  return (
    <table className="compliance">
      <thead><tr><td>Frec [Hz]</td><td style={{ textAlign: "right" }}>Amortig. [%]</td>
        <td style={{ textAlign: "right" }}>σ [1/s]</td></tr></thead>
      <tbody>
        {modes.slice(0, 10).map((m, i) => (
          <tr key={i}>
            <td>{m.freq_hz}</td>
            <td style={{ textAlign: "right", color: m.damping_pct < 5 ? "var(--warn)" : "var(--text)" }}>{m.damping_pct}</td>
            <td style={{ textAlign: "right", color: m.real < 0 ? "var(--good)" : "var(--bad)" }}>{m.real}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function SmallSignalStudy() {
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
    () => (query ? subs.filter((s) => (s.display_name || s.name).toLowerCase().includes(query.toLowerCase())).slice(0, 8) : []),
    [query, subs]
  );
  const running = job?.status === "queued" || job?.status === "running";

  async function launch() {
    if (!selected) return;
    setErr(null); setResult(null);
    try {
      const created = await createRun({ substation: selected, study: "small-signal", ...params, scenario: scenario || undefined });
      setJob(created);
      const close = watchRun(created.run_id, (j) => {
        setJob(j);
        if (j.status === "done") { getResult(j.run_id).then(setResult).catch(() => {}); close(); }
        if (j.status === "error") close();
      });
    } catch (e) { setErr(String(e)); }
  }

  const di = result?.damping_index;
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
              <div><label>PV (MW)</label><input type="number" value={params.pv_mw} onChange={(e) => setParams({ ...params, pv_mw: +e.target.value })} /></div>
              <div><label>BESS (MW)</label><input type="number" value={params.bess_mw} onChange={(e) => setParams({ ...params, bess_mw: +e.target.value })} /></div>
            </div>
            <div className="row">
              <div><label>BESS (MWh)</label><input type="number" value={params.bess_mwh} onChange={(e) => setParams({ ...params, bess_mwh: +e.target.value })} /></div>
              <div><label>Hora del día</label>
                <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
                  <option value="">Auto (escenario activo)</option>
                  {HOURS.map((h) => <option key={h.value} value={h.value}>{h.label}</option>)}
                </select></div>
            </div>
            <div className="row">
              <div><label>Factor de escala de demanda</label>
                <input type="number" step="0.05" min="0.1" value={params.scale_loads ?? 1}
                       onChange={(e) => setParams({ ...params, scale_loads: +e.target.value })} />
              </div>
              <div style={{ display: "flex", alignItems: "flex-end" }}>
                <span className="phase">Escala todas las cargas (excepto auxiliares de plantas). 1.0 = sin cambio.</span>
              </div>
            </div>
            <button className="run" disabled={!selected || running} onClick={launch}>
              {running ? "Ejecutando…" : "Ejecutar Small Signal"}
            </button>
            <p className="phase" style={{ marginTop: 8, color: "var(--warn)" }}>
              ⚠ Corre 2 simulaciones RMS (sin y con planta). En <b>horas de alta generación solar</b>
              (≈ P09–P17) el RMS es mucho más lento por los inversores (puede tardar varios minutos).
              Para pruebas rápidas usa horas nocturnas (P20–P05).
            </p>
            {job && <RunProgress job={job} />}
            {err && <div className="err">{err}</div>}
            {job?.status === "error" && <div className="err">Error: {job.error}</div>}
          </div>
        </div>
      </div>

      {result && (
        <>
          {!result.modes?.con_planta?.length && !result.speeds?.con_planta?.traces?.length && (
            <div className="card" style={{ borderLeft: "4px solid var(--bad)", background: "rgba(231,76,60,0.08)" }}>
              <h3 style={{ color: "var(--bad)", margin: 0 }}>⚠ La simulación no produjo datos</h3>
              <p className="phase" style={{ marginTop: 6 }}>
                El RMS no convergió o no se monitorearon generadores en este escenario. El veredicto es FALLA por
                ausencia de resultados (no por inestabilidad demostrada). Prueba otra hora (nocturna, P20–P05) o
                verifica que el escenario de operación sea válido.
              </p>
            </div>
          )}
          {/* Sección A: autovalores y amortiguamiento */}
          <div className="card">
            <h3>A) Análisis de autovalores y amortiguamiento</h3>
            <ComplianceTable compliance={result.compliance} />
            <div className="kpi" style={{ margin: "10px 0" }}>
              <div className="item"><div className="v">{di?.sin_planta ?? "—"}%</div><div className="l">amortig. crítico SIN planta</div></div>
              <div className="item"><div className="v">{di?.con_planta ?? "—"}%</div><div className="l">amortig. crítico CON planta</div></div>
              <div className="item"><div className="v">{result.crit_freq?.con_planta ?? "—"} Hz</div><div className="l">frecuencia modo crítico</div></div>
            </div>
            <div className="grid2">
              <EigenvalueChart sin={result.modes?.sin_planta ?? []} con={result.modes?.con_planta ?? []} />
              <div>
                <p className="phase">Modos identificados con planta (multi-señal, ordenados por amortiguamiento):</p>
                <ModesTable modes={result.modes?.con_planta ?? []} />
              </div>
            </div>
            <p className="phase" style={{ marginTop: 8 }}>
              Autovalores λ = σ ± jω extraídos por matrix-pencil de la respuesta a la perturbación. Estable si σ &lt; 0;
              el amortiguamiento no debe disminuir al conectar la planta.
            </p>
          </div>

          {/* Sección B: perturbación pequeña — velocidad de los generadores distantes */}
          <div className="card">
            <h3>B) Perturbación pequeña — velocidad de los generadores más distantes</h3>
            <div className="selected" style={{ marginBottom: 10 }}>Perturbación: {result.perturbation}</div>
            <div className="grid2">
              <div>
                <h4 style={{ margin: "0 0 4px", color: "var(--warn)" }}>● SIN planta</h4>
                <SpeedChart series={result.speeds?.sin_planta} title="Velocidad de rotores" yLabel="ω [pu]" />
              </div>
              <div>
                <h4 style={{ margin: "0 0 4px", color: "var(--accent)" }}>✚ CON planta</h4>
                <SpeedChart series={result.speeds?.con_planta} title="Velocidad de rotores" yLabel="ω [pu]" />
              </div>
            </div>
            <p className="phase" style={{ marginTop: 8 }}>
              Generadores monitoreados (los más distantes del punto de oscilación, que tienden a perder sincronismo):
              {" "}{(result.distant_gens ?? []).join(", ")}.
            </p>
          </div>
        </>
      )}
    </>
  );
}
