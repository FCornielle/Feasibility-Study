"use client";
import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import SteadyState from "@/components/SteadyState";
import { TABS } from "@/lib/tabs";

export default function Page() {
  const [tab, setTab] = useState("steady");
  const current = TABS.find((t) => t.id === tab)!;

  return (
    <div className="app">
      <Sidebar active={tab} onSelect={setTab} />
      <div className="content">
        <div className="topbar">
          <h2>{current.label}</h2>
          <p>
            {current.stub
              ? "Pestaña en construcción"
              : "Flujo de carga + N-1 + cortocircuito · comparación con / sin planta (Código de Conexión)"}
          </p>
        </div>
        <div className="scroll">
          {tab === "steady" ? (
            <SteadyState />
          ) : (
            <div className="stub-msg">🚧 {current.label} — en construcción.</div>
          )}
        </div>
      </div>
    </div>
  );
}
