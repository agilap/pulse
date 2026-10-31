import secrets
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from backend.app.db.webhooks import (
    create_webhook_endpoint,
    disable_webhook_endpoint,
    select_webhook_deliveries,
    select_webhook_delivery_attempts,
    select_webhook_endpoint,
    select_webhook_endpoints,
    update_webhook_endpoint,
    webhook_endpoint_exists,
)
from backend.app.monitoring.url_policy import UrlPolicyError
from backend.app.monitoring.webhook import parse_and_validate_webhook_url

router = APIRouter()

WebhookEventType = Literal["incident.opened", "incident.resolved"]
DEFAULT_EVENT_TYPES: list[WebhookEventType] = ["incident.opened", "incident.resolved"]


class WebhookCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: str
    event_types: list[WebhookEventType] = Field(default_factory=lambda: DEFAULT_EVENT_TYPES.copy())
    secret: str | None = Field(default=None, min_length=16, max_length=256)


class WebhookUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    url: str | None = None
    event_types: list[WebhookEventType] | None = None
    enabled: bool | None = None
    secret: str | None = Field(default=None, min_length=16, max_length=256)


class WebhookEndpointResponse(BaseModel):
    id: int
    name: str
    url: str
    event_types: list[str]
    enabled: bool
    has_secret: bool
    created_at: datetime
    updated_at: datetime


class WebhookCreatedResponse(WebhookEndpointResponse):
    secret: str


class WebhookDeliveryAttemptResponse(BaseModel):
    id: int
    attempt_number: int
    attempted_at: datetime
    outcome: str
    response_status: int | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class WebhookDeliveryResponse(BaseModel):
    id: int
    event_id: str
    endpoint_id: int
    event_type: str
    incident_id: int
    status: str
    attempt_count: int
    next_attempt_at: datetime
    delivered_at: datetime | None = None
    last_status_code: int | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    created_at: datetime
    attempts: list[WebhookDeliveryAttemptResponse] = Field(default_factory=list)


def _raise_url_error(error: UrlPolicyError):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"error": {"code": error.code, "message": error.message}},
    ) from None


def _endpoint_response(row) -> WebhookEndpointResponse:
    return WebhookEndpointResponse(
        id=row[0],
        name=row[1],
        url=row[2],
        event_types=row[3],
        enabled=row[4],
        has_secret=True,
        created_at=row[5],
        updated_at=row[6],
    )


def _validate_event_types(event_types: list[str]):
    if not event_types:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "invalid_event_types",
                    "message": "Select at least one event.",
                }
            },
        )
    if len(set(event_types)) != len(event_types):
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "duplicate_event_types",
                    "message": "Event types must be unique.",
                }
            },
        )


@router.post("/webhooks", response_model=WebhookCreatedResponse, status_code=201)
def create_webhook(req: WebhookCreateRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "invalid_name",
                    "message": "Webhook name cannot be blank.",
                }
            },
        )
    _validate_event_types(req.event_types)

    try:
        url = parse_and_validate_webhook_url(req.url)
    except UrlPolicyError as error:
        _raise_url_error(error)

    secret = req.secret or secrets.token_urlsafe(32)
    row = create_webhook_endpoint(name, url, secret, req.event_types)
    response = _endpoint_response(row)
    return WebhookCreatedResponse(**response.model_dump(), secret=secret)


@router.get("/webhooks", response_model=list[WebhookEndpointResponse])
def list_webhooks():
    return [_endpoint_response(row) for row in select_webhook_endpoints()]


@router.patch("/webhooks/{endpoint_id}", response_model=WebhookEndpointResponse)
def patch_webhook(endpoint_id: int, req: WebhookUpdateRequest):
    updates = req.model_dump(exclude_unset=True)
    updates = {key: value for key, value in updates.items() if value is not None}

    if "name" in updates:
        updates["name"] = updates["name"].strip()
        if not updates["name"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "invalid_name",
                        "message": "Webhook name cannot be blank.",
                    }
                },
            )

    if "url" in updates:
        try:
            updates["url"] = parse_and_validate_webhook_url(updates["url"])
        except UrlPolicyError as error:
            _raise_url_error(error)

    if "event_types" in updates:
        _validate_event_types(updates["event_types"])

    if "secret" in updates and not updates["secret"]:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "invalid_secret",
                    "message": "Webhook secret cannot be blank.",
                }
            },
        )

    if not updates:
        row = select_webhook_endpoint(endpoint_id)
    else:
        row = update_webhook_endpoint(endpoint_id, updates)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Webhook endpoint not found."}},
        )
    return _endpoint_response(row)


@router.delete("/webhooks/{endpoint_id}", status_code=204)
def delete_webhook(endpoint_id: int):
    if not disable_webhook_endpoint(endpoint_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Webhook endpoint not found."}},
        )
    return Response(status_code=204)


@router.get(
    "/webhooks/{endpoint_id}/deliveries",
    response_model=list[WebhookDeliveryResponse],
)
def list_webhook_deliveries(endpoint_id: int, limit: int = 50):
    if not webhook_endpoint_exists(endpoint_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Webhook endpoint not found."}},
        )

    rows = select_webhook_deliveries(endpoint_id, limit=max(1, min(limit, 100)))
    delivery_ids = [row[0] for row in rows]
    attempts_by_delivery: dict[int, list[WebhookDeliveryAttemptResponse]] = {
        delivery_id: [] for delivery_id in delivery_ids
    }

    for attempt in select_webhook_delivery_attempts(delivery_ids):
        attempts_by_delivery[attempt[1]].append(
            WebhookDeliveryAttemptResponse(
                id=attempt[0],
                attempt_number=attempt[2],
                attempted_at=attempt[3],
                outcome=attempt[4],
                response_status=attempt[5],
                duration_ms=attempt[6],
                error_code=attempt[7],
                error_message=attempt[8],
            )
        )

    return [
        WebhookDeliveryResponse(
            id=row[0],
            event_id=str(row[1]),
            endpoint_id=row[2],
            event_type=row[3],
            incident_id=row[4],
            status=row[5],
            attempt_count=row[6],
            next_attempt_at=row[7],
            delivered_at=row[8],
            last_status_code=row[9],
            last_error_code=row[10],
            last_error_message=row[11],
            created_at=row[12],
            attempts=attempts_by_delivery[row[0]],
        )
        for row in rows
    ]
