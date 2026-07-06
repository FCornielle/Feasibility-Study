"use client";
import dynamic from "next/dynamic";
import ComplianceTable from "@/components/ComplianceTable";
import { DualAxisChart, EigenvalueChart, LoadingChart, SeriesChart, SpeedChart, VoltageChart } from "@/components/Charts";
import { REPORT_ORDER } from "@/lib/tabs";

const GridMap = dynamic(() => import("@/components/GridMap"), { ssr: false });

// Nombre por defecto del PDF: se fija en document.title antes de imprimir (el navegador lo usa como
// nombre sugerido al "Guardar como PDF"); se restaura despues.
function printReport(result: any) {
  const p = result.params || {};
  const date = new Date().toISOString().slice(0, 10);
  const bess = p.bess_mw ? `BESS ${p.bess_mw}MW ${p.bess_mwh}MWh` : "sin BESS";
  const prev = document.title;
  document.title = `Reporte de interconexion - ${result.substation} - PV ${p.pv_mw}MWn - ${bess} - ${date}`;
  window.print();
  setTimeout(() => { document.title = prev; }, 1500);
}

function KPIs({ obj }: { obj: Record<string, any> }) {
  if (!obj) return null;
  return (
    <div className="kpi" style={{ marginTop: 10 }}>
      {Object.entries(obj).map(([k, v]) => (
        <div className="item" key={k}><div className="v">{String(v)}</div><div className="l">{k.replace(/_/g, " ")}</div></div>
      ))}
    </div>
  );
}

// Conclusión automática a partir del cumplimiento del estudio.
function conclusion(study: any): { ok: boolean; txt: string } {
  if (study?.error) return { ok: false, txt: `No se pudo completar el estudio: ${study.error}` };
  const c = study?.compliance || {};
  const overall = c.overall;
  const fails = Object.entries(c).filter(([k, v]) => k !== "overall" && v === "FALLA").map(([k]) => k.replace(/_/g, " "));
  if (overall === "PASA") return { ok: true, txt: "Cumple todos los criterios evaluados del Código de Conexión." };
  if (fails.length) return { ok: false, txt: `Observaciones — no cumple: ${fails.join("; ")}.` };
  return { ok: overall === "PASA", txt: overall ? `Resultado: ${overall}.` : "Sin veredicto disponible." };
}

function SinCon({ sin, con, title, yLabel }: { sin: any; con: any; title: string; yLabel: string }) {
  return (
    <div className="grid2">
      <div>
        <h4 style={{ margin: "0 0 4px", color: "var(--warn)" }}>● SIN planta</h4>
        <SpeedChart series={sin} title={title} yLabel={yLabel} />
      </div>
      <div>
        <h4 style={{ margin: "0 0 4px", color: "var(--accent)" }}>✚ CON planta</h4>
        <SpeedChart series={con} title={title} yLabel={yLabel} />
      </div>
    </div>
  );
}

// Gráficos comparativos específicos de cada estudio (los mismos de cada pestaña).
function StudyCharts({ studyKey, study }: { studyKey: string; study: any }) {
  if (studyKey === "steady_state") {
    return (
      <>
        {study.base?.buses && study.with_plant?.buses && <VoltageChart base={study.base.buses} plant={study.with_plant.buses} />}
        {study.with_plant?.branches && <LoadingChart branches={study.with_plant.branches} />}
      </>
    );
  }
  if (studyKey === "voltage") {
    return (
      <>
        {study.fault && (
          <>
            <h4 style={{ marginBottom: 6 }}>Falla monofásica con re-cierre exitoso</h4>
            {(study.fault.detail ?? []).length > 0 && (
              <ul className="phase" style={{ margin: "0 0 8px 18px" }}>
                {study.fault.detail.map((d: string, i: number) => <li key={i}>{d}</li>)}
              </ul>
            )}
            <SinCon sin={study.fault.sin?.voltages} con={study.fault.con?.voltages} title="Tensión de las barras" yLabel="u [pu]" />
            {study.fault.con?.reactive?.traces?.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <SpeedChart series={study.fault.con.reactive} title="Potencia reactiva de la planta (CON)" yLabel="Q [Mvar]" />
              </div>
            )}
          </>
        )}
        {study.variation && (
          <>
            <h4 style={{ margin: "12px 0 6px" }}>Respuesta a una variación de tensión (capacitor)</h4>
            <div className="grid2">
              <div>
                <h4 style={{ margin: "0 0 4px", color: "var(--warn)" }}>● SIN planta</h4>
                <SpeedChart series={study.variation.sin?.voltages} title="Tensión de las barras" yLabel="u [pu]" />
              </div>
              <div>
                <h4 style={{ margin: "0 0 4px", color: "var(--accent)" }}>✚ CON planta</h4>
                <DualAxisChart voltages={study.variation.con?.voltages} reactive={study.variation.con?.reactive} title="Tensión y reactivo de la planta" />
              </div>
            </div>
          </>
        )}
      </>
    );
  }
  if (studyKey === "small-signal") {
    return (
      <>
        {(study.modes?.sin_planta?.length || study.modes?.con_planta?.length) && (
          <EigenvalueChart sin={study.modes?.sin_planta ?? []} con={study.modes?.con_planta ?? []} />
        )}
        <SinCon sin={study.speeds?.sin_planta} con={study.speeds?.con_planta} title="Velocidad de rotores" yLabel="ω [pu]" />
        {study.angles && <SinCon sin={study.angles?.sin_planta} con={study.angles?.con_planta} title="Ángulo de rotores" yLabel="δ [°]" />}
      </>
    );
  }
  if (studyKey === "transient") {
    return (
      <>
        {(study.cct_table?.length ?? 0) > 0 && (
          <table className="compliance" style={{ marginBottom: 10 }}>
            <thead><tr><th>Falla</th><th style={{ textAlign: "right" }}>CCT sin planta [ms]</th><th style={{ textAlign: "right" }}>CCT con planta [ms]</th></tr></thead>
            <tbody>
              {study.cct_table.map((r: any, i: number) => (
                <tr key={i}>
                  <td>{r.label ?? r.bus ?? `Falla ${i + 1}`}</td>
                  <td style={{ textAlign: "right" }}>{r.cct_sin_ms ?? "—"}</td>
                  <td style={{ textAlign: "right" }}>{r.cct_con_ms ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {(study.cases ?? []).map((c: any, i: number) => (
          <div key={i} style={{ marginTop: 8 }}>
            <h4 style={{ marginBottom: 6 }}>{c.sub ?? c.bus} · {c.bus} · {c.kv} kV</h4>
            <SinCon sin={c.sin?.voltages} con={c.con?.voltages} title="Tensión de las barras" yLabel="u [pu]" />
          </div>
        ))}
      </>
    );
  }
  if (studyKey === "frequency") {
    const overlay = study.frequency ? {
      x_label: "t [s]",
      x: study.frequency.con_planta?.x ?? study.frequency.sin_planta?.x ?? [],
      traces: [
        { name: "f SIN planta", y: study.frequency.sin_planta?.traces?.[0]?.y ?? [] },
        { name: "f CON planta", y: study.frequency.con_planta?.traces?.[0]?.y ?? [] },
      ],
    } : null;
    return (
      <>
        {study.trip_unit?.name && (
          <p className="phase" style={{ margin: "0 0 8px" }}>
            Disparo a los 500 ms de la unidad <b>{study.trip_unit.name}</b>
            {study.trip_unit.mw ? ` (~${study.trip_unit.mw} MW, similar a la planta)` : ""}.
          </p>
        )}
        {study.baseline && (
          <div style={{ marginBottom: 8 }}>
            <h4 style={{ margin: "0 0 4px" }}>Régimen (sin eventos)</h4>
            <div className="grid2">
              <div><SpeedChart series={study.baseline.frequency} title="Frecuencia (sin eventos)" yLabel="f [Hz]" /></div>
              <div><SpeedChart series={study.baseline.speeds} title="Velocidad de rotores (sin eventos)" yLabel="ω [pu]" /></div>
            </div>
          </div>
        )}
        {overlay && <SpeedChart series={overlay} title="Frecuencia del sistema — SIN vs CON planta" yLabel="f [Hz]" />}
        {study.speeds && (
          <div style={{ marginTop: 8 }}>
            <SinCon sin={study.speeds?.sin_planta} con={study.speeds?.con_planta} title="Velocidad de rotores" yLabel="ω [pu]" />
          </div>
        )}
      </>
    );
  }
  return study.series ? <SeriesChart series={study.series} /> : null;
}

function StudySection({ studyKey, label, study }: { studyKey: string; label: string; study: any }) {
  if (!study) return null;
  const con = conclusion(study);
  return (
    <section className="report-section card">
      <h3>{label}</h3>
      {study.error ? (
        <div className="err">No se pudo completar: {study.error}</div>
      ) : (
        <>
          <ComplianceTable compliance={study.compliance} />
          {study.metrics && <KPIs obj={study.metrics} />}
          {study.delta && (
            <KPIs obj={{
              "nuevas viol. V": study.delta.new_voltage_violations?.length ?? 0,
              "nuevas sobrecargas": study.delta.new_overloads?.length ?? 0,
              "Δ carga máx %": study.delta.max_loading_increase_pct,
              "Ikss 3φ kA": study.short_circuit_with_plant?.ikss_3ph_ka ?? "—",
            }} />
          )}
          <div style={{ margin: "10px 0" }}>
            <StudyCharts studyKey={studyKey} study={study} />
          </div>
          <p className="phase" style={{ marginTop: 8, borderLeft: `3px solid ${con.ok ? "var(--accent)" : "var(--warn)"}`, paddingLeft: 10 }}>
            <b>Conclusión:</b> {con.txt}
          </p>
        </>
      )}
    </section>
  );
}

export default function ReportView({ result }: { result: any }) {
  const p = result.params || {};
  return (
    <div className="report">
      <div className="report-head card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h2 style={{ margin: 0 }}>Estudio de Interconexión al SENI</h2>
            <p style={{ color: "var(--muted)", margin: "4px 0" }}>
              Subestación <b>{result.substation}</b>
              {result.pcc && <> · PCC {result.pcc.name} ({result.pcc.kv} kV)</>}
            </p>
            <p style={{ color: "var(--muted)", margin: 0, fontSize: 12 }}>
              PV {p.pv_mw} MWn · BESS {p.bess_mw ? `${p.bess_mw} MW / ${p.bess_mwh} MWh` : "no requerido (< 20 MWn)"}
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <span className={`badge ${result.overall === "PASA" ? "pasa" : "falla"}`} style={{ fontSize: 14 }}>
              {result.overall}
            </span>
            <div><button className="print-btn no-print" onClick={() => printReport(result)}>Imprimir / PDF</button></div>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Cumplimiento del Código de Conexión — resumen ejecutivo</h3>
        <table className="compliance">
          <tbody>
            {REPORT_ORDER.filter((k) => result.compliance_summary?.[k]).map((k) => (
              <tr key={k}>
                <td>{result.labels?.[k] ?? k}</td>
                <td style={{ textAlign: "right" }}>
                  <span className={`badge ${result.compliance_summary[k] === "PASA" ? "pasa" : "falla"}`}>
                    {result.compliance_summary[k]}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="phase" style={{ marginTop: 8 }}>
          Veredicto global: <b>{result.overall}</b>. El reporte integra en una sola corrida los estudios de
          comportamiento estático, estabilidad de tensión, pequeña señal, transitoria y de frecuencia, cada uno
          comparando el sistema SIN y CON la nueva planta PV+BESS.
        </p>
      </div>

      <div className="card">
        <h3>Ubicación y red — subestación {result.substation}
          {result.pcc && <> · PCC {result.pcc.name} ({result.pcc.kv} kV)</>}</h3>
        <div style={{ height: 380 }}><GridMap selected={result.substation} onSelect={() => {}} /></div>
      </div>

      {REPORT_ORDER.map((k) =>
        result.studies?.[k] ? (
          <StudySection key={k} studyKey={k} label={result.labels?.[k] ?? k} study={result.studies[k]} />
        ) : null
      )}
    </div>
  );
}
