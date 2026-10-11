import type { MonitorStatus } from "../api/types";

const STYLES: Record<MonitorStatus, { badge: string; label: string }> = {
  up: { badge: "bg-emerald-900/60 text-emerald-300 border-emerald-700", label: "Up" },
  degraded: { badge: "bg-amber-900/60 text-amber-300 border-amber-700", label: "Degraded" },
  down: { badge: "bg-red-900/60 text-red-300 border-red-700", label: "Down" },
  stale: { badge: "bg-slate-800 text-slate-300 border-slate-600", label: "Stale" },
  pending: { badge: "bg-slate-800 text-slate-400 border-slate-600", label: "Pending" },
};

export function StatusBadge({ status }: { status: MonitorStatus }) {
  const s = STYLES[status] ?? STYLES.pending;
  // Text + color together — never color alone (PRD §9).
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${s.badge}`}
    >
      {s.label}
    </span>
  );
}
