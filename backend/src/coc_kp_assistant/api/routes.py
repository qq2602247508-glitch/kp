from collections.abc import Iterator
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from coc_kp_assistant.api.schemas import (
    AuditResponse,
    BackstoryReplace,
    CampaignReplace,
    CampaignResponse,
    InvestigatorReplace,
    InvestigatorResponse,
    RecordedRollRequest,
    RecordedRollResponse,
    RuleAnswerRequest,
    RuleAnswerResponse,
    RuleCitationResponse,
    RuleSearchResponse,
    SkillsReplace,
)
from coc_kp_assistant.application import case_service, service
from coc_kp_assistant.domain.campaigns import CampaignCreate
from coc_kp_assistant.domain.case_state import (
    CaseEntityKind,
    CaseEntryCreate,
    CaseEntryReplace,
    CaseEntryResponse,
    PlayerCaseEntryResponse,
)
from coc_kp_assistant.domain.investigators import InvestigatorCreate
from coc_kp_assistant.infrastructure.database import session_dependency
from coc_kp_assistant.rag import IndexCompatibilityError, IndexIncompleteError
from coc_kp_assistant.rules import (
    GroundedAnswerUnavailableError,
    RuleQuery,
    RulesService,
    create_rules_service,
)

router = APIRouter(prefix="/api/v1")


def get_session(request: Request) -> Iterator[Session]:
    yield from session_dependency(request.app.state.session_factory)


DatabaseSession = Annotated[Session, Depends(get_session)]


def get_rules_service(request: Request) -> RulesService:
    existing = getattr(request.app.state, "rules_service", None)
    if existing is None:
        existing = create_rules_service(request.app.state.settings)
        request.app.state.rules_service = existing
    return cast(RulesService, existing)


RulesServiceDependency = Annotated[RulesService, Depends(get_rules_service)]


def _not_found_or_conflict(error: Exception) -> HTTPException:
    if isinstance(error, service.EntityNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


def _case_state_error(error: Exception) -> HTTPException:
    if isinstance(error, case_service.InvalidCaseStateError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        )
    return _not_found_or_conflict(error)


@router.post("/campaigns", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignCreate, session: DatabaseSession) -> CampaignResponse:
    return service.create_campaign(session, payload)


@router.get("/campaigns", response_model=list[CampaignResponse])
def list_campaigns(session: DatabaseSession) -> list[CampaignResponse]:
    return service.list_campaigns(session)


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: UUID, session: DatabaseSession) -> CampaignResponse:
    try:
        return service.get_campaign(session, campaign_id)
    except service.EntityNotFoundError as error:
        raise _not_found_or_conflict(error) from error


@router.put("/campaigns/{campaign_id}", response_model=CampaignResponse)
def replace_campaign(
    campaign_id: UUID, payload: CampaignReplace, session: DatabaseSession
) -> CampaignResponse:
    try:
        return service.replace_campaign(session, campaign_id, payload)
    except (service.EntityNotFoundError, service.VersionConflictError) as error:
        raise _not_found_or_conflict(error) from error


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(
    campaign_id: UUID,
    session: DatabaseSession,
    expected_version: Annotated[int, Query(ge=1)],
) -> Response:
    try:
        service.delete_campaign(session, campaign_id, expected_version)
    except (service.EntityNotFoundError, service.VersionConflictError) as error:
        raise _not_found_or_conflict(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/campaigns/{campaign_id}/case-state/{kind}",
    response_model=CaseEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_case_entry(
    campaign_id: UUID,
    kind: CaseEntityKind,
    payload: CaseEntryCreate,
    session: DatabaseSession,
) -> CaseEntryResponse:
    try:
        return case_service.create_entry(session, campaign_id, kind, payload)
    except (service.EntityNotFoundError, case_service.InvalidCaseStateError) as error:
        raise _case_state_error(error) from error


@router.get(
    "/campaigns/{campaign_id}/case-state/{kind}",
    response_model=list[CaseEntryResponse],
)
def list_case_entries(
    campaign_id: UUID,
    kind: CaseEntityKind,
    session: DatabaseSession,
) -> list[CaseEntryResponse]:
    try:
        return case_service.list_entries(session, campaign_id, kind)
    except service.EntityNotFoundError as error:
        raise _case_state_error(error) from error


@router.get(
    "/campaigns/{campaign_id}/case-state/{kind}/{entity_id}",
    response_model=CaseEntryResponse,
)
def get_case_entry(
    campaign_id: UUID,
    kind: CaseEntityKind,
    entity_id: UUID,
    session: DatabaseSession,
) -> CaseEntryResponse:
    try:
        return case_service.get_entry(session, campaign_id, kind, entity_id)
    except service.EntityNotFoundError as error:
        raise _case_state_error(error) from error


@router.get(
    "/campaigns/{campaign_id}/case-state/{kind}/{entity_id}/player-view",
    response_model=PlayerCaseEntryResponse,
)
def get_player_case_entry(
    campaign_id: UUID,
    kind: CaseEntityKind,
    entity_id: UUID,
    session: DatabaseSession,
) -> PlayerCaseEntryResponse:
    try:
        entry = case_service.get_entry(session, campaign_id, kind, entity_id)
    except service.EntityNotFoundError as error:
        raise _case_state_error(error) from error
    return case_service.player_projection(entry)


@router.put(
    "/campaigns/{campaign_id}/case-state/{kind}/{entity_id}",
    response_model=CaseEntryResponse,
)
def replace_case_entry(
    campaign_id: UUID,
    kind: CaseEntityKind,
    entity_id: UUID,
    payload: CaseEntryReplace,
    session: DatabaseSession,
) -> CaseEntryResponse:
    try:
        return case_service.replace_entry(session, campaign_id, kind, entity_id, payload)
    except (
        service.EntityNotFoundError,
        service.VersionConflictError,
        case_service.InvalidCaseStateError,
    ) as error:
        raise _case_state_error(error) from error


@router.delete(
    "/campaigns/{campaign_id}/case-state/{kind}/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_case_entry(
    campaign_id: UUID,
    kind: CaseEntityKind,
    entity_id: UUID,
    session: DatabaseSession,
    expected_version: Annotated[int, Query(ge=1)],
) -> Response:
    try:
        case_service.delete_entry(
            session, campaign_id, kind, entity_id, expected_version
        )
    except (service.EntityNotFoundError, service.VersionConflictError) as error:
        raise _case_state_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/campaigns/{campaign_id}/investigators",
    response_model=InvestigatorResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_investigator(
    campaign_id: UUID, payload: InvestigatorCreate, session: DatabaseSession
) -> InvestigatorResponse:
    try:
        return service.create_investigator(session, campaign_id, payload)
    except service.EntityNotFoundError as error:
        raise _not_found_or_conflict(error) from error


@router.get(
    "/campaigns/{campaign_id}/investigators",
    response_model=list[InvestigatorResponse],
)
def list_investigators(
    campaign_id: UUID, session: DatabaseSession
) -> list[InvestigatorResponse]:
    try:
        return service.list_investigators(session, campaign_id)
    except service.EntityNotFoundError as error:
        raise _not_found_or_conflict(error) from error


@router.get(
    "/campaigns/{campaign_id}/investigators/{investigator_id}",
    response_model=InvestigatorResponse,
)
def get_investigator(
    campaign_id: UUID, investigator_id: UUID, session: DatabaseSession
) -> InvestigatorResponse:
    try:
        return service.get_investigator(session, campaign_id, investigator_id)
    except service.EntityNotFoundError as error:
        raise _not_found_or_conflict(error) from error


@router.put(
    "/campaigns/{campaign_id}/investigators/{investigator_id}",
    response_model=InvestigatorResponse,
)
def replace_investigator(
    campaign_id: UUID,
    investigator_id: UUID,
    payload: InvestigatorReplace,
    session: DatabaseSession,
) -> InvestigatorResponse:
    try:
        return service.replace_investigator(session, campaign_id, investigator_id, payload)
    except (service.EntityNotFoundError, service.VersionConflictError) as error:
        raise _not_found_or_conflict(error) from error


@router.put(
    "/campaigns/{campaign_id}/investigators/{investigator_id}/skills",
    response_model=InvestigatorResponse,
)
def replace_skills(
    campaign_id: UUID,
    investigator_id: UUID,
    payload: SkillsReplace,
    session: DatabaseSession,
) -> InvestigatorResponse:
    try:
        return service.replace_skills(session, campaign_id, investigator_id, payload)
    except (service.EntityNotFoundError, service.VersionConflictError) as error:
        raise _not_found_or_conflict(error) from error


@router.put(
    "/campaigns/{campaign_id}/investigators/{investigator_id}/backstory",
    response_model=InvestigatorResponse,
)
def replace_backstory(
    campaign_id: UUID,
    investigator_id: UUID,
    payload: BackstoryReplace,
    session: DatabaseSession,
) -> InvestigatorResponse:
    try:
        return service.replace_backstory(session, campaign_id, investigator_id, payload)
    except (service.EntityNotFoundError, service.VersionConflictError) as error:
        raise _not_found_or_conflict(error) from error


@router.delete(
    "/campaigns/{campaign_id}/investigators/{investigator_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_investigator(
    campaign_id: UUID,
    investigator_id: UUID,
    session: DatabaseSession,
    expected_version: Annotated[int, Query(ge=1)],
) -> Response:
    try:
        service.delete_investigator(session, campaign_id, investigator_id, expected_version)
    except (service.EntityNotFoundError, service.VersionConflictError) as error:
        raise _not_found_or_conflict(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/rolls", response_model=RecordedRollResponse, status_code=status.HTTP_201_CREATED
)
def record_roll(payload: RecordedRollRequest, session: DatabaseSession) -> RecordedRollResponse:
    try:
        return service.record_roll(session, payload)
    except service.EntityNotFoundError as error:
        raise _not_found_or_conflict(error) from error


@router.get("/campaigns/{campaign_id}/audits", response_model=list[AuditResponse])
def list_audits(campaign_id: UUID, session: DatabaseSession) -> list[AuditResponse]:
    try:
        return service.list_audits(session, campaign_id)
    except service.EntityNotFoundError as error:
        raise _not_found_or_conflict(error) from error


@router.get("/rules/search", response_model=RuleSearchResponse)
def search_rules(
    rules_service: RulesServiceDependency,
    q: Annotated[str, Query(min_length=1, max_length=1000)],
    source_pack: Annotated[list[str] | None, Query()] = None,
    edition: Annotated[list[str] | None, Query()] = None,
    module: Annotated[list[str] | None, Query()] = None,
    era: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> RuleSearchResponse:
    query = RuleQuery(
        query=q,
        source_pack_ids=tuple(source_pack or ()),
        editions=tuple(edition or ()),
        modules=tuple(module or ()),
        eras=tuple(era or ()),
        limit=limit,
    )
    try:
        results = rules_service.search(query)
    except (IndexCompatibilityError, IndexIncompleteError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="COC7 rule index is unavailable or incompatible",
        ) from error
    return RuleSearchResponse(
        query=query.query,
        results=tuple(
            RuleCitationResponse.model_validate(result, from_attributes=True)
            for result in results
        ),
    )


@router.post("/rules/answer", response_model=RuleAnswerResponse)
def answer_rules(
    payload: RuleAnswerRequest,
    rules_service: RulesServiceDependency,
) -> RuleAnswerResponse:
    query = RuleQuery(
        query=payload.question,
        source_pack_ids=payload.source_pack_ids,
        editions=payload.editions,
        modules=payload.modules,
        eras=payload.eras,
        limit=payload.limit,
    )
    try:
        answer = rules_service.answer(query)
    except GroundedAnswerUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="本地 qwen3:30b-instruct 模型不可用或响应超时",
        ) from error
    except (IndexCompatibilityError, IndexIncompleteError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="COC7 rule index is unavailable or incompatible",
        ) from error
    return RuleAnswerResponse(
        question=query.query,
        answer=answer.answer,
        citations=tuple(
            RuleCitationResponse.model_validate(citation, from_attributes=True)
            for citation in answer.citations
        ),
        abstained=answer.abstained,
        reason=answer.reason,
    )
