"use client";

// Factor de escala de demanda — presentación uniforme en todos los estudios (igual que Steady State).
// Se usa dentro de un <div className="row">. Escala todas las cargas del modelo (menos auxiliares).
export default function ScaleLoadsInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <>
      <div>
        <label>Factor de escala de demanda</label>
        <input type="number" step="0.05" min="0.1" value={value ?? 1} onChange={(e) => onChange(+e.target.value)} />
      </div>
      <div style={{ display: "flex", alignItems: "flex-end" }}>
        <span className="phase">Escala todas las cargas (excepto auxiliares de plantas). 1.0 = sin cambio.</span>
      </div>
    </>
  );
}
