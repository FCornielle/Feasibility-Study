"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { createRun, getResult, getSubstations, watchRun, RunJob, RunParams, Substation, deriveBess, bessLabel } from "@/lib/api";
import PvInput from "@/components/PvInput";
import ScaleLoadsInput from "@/components/ScaleLoadsInput";
import ComplianceTable from "@/components/ComplianceTable";
import { SpeedChart, DualAxisChart } from "@/components/Charts";
import RunProgress from "@/components/RunProgress";
import { HOURS } from "@/lib/tabs";
import { getRun, saveRun, getCommon, saveCommon } from "@/lib/runStore";

const CACHE_KEY = "voltage";

const GridMap = dynamic(() => import("@/components/GridMap"), { ssr: false });
const DEFAULT_PARAMS: RunParams = { pv_mw: 50, bess_mw: 25, bess_mwh: 100, bess_mode: "discharge", scale_loads: 1 };

export default function VoltageStudy() {
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
  // Preserva la última corrida (y la selección) al cambiar de pestaña.
  useEffect(() => { saveRun(CACHE_KEY, { selected, scenario, params, job, result }); },
    [selected, scenario, params, job, result]);
  // Comparte PV / hora / escala / subestación con las demás pestañas (ítem 4).
  useEffect(() => { saveCommon({ selected, scenario, pv_mw: params.pv_mw, scale_loads: params.scale_loads }); },
    [selected, scenario, params.pv_mw, params.scale_loads]);
  // Si al volver hay una corrida en curso, re-engancha el watcher para que termine de actualizar.
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
      const created = await createRun({ substation: selected, study: "voltage", ...params, scenario: scenario || undefined });
      setJob(created);
      const close = watchRun(created.run_id, (j) => {
        setJob(j);
        if (j.status === "done") { getResult(j.run_id).then(setResult).catch(() => {}); close(); }
        if (j.status === "error") close();
      });
    } catch (e) { setErr(String(e)); }
  }

  const m = result?.metrics;
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
                Mapa: mayor variación de la <b>tensión</b> durante la falla por subestación (verde = poca, rojo = mucha).
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
              {running ? "Ejecutando…" : "Ejecutar Voltage Stability"}
            </button>
            <p className="phase" style={{ marginTop: 8, color: "var(--warn)" }}>
              ⚠ Cálculo RMS con falla. Corre rápido en <b>horas nocturnas (P20–P05)</b>. En horas de
              alta generación solar el RMS faltado puede interrumpir el motor; usa una hora nocturna.
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
            <h3>Estabilidad de tensión — recuperación ante falla y respuesta a variaciones</h3>
            <ComplianceTable compliance={result.compliance} />
            <div className="kpi" style={{ margin: "10px 0" }}>
              <div className="item"><div className="v">{m?.v_recup_sin_pu ?? "—"}</div><div className="l">V recuperada SIN planta [pu]</div></div>
              <div className="item"><div className="v">{m?.v_recup_con_pu ?? "—"}</div><div className="l">V recuperada CON planta [pu]</div></div>
              <div className="item"><div className="v">{m?.cap_mvar ?? "—"}</div><div className="l">capacitor maniobrado [Mvar]</div></div>
              {result.pcc && <div className="item"><div className="v">{result.pcc.kv} kV</div><div className="l">PCC {result.pcc.name}</div></div>}
            </div>
            <p className="phase">{result.method}</p>
          </div>

          <div className="card">
            <h3>Falla monofásica con re-cierre exitoso</h3>
            <p className="phase" style={{ marginTop: -4 }}>La falla simulada tiene en cuenta:</p>
            <ul className="phase" style={{ margin: "2px 0 10px 18px" }}>
              {(result.fault?.detail ?? []).map((d: string, i: number) => <li key={i}>{d}</li>)}
            </ul>
            <p className="phase" style={{ marginBottom: 10 }}>
              La tensión debe recuperarse en menos de 2 s; con la planta se observa además la entrega de reactivos.
            </p>
            <div className="grid2">
              <div>
                <h4 style={{ margin: "0 0 6px", color: "var(--warn)" }}>● SIN planta</h4>
                <SpeedChart series={result.fault?.sin?.voltages} title="Tensión de las barras" yLabel="u [pu]" />
              </div>
              <div>
                <h4 style={{ margin: "0 0 6px", color: "var(--accent)" }}>✚ CON planta</h4>
                <SpeedChart series={result.fault?.con?.voltages} title="Tensión de las barras" yLabel="u [pu]" />
                {result.fault?.con?.reactive?.traces?.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <SpeedChart series={result.fault.con.reactive} title="Potencia reactiva de la planta" yLabel="Q [Mvar]" />
                  </div>
                )}
                {result.fault?.con?.active?.traces?.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <SpeedChart series={result.fault.con.active} title="Potencia activa de la planta" yLabel="P [MW]" />
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="card">
            <h3>Respuesta a una variación de tensión en el PCC</h3>
            <p className="phase" style={{ marginTop: -4, marginBottom: 10 }}>
              Se desconecta el banco de capacitores ({result.cap_mvar ?? "—"} Mvar) en el PCC en
              t={result.variation?.open_t ?? 1} s y se reconecta en t={result.variation?.close_t ?? 2} s. Con la
              planta se verifica la compensación reactiva ante la variación de tensión (tensión de la barra y
              reactivo de la planta en un gráfico de doble eje).
            </p>
            <div className="grid2">
              <div>
                <h4 style={{ margin: "0 0 6px", color: "var(--warn)" }}>● SIN planta</h4>
                <SpeedChart series={result.variation?.sin?.voltages} title="Tensión de las barras" yLabel="u [pu]" />
              </div>
              <div>
                <h4 style={{ margin: "0 0 6px", color: "var(--accent)" }}>✚ CON planta</h4>
                <DualAxisChart
                  voltages={result.variation?.con?.voltages}
                  reactive={result.variation?.con?.reactive}
                  title="Tensión de las barras y reactivo de la planta"
                />
              </div>
            </div>
          </div>

          <p className="phase">
            Ambas pruebas se ejecutan SIN y CON la planta PV+BESS. El despacho de la planta sigue la hora del
            escenario: el PV solo aporta reactivo cuando hay sol y el BESS solo cuando descarga (mientras carga no
            aporta). Que la recuperación de tensión con la planta no sea peor que sin ella, y que la planta aporte
            reactivos cuando está despachada, demuestra que la nueva generación no degrada la estabilidad de tensión.
            {result.dispatch?.reactive_sources?.length ? ` Aportan reactivo en este escenario: ${result.dispatch.reactive_sources.join(", ")}.` : " En este escenario la planta no está despachada (no aporta reactivo)."}
          </p>
        </>
      )}
    </>
  );
}
