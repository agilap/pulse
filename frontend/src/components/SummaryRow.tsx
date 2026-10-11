import type { Monitor } from "../api/types";

export function SummaryRow({ monitors }: { monitors: Monitor[] }) {
  const counts: Record<string, number> = {
    total: monitors.length,
    up: 0,
    degraded: 0,
    down: 0,
    stale: 0,
    pending: 0,
  };
  for (const m of monitors) {
    counts[m.status] = (counts[m.status] ?? 0) + 1;
  }

  const cells: [string, string][] = [
    ["Total", String(counts.total)],
    ["Up", String(counts.up)],
    ["Degraded", String(counts.degraded)],
    ["Down", String(counts.down)],
    ["Stale", String(counts.stale)],
    ["Pending", String(counts.pending)],
  ];

  return (
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
      {cells.map(([label, value]) => (
        <div
          key={label}
          className="rounded-lg border border-gray-800 bg-gray-900 px-4 py-3"
        >
          <div className="text-2xl font-semibold tabular-nums">{value}</div>
          <div className="text-xs text-gray-400">{label}</div>
        </div>
      ))}
    </div>
  );
}
