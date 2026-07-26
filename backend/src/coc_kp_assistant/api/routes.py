from collections.abc import Iterator
from typing import Annotated
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
    SkillsReplace,
)
from coc_kp_assistant.application import service
from coc_kp_assistant.domain.campaigns import CampaignCreate
from coc_kp_assistant.domain.investigators import InvestigatorCreate
from coc_kp_assistant.infrastructure.database import session_dependency

router = APIRouter(prefix="/api/v1")


def get_session(request: Request) -> Iterator[Session]:
    yield from session_dependency(request.app.state.session_factory)


DatabaseSession = Annotated[Session, Depends(get_session)]


def _not_found_or_conflict(error: Exception) -> HTTPException:
    if isinstance(error, service.EntityNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


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

