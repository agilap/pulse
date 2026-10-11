import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { CheckResult, Incident, Monitor } from "../api/types";
import { api } from "../api/client";
import { Button } from "../components/Button";
import { Card, CardHeader, PageHeader } from "../components/Card";
import { EmptyState, ErrorBanner, Skeleton } from "../components/Feedback";
import { StatusLabel } from "../components/StatusIndicator";
import { LatencyChart } from "../components/LatencyChart";
import { monitorName, redactUrl, STATUS_META } from "../domain/status";
import { computeUptime } from "../domain/uptime";
import { latencySeries } from "../domain/series";
import {
  fmtDateTime,
  fmtInterval,
  fmtMs,
  fmtPercent,
  fmtRelative,
  fmtDuration,
} from "../domain/format";

export function MonitorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const monitorId = Number(id);
  const navigate = useNavigate();

  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [checks, setChecks] = useState<CheckResult[] | null>(null);
  const [incidents, setIncidents] = useState<Incident[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!Number.isFinite(monitorId)) {
      setError("Invalid monitor id.");
      return;
    }
    Promise.all([
      api.getMonitor(monitorId),
      api.checkHistory(monitorId, 100),
      api.incidentHistory(monitorId),
    ])
      .then(([m, c, i]) => {
        if (cancelled) return;
        setMonitor(m);
        setChecks(c);
        setIncidents(i);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load monitor.");
      });
    const t = setInterval(() => {
      Promise.all([
        api.getMonitor(monitorId),
        api.checkHistory(monitorId, 100),
        api.incidentHistory(monitorId),
      ]).then(([m, c, i]) => {
        if (!cancelled) {
          setMonitor(m);
          setChecks(c);
          setIncidents(i);
        }
      }).catch(() => {});
    }, 5000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [monitorId]);

  async function toggle() {
    if (!monitor) return;
    setBusy(true);
    try {
      const updated = await api.updateMonitor(monitor.id, { enabled: !monitor.enabled });
      setMonitor(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!monitor) return;
    if (!window.confirm(`Delete ${monitorName(monitor)}? This also deletes its history and incidents.`)) {
      return;
    }
    setBusy(true);
    try {
      await api.deleteMonitor(monitor.id);
      navigate("/monitors");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed.");
      setBusy(false);
    }
  }

  if (error && !monitor) {
    return (
      <div className="space-y-4">
        <Link to="/monitors" className="text-sm text-accent hover:underline">
          &larr; Back to monitors
        </Link>
        <ErrorBanner message={error} />
      </div>
    );
  }

  if (!monitor) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const uptime = checks ? computeUptime(checks) : null;
  const points = checks ? latencySeries(checks) : [];

  return (
    <div className="space-y-6">
      <div>
        <Link to="/monitors" className="text-sm text-ink-dim hover:text-ink">
          &larr; Back to monitors
        </Link>
      </div>

      <PageHeader
        title={monitorName(monitor)}
        description={redactUrl(monitor.url)}
        action={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={toggle} disabled={busy}>
              {monitor.enabled ? "Pause" : "Resume"}
            </Button>
            <Button variant="danger" onClick={remove} disabled={busy}>
              Delete
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-line bg-surface px-4 py-3">
        <StatusLabel status={monitor.status} />
        <span className="text-xs text-ink-dim" title={STATUS_META[monitor.status].hint}>
          {STATUS_META[monitor.status].hint}
        </span>
        <span className="ml-auto text-xs text-ink-faint">
          Interval {fmtInterval(monitor.interval_seconds)} · checked{" "}
          {fmtRelative(monitor.last_checked_at)}
        </span>
      </div>

      {error && <ErrorBanner message={error} />}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader title="Response time" description="Successful checks, most recent first." />
            <div className="p-4">
              {checks == null ? (
                <Skeleton className="h-40 w-full" />
              ) : (
                <LatencyChart points={points} height={200} />
              )}
            </div>
          </Card>
        </div>
        <Card>
          <CardHeader title="Observed uptime" description="Ratio of successful checks in the loaded window." />
          <div className="p-4">
            {uptime == null ? (
              <Skeleton className="h-16 w-full" />
            ) : uptime.ratio == null ? (
              <p className="text-sm text-ink-dim">No checks recorded yet.</p>
            ) : (
              <>
                <div className="text-3xl font-semibold tabular-nums text-ink">
                  {fmtPercent(uptime.ratio)}
                </div>
                <p className="mt-1 text-xs text-ink-faint">
                  {uptime.successes} of {uptime.total} checks succeeded
                  {uptime.insufficient ? " (small sample)" : ""}. Observed ratio,
                  not a guaranteed uptime.
                </p>
              </>
            )}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Check history" description="Most recent checks, newest first." />
        <div className="p-4">
          {checks == null ? (
            <Skeleton className="h-32 w-full" />
          ) : checks.length === 0 ? (
            <EmptyState title="No checks yet" description="Results appear after the first completed check." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line-soft text-left text-xs text-ink-faint">
                    <th className="py-2 pr-4 font-medium">Time</th>
                    <th className="py-2 pr-4 font-medium">Outcome</th>
                    <th className="py-2 pr-4 text-right font-medium">Status</th>
                    <th className="py-2 pr-4 text-right font-medium">Latency</th>
                    <th className="py-2 font-medium">Error</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-soft">
                  {checks.map((c) => (
                    <tr key={c.id}>
                      <td className="py-2 pr-4 text-ink-dim" title={fmtDateTime(c.checked_at)}>
                        {fmtRelative(c.checked_at)}
                      </td>
                      <td className="py-2 pr-4">
                        <OutcomePill outcome={c.outcome} />
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums text-ink">
                        {c.status_code ?? "—"}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums text-ink-dim">
                        {fmtMs(c.latency_ms)}
                      </td>
                      <td className="py-2 font-mono text-xs text-ink-faint">{c.error_code ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader title="Incidents" />
        <div className="p-4">
          {incidents == null ? (
            <Skeleton className="h-16 w-full" />
          ) : incidents.length === 0 ? (
            <EmptyState title="No incidents" description="This monitor has not experienced a sustained outage." />
          ) : (
            <ul className="divide-y divide-line-soft">
              {incidents.map((inc) => {
                const ongoing = inc.resolved_at == null;
                const duration = ongoing
                  ? null
                  : new Date(inc.resolved_at!).getTime() - new Date(inc.started_at).getTime();
                return (
                  <li key={inc.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5 text-sm">
                    <span className={`font-medium ${ongoing ? "text-down" : "text-up"}`}>
                      {ongoing ? "Ongoing" : "Resolved"}
                    </span>
                    <span className="text-ink-dim">Started {fmtDateTime(inc.started_at)}</span>
                    {inc.resolved_at && (
                      <span className="text-ink-dim">Recovered {fmtDateTime(inc.resolved_at)}</span>
                    )}
                    {duration != null && (
                      <span className="text-ink-faint">Duration {fmtDuration(duration)}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Card>
    </div>
  );
}

const OUTCOME_TONE: Record<string, string> = {
  success: "bg-up/15 text-up",
  http_error: "bg-degraded/15 text-degraded",
  timeout: "bg-degraded/15 text-degraded",
  dns_error: "bg-down/15 text-down",
  tls_error: "bg-down/15 text-down",
  connection_error: "bg-down/15 text-down",
  blocked_destination: "bg-down/15 text-down",
  internal_error: "bg-down/15 text-down",
};

function OutcomePill({ outcome }: { outcome: string }) {
  return (
    <span
      className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${
        OUTCOME_TONE[outcome] ?? "bg-raised text-ink-dim"
      }`}
    >
      {outcome.replace(/_/g, " ")}
    </span>
  );
}
