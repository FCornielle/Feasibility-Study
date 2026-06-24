"use client";
import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import SteadyState from "@/components/SteadyState";
import DynamicStudy from "@/components/DynamicStudy";
import SmallSignalStudy from "@/components/SmallSignalStudy";
import TransientStudy from "@/components/TransientStudy";
import ReportRunner from "@/components/ReportRunner";
import { DYNAMIC_TABS, TABS } from "@/lib/tabs";

export default function Page() {
  const [tab, setTab] = useState("steady");
  const [navOpen, setNavOpen] = useState(true);
  const current = TABS.find((t) => t.id === tab)!;

  return (
    <div className={`app ${navOpen ? "" : "nav-collapsed"}`}>
      <Sidebar active={tab} onSelect={(id) => setTab(id)} />
      <div className="content">
        <div className="topbar">
          <div className="topbar-row">
            <button className="nav-toggle" onClick={() => setNavOpen((o) => !o)} title="Mostrar/ocultar menú">☰</button>
            <h2>{current.label}</h2>
          </div>
          <p>
            {current.stub
              ? "Pestaña en construcción"
              : "Flujo de carga + N-1 + cortocircuito · comparación con / sin planta (Código de Conexión)"}
          </p>
        </div>
        <div className="scroll">
          {tab === "steady" ? (
            <SteadyState />
          ) : tab === "small-signal" ? (
            <SmallSignalStudy />
          ) : tab === "transient" ? (
            <TransientStudy />
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
