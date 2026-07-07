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
import { getRun, saveRun, getCommon, saveCommon } from "@/lib/runStore";

const CACHE_KEY = "transient";

const GridMap = dynamic(() => import("@/components/GridMap"), { ssr: false });
const DEFAULT_PARAMS: RunParams = { pv_mw: 50, bess_mw: 25, bess_mwh: 100, bess_mode: "discharge", scale_loads: 1 };

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
  const cached = getRun(CACHE_KEY);
  const common = getCommon();
  const initPv = common.pv_mw ?? cached.params?.pv_mw ?? DEFAULT_PARAMS.pv_mw;
  const initScale = common.scale_loads ?? cached.params?.scale_loads ?? DEFAULT_PARAMS.scale_loads;
  const [subs, setSubs] = useState<Substation[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(common.selected ?? cached.selected ?? null);
  const [params, setParams] = useState<RunParams>({
    ...(cached.params ?? DEFAULT_PARAMS), pv_mw: initPv, scale_loads: initScale, ...deriveBess(initPv, "arbitrage"),
  });
  const [scenario, setScenario] = useState<string>(common.scenario ?? cached.scenario ?? "");
  const [job, setJob] = useState<RunJob | null>(cached.job ?? null);
  const [result, setResult] = useState<any | null>(cached.result ?? null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { getSubstations().then(setSubs).catch((e) => setErr(String(e))); }, []);
  useEffect(() => { saveRun(CACHE_KEY, { selected, scenario, params, job, result }); },
    [selected, scenario, params, job, result]);
  useEffect(() => { saveCommon({ selected, scenario, pv_mw: params.pv_mw, scale_loads: params.scale_loads }); },
    [selected, scenario, params.pv_mw, params.scale_loads]);
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
      const created = await createRun({ substation: selected, study: "transient", ...params, scenario: scenario || undefined });
      setJob(created);
      const close = watchRun(created.run_id, (j) => {
        setJob(j);
        if (j.status === "done") { getResult(j.run_id).then(setResult).catch(() => {}); close(); }
        if (j.status === "error") close();
      });
    } catch (e) { setErr(String(e)); }
  }

  const noData = result && !result.cases?.some((c: any) => c.con?.voltages?.traces?.length || c.sin?.voltages?.traces?.length)
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
            <div style={{ marginTop: 10 }}><GridMap selected={selected} onSelect={setSelected} variation={result?.substation_variation} /></div>
            {result?.substation_variation?.values && Object.keys(result.substation_variation.values).length > 0 && (
              <p className="phase" style={{ marginTop: 6 }}>
                Mapa: mayor variación del <b>ángulo del rotor</b> durante la falla por subestación (verde = poca, rojo = mucha).
              </p>
            )}
          </div>
        </div>
        <div>
          <div className="card">
            <h3>Planta a interconectar</h3>
            <div className="selected">{selSub ? <>Subestación: <b>{selSub.display_name || selSub.name}</b></> : "Selecciona una subestación…"}</div>
            <div className="row">
              <PvInput value={params.pv_mw} onChange={(pv) => setParams({ ...params, pv_mw: pv, ...deriveBess(pv, "arbitrage") })} />
              <div><label>BESS de arbitraje</label><input type="text" readOnly value={bessLabel(params.pv_mw, "arbitrage")} title="50% de la potencia PV, 4 h de energía (sin BESS si < 20 MWn)" /></div>
            </div>
            <div className="row">
              <div><label>Hora del día</label>
                <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
                  <option value="">Auto (escenario activo)</option>
                  {HOURS.map((h) => <option key={h.value} value={h.value}>{h.label}</option>)}
                </select></div>
            </div>
            <div className="row">
              <ScaleLoadsInput value={params.scale_loads ?? 1} onChange={(v) => setParams({ ...params, scale_loads: v })} />
            </div>
            <button className="run" disabled={!selected || running} onClick={launch}>
              {running ? "Ejecutando…" : "Ejecutar Transient Stability"}
            </button>
            <p className="phase" style={{ marginTop: 8, color: "var(--warn)" }}>
              ⚠ Cálculo RMS pesado (con falla). Corre rápido en <b>horas nocturnas (P20–P05)</b>. En
              horas de alta generación solar (≈ P09–P17) el RMS faltado es muy lento y puede <b>interrumpir el
              motor</b> (el trabajo quedará en error y el worker se reinicia solo). Usa una hora nocturna.
            </p>
            {job && <RunProgress job={job} />}
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

          {result.truncated && (
            <div className="card" style={{ borderLeft: "4px solid var(--warn)", background: "rgba(243,156,18,0.08)" }}>
              <h3 style={{ color: "var(--warn)", margin: 0 }}>⏱ Resultados parciales (acotado por tiempo)</h3>
              <p className="phase" style={{ marginTop: 6 }}>
                En esta hora el RMS faltado es muy lento, así que el estudio se detuvo para no tardar demasiado
                y muestra solo las barras que alcanzó. Para el estudio completo usa una hora nocturna (P20–P05).
              </p>
            </div>
          )}

          {/* Tabla de estabilidad transitoria (Cuadro 18) */}
          <div className="card">
            <h3>Estabilidad transitoria — falla trifásica despejada, con / sin planta</h3>
            <ComplianceTable compliance={result.compliance} />
            <div style={{ margin: "10px 0" }}><CCTTable rows={result.cct_table ?? []} /></div>
            <p className="phase">{result.method}</p>
          </div>

          {/* Corrida BASE sin falla: tensión, frecuencia y velocidad planas (no hay influencia antes de la falla) */}
          {result.baseline && (
            <div className="card">
              <h3>Corrida base — sin falla (60 s): estabilidad del sistema antes de las fallas</h3>
              <div className="grid2">
                <SpeedChart series={result.baseline.voltages} title="Tensión de las barras" yLabel="u [pu]" />
                <SpeedChart series={result.baseline.frequency} title="Frecuencia del sistema" yLabel="f [Hz]" />
              </div>
              <div style={{ marginTop: 10 }}>
                <SpeedChart series={result.baseline.speeds} title="Velocidad de los generadores" yLabel="ω [pu]" />
              </div>
              <p className="phase" style={{ marginTop: 8 }}>
                Tensión, frecuencia y velocidad estables y planas con la planta conectada → el sistema parte de
                un punto de equilibrio antes de simular cada falla.
              </p>
            </div>
          )}

          {/* Una sección por falla: columna SIN planta vs columna CON planta, cada una despejada a su CCT */}
          {(result.cases ?? []).map((c: any, i: number) => {
            const Side = ({ s, label, color }: { s: any; label: string; color: string }) => (
              <div>
                <h4 style={{ margin: "0 0 6px", color }}>
                  {label} — despejada en {s?.clearing_ms ?? "—"} ms{s?.stable === false ? " (pierde sincronismo)" : ""}
                </h4>
                <SpeedChart series={s?.voltages} title="Tensión de las barras" yLabel="u [pu]" />
                <div style={{ marginTop: 8 }}>
                  <SpeedChart series={s?.angles} title="Ángulo de rotor (vs slack Punta Catalina)" yLabel="δ [pu] (1 = 180°)" />
                </div>
                <div style={{ marginTop: 8 }}>
                  <SpeedChart series={s?.speeds} title="Velocidad de los generadores" yLabel="ω [pu]" />
                </div>
                {s?.machines?.length > 0 && (
                  <p className="phase" style={{ marginTop: 6 }}>Máquinas más comprometidas: {s.machines.join(", ")}.</p>
                )}
              </div>
            );
            return (
              <div className="card" key={i}>
                <h3>
                  {c.degree === 0 ? "★ " : ""}Falla en {c.sub || c.bus} · {c.kv} kV
                  {c.degree === 0 ? " (PCC)" : ` (${c.degree}º grado)`} — gráficos a 5 s, despejada en su CCT
                </h3>
                <div className="grid2">
                  <Side s={c.sin} label="● SIN planta" color="var(--warn)" />
                  <Side s={c.con} label="✚ CON planta" color="var(--accent)" />
                </div>
              </div>
            );
          })}
          <p className="phase">
            Cada falla se grafica SIN y CON la planta, y <b>cada columna se despeja en su propio CCT</b> (no a un
            tiempo fijo): el mayor despeje sin que <b>ningún</b> generador síncrono del sistema pierda el paso
            (señal nativa <i>s:outofstep</i> de PowerFactory, evaluada en los {result.n_generators ?? "todos los"}{" "}
            generadores en servicio). Por eso las tensiones se recuperan y no aparecen oscilaciones de una máquina
            fuera de paso. Que el CCT con planta no sea menor que sin planta demuestra que la nueva planta no le
            quita margen al sistema para despejar fallas sin perder el sincronismo.
          </p>
        </>
      )}
    </>
  );
}
