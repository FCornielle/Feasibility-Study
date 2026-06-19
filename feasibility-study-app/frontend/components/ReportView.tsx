"use client";
import ComplianceTable from "@/components/ComplianceTable";
import { LoadingChart, SeriesChart, VoltageChart } from "@/components/Charts";
import { REPORT_ORDER } from "@/lib/tabs";

function KPIs({ obj }: { obj: Record<string, any> }) {
  if (!obj) return null;
  return (
    <div className="kpi" style={{ marginTop: 10 }}>
      {Object.entries(obj).map(([k, v]) => (
        <div className="item" key={k}><div className="v">{String(v)}</div><div className="l">{k}</div></div>
      ))}
    </div>
  );
}

function StudySection({ label, study }: { label: string; study: any }) {
  if (!study) return null;
  return (
    <section className="report-section card">
      <h3>{label}</h3>
      {study.error ? (
        <div className="err">No se pudo completar: {study.error}</div>
      ) : (
        <>
          <ComplianceTable compliance={study.compliance} />
          {/* KPIs: métricas dinámicas o deltas del estático */}
          {study.metrics && <KPIs obj={study.metrics} />}
          {study.delta && (
            <KPIs obj={{
              "nuevas viol. V": study.delta.new_voltage_violations?.length ?? 0,
              "nuevas sobrecargas": study.delta.new_overloads?.length ?? 0,
              "Δ carga máx %": study.delta.max_loading_increase_pct,
              "Ikss 3φ kA": study.short_circuit_with_plant?.ikss_3ph_ka ?? "—",
            }} />
          )}
          {/* Gráficos */}
          {study.base?.buses && study.with_plant?.buses && (
            <VoltageChart base={study.base.buses} plant={study.with_plant.buses} />
          )}
          {study.with_plant?.branches && <LoadingChart branches={study.with_plant.branches} />}
          {study.series && <SeriesChart series={study.series} />}
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
            <h2 style={{ margin: 0 }}>Estudio de Acceso al SENI</h2>
            <p style={{ color: "var(--muted)", margin: "4px 0" }}>
              Subestación <b>{result.substation}</b>
              {result.pcc && <> · PCC {result.pcc.name} ({result.pcc.kv} kV)</>}
            </p>
            <p style={{ color: "var(--muted)", margin: 0, fontSize: 12 }}>
              PV {p.pv_mw} MW · BESS {p.bess_mw} MW / {p.bess_mwh} MWh ({p.bess_mode})
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <span className={`badge ${result.overall === "PASA" ? "pasa" : "falla"}`} style={{ fontSize: 14 }}>
              {result.overall}
            </span>
            <div><button className="print-btn" onClick={() => window.print()}>Imprimir / PDF</button></div>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Cumplimiento del Código de Conexión — resumen</h3>
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
      </div>

      {REPORT_ORDER.map((k) =>
        result.studies?.[k] ? (
          <StudySection key={k} label={result.labels?.[k] ?? k} study={result.studies[k]} />
        ) : null
      )}
    </div>
  );
}
