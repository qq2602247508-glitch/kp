from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from coc_kp_assistant.domain.case_state import (
    CaseEntityKind,
    CaseEntryCreate,
    CaseEntryReplace,
    CaseEntryResponse,
    PersonAttack,
    PersonEntityType,
    PersonSkill,
    PlayerCaseEntryResponse,
)
from coc_kp_assistant.infrastructure.models import (
    CampaignRecord,
    CaseClueRecord,
    CaseHandoutRecord,
    CaseLocationRecord,
    CasePersonRecord,
    CaseRelationshipRecord,
    CaseSceneRecord,
    CaseSessionRecord,
    CaseTimelineEventRecord,
)

from .service import EntityNotFoundError, VersionConflictError, _audit


class InvalidCaseStateError(Exception):
    pass


MODEL_BY_KIND: dict[CaseEntityKind, type[Any]] = {
    CaseEntityKind.SESSIONS: CaseSessionRecord,
    CaseEntityKind.PEOPLE: CasePersonRecord,
    CaseEntityKind.LOCATIONS: CaseLocationRecord,
    CaseEntityKind.SCENES: CaseSceneRecord,
    CaseEntityKind.CLUES: CaseClueRecord,
    CaseEntityKind.RELATIONSHIPS: CaseRelationshipRecord,
    CaseEntityKind.HANDOUTS: CaseHandoutRecord,
    CaseEntityKind.TIMELINE_EVENTS: CaseTimelineEventRecord,
}

COMMON_FIELDS = {"title", "player_visible_text", "keeper_truth", "status"}
FIELDS_BY_KIND: dict[CaseEntityKind, set[str]] = {
    CaseEntityKind.SESSIONS: COMMON_FIELDS | {"time_label"},
    CaseEntityKind.PEOPLE: COMMON_FIELDS
    | {
        "role",
        "person_type",
        "characteristics",
        "hit_points",
        "move_rate",
        "damage_bonus",
        "build",
        "armor",
        "sanity_loss",
        "skills",
        "attacks",
        "special_abilities",
    },
    CaseEntityKind.LOCATIONS: COMMON_FIELDS,
    CaseEntityKind.SCENES: COMMON_FIELDS | {"session_id", "location_id"},
    CaseEntityKind.CLUES: COMMON_FIELDS
    | {"scene_id", "person_id", "location_id", "discovered"},
    CaseEntityKind.RELATIONSHIPS: COMMON_FIELDS
    | {"source_clue_id", "target_clue_id", "relationship_type"},
    CaseEntityKind.HANDOUTS: COMMON_FIELDS | {"clue_id", "revealed"},
    CaseEntityKind.TIMELINE_EVENTS: COMMON_FIELDS
    | {"session_id", "scene_id", "time_label", "sort_order"},
}

REFERENCE_FIELDS: dict[CaseEntityKind, dict[str, type[Any]]] = {
    CaseEntityKind.SCENES: {
        "session_id": CaseSessionRecord,
        "location_id": CaseLocationRecord,
    },
    CaseEntityKind.CLUES: {
        "scene_id": CaseSceneRecord,
        "person_id": CasePersonRecord,
        "location_id": CaseLocationRecord,
    },
    CaseEntityKind.RELATIONSHIPS: {
        "source_clue_id": CaseClueRecord,
        "target_clue_id": CaseClueRecord,
    },
    CaseEntityKind.HANDOUTS: {"clue_id": CaseClueRecord},
    CaseEntityKind.TIMELINE_EVENTS: {
        "session_id": CaseSessionRecord,
        "scene_id": CaseSceneRecord,
    },
}


def _ensure_campaign(session: Session, campaign_id: UUID) -> None:
    if (
        session.scalar(
            select(CampaignRecord.id).where(CampaignRecord.id == str(campaign_id))
        )
        is None
    ):
        raise EntityNotFoundError("campaign not found")


def _query(kind: CaseEntityKind, campaign_id: UUID, entity_id: UUID) -> Any:
    model = MODEL_BY_KIND[kind]
    return select(model).where(
        model.id == str(entity_id),
        model.campaign_id == str(campaign_id),
    )


def _validate_payload_shape(
    kind: CaseEntityKind, payload: CaseEntryCreate | CaseEntryReplace
) -> None:
    supplied = set(payload.model_fields_set) - {"expected_version"}
    unexpected = supplied - FIELDS_BY_KIND[kind]
    if unexpected:
        names = ", ".join(sorted(unexpected))
        raise InvalidCaseStateError(f"fields are not valid for {kind.value}: {names}")
    if kind is CaseEntityKind.RELATIONSHIPS:
        if (
            payload.source_clue_id is None
            or payload.target_clue_id is None
            or payload.relationship_type is None
        ):
            raise InvalidCaseStateError(
                "clue relationships require source, target, and relationship type"
            )
        if payload.source_clue_id == payload.target_clue_id:
            raise InvalidCaseStateError("a clue cannot link to itself")


def _validate_references(
    session: Session,
    campaign_id: UUID,
    kind: CaseEntityKind,
    payload: CaseEntryCreate | CaseEntryReplace,
) -> None:
    for field_name, model in REFERENCE_FIELDS.get(kind, {}).items():
        reference_id = getattr(payload, field_name)
        if reference_id is None:
            continue
        belongs = session.scalar(
            select(model.id).where(
                model.id == str(reference_id),
                model.campaign_id == str(campaign_id),
            )
        )
        if belongs is None:
            raise InvalidCaseStateError(
                f"{field_name} must reference an entity in the same case"
            )


def _record_values(
    kind: CaseEntityKind, payload: CaseEntryCreate | CaseEntryReplace
) -> dict[str, object]:
    values: dict[str, object] = {}
    for field_name in FIELDS_BY_KIND[kind]:
        value = getattr(payload, field_name)
        if isinstance(value, UUID):
            values[field_name] = str(value)
        elif hasattr(value, "model_dump"):
            values[field_name] = value.model_dump(mode="json")
        elif isinstance(value, tuple):
            values[field_name] = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in value
            ]
        else:
            values[field_name] = value
    return values


def _response(kind: CaseEntityKind, record: Any) -> CaseEntryResponse:
    return CaseEntryResponse(
        entity_id=UUID(record.id),
        campaign_id=UUID(record.campaign_id),
        kind=kind,
        title=record.title,
        player_visible_text=record.player_visible_text,
        keeper_truth=record.keeper_truth,
        status=record.status,
        time_label=getattr(record, "time_label", None),
        role=getattr(record, "role", None),
        person_type=PersonEntityType(getattr(record, "person_type", "keeper_npc")),
        characteristics=getattr(record, "characteristics", None),
        hit_points=getattr(record, "hit_points", None),
        move_rate=getattr(record, "move_rate", None),
        damage_bonus=getattr(record, "damage_bonus", None),
        build=getattr(record, "build", None),
        armor=getattr(record, "armor", None),
        sanity_loss=getattr(record, "sanity_loss", None),
        skills=tuple(
            PersonSkill.model_validate(item) for item in getattr(record, "skills", [])
        ),
        attacks=tuple(
            PersonAttack.model_validate(item)
            for item in getattr(record, "attacks", [])
        ),
        special_abilities=tuple(getattr(record, "special_abilities", [])),
        session_id=getattr(record, "session_id", None),
        location_id=getattr(record, "location_id", None),
        scene_id=getattr(record, "scene_id", None),
        person_id=getattr(record, "person_id", None),
        clue_id=getattr(record, "clue_id", None),
        source_clue_id=getattr(record, "source_clue_id", None),
        target_clue_id=getattr(record, "target_clue_id", None),
        relationship_type=getattr(record, "relationship_type", None),
        discovered=getattr(record, "discovered", False),
        revealed=getattr(record, "revealed", False),
        sort_order=getattr(record, "sort_order", 0),
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def create_entry(
    session: Session,
    campaign_id: UUID,
    kind: CaseEntityKind,
    payload: CaseEntryCreate,
    *,
    commit: bool = True,
) -> CaseEntryResponse:
    _ensure_campaign(session, campaign_id)
    _validate_payload_shape(kind, payload)
    _validate_references(session, campaign_id, kind, payload)
    model = MODEL_BY_KIND[kind]
    record = model(campaign_id=str(campaign_id), **_record_values(kind, payload))
    session.add(record)
    session.flush()
    session.refresh(record)
    response = _response(kind, record)
    _audit(
        session,
        campaign_id=str(campaign_id),
        action="create",
        entity_type=kind.value,
        entity_id=record.id,
        after=response.model_dump(mode="json"),
    )
    if commit:
        session.commit()
    return response


def list_entries(
    session: Session, campaign_id: UUID, kind: CaseEntityKind
) -> list[CaseEntryResponse]:
    _ensure_campaign(session, campaign_id)
    model = MODEL_BY_KIND[kind]
    ordering = (
        (model.sort_order, model.created_at)
        if kind is CaseEntityKind.TIMELINE_EVENTS
        else (model.created_at,)
    )
    records = session.scalars(
        select(model).where(model.campaign_id == str(campaign_id)).order_by(*ordering)
    ).all()
    return [_response(kind, record) for record in records]


def get_entry(
    session: Session,
    campaign_id: UUID,
    kind: CaseEntityKind,
    entity_id: UUID,
) -> CaseEntryResponse:
    record = session.scalar(_query(kind, campaign_id, entity_id))
    if record is None:
        raise EntityNotFoundError(f"{kind.value} entry not found")
    return _response(kind, record)


def replace_entry(
    session: Session,
    campaign_id: UUID,
    kind: CaseEntityKind,
    entity_id: UUID,
    payload: CaseEntryReplace,
    *,
    commit: bool = True,
) -> CaseEntryResponse:
    before = get_entry(session, campaign_id, kind, entity_id)
    _validate_payload_shape(kind, payload)
    _validate_references(session, campaign_id, kind, payload)
    model = MODEL_BY_KIND[kind]
    values = _record_values(kind, payload)
    values["version"] = payload.expected_version + 1
    result = cast(
        CursorResult[Any],
        session.execute(
            update(model)
            .where(
                model.id == str(entity_id),
                model.campaign_id == str(campaign_id),
                model.version == payload.expected_version,
            )
            .values(**values)
        ),
    )
    if result.rowcount != 1:
        session.rollback()
        raise VersionConflictError(f"{kind.value} version conflict")
    record = session.scalar(_query(kind, campaign_id, entity_id))
    assert record is not None
    response = _response(kind, record)
    _audit(
        session,
        campaign_id=str(campaign_id),
        action="replace",
        entity_type=kind.value,
        entity_id=str(entity_id),
        expected_version=payload.expected_version,
        before=before.model_dump(mode="json"),
        after=response.model_dump(mode="json"),
    )
    if commit:
        session.commit()
    return response


def delete_entry(
    session: Session,
    campaign_id: UUID,
    kind: CaseEntityKind,
    entity_id: UUID,
    expected_version: int,
) -> None:
    before = get_entry(session, campaign_id, kind, entity_id)
    model = MODEL_BY_KIND[kind]
    result = cast(
        CursorResult[Any],
        session.execute(
            delete(model).where(
                model.id == str(entity_id),
                model.campaign_id == str(campaign_id),
                model.version == expected_version,
            )
        ),
    )
    if result.rowcount != 1:
        session.rollback()
        raise VersionConflictError(f"{kind.value} version conflict")
    _audit(
        session,
        campaign_id=str(campaign_id),
        action="delete",
        entity_type=kind.value,
        entity_id=str(entity_id),
        expected_version=expected_version,
        before=before.model_dump(mode="json"),
    )
    session.commit()


def player_projection(entry: CaseEntryResponse) -> PlayerCaseEntryResponse:
    return PlayerCaseEntryResponse(
        entity_id=entry.entity_id,
        campaign_id=entry.campaign_id,
        kind=entry.kind,
        title=entry.title,
        player_visible_text=entry.player_visible_text,
        status=entry.status,
        time_label=entry.time_label,
        role=entry.role,
        discovered=entry.discovered,
        revealed=entry.revealed,
    )
