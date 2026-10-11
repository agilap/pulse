import { useEffect, useState } from "react";
import type { CheckResult, Incident, Monitor } from "../api/types";
import { api } from "../api/client";
import { StatusBadge } from "./StatusBadge";
import { fmtInterval, fmtLatency, fmtTime, redactUrl } from "../utils/format";

export function MonitorDetail({
  monitor,
  onBack,
}: {
  monitor: Monitor;
  onBack: () => void;
}) {
  const [checks, setChecks] = useState<CheckResult[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.checkHistory(monitor.id), api.incidentHistory(monitor.id)])
      .then(([c, i]) => {
        if (!cancelled) {
          setChecks(c);
          setIncidents(i);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      });
    return () => {
      cancelled = true;
    };
  }, [monitor.id]);

  const successChecks = checks.filter((c) => c.outcome === "success");
  const successRate =
    checks.length > 0
      ? Math.round((successChecks.length / checks.length) * 1000) / 10
      : null;
  const latencies = successChecks
    .map((c) => c.latency_ms)
    .filter((v): v is number => v != null);
  const maxLatency = latencies.length > 0 ? Math.max(...latencies) : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="rounded px-2 py-1 text-sm text-gray-400 hover:bg-gray-800"
        >
          &larr; Back
        </button>
        <h2 className="truncate text-lg font-semibold" title={monitor.url}>
          {redactUrl(monitor.url)}
        </h2>
        <StatusBadge status={monitor.status} />
      </div>

      {error && (
        <div className="rounded-lg border border-red-900 bg-red-950/40 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Interval" value={fmtInterval(monitor.interval_seconds)} />
        <Stat label="Last checked" value={fmtTime(monitor.last_checked_at)} />
        <Stat
          label="Observed success rate"
          value={successRate != null ? `${successRate}%` : "—"}
          hint="estimate, not guaranteed uptime"
        />
        <Stat
          label="Consecutive failures"
          value={String(monitor.consecutive_failures ?? 0)}
        />
      </div>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-gray-300">
          Response time (successful checks)
        </h3>
        {latencies.length === 0 ? (
          <p className="rounded-lg border border-dashed border-gray-700 p-6 text-center text-sm text-gray-500">
            No successful checks yet.
          </p>
        ) : (
          <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
            <div className="flex h-32 items-end gap-1">
              {latencies.slice(-40).map((v, i) => (
                <div
                  key={i}
                  className="flex-1 rounded-t bg-sky-600/80"
                  style={{ height: `${maxLatency ? (v / maxLatency) * 100 : 0}%` }}
                  title={`${v} ms`}
                />
              ))}
            </div>
            <div className="mt-2 flex justify-between text-xs text-gray-500">
              <span>0 ms</span>
              <span>max {maxLatency} ms</span>
            </div>
          </div>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-gray-300">Recent checks</h3>
        {checks.length === 0 ? (
          <p className="rounded-lg border border-dashed border-gray-700 p-6 text-center text-sm text-gray-500">
            No checks recorded yet.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-sm">
              <thead className="bg-gray-900 text-left text-xs uppercase text-gray-400">
                <tr>
                  <th className="px-3 py-2">Time</th>
                  <th className="px-3 py-2">Outcome</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Latency</th>
                  <th className="px-3 py-2">Error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {checks.map((c) => (
                  <tr key={c.id}>
                    <td className="px-3 py-2 text-gray-400">{fmtTime(c.checked_at)}</td>
                    <td className="px-3 py-2">
                      <OutcomePill outcome={c.outcome} />
                    </td>
                    <td className="px-3 py-2 tabular-nums text-gray-300">
                      {c.status_code ?? "—"}
                    </td>
                    <td className="px-3 py-2 tabular-nums text-gray-300">
                      {fmtLatency(c.latency_ms)}
                    </td>
                    <td className="px-3 py-2 text-gray-500">{c.error_code ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-gray-300">Incidents</h3>
        {incidents.length === 0 ? (
          <p className="rounded-lg border border-dashed border-gray-700 p-6 text-center text-sm text-gray-500">
            No incidents recorded.
          </p>
        ) : (
          <ul className="divide-y divide-gray-800 rounded-lg border border-gray-800">
            {incidents.map((i) => (
              <li key={i.id} className="flex flex-wrap gap-x-6 gap-y-1 px-4 py-3 text-sm">
                <span className={i.resolved_at ? "text-gray-400" : "text-red-300"}>
                  {i.resolved_at ? "Resolved" : "Open"}
                </span>
                <span className="text-gray-400">Started {fmtTime(i.started_at)}</span>
                <span className="text-gray-400">
                  Last failure {fmtTime(i.last_failure_at)}
                </span>
                {i.resolved_at && (
                  <span className="text-gray-500">Resolved {fmtTime(i.resolved_at)}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 px-4 py-3">
      <div className="text-xs text-gray-400">
        {label}
        {hint && <span className="ml-1 text-gray-600">({hint})</span>}
      </div>
      <div className="mt-0.5 text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function OutcomePill({ outcome }: { outcome: string }) {
  const map: Record<string, string> = {
    success: "bg-emerald-900/60 text-emerald-300",
    http_error: "bg-amber-900/60 text-amber-300",
    timeout: "bg-amber-900/60 text-amber-300",
    dns_error: "bg-red-900/60 text-red-300",
    tls_error: "bg-red-900/60 text-red-300",
    connection_error: "bg-red-900/60 text-red-300",
    blocked_destination: "bg-red-900/60 text-red-300",
    internal_error: "bg-red-900/60 text-red-300",
  };
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${map[outcome] ?? "bg-gray-800 text-gray-300"}`}
    >
      {outcome.replace(/_/g, " ")}
    </span>
  );
}
