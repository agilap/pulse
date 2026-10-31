from backend.app.db.core import get_conn


def create_webhook_endpoint(
    name: str,
    url: str,
    secret: str,
    event_types: list[str],
):
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO webhook_endpoints (name, url, secret, event_types)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, url, event_types, enabled, created_at, updated_at
            """,
            (name, url, secret, event_types),
        ).fetchone()
        conn.commit()
    return row


def select_webhook_endpoints():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, url, event_types, enabled, created_at, updated_at
            FROM webhook_endpoints
            ORDER BY id DESC
            """
        ).fetchall()
    return rows


def select_webhook_endpoint(endpoint_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, name, url, event_types, enabled, created_at, updated_at
            FROM webhook_endpoints
            WHERE id = %s
            """,
            (endpoint_id,),
        ).fetchone()
    return row


def update_webhook_endpoint(endpoint_id: int, updates: dict):
    allowed_fields = {"name", "url", "secret", "event_types", "enabled"}
    sets = []
    params = []

    for field, value in updates.items():
        if field not in allowed_fields:
            continue
        sets.append(f"{field} = %s")
        params.append(value)

    if not sets:
        return select_webhook_endpoint(endpoint_id)

    sets.append("updated_at = NOW()")
    params.append(endpoint_id)

    with get_conn() as conn:
        row = conn.execute(
            f"""
            UPDATE webhook_endpoints
            SET {", ".join(sets)}
            WHERE id = %s
            RETURNING id, name, url, event_types, enabled, created_at, updated_at
            """,
            tuple(params),
        ).fetchone()

        if row is not None and updates.get("enabled") is False:
            conn.execute(
                """
                UPDATE webhook_deliveries
                SET status = 'failed',
                    lease_until = NULL,
                    lease_token = NULL,
                    last_error_code = 'endpoint_disabled',
                    last_error_message = 'Webhook endpoint was disabled before delivery.',
                    updated_at = NOW()
                WHERE endpoint_id = %s
                  AND status IN ('pending', 'delivering')
                """,
                (endpoint_id,),
            )
        conn.commit()
    return row


def disable_webhook_endpoint(endpoint_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE webhook_endpoints
            SET enabled = FALSE, updated_at = NOW()
            WHERE id = %s
            RETURNING id
            """,
            (endpoint_id,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return False

        conn.execute(
            """
            UPDATE webhook_deliveries
            SET status = 'failed',
                lease_until = NULL,
                lease_token = NULL,
                last_error_code = 'endpoint_disabled',
                last_error_message = 'Webhook endpoint was disabled before delivery.',
                updated_at = NOW()
            WHERE endpoint_id = %s
              AND status IN ('pending', 'delivering')
            """,
            (endpoint_id,),
        )
        conn.commit()
    return True


def webhook_endpoint_exists(endpoint_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM webhook_endpoints WHERE id = %s",
            (endpoint_id,),
        ).fetchone()
    return row is not None


def select_webhook_deliveries(endpoint_id: int, limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.event_id, d.endpoint_id, e.event_type, e.incident_id,
                   d.status, d.attempt_count, d.next_attempt_at, d.delivered_at,
                   d.last_status_code, d.last_error_code, d.last_error_message,
                   d.created_at
            FROM webhook_deliveries d
            JOIN notification_events e ON e.id = d.event_id
            WHERE d.endpoint_id = %s
            ORDER BY d.created_at DESC
            LIMIT %s
            """,
            (endpoint_id, limit),
        ).fetchall()
    return rows


def select_webhook_delivery_attempts(delivery_ids: list[int]):
    if not delivery_ids:
        return []

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, delivery_id, attempt_number, attempted_at, outcome,
                   response_status, duration_ms, error_code, error_message
            FROM webhook_delivery_attempts
            WHERE delivery_id = ANY(%s)
            ORDER BY delivery_id, attempt_number DESC
            """,
            (delivery_ids,),
        ).fetchall()
    return rows
