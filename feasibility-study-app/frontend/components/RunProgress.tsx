"use client";
import { useEffect, useState } from "react";
import { RunJob } from "@/lib/api";
import { runStart, runEnd } from "@/lib/runStore";

function fmt(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return m > 0 ? `${m}m ${sec.toString().padStart(2, "0")}s` : `${sec}s`;
}

/** Barra de progreso con CRONÓMETRO: cuenta el tiempo de la corrida en vivo y muestra el total al terminar.
 *  El inicio/fin se guardan en runStore por run_id, así el conteo NO se reinicia al cambiar de pestaña. */
export default function RunProgress({ job }: { job: RunJob | null }) {
  const [, tick] = useState(0);
  const running = job?.status === "queued" || job?.status === "running";

  useEffect(() => {
    if (!running) return;
    const iv = setInterval(() => tick((t) => t + 1), 500);
    return () => clearInterval(iv);
  }, [running]);

  if (!job) return null;
  const t0 = runStart(job.run_id);
  const t1 = runEnd(job.run_id, !running);
  const end = t1 ?? Date.now();
  const elapsed = Math.max(0, (end - t0) / 1000);
  const color = job.status === "error" ? "var(--bad)" : job.status === "done" ? "var(--good)" : undefined;
  return (
    <>
      <div className="progress"><div style={{ width: `${job.progress}%`, background: color }} /></div>
      <div className="phase">
        {job.progress}% · {job.phase} · ⏱ <b>{fmt(elapsed)}</b>{job.status === "done" ? " (total)" : running ? "…" : ""}
      </div>
    </>
  );
}
