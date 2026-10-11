import type { Monitor } from "../api/types";
import { STATUS_META } from "../domain/status";

export function StatusDot({ status }: { status: Monitor["status"] }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={`inline-block size-2 shrink-0 rounded-full ${meta.dot}`}
      aria-hidden="true"
    />
  );
}

export function StatusLabel({ status }: { status: Monitor["status"] }) {
  const meta = STATUS_META[status];
  // Text label always accompanies the dot — never color alone.
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${meta.text}`}>
      <StatusDot status={status} />
      {meta.label}
    </span>
  );
}
