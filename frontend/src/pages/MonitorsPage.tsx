import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Monitor } from "../api/types";
import { api } from "../api/client";
import { usePolledResource } from "../hooks/usePolledResource";
import { Button } from "../components/Button";
import { Card, PageHeader } from "../components/Card";
import { EmptyState, ErrorBanner, Skeleton } from "../components/Feedback";
import { StatusLabel } from "../components/StatusIndicator";
import { AddMonitorDialog } from "../components/AddMonitorDialog";
import { monitorName, redactUrl } from "../domain/status";
import { fmtRelative, fmtInterval, fmtDateTime } from "../domain/format";

type Filter = "all" | "up" | "down";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "up", label: "Up" },
  { key: "down", label: "Down" },
];

function matchesFilter(m: Monitor, f: Filter): boolean {
  if (f === "all") return true;
  if (f === "up") return m.status === "up";
  return m.status === "down";
}

export function MonitorsPage() {
  const navigate = useNavigate();
  const [addOpen, setAddOpen] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const { data, loading, error, reload } = usePolledResource<Monitor[]>(
    () => api.listMonitors(),
  );

  const all = data ?? [];
  const filtered = useMemo(() => all.filter((m) => matchesFilter(m, filter)), [all, filter]);

  const counts = useMemo(() => {
    return {
      all: all.length,
      up: all.filter((m) => m.status === "up").length,
      down: all.filter((m) => m.status === "down").length,
    };
  }, [all]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Monitors"
        description="Manage the endpoints Pulse checks on a schedule."
        action={
          <Button variant="primary" onClick={() => setAddOpen(true)}>
            Add monitor
          </Button>
        }
      />

      {error && <ErrorBanner message={`${error} — is the API running on port 8000?`} />}

      <div className="flex gap-1" role="tablist" aria-label="Filter monitors by status">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            role="tab"
            aria-selected={filter === f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
              filter === f.key
                ? "bg-raised text-ink font-medium"
                : "text-ink-dim hover:text-ink"
            }`}
          >
            {f.label}
            <span className="ml-1.5 text-xs text-ink-faint tabular-nums">{counts[f.key]}</span>
          </button>
        ))}
      </div>

      <Card>
        {loading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : all.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No monitors yet"
              description="Add an endpoint to start tracking its availability and response time."
              action={
                <Button variant="primary" onClick={() => setAddOpen(true)}>
                  Add your first monitor
                </Button>
              }
            />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title={`No ${filter} monitors`}
              description="Try a different filter."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line-soft text-left text-xs text-ink-faint">
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Endpoint</th>
                  <th className="px-4 py-2 text-right font-medium">Latest</th>
                  <th className="px-4 py-2 font-medium">Interval</th>
                  <th className="px-4 py-2 font-medium">Last checked</th>
                  <th className="px-4 py-2 font-medium">Enabled</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {filtered.map((m) => (
                  <tr
                    key={m.id}
                    tabIndex={0}
                    role="button"
                    onClick={() => navigate(`/monitors/${m.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") navigate(`/monitors/${m.id}`);
                    }}
                    className="cursor-pointer hover:bg-raised/40 focus:bg-raised/40"
                  >
                    <td className="px-4 py-2.5">
                      <StatusLabel status={m.status} />
                    </td>
                    <td className="max-w-[12rem] truncate px-4 py-2.5 text-ink" title={m.url}>
                      {monitorName(m)}
                    </td>
                    <td className="max-w-[18rem] truncate px-4 py-2.5 font-mono text-xs text-ink-dim" title={m.url}>
                      {redactUrl(m.url)}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-ink-dim">
                      {m.last_status_code != null ? m.last_status_code : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-ink-dim">{fmtInterval(m.interval_seconds)}</td>
                    <td className="px-4 py-2.5 text-ink-dim" title={fmtDateTime(m.last_checked_at)}>
                      {fmtRelative(m.last_checked_at)}
                    </td>
                    <td className="px-4 py-2.5 text-ink-dim">{m.enabled ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <AddMonitorDialog open={addOpen} onClose={() => setAddOpen(false)} onCreated={reload} />
    </div>
  );
}
