from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_flow_service, require
from app.api.request_info import client_ip
from app.db.session import get_db
from app.schemas.flow import (
    FlowCreate,
    FlowOut,
    FlowRunCreate,
    FlowRunOut,
    FlowSummaryOut,
    FlowUpdate,
)
from app.services.audit import record_audit
from app.services.flows import FlowService

router = APIRouter(prefix="/flows", tags=["flows"])


@router.get("", response_model=list[FlowOut])
def list_flows(
    principal: Principal = Depends(require("jobs:read")),
    service: FlowService = Depends(get_flow_service),
) -> list[FlowOut]:
    return [
        FlowOut.model_validate(flow) for flow in service.list_all(principal.tenant_id)
    ]


@router.post("", response_model=FlowOut, status_code=status.HTTP_201_CREATED)
def create_flow(
    payload: FlowCreate,
    request: Request,
    principal: Principal = Depends(require("jobs:write")),
    service: FlowService = Depends(get_flow_service),
    db: Session = Depends(get_db),
) -> FlowOut:
    flow = service.create(principal.tenant_id, payload, principal.user_id)
    record_audit(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="flow.created",
        event_data={"flow_id": str(flow.id), "name": flow.name},
        ip=client_ip(request),
    )
    return FlowOut.model_validate(flow)


@router.get("/summary", response_model=FlowSummaryOut)
def flows_summary(
    principal: Principal = Depends(require("jobs:read")),
    service: FlowService = Depends(get_flow_service),
) -> FlowSummaryOut:
    return FlowSummaryOut.model_validate(service.summary(principal.tenant_id))


@router.get("/{flow_id}", response_model=FlowOut)
def get_flow(
    flow_id: UUID,
    principal: Principal = Depends(require("jobs:read")),
    service: FlowService = Depends(get_flow_service),
) -> FlowOut:
    return FlowOut.model_validate(service.get(principal.tenant_id, flow_id))


@router.patch("/{flow_id}", response_model=FlowOut)
def update_flow(
    flow_id: UUID,
    payload: FlowUpdate,
    principal: Principal = Depends(require("jobs:write")),
    service: FlowService = Depends(get_flow_service),
) -> FlowOut:
    return FlowOut.model_validate(
        service.update(principal.tenant_id, flow_id, payload)
    )


@router.delete("/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flow(
    flow_id: UUID,
    request: Request,
    principal: Principal = Depends(require("jobs:write")),
    service: FlowService = Depends(get_flow_service),
    db: Session = Depends(get_db),
) -> Response:
    service.delete(principal.tenant_id, flow_id)
    record_audit(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="flow.deleted",
        event_data={"flow_id": str(flow_id)},
        ip=client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{flow_id}/run", response_model=FlowRunOut)
def run_flow(
    flow_id: UUID,
    payload: FlowRunCreate,
    request: Request,
    principal: Principal = Depends(require("jobs:write")),
    service: FlowService = Depends(get_flow_service),
    db: Session = Depends(get_db),
) -> FlowRunOut:
    run = service.run(principal.tenant_id, flow_id, payload, principal.user_id)
    record_audit(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="flow.run",
        event_data={"flow_id": str(flow_id), "run_id": str(run.id), "status": run.status},
        ip=client_ip(request),
    )
    return FlowRunOut.model_validate(run)


@router.get("/{flow_id}/runs", response_model=list[FlowRunOut])
def list_runs(
    flow_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require("jobs:read")),
    service: FlowService = Depends(get_flow_service),
) -> list[FlowRunOut]:
    return [
        FlowRunOut.model_validate(run)
        for run in service.runs(principal.tenant_id, flow_id, limit)
    ]
