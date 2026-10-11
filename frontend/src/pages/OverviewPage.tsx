import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { CheckResult, Incident, Monitor } from "../api/types";
import { api } from "../api/client";
import { usePolledResource } from "../hooks/usePolledResource";
import { Button } from "../components/Button";
import { Card, CardHeader, PageHeader } from "../components/Card";
import { EmptyState, ErrorBanner, Skeleton } from "../components/Feedback";
import { StatusLabel } from "../components/StatusIndicator";
import { LatencyChart } from "../components/LatencyChart";
import { AddMonitorDialog } from "../components/AddMonitorDialog";
import { monitorName, redactUrl } from "../domain/status";
import { latencySeries } from "../domain/series";
import { fmtRelative, fmtInterval } from "../domain/format";

export function OverviewPage() {
  const navigate = useNavigate();
  const [addOpen, setAddOpen] = useState(false);
  const monitors = usePolledResource<Monitor[]>(() => api.listMonitors());
  const incidents = usePolledResource<Incident[]>(() => api.incidents("all"));

  const reload = () => {
    monitors.reload();
    incidents.reload();
  };

  const list = monitors.data ?? [];
  const counts = useMemo(() => {
    let up = 0;
    let down = 0;
    for (const m of list) {
      if (m.status === "up") up++;
      if (m.status === "down") down++;
    }
    return { total: list.length, up, down };
  }, [list]);

  const recentIncidents = (incidents.data ?? [])
    .slice()
    .sort((a, b) => b.started_at.localeCompare(a.started_at))
    .slice(0, 6);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description="Monitor the health and performance of your services."
        action={
          <Button variant="primary" onClick={() => setAddOpen(true)}>
            Add monitor
          </Button>
        }
      />

      {monitors.error && (
        <ErrorBanner message={`${monitors.error} — is the API running on port 8000?`} />
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Total monitors" value={monitors.loading ? null : String(counts.total)} />
        <Metric
          label="Operational"
          value={monitors.loading ? null : String(counts.up)}
          tone="up"
          detail={counts.total ? `of ${counts.total}` : undefined}
        />
        <Metric
          label="Down"
          value={monitors.loading ? null : String(counts.down)}
          tone={counts.down > 0 ? "down" : undefined}
          detail={counts.down > 0 ? "needs attention" : "none"}
        />
        <Metric
          label="Observed uptime"
          value={null}
          detail="per monitor"
          raw
        />
      </div>

      <Card>
        <CardHeader
          title="Response time"
          description="Most recent successful checks across all monitors."
        />
        <div className="p-4">
          <AggregateLatency monitors={list} />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Monitored services"
          description="Current status and latest response for every endpoint."
          action={
            <Button variant="ghost" onClick={() => navigate("/monitors")}>
              View all
            </Button>
          }
        />
        <OverviewTable monitors={list} loading={monitors.loading} onAdd={() => setAddOpen(true)} />
      </Card>

      <Card>
        <CardHeader title="Recent incidents" />
        <div className="p-4">
          {incidents.error ? (
            <ErrorBanner message={incidents.error} />
          ) : incidents.loading ? (
            <Skeleton className="h-16 w-full" />
          ) : recentIncidents.length === 0 ? (
            <p className="text-sm text-ink-dim">
              No incidents recorded. Incident history will appear here when
              monitored services experience sustained failures.
            </p>
          ) : (
            <ul className="divide-y divide-line-soft">
              {recentIncidents.map((inc) => {
                const url = inc.url ?? `Monitor ${inc.monitor_id ?? inc.id}`;
                const duration =
                  inc.resolved_at != null
                    ? new Date(inc.resolved_at).getTime() -
                      new Date(inc.started_at).getTime()
                    : null;
                return (
                  <li key={inc.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5 text-sm">
                    <span
                      className={`inline-flex items-center gap-1.5 font-medium ${
                        inc.resolved_at ? "text-ink-dim" : "text-down"
                      }`}
                    >
                      <span
                        className={`inline-block size-2 rounded-full ${
                          inc.resolved_at ? "bg-up" : "bg-down"
                        }`}
                        aria-hidden="true"
                      />
                      {inc.resolved_at ? "Resolved" : "Ongoing"}
                    </span>
                    <button
                      className="truncate text-accent hover:underline"
                      onClick={() => inc.monitor_id && navigate(`/monitors/${inc.monitor_id}`)}
                    >
                      {redactUrl(url)}
                    </button>
                    <span className="text-ink-dim">started {fmtRelative(inc.started_at)}</span>
                    {duration != null && (
                      <span className="text-ink-faint">lasted {fmtDurationShort(duration)}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Card>

      <AddMonitorDialog open={addOpen} onClose={() => setAddOpen(false)} onCreated={reload} />
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  tone,
  raw,
}: {
  label: string;
  value: string | null;
  detail?: string;
  tone?: "up" | "down";
  raw?: boolean;
}) {
  const toneClass =
    tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-ink";
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <div className="text-xs text-ink-dim">{label}</div>
      {raw ? (
        <div className="mt-1 text-2xl font-semibold text-ink-dim">—</div>
      ) : value == null ? (
        <Skeleton className="mt-1.5 h-7 w-14" />
      ) : (
        <div className={`mt-1 text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</div>
      )}
      {detail && <div className="mt-0.5 text-xs text-ink-faint">{detail}</div>}
    </div>
  );
}

function OverviewTable({
  monitors,
  loading,
  onAdd,
}: {
  monitors: Monitor[];
  loading: boolean;
  onAdd: () => void;
}) {
  const navigate = useNavigate();

  if (loading) {
    return (
      <div className="space-y-2 p-4">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    );
  }

  if (monitors.length === 0) {
    return (
      <div className="p-4">
        <EmptyState
          title="No monitors yet"
          description="Pulse checks your public endpoints on a schedule, records response times, and tracks incidents. Add your first monitor to get started."
          action={
            <Button variant="primary" onClick={onAdd}>
              Add your first monitor
            </Button>
          }
        />
      </div>
    );
  }

  const shown = monitors.slice(0, 8);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line-soft text-left text-xs text-ink-faint">
            <th className="px-4 py-2 font-medium">Status</th>
            <th className="px-4 py-2 font-medium">Name</th>
            <th className="px-4 py-2 font-medium">Interval</th>
            <th className="px-4 py-2 text-right font-medium">Latest</th>
            <th className="px-4 py-2 font-medium">Last checked</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line-soft">
          {shown.map((m) => (
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
              <td className="max-w-[16rem] truncate px-4 py-2.5 text-ink" title={m.url}>
                {monitorName(m)}
              </td>
              <td className="px-4 py-2.5 text-ink-dim">{fmtInterval(m.interval_seconds)}</td>
              <td className="px-4 py-2.5 text-right tabular-nums text-ink-dim">
                {m.last_status_code != null ? m.last_status_code : "—"}
              </td>
              <td className="px-4 py-2.5 text-ink-dim">{fmtRelative(m.last_checked_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AggregateLatency({ monitors }: { monitors: Monitor[] }) {
  // Fetch recent checks for the first few monitors to build an honest,
  // real-data latency curve. Missing data is skipped, never zeroed.
  const idsKey = monitors.slice(0, 5).map((m) => m.id).join(",");
  const [series, setSeries] = useState<CheckResult[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const ids = idsKey ? idsKey.split(",").map(Number) : [];
    if (ids.length === 0) {
      setSeries([]);
      return;
    }
    Promise.all(ids.map((id) => api.checkHistory(id, 40)))
      .then((results) => {
        if (!cancelled) setSeries(results.flat());
      })
      .catch(() => {
        if (!cancelled) setSeries([]);
      });
    return () => {
      cancelled = true;
    };
  }, [idsKey]);

  if (series == null) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (series.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-line text-sm text-ink-dim">
        No successful checks recorded yet. The chart fills in as Pulse checks your monitors.
      </div>
    );
  }
  return <LatencyChart points={latencySeries(series)} height={180} />;
}

function fmtDurationShort(ms: number): string {
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}
