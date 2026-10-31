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

export type WebhookEventType = "incident.opened" | "incident.resolved";

export interface WebhookEndpoint {
  id: number;
  name: string;
  url: string;
  event_types: WebhookEventType[];
  enabled: boolean;
  has_secret: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreatedWebhookEndpoint extends WebhookEndpoint {
  secret: string;
}

export interface WebhookDeliveryAttempt {
  id: number;
  attempt_number: number;
  attempted_at: string;
  outcome: "delivered" | "retrying" | "failed";
  response_status: number | null;
  duration_ms: number | null;
  error_code: string | null;
  error_message: string | null;
}

export interface WebhookDelivery {
  id: number;
  event_id: string;
  endpoint_id: number;
  event_type: WebhookEventType;
  incident_id: number;
  status: "pending" | "delivering" | "delivered" | "failed";
  attempt_count: number;
  next_attempt_at: string;
  delivered_at: string | null;
  last_status_code: number | null;
  last_error_code: string | null;
  last_error_message: string | null;
  created_at: string;
  attempts: WebhookDeliveryAttempt[];
}
