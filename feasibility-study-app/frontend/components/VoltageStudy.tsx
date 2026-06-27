"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { createRun, getResult, getSubstations, watchRun, RunJob, RunParams, Substation } from "@/lib/api";
import ComplianceTable from "@/components/ComplianceTable";
import { SpeedChart } from "@/components/Charts";
import RunProgress from "@/components/RunProgress";
import { HOURS } from "@/lib/tabs";

const GridMap = dynamic(() => import("@/components/GridMap"), { ssr: false });
const DEFAULT_PARAMS: RunParams = { pv_mw: 50, bess_mw: 20, bess_mwh: 80, bess_mode: "discharge", scale_loads: 1 };

function Section({ title, subtitle, data, showReactive }: { title: string; subtitle: string; data: any; showReactive?: boolean }) {
  if (!data) return null;
  const Side = ({ s, label, color }: { s: any; label: string; color: string }) => (
    <div>
      <h4 style={{ margin: "0 0 6px", color }}>{label}</h4>
      <SpeedChart series={s?.voltages} title="Tensión de las barras" yLabel="u [pu]" />
      {showReactive && s?.reactive?.traces?.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <SpeedChart series={s.reactive} title="Potencia reactiva de la planta" yLabel="Q [Mvar]" />
        </div>
      )}
    </div>
  );
  return (
    <div className="card">
      <h3>{title}</h3>
      <p className="phase" style={{ marginTop: -4, marginBottom: 10 }}>{subtitle}</p>
      <div className="grid2">
        <Side s={data.sin} label="● SIN planta" color="var(--warn)" />
        <Side s={data.con} label="✚ CON planta" color="var(--accent)" />
      </div>
    </div>
  );
}

export default function VoltageStudy() {
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
              {running ? "Ejecutando…" : "Ejecutar Voltage Stability"}
            </button>
            <p className="phase" style={{ marginTop: 8, color: "var(--warn)" }}>
              ⚠ Estudio RMS con falla (réplica Sajoma §9.3). Corre rápido (~30 s) en <b>horas nocturnas
              (P20–P05)</b>. En horas de alta generación solar el RMS faltado puede interrumpir el motor; usa
              una hora nocturna.
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

          <Section
            title="9.3.1 — Falla monofásica con re-cierre exitoso"
            subtitle={`Cortocircuito monofásico (fase A) con ${result.fault?.r_fault_ohm ?? 2} Ω de resistencia en el PCC, despejado y re-cerrado a los ${result.fault?.clearing_ms ?? 250} ms. La tensión debe recuperarse en menos de 2 s; con la planta se observa además la entrega de reactivos.`}
            data={result.fault}
            showReactive
          />

          <Section
            title="9.3.2 — Respuesta a una variación de tensión en el PCC"
            subtitle={`Se desconecta el banco de capacitores (${result.cap_mvar ?? "—"} Mvar) en el PCC en t=${result.variation?.open_t ?? 1} s y se reconecta en t=${result.variation?.close_t ?? 2} s. Con la planta se verifica la compensación reactiva ante la variación de tensión.`}
            data={result.variation}
            showReactive
          />

          <p className="phase">
            Ambas pruebas se ejecutan SIN y CON la planta PV+BESS. Que la recuperación de tensión con la planta no
            sea peor que sin ella, y que la planta aporte reactivos durante la falla y la variación, demuestra que
            la nueva generación no degrada la estabilidad de tensión del sistema (criterio del estudio Sajoma §9.3).
          </p>
        </>
      )}
    </>
  );
}
