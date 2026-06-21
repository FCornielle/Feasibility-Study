"use client";
import { LoadingChart } from "@/components/Charts";

export function SystemPanel({ base, plant }: { base: any; plant: any }) {
  if (!plant?.system) return null;
  const b = base?.system, p = plant.system;
  const Item = ({ l, v, u, d }: { l: string; v: number; u: string; d?: number }) => (
    <div className="item">
      <div className="v">{v} <small style={{ fontSize: 11, color: "var(--muted)" }}>{u}</small></div>
      <div className="l">{l}{d != null && Math.abs(d) >= 0.05 ? ` (Δ ${d > 0 ? "+" : ""}${d.toFixed(1)})` : ""}</div>
    </div>
  );
  return (
    <div className="card">
      <h3>Balance del sistema (flujo con planta)</h3>
      <div className="kpi">
        <Item l="Demanda" v={p.demand_mw} u="MW" />
        <Item l="Generación" v={p.generation_mw} u="MW" d={b ? p.generation_mw - b.generation_mw : undefined} />
        <Item l="Pérdidas" v={p.losses_mw} u="MW" d={b ? p.losses_mw - b.losses_mw : undefined} />
        <Item l="Q demanda" v={p.demand_mvar} u="Mvar" />
        <Item l="Q generación" v={p.generation_mvar} u="Mvar" d={b ? p.generation_mvar - b.generation_mvar : undefined} />
      </div>
      <p className="phase" style={{ marginTop: 10 }}>
        Metodología: flujo de carga IEC, comparación <b>con vs sin planta</b> (veredicto por delta),
        confiabilidad <b>N-1</b> en circuitos de evacuación y <b>cortocircuito</b> (IEC 60909) en el PCC.
      </p>
    </div>
  );
}

export function DispatchPanel({ dispatch }: { dispatch: any }) {
  if (!dispatch?.technologies?.length) return null;
  return (
    <div className="card">
      <h3>Despacho por tecnología — {dispatch.total_p_mw} MW / {dispatch.total_q_mvar} Mvar</h3>
      {dispatch.technologies.map((t: any) => (
        <details key={t.tech} className="disp">
          <summary>
            <span>{t.tech}</span>
            <span className="muted">{t.p_mw} MW · {t.q_mvar} Mvar · {t.units.length} u.</span>
          </summary>
          <table className="compliance">
            <tbody>
              {t.units.map((u: any) => (
                <tr key={u.name}>
                  <td>{u.name}</td>
                  <td style={{ textAlign: "right" }}>{u.p_mw} MW</td>
                  <td style={{ textAlign: "right", color: "var(--muted)" }}>{u.q_mvar} Mvar</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ))}
    </div>
  );
}

export function ContingencyTable({ contingency, branches }: { contingency: any; branches?: any[] }) {
  if (!contingency?.lines?.length) return null;
  const { lines, contingencies, matrix, base_loading, worst_loading_pct } = contingency;
  return (
    <div className="card">
      <h3>Análisis de Contingencia (N-1) — peor carga {worst_loading_pct}%</h3>
      {branches && branches.length > 0 && <LoadingChart branches={branches} />}
      <div className="ctab-wrap">
        <table className="ctab">
          <thead>
            <tr>
              <th className="lname">Circuito influenciado</th>
              <th title="Carga sin contingencia">N</th>
              {contingencies.map((c: string, j: number) => (
                <th key={j} title={c}>F{j + 1}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.map((l: any, i: number) => (
              <tr key={i}>
                <td className="lname" title={l.name}>
                  <span className={l.degree === 1 ? "deg1" : "deg2"}>{l.degree === 1 ? "●" : "○"}</span> {l.name}
                </td>
                <td>{base_loading[i]}</td>
                {matrix[i].map((v: number | null, j: number) => (
                  <td key={j} className={v != null && v > 100 ? "over" : ""}>{v == null ? "·" : v}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="phase" style={{ marginTop: 8 }}>
        Columnas <b>F1…F{contingencies.length}</b> = falla de cada circuito · <b>N</b> = sin contingencia ·
        celdas en % de cargabilidad (<span style={{ color: "var(--bad)" }}>rojo</span> &gt; 100%).
        <span className="deg1"> ●</span> 1.er grado · <span className="deg2">○</span> 2.º grado.
      </p>
      <div className="cleg">
        {contingencies.map((c: string, j: number) => (
          <span key={j}><b>F{j + 1}</b>: {c} &nbsp;</span>
        ))}
      </div>
    </div>
  );
}

export function NeighborTable({ rows }: { rows: any[] }) {
  if (!rows?.length) return null;
  return (
    <table className="compliance">
      <thead>
        <tr><td>Barra</td><td style={{ textAlign: "right" }}>sin planta</td>
          <td style={{ textAlign: "right" }}>con planta</td><td style={{ textAlign: "right" }}>Δ pu</td></tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const d = r.v_base != null && r.v_plant != null ? r.v_plant - r.v_base : null;
          return (
            <tr key={i} style={{ fontWeight: r.is_pcc ? 700 : 400 }}>
              <td>{r.is_pcc ? "★ " : ""}{r.sub ?? ""} {r.bus}</td>
              <td style={{ textAlign: "right" }}>{r.v_base ?? "—"}</td>
              <td style={{ textAlign: "right" }}>{r.v_plant ?? "—"}</td>
              <td style={{ textAlign: "right", color: d && d > 0 ? "var(--good)" : "var(--muted)" }}>
                {d != null ? (d > 0 ? "+" : "") + d.toFixed(4) : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
