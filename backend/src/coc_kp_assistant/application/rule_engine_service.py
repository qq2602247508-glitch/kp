from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from coc_kp_assistant.api.schemas import (
    ChaseAdvanceRequest,
    ChaseCreateRequest,
    ChaseParticipant,
    ChaseResponse,
    CombatRequest,
    EngineCitationResponse,
    EngineOperationResponse,
    InjuryRequest,
    RecoveryRequest,
    RuleOperationLogResponse,
    SanityLossRequest,
)
from coc_kp_assistant.application import service
from coc_kp_assistant.domain.rule_engines import (
    CHASE_CITATION,
    COMBAT_CITATION,
    INJURY_CITATION,
    RECOVERY_CITATION,
    SANITY_CITATION,
    WEAPON_BY_KEY,
    injury_state,
    recovery_amount,
    sanity_conditions,
)
from coc_kp_assistant.infrastructure.models import (
    CampaignRecord,
    CaseSessionRecord,
    ChaseRecord,
    InvestigatorRecord,
    RollRecord,
    RuleOperationRecord,
)


class InvalidRuleOperationError(Exception):
    pass


def _operation_response(
    record: RuleOperationRecord, investigator: InvestigatorRecord
) -> EngineOperationResponse:
    response = service._investigator_response(investigator)
    return EngineOperationResponse(
        operation_id=UUID(record.id),
        operation_type=record.operation_type,
        investigator=response,
        target=response if record.operation_type == "combat" else None,
        citation=EngineCitationResponse.model_validate(record.citation_data),
        created_at=record.created_at,
        **record.output_data,
    )


def _add_operation(
    session: Session,
    *,
    campaign_id: UUID,
    operation_type: str,
    subject_id: str,
    case_session_id: UUID | None,
    session_key: str | None,
    input_data: dict[str, Any],
    output_data: dict[str, Any],
    citation: dict[str, Any],
) -> RuleOperationRecord:
    record = RuleOperationRecord(
        campaign_id=str(campaign_id),
        subject_id=subject_id,
        case_session_id=str(case_session_id) if case_session_id else None,
        session_key=session_key,
        operation_type=operation_type,
        input_data=input_data,
        output_data=output_data,
        citation_data=citation,
    )
    session.add(record)
    session.flush()
    return record


def _validate_case_session(
    session: Session, campaign_id: UUID, case_session_id: UUID | None
) -> None:
    if case_session_id is None:
        return
    if session.scalar(
        select(CaseSessionRecord.id).where(
            CaseSessionRecord.id == str(case_session_id),
            CaseSessionRecord.campaign_id == str(campaign_id),
        )
    ) is None:
        raise InvalidRuleOperationError(
            "case session does not belong to this campaign"
        )


def _claim_investigator(
    session: Session,
    campaign_id: UUID,
    investigator_id: UUID,
    expected_version: int,
) -> tuple[InvestigatorRecord, dict[str, Any]]:
    before = service.get_investigator(session, campaign_id, investigator_id)
    record = service._claim_investigator_version(
        session, campaign_id, investigator_id, expected_version
    )
    return record, before.model_dump(mode="json")


def apply_sanity_loss(
    session: Session,
    campaign_id: UUID,
    investigator_id: UUID,
    payload: SanityLossRequest,
) -> EngineOperationResponse:
    _validate_case_session(session, campaign_id, payload.case_session_id)
    if payload.loss >= 5 and payload.intelligence_check_passed is None:
        raise InvalidRuleOperationError(
            "a 5+ sanity loss requires the recorded INT check outcome"
        )
    record, before = _claim_investigator(
        session, campaign_id, investigator_id, payload.expected_version
    )
    prior = session.scalars(
        select(RuleOperationRecord)
        .where(
            RuleOperationRecord.campaign_id == str(campaign_id),
            RuleOperationRecord.subject_id == str(investigator_id),
            RuleOperationRecord.session_key == payload.session_key,
            RuleOperationRecord.operation_type == "sanity_loss",
        )
        .order_by(RuleOperationRecord.created_at, RuleOperationRecord.id)
    ).all()
    applied_loss = min(record.sanity, payload.loss)
    session_loss = sum(int(item.output_data.get("loss", 0)) for item in prior) + applied_loss
    daily_start_sanity = (
        int(prior[0].output_data["sanity_before"]) if prior else record.sanity
    )
    record.sanity -= applied_loss
    record.conditions = sorted(
        sanity_conditions(
            starting_sanity=daily_start_sanity,
            single_loss=applied_loss,
            session_loss=session_loss,
            intelligence_check_passed=payload.intelligence_check_passed,
            existing=set(record.conditions),
        )
    )
    output = {
        "loss": applied_loss,
        "sanity_before": record.sanity + applied_loss,
        "session_sanity_loss": session_loss,
        "reason": payload.reason,
    }
    operation = _add_operation(
        session,
        campaign_id=campaign_id,
        operation_type="sanity_loss",
        subject_id=record.id,
        case_session_id=payload.case_session_id,
        session_key=payload.session_key,
        input_data=payload.model_dump(mode="json"),
        output_data=output,
        citation=SANITY_CITATION.as_dict(),
    )
    session.flush()
    service._audit(
        session,
        campaign_id=record.campaign_id,
        action="sanity_loss",
        entity_type="investigator",
        entity_id=record.id,
        expected_version=payload.expected_version,
        before=before,
        after=service._investigator_response(record).model_dump(mode="json"),
    )
    response = _operation_response(operation, record)
    session.commit()
    return response


def apply_injury(
    session: Session,
    campaign_id: UUID,
    investigator_id: UUID,
    payload: InjuryRequest,
) -> EngineOperationResponse:
    _validate_case_session(session, campaign_id, payload.case_session_id)
    record, before = _claim_investigator(
        session, campaign_id, investigator_id, payload.expected_version
    )
    maximum_hit_points = (record.constitution + record.size) // 10
    record.hit_points, conditions = injury_state(
        hit_points=record.hit_points,
        maximum_hit_points=maximum_hit_points,
        damage=payload.damage,
        existing=set(record.conditions),
    )
    record.conditions = sorted(conditions)
    output = {"damage_applied": payload.damage, "reason": payload.reason}
    operation = _add_operation(
        session,
        campaign_id=campaign_id,
        operation_type="injury",
        subject_id=record.id,
        case_session_id=payload.case_session_id,
        session_key=payload.session_key,
        input_data=payload.model_dump(mode="json"),
        output_data=output,
        citation=INJURY_CITATION.as_dict(),
    )
    session.flush()
    service._audit(
        session,
        campaign_id=record.campaign_id,
        action="injury",
        entity_type="investigator",
        entity_id=record.id,
        expected_version=payload.expected_version,
        before=before,
        after=service._investigator_response(record).model_dump(mode="json"),
    )
    response = _operation_response(operation, record)
    session.commit()
    return response


def apply_recovery(
    session: Session,
    campaign_id: UUID,
    investigator_id: UUID,
    payload: RecoveryRequest,
) -> EngineOperationResponse:
    _validate_case_session(session, campaign_id, payload.case_session_id)
    try:
        healing = recovery_amount(payload.care_type, payload.healing_roll)
    except ValueError as error:
        raise InvalidRuleOperationError(str(error)) from error
    if payload.care_type == "first_aid":
        recent = session.scalars(
            select(RuleOperationRecord)
            .where(
                RuleOperationRecord.campaign_id == str(campaign_id),
                RuleOperationRecord.subject_id == str(investigator_id),
                RuleOperationRecord.operation_type.in_(("injury", "combat", "recovery")),
            )
            .order_by(
                RuleOperationRecord.created_at.desc(),
                RuleOperationRecord.id.desc(),
            )
        ).all()
        for item in recent:
            if item.operation_type == "injury" or (
                item.operation_type == "combat"
                and int(item.output_data.get("damage_applied", 0)) > 0
            ):
                break
            if (
                item.operation_type == "recovery"
                and item.output_data.get("care_type") == "first_aid"
            ):
                raise InvalidRuleOperationError(
                    "first aid may be applied only once to the current injury"
                )
    record, before = _claim_investigator(
        session, campaign_id, investigator_id, payload.expected_version
    )
    maximum_hit_points = (record.constitution + record.size) // 10
    healed = min(healing, maximum_hit_points - record.hit_points)
    record.hit_points += healed
    if record.hit_points > 0:
        record.conditions = sorted(
            set(record.conditions).difference({"unconscious", "dying"})
        )
    output = {"healed": healed, "care_type": payload.care_type}
    operation = _add_operation(
        session,
        campaign_id=campaign_id,
        operation_type="recovery",
        subject_id=record.id,
        case_session_id=payload.case_session_id,
        session_key=payload.session_key,
        input_data=payload.model_dump(mode="json"),
        output_data=output,
        citation=RECOVERY_CITATION.as_dict(),
    )
    session.flush()
    service._audit(
        session,
        campaign_id=record.campaign_id,
        action="recovery",
        entity_type="investigator",
        entity_id=record.id,
        expected_version=payload.expected_version,
        before=before,
        after=service._investigator_response(record).model_dump(mode="json"),
    )
    response = _operation_response(operation, record)
    session.commit()
    return response


def resolve_combat(
    session: Session, campaign_id: UUID, payload: CombatRequest
) -> EngineOperationResponse:
    _validate_case_session(session, campaign_id, payload.case_session_id)
    weapon = WEAPON_BY_KEY.get(payload.weapon_key)
    if weapon is None:
        raise InvalidRuleOperationError("unknown COC7 weapon policy")
    if (
        not weapon.uses_damage_bonus
        and payload.rolled_damage > weapon.maximum_rolled_damage
    ):
        raise InvalidRuleOperationError("rolled damage exceeds the weapon policy")
    roll = session.scalar(
        select(RollRecord).where(
            RollRecord.id == str(payload.attack_roll_id),
            RollRecord.campaign_id == str(campaign_id),
            RollRecord.investigator_id == str(payload.attacker_id),
        )
    )
    if roll is None:
        raise InvalidRuleOperationError("attack roll does not belong to this attacker")
    if roll.skill_key != weapon.skill_key:
        raise InvalidRuleOperationError("attack roll skill does not match the weapon policy")
    hit = bool(roll.resolution_data.get("passed", False))
    target, before = _claim_investigator(
        session, campaign_id, payload.target_id, payload.target_expected_version
    )
    damage = payload.rolled_damage if hit else 0
    maximum_hit_points = (target.constitution + target.size) // 10
    target.hit_points, conditions = injury_state(
        hit_points=target.hit_points,
        maximum_hit_points=maximum_hit_points,
        damage=damage,
        existing=set(target.conditions),
    )
    target.conditions = sorted(conditions)
    output = {
        "hit": hit,
        "damage_applied": damage,
        "weapon_key": weapon.weapon_key,
        "attack_roll_id": str(payload.attack_roll_id),
    }
    operation = _add_operation(
        session,
        campaign_id=campaign_id,
        operation_type="combat",
        subject_id=target.id,
        case_session_id=payload.case_session_id,
        session_key=payload.session_key,
        input_data=payload.model_dump(mode="json"),
        output_data=output,
        citation=COMBAT_CITATION.as_dict(),
    )
    session.flush()
    service._audit(
        session,
        campaign_id=target.campaign_id,
        action="combat",
        entity_type="investigator",
        entity_id=target.id,
        expected_version=payload.target_expected_version,
        before=before,
        after=service._investigator_response(target).model_dump(mode="json"),
    )
    response = _operation_response(operation, target)
    session.commit()
    return response


def _chase_response(record: ChaseRecord) -> ChaseResponse:
    return ChaseResponse(
        chase_id=UUID(record.id),
        campaign_id=UUID(record.campaign_id),
        title=record.title,
        case_session_id=UUID(record.case_session_id) if record.case_session_id else None,
        session_key=record.session_key,
        status=record.status,
        participants=tuple(
            ChaseParticipant.model_validate(item) for item in record.participants
        ),
        version=record.version,
        citation=EngineCitationResponse.model_validate(CHASE_CITATION.as_dict()),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def create_chase(
    session: Session, campaign_id: UUID, payload: ChaseCreateRequest
) -> ChaseResponse:
    _validate_case_session(session, campaign_id, payload.case_session_id)
    if session.scalar(
        select(CampaignRecord.id).where(CampaignRecord.id == str(campaign_id))
    ) is None:
        raise service.EntityNotFoundError("campaign not found")
    requested_ids = {str(item.investigator_id) for item in payload.participants}
    found_ids = set(
        session.scalars(
            select(InvestigatorRecord.id).where(
                InvestigatorRecord.campaign_id == str(campaign_id),
                InvestigatorRecord.id.in_(requested_ids),
            )
        ).all()
    )
    if found_ids != requested_ids:
        raise InvalidRuleOperationError("chase participant does not belong to campaign")
    record = ChaseRecord(
        campaign_id=str(campaign_id),
        title=payload.title,
        case_session_id=(
            str(payload.case_session_id) if payload.case_session_id else None
        ),
        session_key=payload.session_key,
        status="active",
        participants=[item.model_dump(mode="json") for item in payload.participants],
    )
    session.add(record)
    session.flush()
    response = _chase_response(record)
    _add_operation(
        session,
        campaign_id=campaign_id,
        operation_type="chase_created",
        subject_id=record.id,
        case_session_id=payload.case_session_id,
        session_key=payload.session_key,
        input_data=payload.model_dump(mode="json"),
        output_data={"version": record.version, "participants": record.participants},
        citation=CHASE_CITATION.as_dict(),
    )
    service._audit(
        session,
        campaign_id=record.campaign_id,
        action="create",
        entity_type="chase",
        entity_id=record.id,
        after=response.model_dump(mode="json"),
    )
    session.commit()
    return response


def list_chases(session: Session, campaign_id: UUID) -> list[ChaseResponse]:
    if session.scalar(
        select(CampaignRecord.id).where(CampaignRecord.id == str(campaign_id))
    ) is None:
        raise service.EntityNotFoundError("campaign not found")
    records = session.scalars(
        select(ChaseRecord)
        .where(ChaseRecord.campaign_id == str(campaign_id))
        .order_by(ChaseRecord.created_at)
    ).all()
    return [_chase_response(record) for record in records]


def advance_chase(
    session: Session,
    campaign_id: UUID,
    chase_id: UUID,
    payload: ChaseAdvanceRequest,
) -> ChaseResponse:
    record = session.scalar(
        select(ChaseRecord).where(
            ChaseRecord.id == str(chase_id),
            ChaseRecord.campaign_id == str(campaign_id),
        )
    )
    if record is None:
        raise service.EntityNotFoundError("chase not found")
    before = _chase_response(record)
    move_by_id = {str(move.investigator_id): move.move_units for move in payload.moves}
    participants = [dict(item) for item in record.participants]
    participant_ids = {str(item["investigator_id"]) for item in participants}
    if not set(move_by_id) <= participant_ids:
        raise InvalidRuleOperationError("move references a non-participant")
    for item in participants:
        item["position"] = int(item["position"]) + move_by_id.get(
            str(item["investigator_id"]), 0
        )
    result = cast(
        CursorResult[Any],
        session.execute(
            update(ChaseRecord)
            .where(
                ChaseRecord.id == str(chase_id),
                ChaseRecord.campaign_id == str(campaign_id),
                ChaseRecord.version == payload.expected_version,
            )
            .values(
                participants=participants,
                version=payload.expected_version + 1,
            )
        ),
    )
    if result.rowcount != 1:
        session.rollback()
        raise service.VersionConflictError("chase version conflict")
    record = session.scalar(
        select(ChaseRecord).where(ChaseRecord.id == str(chase_id))
    )
    assert record is not None
    response = _chase_response(record)
    _add_operation(
        session,
        campaign_id=campaign_id,
        operation_type="chase_advanced",
        subject_id=record.id,
        case_session_id=(
            UUID(record.case_session_id) if record.case_session_id else None
        ),
        session_key=record.session_key,
        input_data=payload.model_dump(mode="json"),
        output_data={"version": record.version, "participants": participants},
        citation=CHASE_CITATION.as_dict(),
    )
    service._audit(
        session,
        campaign_id=record.campaign_id,
        action="advance",
        entity_type="chase",
        entity_id=record.id,
        expected_version=payload.expected_version,
        before=before.model_dump(mode="json"),
        after=response.model_dump(mode="json"),
    )
    session.commit()
    return response


def list_operations(
    session: Session, campaign_id: UUID
) -> list[RuleOperationLogResponse]:
    if session.scalar(
        select(CampaignRecord.id).where(CampaignRecord.id == str(campaign_id))
    ) is None:
        raise service.EntityNotFoundError("campaign not found")
    records = session.scalars(
        select(RuleOperationRecord)
        .where(RuleOperationRecord.campaign_id == str(campaign_id))
        .order_by(RuleOperationRecord.created_at, RuleOperationRecord.id)
        .limit(500)
    ).all()
    return [
        RuleOperationLogResponse(
            operation_id=UUID(record.id),
            campaign_id=UUID(record.campaign_id),
            subject_id=UUID(record.subject_id),
            case_session_id=(
                UUID(record.case_session_id) if record.case_session_id else None
            ),
            session_key=record.session_key,
            operation_type=record.operation_type,
            input_data=record.input_data,
            output_data=record.output_data,
            citation=EngineCitationResponse.model_validate(record.citation_data),
            created_at=record.created_at,
        )
        for record in records
    ]
