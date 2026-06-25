"use client";
import { useEffect, useRef, useState } from "react";
import { RunJob } from "@/lib/api";

function fmt(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return m > 0 ? `${m}m ${sec.toString().padStart(2, "0")}s` : `${sec}s`;
}

/** Barra de progreso con CRONÓMETRO: cuenta el tiempo de la corrida en vivo y muestra el total al terminar. */
export default function RunProgress({ job }: { job: RunJob | null }) {
  const ref = useRef<{ id: string; t0: number; t1: number | null }>({ id: "", t0: 0, t1: null });
  const [, tick] = useState(0);
  const running = job?.status === "queued" || job?.status === "running";

  if (job && ref.current.id !== job.run_id) ref.current = { id: job.run_id, t0: Date.now(), t1: null };
  if (job && !running && ref.current.t1 == null) ref.current.t1 = Date.now();

  useEffect(() => {
    if (!running) return;
    const iv = setInterval(() => tick((t) => t + 1), 500);
    return () => clearInterval(iv);
  }, [running]);

  if (!job) return null;
  const end = ref.current.t1 ?? Date.now();
  const elapsed = Math.max(0, (end - ref.current.t0) / 1000);
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
