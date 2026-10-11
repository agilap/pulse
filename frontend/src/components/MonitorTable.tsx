import type { Monitor } from "../api/types";
import { StatusBadge } from "./StatusBadge";
import { fmtInterval, fmtTime, redactUrl } from "../utils/format";

interface Props {
  monitors: Monitor[];
  onSelect: (m: Monitor) => void;
  onToggle: (m: Monitor) => void;
  onDelete: (m: Monitor) => void;
}

export function MonitorTable({ monitors, onSelect, onToggle, onDelete }: Props) {
  if (monitors.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-700 p-10 text-center">
        <p className="text-gray-400">No monitors yet.</p>
        <p className="mt-1 text-sm text-gray-500">
          Add one above to start tracking an endpoint.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-sm">
        <thead className="bg-gray-900 text-left text-xs uppercase text-gray-400">
          <tr>
            <th className="px-4 py-3">Target</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Latency</th>
            <th className="px-4 py-3">Last checked</th>
            <th className="px-4 py-3">Interval</th>
            <th className="px-4 py-3">Enabled</th>
            <th className="px-4 py-3 text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {monitors.map((m) => (
            <tr key={m.id} className="hover:bg-gray-900/50">
              <td className="px-4 py-3">
                <button
                  onClick={() => onSelect(m)}
                  className="max-w-xs truncate text-left text-sky-400 hover:underline"
                  title={m.url}
                >
                  {redactUrl(m.url)}
                </button>
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={m.status} />
              </td>
              <td className="px-4 py-3 tabular-nums text-gray-300">
                {m.last_status_code != null ? m.last_status_code : "—"}
              </td>
              <td className="px-4 py-3 text-gray-400">{fmtTime(m.last_checked_at)}</td>
              <td className="px-4 py-3 text-gray-400">{fmtInterval(m.interval_seconds)}</td>
              <td className="px-4 py-3 text-gray-400">{m.enabled ? "Yes" : "No"}</td>
              <td className="px-4 py-3 text-right whitespace-nowrap">
                <button
                  onClick={() => onToggle(m)}
                  className="mr-2 rounded px-2 py-1 text-xs text-gray-300 hover:bg-gray-800"
                >
                  {m.enabled ? "Disable" : "Enable"}
                </button>
                <button
                  onClick={() => {
                    if (
                      window.confirm(
                        `Delete ${m.url}? This also deletes its check history and incidents.`,
                      )
                    ) {
                      onDelete(m);
                    }
                  }}
                  className="rounded px-2 py-1 text-xs text-red-400 hover:bg-red-950"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
