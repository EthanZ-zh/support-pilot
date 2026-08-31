import json
from collections.abc import Iterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from support_pilot.agent.contracts import AgentRequest, AgentResponse
from support_pilot.agent.providers import get_decision_provider
from support_pilot.agent.service import AgentService
from support_pilot.api.dependencies import CurrentUserDep, SessionDep
from support_pilot.api.schemas import ErrorResponse
from support_pilot.application.contracts import SupportInput, SupportResponse
from support_pilot.application.services import SupportService
from support_pilot.auth.contracts import CurrentUserResponse, LoginRequest, TokenResponse
from support_pilot.auth.service import authenticate_user, issue_access_token
from support_pilot.domain.enums import TicketStatus
from support_pilot.domain.errors import DomainError
from support_pilot.rag.contracts import KnowledgeSearchInput, KnowledgeSearchResponse
from support_pilot.rag.providers.factory import get_provider_bundle
from support_pilot.rag.retrieval import HybridRetrievalService
from support_pilot.tickets.contracts import (
    ClaimTicketRequest,
    HumanFeedbackRequest,
    HumanFeedbackResponse,
    TicketListResponse,
    TicketResponse,
    TransitionTicketRequest,
)
from support_pilot.tickets.service import TicketWorkflowService

router = APIRouter(prefix="/api/v1")


def _sse_event(event: str, payload: Any) -> str:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["auth"],
)
def login(request: LoginRequest, session: SessionDep) -> TokenResponse:
    user = authenticate_user(session, email=request.email, password=request.password)
    return issue_access_token(user)


@router.get("/auth/me", response_model=CurrentUserResponse, tags=["auth"])
def current_user(actor: CurrentUserDep) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=actor.id,
        tenant_id=actor.tenant_id,
        email=actor.email,
        display_name=actor.display_name,
        role=actor.role,
    )


@router.get("/tickets", response_model=TicketListResponse, tags=["tickets"])
def list_tickets(
    actor: CurrentUserDep,
    session: SessionDep,
    tenant_id: UUID | None = None,
    status: TicketStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TicketListResponse:
    return TicketWorkflowService(session).list_tickets(
        actor=actor,
        tenant_id=tenant_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/tickets/{ticket_id}",
    response_model=TicketResponse,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["tickets"],
)
def get_ticket(ticket_id: UUID, actor: CurrentUserDep, session: SessionDep) -> TicketResponse:
    return TicketWorkflowService(session).get_ticket(ticket_id, actor=actor)


@router.post(
    "/tickets/{ticket_id}/claim",
    response_model=TicketResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["tickets"],
)
def claim_ticket(
    ticket_id: UUID,
    request: ClaimTicketRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> TicketResponse:
    return TicketWorkflowService(session).claim_ticket(
        ticket_id,
        request,
        actor=actor,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/tickets/{ticket_id}/transitions",
    response_model=TicketResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["tickets"],
)
def transition_ticket(
    ticket_id: UUID,
    request: TransitionTicketRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> TicketResponse:
    return TicketWorkflowService(session).transition_ticket(
        ticket_id,
        request,
        actor=actor,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/tickets/{ticket_id}/feedback",
    response_model=HumanFeedbackResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["tickets"],
)
def submit_feedback(
    ticket_id: UUID,
    request: HumanFeedbackRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> HumanFeedbackResponse:
    return TicketWorkflowService(session).submit_feedback(
        ticket_id,
        request,
        actor=actor,
        idempotency_key=idempotency_key,
    )


@router.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
def readiness(session: SessionDep) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.post(
    "/support/resolve",
    response_model=SupportResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["support"],
)
def resolve_support_request(
    request: SupportInput,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> SupportResponse:
    return SupportService(session).process(
        request,
        actor=actor,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/knowledge/search",
    response_model=KnowledgeSearchResponse,
    tags=["knowledge"],
)
def search_knowledge(
    request: KnowledgeSearchInput,
    session: SessionDep,
) -> KnowledgeSearchResponse:
    embedding_provider, reranker_provider = get_provider_bundle()
    return HybridRetrievalService(
        session,
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
    ).search(request)


@router.post(
    "/agent/resolve",
    response_model=AgentResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    tags=["agent"],
)
def resolve_agent_request(
    request: AgentRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> AgentResponse:
    embedding_provider, reranker_provider = get_provider_bundle()
    return AgentService(
        session,
        decision_provider=get_decision_provider(),
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
    ).resolve(request, actor=actor, idempotency_key=idempotency_key)


@router.post(
    "/agent/resolve/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "LangGraph node progress followed by one result event",
        },
        401: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    tags=["agent"],
)
def stream_agent_request(
    request: AgentRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> StreamingResponse:
    embedding_provider, reranker_provider = get_provider_bundle()
    service = AgentService(
        session,
        decision_provider=get_decision_provider(),
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
    )

    def event_stream() -> Iterator[str]:
        try:
            for event_name, payload in service.resolve_events(
                request,
                actor=actor,
                idempotency_key=idempotency_key,
            ):
                yield _sse_event(event_name, payload)
        except DomainError as error:
            yield _sse_event(
                "error",
                {"error": {"code": error.code, "message": str(error)}},
            )
        except Exception:
            yield _sse_event(
                "error",
                {
                    "error": {
                        "code": "unexpected_agent_failure",
                        "message": "Agent execution failed; retry or request human support.",
                    }
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
