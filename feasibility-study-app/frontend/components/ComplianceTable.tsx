"use client";

const LABELS: Record<string, string> = {
  no_new_voltage_violation: "Sin nuevas violaciones de tensión",
  no_new_overload: "Sin nuevas sobrecargas",
  no_loading_worsening_over_limit: "No empeora cargabilidad sobre el límite",
  sistema_estable: "Sistema estable (σ < 0 en todos los modos)",
  amortiguamiento_adecuado: "Amortiguamiento del modo crítico ≥ 5%",
  no_reduce_amortiguamiento: "La planta no reduce el amortiguamiento",
  overall: "RESULTADO GENERAL",
};

export default function ComplianceTable({ compliance }: { compliance: Record<string, string> | null }) {
  if (!compliance) return null;
  const keys = Object.keys(compliance).sort((a, b) => (a === "overall" ? 1 : b === "overall" ? -1 : 0));
  return (
    <table className="compliance">
      <tbody>
        {keys.map((k) => (
          <tr key={k}>
            <td style={{ fontWeight: k === "overall" ? 700 : 400 }}>{LABELS[k] ?? k}</td>
            <td style={{ textAlign: "right" }}>
              <span className={`badge ${compliance[k] === "PASA" ? "pasa" : "falla"}`}>{compliance[k]}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
