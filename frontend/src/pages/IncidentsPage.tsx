import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Incident } from "../api/types";
import { api } from "../api/client";
import { usePolledResource } from "../hooks/usePolledResource";
import { Card, CardHeader, PageHeader } from "../components/Card";
import { EmptyState, ErrorBanner, Skeleton } from "../components/Feedback";
import { redactUrl } from "../domain/status";
import { fmtDateTime, fmtDuration } from "../domain/format";

type Filter = "all" | "open" | "resolved";

export function IncidentsPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const { data, loading, error } = usePolledResource<Incident[]>(() =>
    api.incidents("all"),
  );

  const all = data ?? [];
  const filtered = useMemo(() => {
    const sorted = all.slice().sort((a, b) => b.started_at.localeCompare(a.started_at));
    if (filter === "open") return sorted.filter((i) => i.resolved_at == null);
    if (filter === "resolved") return sorted.filter((i) => i.resolved_at != null);
    return sorted;
  }, [all, filter]);

  const openCount = all.filter((i) => i.resolved_at == null).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Incidents"
        description="Sustained failures and their resolution, tracked per monitor."
      />

      {error && <ErrorBanner message={`${error} — is the API running on port 8000?`} />}

      <div className="flex gap-1" role="tablist" aria-label="Filter incidents">
        {(["all", "open", "resolved"] as Filter[]).map((f) => (
          <button
            key={f}
            role="tab"
            aria-selected={filter === f}
            onClick={() => setFilter(f)}
            className={`rounded-md px-3 py-1.5 text-sm capitalize transition-colors ${
              filter === f ? "bg-raised text-ink font-medium" : "text-ink-dim hover:text-ink"
            }`}
          >
            {f}
            {f === "open" && openCount > 0 && (
              <span className="ml-1.5 rounded bg-down/20 px-1.5 text-xs text-down">
                {openCount}
              </span>
            )}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader
          title={`${filtered.length} incident${filtered.length === 1 ? "" : "s"}`}
          description="An incident opens after consecutive failed checks and resolves on recovery."
        />
        <div className="p-4">
          {loading ? (
            <Skeleton className="h-24 w-full" />
          ) : filtered.length === 0 ? (
            <EmptyState
              title="No incidents"
              description="Incident history will appear here when monitored services experience sustained failures."
            />
          ) : (
            <ul className="divide-y divide-line-soft">
              {filtered.map((inc) => {
                const ongoing = inc.resolved_at == null;
                const duration = ongoing
                  ? null
                  : new Date(inc.resolved_at!).getTime() -
                    new Date(inc.started_at).getTime();
                return (
                  <li key={inc.id} className="py-3">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span
                        className={`inline-flex items-center gap-1.5 text-sm font-medium ${
                          ongoing ? "text-down" : "text-up"
                        }`}
                      >
                        <span
                          className={`inline-block size-2 rounded-full ${
                            ongoing ? "bg-down" : "bg-up"
                          }`}
                          aria-hidden="true"
                        />
                        {ongoing ? "Ongoing" : "Resolved"}
                      </span>
                      {inc.monitor_id ? (
                        <Link
                          to={`/monitors/${inc.monitor_id}`}
                          className="truncate text-sm text-accent hover:underline"
                        >
                          {redactUrl(inc.url ?? `Monitor ${inc.monitor_id}`)}
                        </Link>
                      ) : (
                        <span className="truncate text-sm text-ink-dim">
                          {redactUrl(inc.url ?? "Unknown monitor")}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-ink-dim">
                      <span>Started {fmtDateTime(inc.started_at)}</span>
                      <span>
                        {ongoing
                          ? "Still ongoing"
                          : `Recovered ${fmtDateTime(inc.resolved_at)}`}
                      </span>
                      {duration != null && <span>Duration {fmtDuration(duration)}</span>}
                      <span>{inc.failure_count_at_open} failures at open</span>
                    </div>
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
