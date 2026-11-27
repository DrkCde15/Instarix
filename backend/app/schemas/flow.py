from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FlowNodeIn(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] | None = None


class FlowEdgeIn(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    source: str
    target: str
    source_handle: str | None = None


class FlowGraphIn(BaseModel):
    nodes: list[FlowNodeIn] = Field(default_factory=list, max_length=100)
    edges: list[FlowEdgeIn] = Field(default_factory=list, max_length=200)


TriggerSource = Literal["manual", "dm", "comment"]


class FlowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: str = Field(default="geral", min_length=1, max_length=40)
    graph: FlowGraphIn
    enabled: bool = True
    trigger_source: TriggerSource = "manual"
    account_id: UUID | None = None
    poll_interval_seconds: int = Field(default=30, ge=5, le=3600)


class FlowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, min_length=1, max_length=40)
    graph: FlowGraphIn | None = None
    enabled: bool | None = None
    trigger_source: TriggerSource | None = None
    account_id: UUID | None = None
    poll_interval_seconds: int | None = Field(default=None, ge=5, le=3600)


class FlowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    category: str
    enabled: bool
    graph: dict[str, Any]
    trigger_source: str
    account_id: UUID | None
    poll_interval_seconds: int
    created_at: datetime
    updated_at: datetime


class FlowRunCreate(BaseModel):
    trigger: str = Field(default="manual", min_length=1, max_length=64)
    context: dict[str, Any] = Field(default_factory=dict)


class FlowRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    flow_id: UUID
    status: str
    trigger: str
    context: dict[str, Any]
    steps: list[dict[str, Any]]
    error_code: str | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None


class FlowSummaryOut(BaseModel):
    total_flows: int
    active_flows: int
    paused_flows: int
    draft_flows: int
    total_runs: int
    succeeded_runs: int
    success_rate: float
    recent_runs: list[FlowRunOut]
    top_flows: list[dict[str, Any]]
    activity: list[dict[str, Any]]
