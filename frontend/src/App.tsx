import { useCallback, useEffect, useState } from "react";
import type { Monitor } from "./api/types";
import { api } from "./api/client";
import { AddMonitorForm } from "./components/AddMonitorForm";
import { MonitorDetail } from "./components/MonitorDetail";
import { MonitorTable } from "./components/MonitorTable";
import { SummaryRow } from "./components/SummaryRow";

export default function App() {
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [selected, setSelected] = useState<Monitor | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.listMonitors();
      setMonitors(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load monitors");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  async function handleToggle(m: Monitor) {
    await api.updateMonitor(m.id, { enabled: !m.enabled });
    refresh();
  }

  async function handleDelete(m: Monitor) {
    await api.deleteMonitor(m.id);
    if (selected?.id === m.id) setSelected(null);
    refresh();
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6 flex items-baseline justify-between">
        <h1 className="text-xl font-bold tracking-tight">
          Pulse <span className="text-sm font-normal text-gray-500">uptime monitor</span>
        </h1>
      </header>

      {error && (
        <div className="mb-4 rounded-lg border border-red-900 bg-red-950/40 p-3 text-sm text-red-300">
          {error} — is the API running on port 8000?
        </div>
      )}

      {selected ? (
        <MonitorDetail
          monitor={monitors.find((m) => m.id === selected.id) ?? selected}
          onBack={() => setSelected(null)}
        />
      ) : (
        <div className="space-y-6">
          <SummaryRow monitors={monitors} />
          <AddMonitorForm onCreated={refresh} />
          {loading ? (
            <p className="text-sm text-gray-500">Loading monitors...</p>
          ) : (
            <MonitorTable
              monitors={monitors}
              onSelect={setSelected}
              onToggle={handleToggle}
              onDelete={handleDelete}
            />
          )}
        </div>
      )}
    </div>
  );
}
