"use client";
import { TABS } from "@/lib/tabs";

export default function Sidebar({
  active,
  onSelect,
}: {
  active: string;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <h1>Interconexión PV + BESS</h1>
        <p>Estudios de acceso al SENI · DigSILENT</p>
      </div>
      <ul className="nav">
        {TABS.map((t) => (
          <li
            key={t.id}
            className={`${active === t.id ? "active" : ""} ${t.stub ? "stub" : ""}`}
            onClick={() => onSelect(t.id)}
            title={t.stub ? "En construcción" : ""}
          >
            <span className="dot" />
            {t.label}
          </li>
        ))}
      </ul>
    </aside>
  );
}
