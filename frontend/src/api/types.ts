export type MonitorStatus =
  | "pending"
  | "up"
  | "degraded"
  | "down"
  | "stale";

export interface Monitor {
  id: number;
  url: string;
  interval_seconds: number;
  enabled: boolean;
  status: MonitorStatus;
  created_at: string;
  updated_at: string;
  next_check_at: string;
  last_checked_at: string | null;
  last_outcome: string | null;
  last_status_code: number | null;
  consecutive_failures: number | null;
}

export interface CheckResult {
  id: number;
  checked_at: string;
  outcome: string;
  status_code: number | null;
  latency_ms: number | null;
  error_code: string | null;
  error_message: string | null;
}

export interface Incident {
  id: number;
  monitor_id?: number;
  url?: string;
  started_at: string;
  last_failure_at: string;
  resolved_at: string | null;
  failure_count_at_open: number;
}
