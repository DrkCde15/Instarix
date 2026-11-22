from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_webhook_service, require
from app.api.request_info import client_ip
from app.db.session import get_db
from app.schemas.webhook import (
    WebhookCreate,
    WebhookDeliveryOut,
    WebhookEndpointCreated,
    WebhookEndpointOut,
)
from app.services.audit import record_audit
from app.services.webhooks import WebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookEndpointCreated, status_code=status.HTTP_201_CREATED)
def create_webhook(
    payload: WebhookCreate,
    request: Request,
    principal: Principal = Depends(require("webhooks:write")),
    service: WebhookService = Depends(get_webhook_service),
    db: Session = Depends(get_db),
) -> WebhookEndpointCreated:
    endpoint, secret = service.create(
        principal.tenant_id, url=payload.url, events=payload.events
    )
    record_audit(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="webhook.created",
        event_data={"endpoint_id": str(endpoint.id), "events": endpoint.events},
        ip=client_ip(request),
    )
    return WebhookEndpointCreated(
        **WebhookEndpointOut.model_validate(endpoint).model_dump(), secret=secret
    )


@router.get("", response_model=list[WebhookEndpointOut])
def list_webhooks(
    principal: Principal = Depends(require("webhooks:read")),
    service: WebhookService = Depends(get_webhook_service),
) -> list[WebhookEndpointOut]:
    return [
        WebhookEndpointOut.model_validate(endpoint)
        for endpoint in service.list(principal.tenant_id)
    ]


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    endpoint_id: UUID,
    request: Request,
    principal: Principal = Depends(require("webhooks:write")),
    service: WebhookService = Depends(get_webhook_service),
    db: Session = Depends(get_db),
) -> Response:
    service.delete(principal.tenant_id, endpoint_id)
    record_audit(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="webhook.deleted",
        event_data={"endpoint_id": str(endpoint_id)},
        ip=client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryOut])
def list_deliveries(
    endpoint_id: UUID,
    limit: int = Query(default=100, ge=1, le=200),
    principal: Principal = Depends(require("webhooks:read")),
    service: WebhookService = Depends(get_webhook_service),
) -> list[WebhookDeliveryOut]:
    return [
        WebhookDeliveryOut.model_validate(delivery)
        for delivery in service.deliveries(
            principal.tenant_id, endpoint_id, limit=limit
        )
    ]
