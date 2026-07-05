"use client";
import { useEffect, useState } from "react";
import { PV_MAX_MW } from "@/lib/api";

// Entrada de potencia de la planta PV: libre escritura, pero solo número entero con hasta 2 decimales.
// Si se ingresan letras/símbolos o se supera el máximo (200 MWn) se muestra un mensaje de error y NO se
// propaga el valor (params conserva el último válido). Acepta, p.ej., "50", "49.5", "120.75".
export default function PvInput({ value, onChange }: { value: number; onChange: (mw: number) => void }) {
  const [text, setText] = useState(String(value ?? ""));
  const [error, setError] = useState<string | null>(null);

  // Sincroniza el texto si el valor cambia por fuera (p.ej. al recuperar la caché), sin pisar lo tecleado.
  useEffect(() => {
    setText((prev) => (parseFloat(prev) === value ? prev : String(value ?? "")));
  }, [value]);

  function handle(raw: string) {
    setText(raw);
    const s = raw.trim();
    if (s === "") { setError("Ingresa la potencia de la planta (MWn)."); return; }
    if (!/^\d+(\.\d{1,2})?$/.test(s)) {
      setError("Solo números: entero y hasta 2 decimales (sin letras ni símbolos).");
      return;
    }
    const n = parseFloat(s);
    if (n > PV_MAX_MW) { setError(`Máximo ${PV_MAX_MW} MWn.`); return; }
    if (n <= 0) { setError("La potencia debe ser mayor que 0."); return; }
    setError(null);
    onChange(n);
  }

  return (
    <div>
      <label>PV (MWn)</label>
      <input
        type="text"
        inputMode="decimal"
        value={text}
        onChange={(e) => handle(e.target.value)}
        aria-invalid={!!error}
        style={error ? { borderColor: "#d33" } : undefined}
      />
      {error && <div style={{ color: "#d33", fontSize: "0.78em", marginTop: 3 }}>{error}</div>}
    </div>
  );
}
