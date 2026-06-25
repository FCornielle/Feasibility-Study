"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { createRun, getResult, getSubstations, watchRun, RunJob, RunParams, Substation } from "@/lib/api";
import ComplianceTable from "@/components/ComplianceTable";
import { SpeedChart } from "@/components/Charts";
import { HOURS } from "@/lib/tabs";

const GridMap = dynamic(() => import("@/components/GridMap"), { ssr: false });
const DEFAULT_PARAMS: RunParams = { pv_mw: 50, bess_mw: 20, bess_mwh: 80, bess_mode: "discharge", scale_loads: 1 };

function CCTTable({ rows }: { rows: any[] }) {
  if (!rows?.length) return null;
  const fmt = (v: number | null, up: number | null) =>
    v == null ? (up ? `< ${up}` : "—") : up && up > v ? `${v}–${up}` : `≥ ${v}`;
  return (
    <table className="compliance">
      <thead>
        <tr><td>Punto de falla</td><td>grado</td>
          <td style={{ textAlign: "right" }}>CCT sin planta [ms]</td>
          <td style={{ textAlign: "right" }}>CCT con planta [ms]</td>
          <td style={{ textAlign: "right" }}>Δ [ms]</td></tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} style={{ fontWeight: r.degree === 0 ? 700 : 400 }}>
            <td>{r.degree === 0 ? "★ " : ""}{r.sub || r.bus} · {r.kv} kV</td>
            <td><span className={r.degree === 1 ? "deg1" : r.degree === 2 ? "deg2" : ""}>{r.degree === 0 ? "PCC" : r.degree + "º"}</span></td>
            <td style={{ textAlign: "right" }}>{fmt(r.cct_sin_ms, r.cct_sin_upper_ms)}</td>
            <td style={{ textAlign: "right" }}>{fmt(r.cct_con_ms, r.cct_con_upper_ms)}</td>
            <td style={{ textAlign: "right", color: r.delta_ms < 0 ? "var(--bad)" : "var(--good)" }}>
              {r.delta_ms != null ? (r.delta_ms >= 0 ? "+" : "") + r.delta_ms : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function TransientStudy() {
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
      const created = await createRun({ substation: selected, study: "transient", ...params, scenario: scenario || undefined });
      setJob(created);
      const close = watchRun(created.run_id, (j) => {
        setJob(j);
        if (j.status === "done") { getResult(j.run_id).then(setResult).catch(() => {}); close(); }
        if (j.status === "error") close();
      });
    } catch (e) { setErr(String(e)); }
  }

  const noData = result && !result.cases?.some((c: any) => c.voltages?.traces?.length)
    && !result.cct_table?.some((r: any) => r.cct_con_ms != null);
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
                       onChange={(e) => setParams({ ...params, scale_loads: +e.target.value })} /></div>
              <div />
            </div>
            <button className="run" disabled={!selected || running} onClick={launch}>
              {running ? "Ejecutando…" : "Ejecutar Transient Stability"}
            </button>
            <p className="phase" style={{ marginTop: 8, color: "var(--warn)" }}>
              ⚠ Estudio pesado: busca el tiempo crítico de despeje (CCT) con varias simulaciones RMS de falla
              franca en el PCC y 2 vecinas, sin y con planta. Tarda <b>varios minutos</b>; el RMS faltado es
              mucho más lento en horas de alta generación — usa una hora nocturna (P20–P05).
            </p>
            {job && running && (<><div className="progress"><div style={{ width: `${job.progress}%` }} /></div><div className="phase">{job.progress}% · {job.phase}</div></>)}
            {err && <div className="err">{err}</div>}
            {job?.status === "error" && <div className="err">Error: {job.error}</div>}
          </div>
        </div>
      </div>

      {result && (
        <>
          {noData && (
            <div className="card" style={{ borderLeft: "4px solid var(--bad)", background: "rgba(231,76,60,0.08)" }}>
              <h3 style={{ color: "var(--bad)", margin: 0 }}>⚠ La simulación no produjo datos</h3>
              <p className="phase" style={{ marginTop: 6 }}>El RMS no convergió en este escenario. Prueba una hora nocturna (P20–P05).</p>
            </div>
          )}

          {/* Tabla de tiempos críticos de despeje (Cuadro 18) */}
          <div className="card">
            <h3>Tiempo crítico de despeje (CCT) — falla trifásica sin impedancia, con / sin planta</h3>
            <ComplianceTable compliance={result.compliance} />
            <div style={{ margin: "10px 0" }}><CCTTable rows={result.cct_table ?? []} /></div>
            <p className="phase">
              Referencia de ángulo: <b>{result.reference_machine}</b> (slack). El CCT es el máximo tiempo de
              despeje sin pérdida de sincronismo (ángulo de rotor relativo &lt; 180°) ni sobrevelocidad &gt; 5 %.
              Valores en pasos gruesos; la planta no debe reducir el CCT.
            </p>
          </div>

          {/* Una sección de gráficos por cada punto de falla, despejado a su CCT (mismo de la tabla) */}
          {(result.cases ?? []).map((c: any, i: number) => (
            <div className="card" key={i}>
              <h3>
                {c.degree === 0 ? "★ " : ""}Falla en {c.sub || c.bus} · {c.kv} kV
                {c.degree === 0 ? " (PCC)" : ` (${c.degree}º grado)`} — despejada en {c.clearing_ms} ms (5 s)
              </h3>
              <div className="grid2">
                <SpeedChart series={c.voltages} title="Tensiones de las barras [pu]" />
                <SpeedChart series={c.angles} title="Ángulo de rotor [pu] (1 pu = 180° vs slack)" />
              </div>
              <div style={{ marginTop: 10 }}>
                <SpeedChart series={c.speeds} title="Velocidad de los generadores [pu]" />
              </div>
            </div>
          ))}
          <p className="phase">
            Cada sección: falla trifásica despejada al CCT de la tabla. Las tensiones se recuperan y los
            ángulos (|pu| &lt; 1) y velocidades se estabilizan → el sincronismo se mantiene. Generadores
            monitoreados (los más distantes de la falla): {(result.monitored_machines ?? []).join(", ")}.
          </p>
        </>
      )}
    </>
  );
}
