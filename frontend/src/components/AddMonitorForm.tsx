import { useState } from "react";
import { api } from "../api/client";

export function AddMonitorForm({ onCreated }: { onCreated: () => void }) {
  const [url, setUrl] = useState("");
  const [interval, setInterval] = useState(60);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.createMonitor(url.trim(), interval);
      setUrl("");
      setInterval(60);
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create monitor");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-lg border border-gray-800 bg-gray-900 p-4"
    >
      <h2 className="mb-3 text-sm font-semibold text-gray-300">Add monitor</h2>
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          type="url"
          required
          placeholder="https://example.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1 rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm outline-none focus:border-sky-500"
        />
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={60}
            max={86400}
            value={interval}
            onChange={(e) => setInterval(Number(e.target.value))}
            className="w-28 rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm outline-none focus:border-sky-500"
          />
          <span className="text-xs text-gray-500">seconds</span>
        </div>
        <button
          type="submit"
          disabled={busy || !url.trim()}
          className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {busy ? "Adding..." : "Add"}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
    </form>
  );
}
