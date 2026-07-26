from collections.abc import Iterator
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from coc_kp_assistant.api.schemas import (
    AuditResponse,
    BackstoryReplace,
    BackupCreateRequest,
    BackupVerifyRequest,
    CampaignReplace,
    CampaignResponse,
    ChaseAdvanceRequest,
    ChaseCreateRequest,
    ChaseResponse,
    CombatRequest,
    DyingCheckRequest,
    EngineCitationResponse,
    EngineOperationResponse,
    InjuryRequest,
    InsanityTransitionRequest,
    InvestigatorReplace,
    InvestigatorResponse,
    RecordedRollRequest,
    RecordedRollResponse,
    RecoveryRequest,
    RuleAnswerRequest,
    RuleAnswerResponse,
    RuleCitationResponse,
    RuleOperationLogResponse,
    RuleSearchResponse,
    SanityLossRequest,
    SkillImprovementRequest,
    SkillsReplace,
    SourcePackSelectionReplace,
    WeaponPolicyResponse,
)
from coc_kp_assistant.application import (
    ai_kp_service,
    case_service,
    delivery_service,
    rule_engine_service,
    service,
)
from coc_kp_assistant.domain.ai_kp import (
    AIKPRequest,
    AIKPResponse,
    AIProposalResponse,
    ProposalAuditResponse,
    ProposalDecision,
)
from coc_kp_assistant.domain.campaigns import CampaignCreate
from coc_kp_assistant.domain.case_state import (
    CaseEntityKind,
    CaseEntryCreate,
    CaseEntryReplace,
    CaseEntryResponse,
    PlayerCaseEntryResponse,
)
from coc_kp_assistant.domain.investigators import InvestigatorCreate
from coc_kp_assistant.domain.rule_engines import WEAPONS
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


def get_ai_kp_orchestrator(
    request: Request,
) -> ai_kp_service.AIKPOrchestrator:
    existing = getattr(request.app.state, "ai_kp_orchestrator", None)
    if existing is None:
        rules_service = get_rules_service(request)

        def read_rules(
            question: str, source_pack_ids: tuple[str, ...]
        ) -> list[dict[str, object]]:
            citations = rules_service.search(
                RuleQuery(
                    query=question,
                    source_pack_ids=source_pack_ids,
                    limit=8,
                )
            )
            return [
                {
                    "citation_id": item.citation_id,
                    "excerpt": item.excerpt,
                    "score": item.score,
                    "source_pack": item.source_pack,
                    "edition": item.edition,
                    "module": item.module,
                    "era": list(item.era),
                    "filename": item.filename,
                    "page": item.page,
                    "section": item.section,
                    "checksum": item.checksum,
                }
                for item in citations
            ]

        existing = ai_kp_service.AIKPOrchestrator(
            provider=ai_kp_service.OllamaAIKPProvider(),
            rules_reader=read_rules,
            source_pack_resolver=lambda session, campaign_id: (
                delivery_service.campaign_source_packs(
                    session, request.app.state.settings, campaign_id
                )["enabled_source_pack_ids"]
            ),
            proposal_ttl_minutes=request.app.state.settings.ai_kp_proposal_ttl_minutes,
        )
        request.app.state.ai_kp_orchestrator = existing
    return cast(ai_kp_service.AIKPOrchestrator, existing)


AIKPDependency = Annotated[
    ai_kp_service.AIKPOrchestrator, Depends(get_ai_kp_orchestrator)
]


def _not_found_or_conflict(error: Exception) -> HTTPException:
    if isinstance(error, service.EntityNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


def _case_state_error(error: Exception) -> HTTPException:
    if isinstance(error, case_service.InvalidCaseStateError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    return _not_found_or_conflict(error)


def _rule_engine_error(error: Exception) -> HTTPException:
    if isinstance(error, rule_engine_service.InvalidRuleOperationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    return _not_found_or_conflict(error)


@router.post("/campaigns", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate, request: Request, session: DatabaseSession
) -> CampaignResponse:
    try:
        enabled = delivery_service.validated_campaign_source_pack_ids(
            request.app.state.settings,
            payload.era,
            list(payload.enabled_source_pack_ids),
        )
    except delivery_service.DeliveryValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return service.create_campaign(
        session, payload.model_copy(update={"enabled_source_pack_ids": tuple(enabled)})
    )


@router.get("/campaigns", response_model=list[CampaignResponse])
def list_campaigns(request: Request, session: DatabaseSession) -> list[CampaignResponse]:
    campaigns = service.list_campaigns(session)
    try:
        for campaign in campaigns:
            delivery_service.campaign_source_packs(
                session, request.app.state.settings, campaign.campaign_id
            )
    except delivery_service.DeliveryValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return campaigns


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
def get_campaign(
    campaign_id: UUID, request: Request, session: DatabaseSession
) -> CampaignResponse:
    try:
        campaign = service.get_campaign(session, campaign_id)
        delivery_service.campaign_source_packs(
            session, request.app.state.settings, campaign_id
        )
        return campaign
    except delivery_service.DeliveryValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except service.EntityNotFoundError as error:
        raise _not_found_or_conflict(error) from error


@router.put("/campaigns/{campaign_id}", response_model=CampaignResponse)
def replace_campaign(
    campaign_id: UUID,
    payload: CampaignReplace,
    request: Request,
    session: DatabaseSession,
) -> CampaignResponse:
    try:
        enabled = delivery_service.validated_campaign_source_pack_ids(
            request.app.state.settings,
            payload.era,
            list(payload.enabled_source_pack_ids),
        )
        return service.replace_campaign(
            session,
            campaign_id,
            payload.model_copy(update={"enabled_source_pack_ids": tuple(enabled)}),
        )
    except delivery_service.DeliveryValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
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
        case_service.delete_entry(session, campaign_id, kind, entity_id, expected_version)
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
def list_investigators(campaign_id: UUID, session: DatabaseSession) -> list[InvestigatorResponse]:
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
    "/campaigns/{campaign_id}/investigators/{investigator_id}/sanity-loss",
    response_model=EngineOperationResponse,
)
def apply_sanity_loss(
    campaign_id: UUID,
    investigator_id: UUID,
    payload: SanityLossRequest,
    session: DatabaseSession,
) -> EngineOperationResponse:
    try:
        return rule_engine_service.apply_sanity_loss(session, campaign_id, investigator_id, payload)
    except (
        service.EntityNotFoundError,
        service.VersionConflictError,
        rule_engine_service.InvalidRuleOperationError,
    ) as error:
        raise _rule_engine_error(error) from error


@router.post(
    "/campaigns/{campaign_id}/investigators/{investigator_id}/injury",
    response_model=EngineOperationResponse,
)
def apply_injury(
    campaign_id: UUID,
    investigator_id: UUID,
    payload: InjuryRequest,
    session: DatabaseSession,
) -> EngineOperationResponse:
    try:
        return rule_engine_service.apply_injury(session, campaign_id, investigator_id, payload)
    except (
        service.EntityNotFoundError,
        service.VersionConflictError,
        rule_engine_service.InvalidRuleOperationError,
    ) as error:
        raise _rule_engine_error(error) from error


@router.post(
    "/campaigns/{campaign_id}/investigators/{investigator_id}/dying-check",
    response_model=EngineOperationResponse,
)
def dying_check(
    campaign_id: UUID, investigator_id: UUID, payload: DyingCheckRequest, session: DatabaseSession
) -> EngineOperationResponse:
    try:
        return rule_engine_service.apply_dying_check(session, campaign_id, investigator_id, payload)
    except (
        service.EntityNotFoundError,
        service.VersionConflictError,
        rule_engine_service.InvalidRuleOperationError,
    ) as error:
        raise _rule_engine_error(error) from error


@router.post(
    "/campaigns/{campaign_id}/investigators/{investigator_id}/insanity-transition",
    response_model=EngineOperationResponse,
)
def insanity_transition(
    campaign_id: UUID,
    investigator_id: UUID,
    payload: InsanityTransitionRequest,
    session: DatabaseSession,
) -> EngineOperationResponse:
    try:
        return rule_engine_service.apply_insanity_transition(
            session, campaign_id, investigator_id, payload
        )
    except (
        service.EntityNotFoundError,
        service.VersionConflictError,
        rule_engine_service.InvalidRuleOperationError,
    ) as error:
        raise _rule_engine_error(error) from error


@router.post(
    "/campaigns/{campaign_id}/investigators/{investigator_id}/recovery",
    response_model=EngineOperationResponse,
)
def apply_recovery(
    campaign_id: UUID,
    investigator_id: UUID,
    payload: RecoveryRequest,
    session: DatabaseSession,
) -> EngineOperationResponse:
    try:
        return rule_engine_service.apply_recovery(session, campaign_id, investigator_id, payload)
    except (
        service.EntityNotFoundError,
        service.VersionConflictError,
        rule_engine_service.InvalidRuleOperationError,
    ) as error:
        raise _rule_engine_error(error) from error


@router.get("/rule-engines/weapons", response_model=list[WeaponPolicyResponse])
def list_weapons() -> list[WeaponPolicyResponse]:
    return [
        WeaponPolicyResponse(
            weapon_key=weapon.weapon_key,
            name=weapon.name,
            damage_notation=weapon.damage_notation,
            maximum_rolled_damage=weapon.maximum_rolled_damage,
            skill_key=weapon.skill_key,
            uses_damage_bonus=weapon.uses_damage_bonus,
            citation=EngineCitationResponse.model_validate(weapon.citation.as_dict()),
            citations=tuple(
                EngineCitationResponse.model_validate(citation.as_dict())
                for citation in weapon.citations
            ),
        )
        for weapon in WEAPONS
    ]


@router.post(
    "/campaigns/{campaign_id}/combat/resolve",
    response_model=EngineOperationResponse,
)
def resolve_combat(
    campaign_id: UUID,
    payload: CombatRequest,
    session: DatabaseSession,
) -> EngineOperationResponse:
    try:
        return rule_engine_service.resolve_combat(session, campaign_id, payload)
    except (
        service.EntityNotFoundError,
        service.VersionConflictError,
        rule_engine_service.InvalidRuleOperationError,
    ) as error:
        raise _rule_engine_error(error) from error


@router.post(
    "/campaigns/{campaign_id}/investigators/{investigator_id}/skill-improvement",
    response_model=EngineOperationResponse,
)
def apply_skill_improvement(
    campaign_id: UUID,
    investigator_id: UUID,
    payload: SkillImprovementRequest,
    session: DatabaseSession,
) -> EngineOperationResponse:
    try:
        return rule_engine_service.apply_skill_improvement(
            session, campaign_id, investigator_id, payload
        )
    except (
        service.EntityNotFoundError,
        service.VersionConflictError,
        rule_engine_service.InvalidRuleOperationError,
    ) as error:
        raise _rule_engine_error(error) from error


@router.post(
    "/campaigns/{campaign_id}/chases",
    response_model=ChaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chase(
    campaign_id: UUID,
    payload: ChaseCreateRequest,
    session: DatabaseSession,
) -> ChaseResponse:
    try:
        return rule_engine_service.create_chase(session, campaign_id, payload)
    except (
        service.EntityNotFoundError,
        rule_engine_service.InvalidRuleOperationError,
    ) as error:
        raise _rule_engine_error(error) from error


@router.get("/campaigns/{campaign_id}/chases", response_model=list[ChaseResponse])
def list_chases(campaign_id: UUID, session: DatabaseSession) -> list[ChaseResponse]:
    try:
        return rule_engine_service.list_chases(session, campaign_id)
    except service.EntityNotFoundError as error:
        raise _rule_engine_error(error) from error


@router.post(
    "/campaigns/{campaign_id}/chases/{chase_id}/advance",
    response_model=ChaseResponse,
)
def advance_chase(
    campaign_id: UUID,
    chase_id: UUID,
    payload: ChaseAdvanceRequest,
    session: DatabaseSession,
) -> ChaseResponse:
    try:
        return rule_engine_service.advance_chase(session, campaign_id, chase_id, payload)
    except (
        service.EntityNotFoundError,
        service.VersionConflictError,
        rule_engine_service.InvalidRuleOperationError,
    ) as error:
        raise _rule_engine_error(error) from error


@router.get(
    "/campaigns/{campaign_id}/rule-operations",
    response_model=list[RuleOperationLogResponse],
)
def list_rule_operations(
    campaign_id: UUID, session: DatabaseSession
) -> list[RuleOperationLogResponse]:
    try:
        return rule_engine_service.list_operations(session, campaign_id)
    except service.EntityNotFoundError as error:
        raise _rule_engine_error(error) from error


@router.post("/rolls", response_model=RecordedRollResponse, status_code=status.HTTP_201_CREATED)
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
            RuleCitationResponse.model_validate(result, from_attributes=True) for result in results
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


@router.post(
    "/campaigns/{campaign_id}/ai-kp/ask",
    response_model=AIKPResponse,
)
def ask_ai_kp(
    campaign_id: UUID,
    payload: AIKPRequest,
    session: DatabaseSession,
    orchestrator: AIKPDependency,
) -> AIKPResponse:
    try:
        return orchestrator.ask(session, campaign_id, payload)
    except service.EntityNotFoundError as error:
        raise _not_found_or_conflict(error) from error
    except ai_kp_service.AIKPUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="本地 qwen3:30b-instruct 或 COC7 规则索引不可用",
        ) from error
    except (
        ai_kp_service.InvalidAIOutputError,
        ai_kp_service.PrivateTruthLeakError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get(
    "/campaigns/{campaign_id}/ai-kp/proposals",
    response_model=list[AIProposalResponse],
)
def list_ai_kp_proposals(
    campaign_id: UUID,
    session: DatabaseSession,
    proposal_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[AIProposalResponse]:
    try:
        return ai_kp_service.list_proposals(
            session, campaign_id, status=proposal_status
        )
    except service.EntityNotFoundError as error:
        raise _not_found_or_conflict(error) from error
    except ai_kp_service.InvalidAIOutputError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@router.get(
    "/campaigns/{campaign_id}/ai-kp/proposal-audits",
    response_model=list[ProposalAuditResponse],
)
def list_ai_kp_proposal_audits(
    campaign_id: UUID,
    session: DatabaseSession,
) -> list[ProposalAuditResponse]:
    try:
        return ai_kp_service.list_proposal_audits(session, campaign_id)
    except service.EntityNotFoundError as error:
        raise _not_found_or_conflict(error) from error


@router.post(
    "/campaigns/{campaign_id}/ai-kp/proposals/{proposal_id}/decision",
    response_model=AIProposalResponse,
)
def decide_ai_kp_proposal(
    campaign_id: UUID,
    proposal_id: UUID,
    payload: ProposalDecision,
    session: DatabaseSession,
) -> AIProposalResponse:
    try:
        return ai_kp_service.decide_proposal(
            session, campaign_id, proposal_id, payload
        )
    except (
        service.EntityNotFoundError,
        service.VersionConflictError,
    ) as error:
        raise _not_found_or_conflict(error) from error
    except (
        case_service.InvalidCaseStateError,
        ai_kp_service.InvalidAIOutputError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@router.get("/delivery/readiness")
def delivery_readiness(request: Request, session: DatabaseSession) -> dict[str, Any]:
    return delivery_service.readiness(session, request.app.state.settings)


@router.get("/campaigns/{campaign_id}/source-packs")
def get_campaign_source_packs(
    campaign_id: UUID, request: Request, session: DatabaseSession
) -> dict[str, Any]:
    try:
        return delivery_service.campaign_source_packs(
            session, request.app.state.settings, campaign_id
        )
    except delivery_service.DeliveryValidationError as error:
        code = status.HTTP_404_NOT_FOUND if str(error) == "campaign not found" else 422
        raise HTTPException(status_code=code, detail=str(error)) from error


@router.put("/campaigns/{campaign_id}/source-packs")
def put_campaign_source_packs(
    campaign_id: UUID,
    payload: SourcePackSelectionReplace,
    request: Request,
    session: DatabaseSession,
) -> dict[str, Any]:
    try:
        return delivery_service.replace_campaign_source_packs(
            session,
            request.app.state.settings,
            campaign_id,
            expected_version=payload.expected_version,
            enabled_source_pack_ids=list(payload.enabled_source_pack_ids),
        )
    except delivery_service.DeliveryConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except delivery_service.DeliveryValidationError as error:
        code = status.HTTP_404_NOT_FOUND if str(error) == "campaign not found" else 422
        raise HTTPException(status_code=code, detail=str(error)) from error


@router.get("/campaigns/{campaign_id}/export")
def export_campaign(campaign_id: UUID, session: DatabaseSession) -> dict[str, Any]:
    try:
        return delivery_service.export_campaign(session, campaign_id)
    except delivery_service.DeliveryValidationError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/imports/campaign", status_code=status.HTTP_201_CREATED)
def import_campaign(
    payload: dict[str, Any], request: Request, session: DatabaseSession
) -> dict[str, str]:
    try:
        campaign_id = delivery_service.import_campaign(
            session, request.app.state.settings, payload
        )
    except delivery_service.DeliveryConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except delivery_service.DeliveryValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return {"campaign_id": campaign_id, "status": "imported"}


@router.post("/delivery/backups", status_code=status.HTTP_201_CREATED)
def create_delivery_backup(
    payload: BackupCreateRequest, request: Request
) -> dict[str, Any]:
    try:
        return delivery_service.create_backup(
            request.app.state.engine,
            request.app.state.settings,
            payload.destination,
        )
    except delivery_service.DeliveryConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except delivery_service.DeliveryValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@router.post("/delivery/backups/verify")
def verify_delivery_backup(payload: BackupVerifyRequest) -> dict[str, Any]:
    try:
        return delivery_service.verify_backup(payload.path)
    except delivery_service.DeliveryValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
