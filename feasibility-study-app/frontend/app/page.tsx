"use client";
import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import SteadyState from "@/components/SteadyState";
import DynamicStudy from "@/components/DynamicStudy";
import ReportRunner from "@/components/ReportRunner";
import { DYNAMIC_TABS, TABS } from "@/lib/tabs";

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
          ) : tab === "report" ? (
            <ReportRunner />
          ) : DYNAMIC_TABS.includes(tab) ? (
            <DynamicStudy study={tab} key={tab} />
          ) : tab === "recurso" ? (
            <div className="stub-msg">
              ☀️ <b>Estudio de Recurso</b> — pendiente de definir la fuente de datos del recurso solar
              (irradiancia / estación meteorológica). Es un estudio distinto al de interconexión.
            </div>
          ) : (
            <div className="stub-msg">🚧 {current.label} — en construcción.</div>
          )}
        </div>
      </div>
    </div>
  );
}
