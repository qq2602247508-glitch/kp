from secrets import randbelow
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, selectinload

from coc_kp_assistant.api.schemas import (
    AuditResponse,
    BackstoryReplace,
    CampaignReplace,
    CampaignResponse,
    DifficultyLabel,
    InvestigatorReplace,
    InvestigatorResponse,
    RecordedRollRequest,
    RecordedRollResponse,
    SkillsReplace,
)
from coc_kp_assistant.domain.campaigns import CampaignCreate, CampaignEra
from coc_kp_assistant.domain.investigators import (
    CoreCharacteristics,
    InvestigatorBackstory,
    InvestigatorCondition,
    InvestigatorCreate,
    SkillEntry,
)
from coc_kp_assistant.domain.rolls import (
    PercentileDice,
    RollDifficulty,
    RollRequest,
    resolve_percentile_roll,
)
from coc_kp_assistant.infrastructure.models import (
    CampaignRecord,
    InvestigatorBackstoryRecord,
    InvestigatorRecord,
    InvestigatorSkillRecord,
    RollRecord,
    StateAuditRecord,
)


class EntityNotFoundError(Exception):
    pass


class VersionConflictError(Exception):
    pass


def _campaign_response(record: CampaignRecord) -> CampaignResponse:
    return CampaignResponse(
        campaign_id=UUID(record.id),
        title=record.title,
        ruleset="coc7e",
        era=CampaignEra(record.era),
        custom_era_label=record.custom_era_label,
        in_world_date=record.in_world_date,
        starting_location=record.starting_location,
        enabled_source_pack_ids=tuple(record.enabled_source_pack_ids),
        house_rules=tuple(record.house_rules),
        keeper_notes=record.keeper_notes,
        version=record.version,
    )


def _backstory_from_record(
    record: InvestigatorBackstoryRecord | None,
) -> InvestigatorBackstory:
    if record is None:
        return InvestigatorBackstory()
    return InvestigatorBackstory(
        personal_description=tuple(record.personal_description),
        ideology_and_beliefs=tuple(record.ideology_and_beliefs),
        significant_people=tuple(record.significant_people),
        meaningful_locations=tuple(record.meaningful_locations),
        treasured_possessions=tuple(record.treasured_possessions),
        traits=tuple(record.traits),
        injuries_and_scars=tuple(record.injuries_and_scars),
        phobias_and_manias=tuple(record.phobias_and_manias),
        mythos_tomes_spells_artifacts=tuple(record.mythos_tomes_spells_artifacts),
        strange_encounters=tuple(record.strange_encounters),
    )


def _skill_from_record(record: InvestigatorSkillRecord) -> SkillEntry:
    return SkillEntry(
        skill_key=record.skill_key,
        display_name=record.display_name,
        specialization=record.specialization,
        base_value=record.base_value,
        current_value=record.current_value,
        improvement_mark=record.improvement_mark,
        source_pack_id=record.source_pack_id,
    )


def _investigator_response(record: InvestigatorRecord) -> InvestigatorResponse:
    return InvestigatorResponse(
        investigator_id=UUID(record.id),
        campaign_id=UUID(record.campaign_id),
        name=record.name,
        player_name=record.player_name,
        occupation=record.occupation,
        age=record.age,
        gender=record.gender,
        residence=record.residence,
        birthplace=record.birthplace,
        era=record.era,
        characteristics=CoreCharacteristics(
            strength=record.strength,
            constitution=record.constitution,
            size=record.size,
            dexterity=record.dexterity,
            appearance=record.appearance,
            intelligence=record.intelligence,
            power=record.power,
            education=record.education,
        ),
        luck=record.luck,
        move_rate=record.move_rate,
        damage_bonus=record.damage_bonus,
        build=record.build,
        credit_rating=record.credit_rating,
        spending_level=record.spending_level,
        cash=record.cash,
        assets=record.assets,
        skills=tuple(_skill_from_record(item) for item in record.skills),
        backstory=_backstory_from_record(record.backstory),
        hit_points=record.hit_points,
        magic_points=record.magic_points,
        sanity=record.sanity,
        mythos=record.mythos,
        conditions=frozenset(InvestigatorCondition(item) for item in record.conditions),
        version=record.version,
    )


def _campaign_query(campaign_id: UUID) -> Select[tuple[CampaignRecord]]:
    return select(CampaignRecord).where(CampaignRecord.id == str(campaign_id))


def _investigator_query(
    campaign_id: UUID, investigator_id: UUID
) -> Select[tuple[InvestigatorRecord]]:
    return (
        select(InvestigatorRecord)
        .where(
            InvestigatorRecord.id == str(investigator_id),
            InvestigatorRecord.campaign_id == str(campaign_id),
        )
        .options(
            selectinload(InvestigatorRecord.skills),
            selectinload(InvestigatorRecord.backstory),
        )
    )


def _audit(
    session: Session,
    *,
    campaign_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    expected_version: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    session.add(
        StateAuditRecord(
            campaign_id=campaign_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            expected_version=expected_version,
            before_data=before,
            after_data=after,
        )
    )


def create_campaign(session: Session, payload: CampaignCreate) -> CampaignResponse:
    record = CampaignRecord(
        title=payload.title,
        era=payload.era.value,
        custom_era_label=payload.custom_era_label,
        in_world_date=payload.in_world_date,
        starting_location=payload.starting_location,
        enabled_source_pack_ids=list(payload.enabled_source_pack_ids),
        house_rules=list(payload.house_rules),
        keeper_notes=payload.keeper_notes,
    )
    session.add(record)
    session.flush()
    response = _campaign_response(record)
    _audit(
        session,
        campaign_id=record.id,
        action="create",
        entity_type="campaign",
        entity_id=record.id,
        after=response.model_dump(mode="json"),
    )
    session.commit()
    return response


def list_campaigns(session: Session) -> list[CampaignResponse]:
    records = session.scalars(select(CampaignRecord).order_by(CampaignRecord.created_at)).all()
    return [_campaign_response(record) for record in records]


def get_campaign(session: Session, campaign_id: UUID) -> CampaignResponse:
    record = session.scalar(_campaign_query(campaign_id))
    if record is None:
        raise EntityNotFoundError("campaign not found")
    return _campaign_response(record)


def replace_campaign(
    session: Session, campaign_id: UUID, payload: CampaignReplace
) -> CampaignResponse:
    before = get_campaign(session, campaign_id)
    result = cast(
        CursorResult[Any],
        session.execute(
            update(CampaignRecord)
            .where(
                CampaignRecord.id == str(campaign_id),
                CampaignRecord.version == payload.expected_version,
            )
            .values(
                title=payload.title,
                era=payload.era.value,
                custom_era_label=payload.custom_era_label,
                in_world_date=payload.in_world_date,
                starting_location=payload.starting_location,
                enabled_source_pack_ids=list(payload.enabled_source_pack_ids),
                house_rules=list(payload.house_rules),
                keeper_notes=payload.keeper_notes,
                version=payload.expected_version + 1,
            )
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise VersionConflictError("campaign version conflict")
    record = session.scalar(_campaign_query(campaign_id))
    assert record is not None
    response = _campaign_response(record)
    _audit(
        session,
        campaign_id=record.id,
        action="replace",
        entity_type="campaign",
        entity_id=record.id,
        expected_version=payload.expected_version,
        before=before.model_dump(mode="json"),
        after=response.model_dump(mode="json"),
    )
    session.commit()
    return response


def delete_campaign(session: Session, campaign_id: UUID, expected_version: int) -> None:
    before = get_campaign(session, campaign_id)
    result = cast(
        CursorResult[Any],
        session.execute(
            delete(CampaignRecord).where(
                CampaignRecord.id == str(campaign_id),
                CampaignRecord.version == expected_version,
            )
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise VersionConflictError("campaign version conflict")
    _audit(
        session,
        campaign_id=None,
        action="delete",
        entity_type="campaign",
        entity_id=str(campaign_id),
        expected_version=expected_version,
        before=before.model_dump(mode="json"),
    )
    session.commit()


def _new_skill(record_id: str, skill: SkillEntry) -> InvestigatorSkillRecord:
    return InvestigatorSkillRecord(
        investigator_id=record_id,
        skill_key=skill.skill_key,
        display_name=skill.display_name,
        specialization=skill.specialization,
        specialization_key=skill.specialization or "",
        base_value=skill.base_value,
        current_value=skill.current_value,
        improvement_mark=skill.improvement_mark,
        source_pack_id=skill.source_pack_id,
    )


def _new_backstory(
    record_id: str, backstory: InvestigatorBackstory
) -> InvestigatorBackstoryRecord:
    return InvestigatorBackstoryRecord(
        investigator_id=record_id,
        personal_description=list(backstory.personal_description),
        ideology_and_beliefs=list(backstory.ideology_and_beliefs),
        significant_people=list(backstory.significant_people),
        meaningful_locations=list(backstory.meaningful_locations),
        treasured_possessions=list(backstory.treasured_possessions),
        traits=list(backstory.traits),
        injuries_and_scars=list(backstory.injuries_and_scars),
        phobias_and_manias=list(backstory.phobias_and_manias),
        mythos_tomes_spells_artifacts=list(backstory.mythos_tomes_spells_artifacts),
        strange_encounters=list(backstory.strange_encounters),
    )


def _profile_values(profile: InvestigatorCreate) -> dict[str, Any]:
    characteristics = profile.characteristics
    return {
        "name": profile.name,
        "player_name": profile.player_name,
        "occupation": profile.occupation,
        "age": profile.age,
        "gender": profile.gender,
        "residence": profile.residence,
        "birthplace": profile.birthplace,
        "era": profile.era,
        "strength": characteristics.strength,
        "constitution": characteristics.constitution,
        "size": characteristics.size,
        "dexterity": characteristics.dexterity,
        "appearance": characteristics.appearance,
        "intelligence": characteristics.intelligence,
        "power": characteristics.power,
        "education": characteristics.education,
        "luck": profile.luck,
        "move_rate": profile.move_rate,
        "damage_bonus": profile.damage_bonus,
        "build": profile.build,
        "credit_rating": profile.credit_rating,
        "spending_level": profile.spending_level,
        "cash": profile.cash,
        "assets": profile.assets,
    }


def create_investigator(
    session: Session, campaign_id: UUID, profile: InvestigatorCreate
) -> InvestigatorResponse:
    if session.scalar(_campaign_query(campaign_id)) is None:
        raise EntityNotFoundError("campaign not found")
    record = InvestigatorRecord(
        campaign_id=str(campaign_id),
        **_profile_values(profile),
        hit_points=profile.maximum_hit_points,
        magic_points=profile.maximum_magic_points,
        sanity=profile.starting_sanity,
        mythos=0,
        conditions=[],
    )
    session.add(record)
    session.flush()
    record.skills = [_new_skill(record.id, skill) for skill in profile.skills]
    record.backstory = _new_backstory(record.id, profile.backstory)
    session.flush()
    response = _investigator_response(record)
    _audit(
        session,
        campaign_id=record.campaign_id,
        action="create",
        entity_type="investigator",
        entity_id=record.id,
        after=response.model_dump(mode="json"),
    )
    session.commit()
    return response


def list_investigators(session: Session, campaign_id: UUID) -> list[InvestigatorResponse]:
    if session.scalar(_campaign_query(campaign_id)) is None:
        raise EntityNotFoundError("campaign not found")
    records = session.scalars(
        select(InvestigatorRecord)
        .where(InvestigatorRecord.campaign_id == str(campaign_id))
        .options(
            selectinload(InvestigatorRecord.skills),
            selectinload(InvestigatorRecord.backstory),
        )
        .order_by(InvestigatorRecord.created_at)
    ).all()
    return [_investigator_response(record) for record in records]


def get_investigator(
    session: Session, campaign_id: UUID, investigator_id: UUID
) -> InvestigatorResponse:
    record = session.scalar(_investigator_query(campaign_id, investigator_id))
    if record is None:
        raise EntityNotFoundError("investigator not found")
    return _investigator_response(record)


def _claim_investigator_version(
    session: Session, campaign_id: UUID, investigator_id: UUID, expected_version: int
) -> InvestigatorRecord:
    result = cast(
        CursorResult[Any],
        session.execute(
            update(InvestigatorRecord)
            .where(
                InvestigatorRecord.id == str(investigator_id),
                InvestigatorRecord.campaign_id == str(campaign_id),
                InvestigatorRecord.version == expected_version,
            )
            .values(version=expected_version + 1)
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise VersionConflictError("investigator version conflict")
    record = session.scalar(_investigator_query(campaign_id, investigator_id))
    assert record is not None
    return record


def replace_investigator(
    session: Session,
    campaign_id: UUID,
    investigator_id: UUID,
    payload: InvestigatorReplace,
) -> InvestigatorResponse:
    before = get_investigator(session, campaign_id, investigator_id)
    record = _claim_investigator_version(
        session, campaign_id, investigator_id, payload.expected_version
    )
    for key, value in _profile_values(payload).items():
        setattr(record, key, value)
    record.hit_points = payload.hit_points
    record.magic_points = payload.magic_points
    record.sanity = payload.sanity
    record.mythos = payload.mythos
    record.conditions = [item.value for item in payload.conditions]
    record.skills.clear()
    session.flush()
    record.skills.extend(_new_skill(record.id, skill) for skill in payload.skills)
    if record.backstory is not None:
        session.delete(record.backstory)
        session.flush()
    record.backstory = _new_backstory(record.id, payload.backstory)
    session.flush()
    response = _investigator_response(record)
    _audit(
        session,
        campaign_id=record.campaign_id,
        action="replace",
        entity_type="investigator",
        entity_id=record.id,
        expected_version=payload.expected_version,
        before=before.model_dump(mode="json"),
        after=response.model_dump(mode="json"),
    )
    session.commit()
    return response


def replace_skills(
    session: Session,
    campaign_id: UUID,
    investigator_id: UUID,
    payload: SkillsReplace,
) -> InvestigatorResponse:
    before = get_investigator(session, campaign_id, investigator_id)
    record = _claim_investigator_version(
        session, campaign_id, investigator_id, payload.expected_version
    )
    record.skills.clear()
    session.flush()
    record.skills.extend(_new_skill(record.id, skill) for skill in payload.skills)
    session.flush()
    response = _investigator_response(record)
    _audit(
        session,
        campaign_id=record.campaign_id,
        action="replace_skills",
        entity_type="investigator",
        entity_id=record.id,
        expected_version=payload.expected_version,
        before=before.model_dump(mode="json"),
        after=response.model_dump(mode="json"),
    )
    session.commit()
    return response


def replace_backstory(
    session: Session,
    campaign_id: UUID,
    investigator_id: UUID,
    payload: BackstoryReplace,
) -> InvestigatorResponse:
    before = get_investigator(session, campaign_id, investigator_id)
    record = _claim_investigator_version(
        session, campaign_id, investigator_id, payload.expected_version
    )
    if record.backstory is not None:
        session.delete(record.backstory)
        session.flush()
    record.backstory = _new_backstory(record.id, payload.backstory)
    session.flush()
    response = _investigator_response(record)
    _audit(
        session,
        campaign_id=record.campaign_id,
        action="replace_backstory",
        entity_type="investigator",
        entity_id=record.id,
        expected_version=payload.expected_version,
        before=before.model_dump(mode="json"),
        after=response.model_dump(mode="json"),
    )
    session.commit()
    return response


def delete_investigator(
    session: Session, campaign_id: UUID, investigator_id: UUID, expected_version: int
) -> None:
    before = get_investigator(session, campaign_id, investigator_id)
    result = cast(
        CursorResult[Any],
        session.execute(
            delete(InvestigatorRecord).where(
                InvestigatorRecord.id == str(investigator_id),
                InvestigatorRecord.campaign_id == str(campaign_id),
                InvestigatorRecord.version == expected_version,
            )
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise VersionConflictError("investigator version conflict")
    _audit(
        session,
        campaign_id=str(campaign_id),
        action="delete",
        entity_type="investigator",
        entity_id=str(investigator_id),
        expected_version=expected_version,
        before=before.model_dump(mode="json"),
    )
    session.commit()


def record_roll(session: Session, payload: RecordedRollRequest) -> RecordedRollResponse:
    if session.scalar(_campaign_query(payload.campaign_id)) is None:
        raise EntityNotFoundError("campaign not found")
    if (
        payload.investigator_id is not None
        and session.scalar(
            _investigator_query(payload.campaign_id, payload.investigator_id)
        )
        is None
    ):
        raise EntityNotFoundError("investigator not found")

    dice = payload.dice or PercentileDice(
        units_digit=randbelow(10),
        tens_digits=tuple(randbelow(10) for _ in range(abs(payload.bonus_penalty) + 1)),
    )
    difficulty = {
        DifficultyLabel.REGULAR: RollDifficulty.REGULAR,
        DifficultyLabel.HARD: RollDifficulty.HARD,
        DifficultyLabel.EXTREME: RollDifficulty.EXTREME,
    }[payload.difficulty]
    request = RollRequest(
        target_value=payload.target,
        difficulty=difficulty,
        modifier_dice=payload.bonus_penalty,
        dice=dice,
    )
    resolution = resolve_percentile_roll(request)
    record = RollRecord(
        campaign_id=str(payload.campaign_id),
        investigator_id=str(payload.investigator_id) if payload.investigator_id else None,
        skill_key=payload.skill_key,
        label=payload.label,
        request_data=request.model_dump(mode="json"),
        resolution_data=resolution.model_dump(mode="json"),
    )
    session.add(record)
    session.flush()
    session.refresh(record)
    response = RecordedRollResponse(
        roll_id=UUID(record.id),
        campaign_id=payload.campaign_id,
        investigator_id=payload.investigator_id,
        skill_key=payload.skill_key,
        label=payload.label,
        roll=resolution.total,
        tens=dice.tens_digits,
        selected_tens=resolution.selected_tens_digit,
        ones=dice.units_digit,
        target=payload.target,
        regular_threshold=resolution.regular_threshold,
        hard_threshold=resolution.hard_threshold,
        extreme_threshold=resolution.extreme_threshold,
        outcome=resolution.success_level.name.lower(),
        difficulty=payload.difficulty,
        bonus_penalty=payload.bonus_penalty,
        passed=resolution.passed,
        created_at=record.created_at,
    )
    _audit(
        session,
        campaign_id=record.campaign_id,
        action="roll_recorded",
        entity_type="roll",
        entity_id=record.id,
        after=response.model_dump(mode="json"),
    )
    session.commit()
    return response


def list_audits(session: Session, campaign_id: UUID) -> list[AuditResponse]:
    if session.scalar(_campaign_query(campaign_id)) is None:
        raise EntityNotFoundError("campaign not found")
    records = session.scalars(
        select(StateAuditRecord)
        .where(StateAuditRecord.campaign_id == str(campaign_id))
        .order_by(StateAuditRecord.created_at, StateAuditRecord.id)
        .limit(500)
    ).all()
    return [
        AuditResponse(
            audit_id=UUID(record.id),
            campaign_id=UUID(record.campaign_id) if record.campaign_id else None,
            action=record.action,
            entity_type=record.entity_type,
            entity_id=UUID(record.entity_id),
            expected_version=record.expected_version,
            before=record.before_data,
            after=record.after_data,
            created_at=record.created_at,
        )
        for record in records
    ]
