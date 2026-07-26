from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from coc_kp_assistant.api.schemas import (
    ChaseAdvanceRequest,
    ChaseCreateRequest,
    ChaseParticipantState,
    ChaseResponse,
    CombatRequest,
    DyingCheckRequest,
    EngineCitationResponse,
    EngineOperationResponse,
    InjuryRequest,
    InsanityTransitionRequest,
    RecoveryRequest,
    RuleOperationLogResponse,
    SanityLossRequest,
)
from coc_kp_assistant.application import service
from coc_kp_assistant.domain.rule_engines import (
    CHASE_BARRIERS_CITATION,
    CHASE_CITATIONS,
    CHASE_HAZARDS_CITATION,
    COMBAT_CITATION,
    CORE_CHECKSUM,
    INJURY_CITATION,
    RECOVERY_CITATION,
    RECOVERY_CONTEXT_CITATION,
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


def _citation_items(data: dict[str, Any]) -> tuple[EngineCitationResponse, ...]:
    """Read current {items: [...]} storage and pre-list legacy citation records."""
    raw_items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        legacy_id = data.get("citation_id")
        legacy_by_id = {
            "coc7e.core.sanity-loss-and-insanity": (SANITY_CITATION,),
            "coc7e.core.damage-major-wounds-and-dying": (INJURY_CITATION,),
            "coc7e.core.healing-and-recovery": (
                RECOVERY_CITATION,
                RECOVERY_CONTEXT_CITATION,
            ),
            "coc7e.core.combat-and-damage": (COMBAT_CITATION,),
            "coc7e.core.chases-movement-actions": CHASE_CITATIONS,
        }
        legacy = legacy_by_id.get(legacy_id) if isinstance(legacy_id, str) else None
        if legacy is not None:
            return tuple(
                EngineCitationResponse.model_validate(citation.as_dict()) for citation in legacy
            )
        raw_items = [data]
    return tuple(
        EngineCitationResponse.model_validate(
            {
                "edition": "7e",
                "module": "core",
                "era": [],
                "checksum": CORE_CHECKSUM,
                **item,
            }
        )
        for item in raw_items
    )


def _citation_data(*citations: Any) -> dict[str, list[dict[str, Any]]]:
    return {"items": [citation.as_dict() for citation in citations]}


def _operation_response(
    record: RuleOperationRecord, investigator: InvestigatorRecord
) -> EngineOperationResponse:
    response = service._investigator_response(investigator)
    citations = _citation_items(record.citation_data)
    return EngineOperationResponse(
        operation_id=UUID(record.id),
        operation_type=record.operation_type,
        investigator=response,
        target=response if record.operation_type == "combat" else None,
        citations=citations,
        citation=citations[0],
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
    citations: tuple[Any, ...],
) -> RuleOperationRecord:
    record = RuleOperationRecord(
        campaign_id=str(campaign_id),
        subject_id=subject_id,
        case_session_id=str(case_session_id) if case_session_id else None,
        session_key=session_key,
        operation_type=operation_type,
        input_data=input_data,
        output_data=output_data,
        citation_data=_citation_data(*citations),
    )
    session.add(record)
    session.flush()
    return record


def _validate_case_session(
    session: Session, campaign_id: UUID, case_session_id: UUID | None
) -> None:
    if case_session_id is None:
        return
    if (
        session.scalar(
            select(CaseSessionRecord.id).where(
                CaseSessionRecord.id == str(case_session_id),
                CaseSessionRecord.campaign_id == str(campaign_id),
            )
        )
        is None
    ):
        raise InvalidRuleOperationError("case session does not belong to this campaign")


def _required_case_session(session: Session, campaign_id: UUID, case_session_id: UUID) -> None:
    _validate_case_session(session, campaign_id, case_session_id)


def _roll_for(
    session: Session,
    *,
    roll_id: UUID,
    campaign_id: UUID,
    investigator_id: UUID,
    case_session_id: UUID,
    skill_key: str | None = None,
    target: int | None = None,
) -> RollRecord:
    roll = session.scalar(
        select(RollRecord).where(
            RollRecord.id == str(roll_id),
            RollRecord.campaign_id == str(campaign_id),
            RollRecord.investigator_id == str(investigator_id),
            RollRecord.case_session_id == str(case_session_id),
        )
    )
    if roll is None:
        raise InvalidRuleOperationError(
            "recorded roll does not match campaign, investigator, and case session"
        )
    if skill_key is not None and roll.skill_key != skill_key:
        raise InvalidRuleOperationError("recorded roll skill does not match the required check")
    if target is not None and int(roll.request_data.get("target_value", -1)) != target:
        raise InvalidRuleOperationError("recorded roll target does not match the current value")
    return roll


def _passed(roll: RollRecord) -> bool:
    return bool(roll.resolution_data.get("passed", False))


def _current_skill(record: InvestigatorRecord, skill_key: str) -> int:
    for skill in record.skills:
        if skill.skill_key == skill_key:
            return skill.current_value
    raise InvalidRuleOperationError("investigator does not have the required skill")


def _stored_damage_bonus_max(record: InvestigatorRecord) -> int:
    """Return the maximum COC7 damage bonus from stored STR+SIZ, never profile text."""
    total = record.strength + record.size
    if total <= 64:
        return -2
    if total <= 84:
        return -1
    if total <= 124:
        return 0
    if total <= 164:
        return 4
    if total <= 204:
        return 6
    # COC7 continues at one additional D6 for each 80 points above 205.
    dice = 2 + (total - 205) // 80
    return dice * 6


def _roll_already_consumed(
    session: Session, *, operation_type: str, roll_id: UUID, json_path: Any
) -> bool:
    consumed = select(RuleOperationRecord.id).where(
        RuleOperationRecord.operation_type == operation_type,
        json_path.as_string() == str(roll_id),
    )
    return session.scalar(consumed) is not None


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
    _required_case_session(session, campaign_id, payload.case_session_id)
    if payload.loss >= 5 and payload.intelligence_roll_id is None:
        raise InvalidRuleOperationError("a 5+ sanity loss requires the recorded INT check outcome")
    record, before = _claim_investigator(
        session, campaign_id, investigator_id, payload.expected_version
    )
    intelligence_passed: bool | None = None
    if payload.intelligence_roll_id is not None:
        intelligence_roll = _roll_for(
            session,
            roll_id=payload.intelligence_roll_id,
            campaign_id=campaign_id,
            investigator_id=investigator_id,
            case_session_id=payload.case_session_id,
            skill_key="intelligence",
            target=record.intelligence,
        )
        if _roll_already_consumed(
            session,
            operation_type="sanity_loss",
            roll_id=payload.intelligence_roll_id,
            json_path=RuleOperationRecord.input_data["intelligence_roll_id"],
        ):
            raise InvalidRuleOperationError("intelligence roll has already been consumed")
        intelligence_passed = _passed(intelligence_roll)
    prior = session.scalars(
        select(RuleOperationRecord)
        .where(
            RuleOperationRecord.campaign_id == str(campaign_id),
            RuleOperationRecord.subject_id == str(investigator_id),
            RuleOperationRecord.case_session_id == str(payload.case_session_id),
            RuleOperationRecord.operation_type == "sanity_loss",
        )
        .order_by(RuleOperationRecord.created_at, RuleOperationRecord.id)
    ).all()
    applied_loss = min(record.sanity, payload.loss)
    session_loss = sum(int(item.output_data.get("loss", 0)) for item in prior) + applied_loss
    daily_start_sanity = int(prior[0].output_data["sanity_before"]) if prior else record.sanity
    record.sanity -= applied_loss
    record.conditions = sorted(
        sanity_conditions(
            starting_sanity=daily_start_sanity,
            single_loss=applied_loss,
            session_loss=session_loss,
            intelligence_check_passed=intelligence_passed,
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
        citations=(SANITY_CITATION,),
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
    _required_case_session(session, campaign_id, payload.case_session_id)
    record, before = _claim_investigator(
        session, campaign_id, investigator_id, payload.expected_version
    )
    if "dead" in record.conditions:
        raise InvalidRuleOperationError(
            "a dead investigator cannot receive further engine injury changes"
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
        citations=(INJURY_CITATION,),
    )
    output["injury_id"] = operation.id
    operation.output_data = output
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
    _required_case_session(session, campaign_id, payload.case_session_id)
    injury = session.scalar(
        select(RuleOperationRecord).where(
            RuleOperationRecord.id == str(payload.injury_id),
            RuleOperationRecord.campaign_id == str(campaign_id),
            RuleOperationRecord.subject_id == str(investigator_id),
            RuleOperationRecord.operation_type == "injury",
        )
    )
    if injury is None or int(injury.output_data.get("damage_applied", 0)) <= 0:
        raise InvalidRuleOperationError(
            "injury_id must identify a damaging injury for this investigator"
        )
    duplicate_care = select(RuleOperationRecord.id).where(
        RuleOperationRecord.campaign_id == str(campaign_id),
        RuleOperationRecord.subject_id == str(investigator_id),
        RuleOperationRecord.operation_type == "recovery",
        RuleOperationRecord.input_data["injury_id"].as_string() == str(payload.injury_id),
        RuleOperationRecord.output_data["care_type"].as_string() == payload.care_type,
    )
    if session.scalar(duplicate_care) is not None:
        raise InvalidRuleOperationError("this care type has already been applied to the injury")
    record, before = _claim_investigator(
        session, campaign_id, investigator_id, payload.expected_version
    )
    if "dead" in record.conditions:
        raise InvalidRuleOperationError("a dead investigator cannot recover")
    if payload.care_type == "first_aid":
        if payload.first_aid_roll_id is None:
            raise InvalidRuleOperationError("first aid recovery requires a recorded first_aid roll")
        if _roll_already_consumed(
            session,
            operation_type="recovery",
            roll_id=payload.first_aid_roll_id,
            json_path=RuleOperationRecord.input_data["first_aid_roll_id"],
        ) or _roll_already_consumed(
            session,
            operation_type="stabilize",
            roll_id=payload.first_aid_roll_id,
            json_path=RuleOperationRecord.input_data["first_aid_roll_id"],
        ):
            raise InvalidRuleOperationError("first aid roll has already been consumed")
        roll = _roll_for(
            session,
            roll_id=payload.first_aid_roll_id,
            campaign_id=campaign_id,
            investigator_id=investigator_id,
            case_session_id=payload.case_session_id,
            skill_key="first_aid",
            target=_current_skill(record, "first_aid"),
        )
        if not _passed(roll):
            raise InvalidRuleOperationError("first aid roll must pass")
        if "dying" in record.conditions:
            conditions = set(record.conditions)
            conditions.discard("dying")
            conditions.add("stabilized")
            record.hit_points = 1
            record.conditions = sorted(conditions)
            output = {"healed": 1, "care_type": "first_aid", "stabilized": True}
            operation = _add_operation(
                session,
                campaign_id=campaign_id,
                operation_type="stabilize",
                subject_id=record.id,
                case_session_id=payload.case_session_id,
                session_key=payload.session_key,
                input_data=payload.model_dump(mode="json"),
                output_data=output,
                citations=(INJURY_CITATION, RECOVERY_CITATION),
            )
            session.flush()
            service._audit(
                session,
                campaign_id=record.campaign_id,
                action="stabilize",
                entity_type="investigator",
                entity_id=record.id,
                expected_version=payload.expected_version,
                before=before,
                after=service._investigator_response(record).model_dump(mode="json"),
            )
            response = _operation_response(operation, record)
            session.commit()
            return response
        healing = 1
    elif payload.care_type == "medicine":
        if payload.medicine_roll_id is None:
            raise InvalidRuleOperationError("medicine recovery requires a recorded medicine roll")
        roll = _roll_for(
            session,
            roll_id=payload.medicine_roll_id,
            campaign_id=campaign_id,
            investigator_id=investigator_id,
            case_session_id=payload.case_session_id,
            skill_key="medicine",
            target=_current_skill(record, "medicine"),
        )
        if not _passed(roll):
            raise InvalidRuleOperationError("medicine roll must pass")
        if _roll_already_consumed(
            session,
            operation_type="recovery",
            roll_id=payload.medicine_roll_id,
            json_path=RuleOperationRecord.input_data["medicine_roll_id"],
        ):
            raise InvalidRuleOperationError("medicine roll has already been consumed")
        if "dying" in record.conditions:
            raise InvalidRuleOperationError("medicine cannot silently clear dying; stabilize first")
        healing = recovery_amount("medicine", payload.healing_roll)
    else:
        if payload.constitution_roll_id is None or payload.period_key is None:
            raise InvalidRuleOperationError(
                "natural recovery requires a constitution roll and period key"
            )
        roll = _roll_for(
            session,
            roll_id=payload.constitution_roll_id,
            campaign_id=campaign_id,
            investigator_id=investigator_id,
            case_session_id=payload.case_session_id,
            skill_key="constitution",
            target=record.constitution,
        )
        if not _passed(roll):
            raise InvalidRuleOperationError("constitution roll must pass")
        if _roll_already_consumed(
            session,
            operation_type="recovery",
            roll_id=payload.constitution_roll_id,
            json_path=RuleOperationRecord.input_data["constitution_roll_id"],
        ):
            raise InvalidRuleOperationError("constitution roll has already been consumed")
        duplicate_period = select(RuleOperationRecord.id).where(
            RuleOperationRecord.campaign_id == str(campaign_id),
            RuleOperationRecord.subject_id == str(investigator_id),
            RuleOperationRecord.operation_type == "recovery",
            RuleOperationRecord.input_data["period_key"].as_string() == payload.period_key,
        )
        if session.scalar(duplicate_period) is not None:
            raise InvalidRuleOperationError(
                "natural recovery has already been applied for this period"
            )
        healing = recovery_amount("natural", payload.healing_roll)
    maximum_hit_points = (record.constitution + record.size) // 10
    healed = min(healing, maximum_hit_points - record.hit_points)
    record.hit_points += healed
    conditions = set(record.conditions)
    if "stabilized" in conditions and payload.care_type == "medicine":
        conditions.discard("stabilized")
        conditions.discard("unconscious")
    elif record.hit_points > 0:
        conditions.discard("unconscious")
    if record.hit_points >= (maximum_hit_points + 1) // 2:
        conditions.discard("major_wound")
    record.conditions = sorted(conditions)
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
        citations=(RECOVERY_CITATION, RECOVERY_CONTEXT_CITATION),
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


def apply_dying_check(
    session: Session, campaign_id: UUID, investigator_id: UUID, payload: DyingCheckRequest
) -> EngineOperationResponse:
    _required_case_session(session, campaign_id, payload.case_session_id)
    duplicate = select(RuleOperationRecord.id).where(
        RuleOperationRecord.campaign_id == str(campaign_id),
        RuleOperationRecord.subject_id == str(investigator_id),
        RuleOperationRecord.operation_type == "dying_check",
        RuleOperationRecord.input_data["period_key"].as_string() == payload.period_key,
    )
    if session.scalar(duplicate) is not None:
        raise InvalidRuleOperationError("dying check already recorded for this period")
    if _roll_already_consumed(
        session,
        operation_type="dying_check",
        roll_id=payload.constitution_roll_id,
        json_path=RuleOperationRecord.input_data["constitution_roll_id"],
    ):
        raise InvalidRuleOperationError("constitution roll has already been consumed")
    record, before = _claim_investigator(
        session, campaign_id, investigator_id, payload.expected_version
    )
    if "dead" in record.conditions:
        raise InvalidRuleOperationError("a dead investigator cannot make dying checks")
    if not ({"dying", "stabilized"} & set(record.conditions)):
        raise InvalidRuleOperationError("dying checks require dying or stabilized condition")
    roll = _roll_for(
        session,
        roll_id=payload.constitution_roll_id,
        campaign_id=campaign_id,
        investigator_id=investigator_id,
        case_session_id=payload.case_session_id,
        skill_key="constitution",
        target=record.constitution,
    )
    passed = _passed(roll)
    conditions = set(record.conditions)
    if not passed:
        if "stabilized" in conditions:
            conditions.discard("stabilized")
            conditions.add("dying")
            record.hit_points = 0
        else:
            conditions.discard("dying")
            conditions.add("dead")
    record.conditions = sorted(conditions)
    operation = _add_operation(
        session,
        campaign_id=campaign_id,
        operation_type="dying_check",
        subject_id=record.id,
        case_session_id=payload.case_session_id,
        session_key=payload.session_key,
        input_data=payload.model_dump(mode="json"),
        output_data={
            "passed": passed,
            "period_key": payload.period_key,
            "terminal": "dead" in conditions,
        },
        citations=(INJURY_CITATION,),
    )
    session.flush()
    service._audit(
        session,
        campaign_id=record.campaign_id,
        action="dying_check",
        entity_type="investigator",
        entity_id=record.id,
        expected_version=payload.expected_version,
        before=before,
        after=service._investigator_response(record).model_dump(mode="json"),
    )
    response = _operation_response(operation, record)
    session.commit()
    return response


def apply_insanity_transition(
    session: Session, campaign_id: UUID, investigator_id: UUID, payload: InsanityTransitionRequest
) -> EngineOperationResponse:
    _required_case_session(session, campaign_id, payload.case_session_id)
    record, before = _claim_investigator(
        session, campaign_id, investigator_id, payload.expected_version
    )
    conditions = set(record.conditions)
    if payload.transition == "bout_started":
        if "temporary_insanity" not in conditions:
            raise InvalidRuleOperationError("bout start requires temporary_insanity")
        conditions.add("bout_of_madness")
    elif payload.transition == "bout_ended":
        if "bout_of_madness" not in conditions:
            raise InvalidRuleOperationError("bout end requires an active bout_of_madness")
        conditions.discard("bout_of_madness")
    elif "temporary_insanity" in conditions:
        if not payload.evidence:
            raise InvalidRuleOperationError(
                "temporary insanity recovery requires explicit elapsed/rest evidence"
            )
        conditions.discard("temporary_insanity")
        conditions.discard("bout_of_madness")
    elif "indefinite_insanity" in conditions:
        if payload.treatment_roll_id is None or payload.period_key is None:
            raise InvalidRuleOperationError(
                "indefinite insanity recovery requires treatment roll and period key"
            )
        duplicate = select(RuleOperationRecord.id).where(
            RuleOperationRecord.campaign_id == str(campaign_id),
            RuleOperationRecord.subject_id == str(investigator_id),
            RuleOperationRecord.operation_type == "insanity_transition",
            RuleOperationRecord.input_data["period_key"].as_string() == payload.period_key,
        )
        if session.scalar(duplicate) is not None:
            raise InvalidRuleOperationError("insanity recovery already recorded for this period")
        raw_roll = _roll_for(
            session,
            roll_id=payload.treatment_roll_id,
            campaign_id=campaign_id,
            investigator_id=investigator_id,
            case_session_id=payload.case_session_id,
        )
        if raw_roll.skill_key not in {"medicine", "psychoanalysis"}:
            raise InvalidRuleOperationError(
                "indefinite insanity recovery requires medicine or psychoanalysis"
            )
        roll = _roll_for(
            session,
            roll_id=payload.treatment_roll_id,
            campaign_id=campaign_id,
            investigator_id=investigator_id,
            case_session_id=payload.case_session_id,
            skill_key=raw_roll.skill_key,
            target=_current_skill(record, raw_roll.skill_key),
        )
        if not _passed(roll):
            raise InvalidRuleOperationError(
                "indefinite insanity recovery requires a successful treatment roll"
            )
        conditions.discard("indefinite_insanity")
    else:
        raise InvalidRuleOperationError("recovery requires temporary or indefinite insanity")
    record.conditions = sorted(conditions)
    operation = _add_operation(
        session,
        campaign_id=campaign_id,
        operation_type="insanity_transition",
        subject_id=record.id,
        case_session_id=payload.case_session_id,
        session_key=payload.session_key,
        input_data=payload.model_dump(mode="json"),
        output_data={"transition": payload.transition, "evidence": payload.evidence},
        citations=(SANITY_CITATION,),
    )
    session.flush()
    service._audit(
        session,
        campaign_id=record.campaign_id,
        action="insanity_transition",
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
    _required_case_session(session, campaign_id, payload.case_session_id)
    weapon = WEAPON_BY_KEY.get(payload.weapon_key)
    if weapon is None:
        raise InvalidRuleOperationError("unknown COC7 weapon policy")
    attacker = session.scalar(service._investigator_query(campaign_id, payload.attacker_id))
    if attacker is None:
        raise service.EntityNotFoundError("investigator not found")
    if "dead" in attacker.conditions:
        raise InvalidRuleOperationError("a dead investigator cannot participate in combat")
    maximum_damage = weapon.maximum_rolled_damage
    if weapon.uses_damage_bonus:
        maximum_damage += _stored_damage_bonus_max(attacker)
    if payload.rolled_damage > maximum_damage:
        raise InvalidRuleOperationError("rolled damage exceeds the weapon policy")
    roll = _roll_for(
        session,
        roll_id=payload.attack_roll_id,
        campaign_id=campaign_id,
        investigator_id=payload.attacker_id,
        case_session_id=payload.case_session_id,
        skill_key=weapon.skill_key,
        target=_current_skill(attacker, weapon.skill_key),
    )
    consumed_roll = select(RuleOperationRecord.id).where(
        RuleOperationRecord.operation_type == "combat",
        RuleOperationRecord.output_data["attack_roll_id"].as_string()
        == str(payload.attack_roll_id),
    )
    if session.scalar(consumed_roll) is not None:
        raise InvalidRuleOperationError("attack roll has already been consumed")
    hit = _passed(roll)
    if hit and payload.rolled_damage == 0:
        raise InvalidRuleOperationError("a hit must apply at least one point of damage")
    target, before = _claim_investigator(
        session, campaign_id, payload.target_id, payload.target_expected_version
    )
    if "dead" in target.conditions:
        raise InvalidRuleOperationError("a dead investigator cannot participate in combat")
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
        citations=(COMBAT_CITATION, *weapon.citations),
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
    if record.case_session_id is None:
        raise InvalidRuleOperationError("chase is missing its required case session")
    return ChaseResponse(
        chase_id=UUID(record.id),
        campaign_id=UUID(record.campaign_id),
        title=record.title,
        case_session_id=UUID(record.case_session_id),
        session_key=record.session_key,
        status=record.status,
        participants=tuple(
            ChaseParticipantState.model_validate(item) for item in record.participants
        ),
        round=record.round,
        escape_distance=record.escape_distance,
        track_length=record.track_length,
        version=record.version,
        citations=tuple(
            EngineCitationResponse.model_validate(item.as_dict()) for item in CHASE_CITATIONS
        ),
        citation=EngineCitationResponse.model_validate(CHASE_CITATIONS[0].as_dict()),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def create_chase(session: Session, campaign_id: UUID, payload: ChaseCreateRequest) -> ChaseResponse:
    _required_case_session(session, campaign_id, payload.case_session_id)
    if (
        session.scalar(select(CampaignRecord.id).where(CampaignRecord.id == str(campaign_id)))
        is None
    ):
        raise service.EntityNotFoundError("campaign not found")
    requested_ids = {str(item.investigator_id) for item in payload.participants}
    investigators = {
        record.id: record
        for record in session.scalars(
            select(InvestigatorRecord).where(
                InvestigatorRecord.campaign_id == str(campaign_id),
                InvestigatorRecord.id.in_(requested_ids),
            )
        ).all()
    }
    if set(investigators) != requested_ids:
        raise InvalidRuleOperationError("chase participant does not belong to campaign")
    # Read MOV only from the stored investigator record; it is never client input.
    move_rates = {
        investigator_id: int(investigators[investigator_id].move_rate)
        for investigator_id in requested_ids
    }
    slowest = min(move_rates.values())
    participants = [
        {
            **item.model_dump(mode="json"),
            "move_rate": move_rates[str(item.investigator_id)],
            "actions_remaining": 1 + max(0, move_rates[str(item.investigator_id)] - slowest),
        }
        for item in payload.participants
    ]
    pursuers = [int(item["position"]) for item in participants if item["role"] == "pursuer"]
    fleeing = [int(item["position"]) for item in participants if item["role"] == "fleeing"]
    status = "active"
    if pursuers and fleeing and max(pursuers) >= min(fleeing):
        status = "caught"
    elif fleeing and max(fleeing) >= min(payload.escape_distance, payload.track_length):
        status = "escaped"
    record = ChaseRecord(
        campaign_id=str(campaign_id),
        title=payload.title,
        case_session_id=str(payload.case_session_id),
        session_key=payload.session_key,
        status=status,
        participants=participants,
        round=1,
        escape_distance=payload.escape_distance,
        track_length=payload.track_length,
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
        output_data={"version": record.version, "participants": record.participants, "round": 1},
        citations=CHASE_CITATIONS,
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
    if (
        session.scalar(select(CampaignRecord.id).where(CampaignRecord.id == str(campaign_id)))
        is None
    ):
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
    if record.version != payload.expected_version:
        raise service.VersionConflictError("chase version conflict")
    if record.status != "active":
        raise InvalidRuleOperationError("cannot act after chase is complete")
    before = _chase_response(record)
    action = payload.action
    participants = [dict(item) for item in record.participants]
    participant = next(
        (item for item in participants if item["investigator_id"] == str(action.investigator_id)),
        None,
    )
    if participant is None:
        raise InvalidRuleOperationError("action references a non-participant")
    if int(participant["actions_remaining"]) <= 0:
        raise InvalidRuleOperationError("participant has no actions remaining this round")
    succeeded = True
    if action.action == "hazard":
        investigator = session.get(InvestigatorRecord, str(action.investigator_id))
        if investigator is None or investigator.campaign_id != str(campaign_id):
            raise InvalidRuleOperationError("chase participant does not belong to campaign")
        current_target = _current_skill(investigator, cast(str, action.skill_key))
        roll = _roll_for(
            session,
            roll_id=cast(UUID, action.roll_id),
            campaign_id=campaign_id,
            investigator_id=action.investigator_id,
            case_session_id=UUID(record.case_session_id),
            skill_key=action.skill_key,
            target=current_target,
        )
        succeeded = _passed(roll)
        if _roll_already_consumed(
            session,
            operation_type="chase_advanced",
            roll_id=cast(UUID, action.roll_id),
            json_path=RuleOperationRecord.input_data["action"]["roll_id"],
        ):
            raise InvalidRuleOperationError("hazard roll has already been consumed")
    if succeeded:
        participant["position"] = min(int(participant["position"]) + 1, record.track_length)
    participant["actions_remaining"] = int(participant["actions_remaining"]) - 1
    pursuers = [int(item["position"]) for item in participants if item["role"] == "pursuer"]
    fleeing = [int(item["position"]) for item in participants if item["role"] == "fleeing"]
    status = "active"
    if pursuers and fleeing and max(pursuers) >= min(fleeing):
        status = "caught"
    elif fleeing and max(fleeing) >= record.escape_distance:
        status = "escaped"
    next_round = record.round
    if status == "active" and all(int(item["actions_remaining"]) == 0 for item in participants):
        slowest = min(int(item["move_rate"]) for item in participants)
        for item in participants:
            item["actions_remaining"] = 1 + max(0, int(item["move_rate"]) - slowest)
        next_round += 1
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
                status=status,
                round=next_round,
                version=payload.expected_version + 1,
            )
        ),
    )
    if result.rowcount != 1:
        session.rollback()
        raise service.VersionConflictError("chase version conflict")
    record = session.scalar(select(ChaseRecord).where(ChaseRecord.id == str(chase_id)))
    assert record is not None
    response = _chase_response(record)
    if action.action == "hazard":
        citations = (*CHASE_CITATIONS, CHASE_HAZARDS_CITATION, CHASE_BARRIERS_CITATION)
        response = response.model_copy(
            update={
                "citations": tuple(
                    EngineCitationResponse.model_validate(citation.as_dict())
                    for citation in citations
                ),
                "citation": EngineCitationResponse.model_validate(citations[0].as_dict()),
            }
        )
    _add_operation(
        session,
        campaign_id=campaign_id,
        operation_type="chase_advanced",
        subject_id=record.id,
        case_session_id=UUID(record.case_session_id),
        session_key=record.session_key,
        input_data=payload.model_dump(mode="json"),
        output_data={
            "version": record.version,
            "participants": participants,
            "round": record.round,
            "status": record.status,
            "succeeded": succeeded,
        },
        citations=(
            *CHASE_CITATIONS,
            *(
                (CHASE_HAZARDS_CITATION, CHASE_BARRIERS_CITATION)
                if action.action == "hazard"
                else ()
            ),
        ),
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


def list_operations(session: Session, campaign_id: UUID) -> list[RuleOperationLogResponse]:
    if (
        session.scalar(select(CampaignRecord.id).where(CampaignRecord.id == str(campaign_id)))
        is None
    ):
        raise service.EntityNotFoundError("campaign not found")
    records = session.scalars(
        select(RuleOperationRecord)
        .where(RuleOperationRecord.campaign_id == str(campaign_id))
        .order_by(RuleOperationRecord.created_at, RuleOperationRecord.id)
        .limit(500)
    ).all()

    def response_for(record: RuleOperationRecord) -> RuleOperationLogResponse:
        citations = _citation_items(record.citation_data)
        return RuleOperationLogResponse(
            operation_id=UUID(record.id),
            campaign_id=UUID(record.campaign_id),
            subject_id=UUID(record.subject_id),
            case_session_id=(UUID(record.case_session_id) if record.case_session_id else None),
            session_key=record.session_key,
            operation_type=record.operation_type,
            input_data=record.input_data,
            output_data=record.output_data,
            citations=citations,
            citation=citations[0],
            created_at=record.created_at,
        )

    return [response_for(record) for record in records]
