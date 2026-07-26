from __future__ import annotations

import hashlib
import json
import math
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
from pydantic import ValidationError
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Engine,
    Integer,
    String,
    Text,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from coc_kp_assistant.api.schemas import ChaseParticipantState
from coc_kp_assistant.config import Settings
from coc_kp_assistant.domain import SourcePackManifest
from coc_kp_assistant.domain.campaigns import CampaignCreate, CampaignEra
from coc_kp_assistant.domain.investigators import (
    CoreCharacteristics,
    InvestigatorBackstory,
    InvestigatorCondition,
    InvestigatorCreate,
    InvestigatorState,
    SkillEntry,
)
from coc_kp_assistant.domain.rolls import RollRequest, RollResolution, resolve_percentile_roll
from coc_kp_assistant.infrastructure.models import (
    Base,
    CampaignRecord,
    StateAuditRecord,
)
from coc_kp_assistant.rag import (
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    PRODUCT_NAMESPACE,
    RULESET_NAMESPACE,
)

EXPORT_SCHEMA_VERSION = 1
COMPLETION_MODEL = "qwen3:30b-instruct"


class DeliveryValidationError(Exception):
    pass


class DeliveryConflictError(Exception):
    pass


EXPORT_TABLES = (
    "campaigns",
    "case_sessions",
    "case_people",
    "case_locations",
    "investigators",
    "investigator_skills",
    "investigator_backstories",
    "case_scenes",
    "case_clues",
    "case_relationships",
    "case_handouts",
    "case_timeline_events",
    "roll_records",
    "rule_operation_logs",
    "chases",
    "ai_proposals",
    "proposal_audits",
    "state_audits",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _model_readiness(settings: Settings) -> dict[str, Any]:
    available: set[str] = set()
    provider_status = "unavailable"
    try:
        with httpx.Client(timeout=1.5, trust_env=False) as client:
            response = client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            payload = response.json()
        models = payload.get("models", []) if isinstance(payload, dict) else []
        if isinstance(models, list):
            for model in models:
                if isinstance(model, dict):
                    name = model.get("name") or model.get("model")
                    if isinstance(name, str):
                        available.add(name)
            provider_status = "ready"
    except (httpx.HTTPError, json.JSONDecodeError, TypeError):
        pass

    def item(name: str) -> dict[str, Any]:
        present = name in available or name.removesuffix(":latest") in available
        return {
            "name": name,
            "status": "ready" if present else "unavailable",
            "installed": present,
            "download_attempted": False,
        }

    return {
        "provider": "ollama",
        "provider_status": provider_status,
        "embedding": item(EMBEDDING_MODEL),
        "completion": item(COMPLETION_MODEL),
    }


def readiness(session: Session, settings: Settings) -> dict[str, Any]:
    database_status = "ready"
    try:
        session.execute(text("SELECT 1")).scalar_one()
    except Exception:  # pragma: no cover - provider/database failures are summarized
        database_status = "unavailable"

    ingestion = _read_json(settings.generated_content_root / "ingestion-report.json")
    source_status = "missing"
    source_details: dict[str, Any] = {"ready_packs": 0, "failed_packs": 0}
    if ingestion is not None:
        packs = ingestion.get("packs", [])
        if ingestion.get("ruleset") != RULESET_NAMESPACE or not isinstance(packs, list):
            source_status = "incompatible"
        else:
            ready_count = sum(
                1 for pack in packs if isinstance(pack, dict) and pack.get("status") == "ready"
            )
            failed_count = len(packs) - ready_count
            source_details = {"ready_packs": ready_count, "failed_packs": failed_count}
            source_status = "ready" if ingestion.get("status") == "ready" else "failed"

    vector_manifest = _read_json(settings.vector_root / f"{COLLECTION_NAME}-manifest.json")
    vector_status = "missing"
    vector_details: dict[str, Any] = {"chunk_count": 0}
    if vector_manifest is not None:
        compatible = (
            vector_manifest.get("product") == PRODUCT_NAMESPACE
            and vector_manifest.get("ruleset") == RULESET_NAMESPACE
            and vector_manifest.get("collection") == COLLECTION_NAME
            and vector_manifest.get("embedding", {}).get("model") == EMBEDDING_MODEL
        )
        vector_status = (
            "ready"
            if compatible and vector_manifest.get("status") == "complete"
            else "incompatible"
        )
        vector_details = {
            "chunk_count": vector_manifest.get("chunk_count", 0),
            "collection": vector_manifest.get("collection"),
            "corpus_digest": vector_manifest.get("corpus_digest"),
        }
    models = _model_readiness(settings)
    return {
        "product": PRODUCT_NAMESPACE,
        "ruleset": RULESET_NAMESPACE,
        "ready": (
            database_status == "ready"
            and source_status == "ready"
            and vector_status == "ready"
            and models["embedding"]["status"] == "ready"
            and models["completion"]["status"] == "ready"
        ),
        "database": {"status": database_status},
        "sources": {"status": source_status, **source_details},
        "vector_index": {"status": vector_status, **vector_details},
        "models": models,
    }


def _catalog_packs(settings: Settings) -> list[dict[str, Any]]:
    catalog = _read_json(settings.source_catalog_path)
    if catalog is None or catalog.get("ruleset") != RULESET_NAMESPACE:
        raise DeliveryValidationError("COC7 source catalog is missing or incompatible")
    raw_packs = catalog.get("packs")
    if not isinstance(raw_packs, list):
        raise DeliveryValidationError("COC7 source catalog packs are invalid")
    packs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_packs:
        manifest = raw.get("manifest") if isinstance(raw, dict) else None
        if not isinstance(manifest, dict):
            raise DeliveryValidationError("COC7 source pack manifest is invalid")
        required_fields = {
            "pack_id",
            "title",
            "version",
            "edition",
            "kind",
            "priority",
            "default_enabled",
            "eras",
        }
        if not required_fields.issubset(manifest):
            raise DeliveryValidationError("COC7 source pack manifest is incomplete")
        try:
            parsed = SourcePackManifest.model_validate(manifest)
        except ValidationError as error:
            raise DeliveryValidationError("COC7 source pack manifest is invalid") from error
        pack_id = parsed.pack_id
        if pack_id in seen:
            raise DeliveryValidationError("COC7 source pack identity is invalid")
        seen.add(pack_id)
        packs.append(
            {
                "pack_id": pack_id,
                "title": parsed.title,
                "version": parsed.version,
                "edition": parsed.edition,
                "kind": parsed.kind.value,
                "default_enabled": parsed.default_enabled,
                "eras": list(parsed.eras),
                "priority": parsed.priority,
                "legacy_namespace": pack_id.startswith("coc-classic."),
            }
        )
    return sorted(packs, key=lambda item: (item["priority"], item["pack_id"]))


def _compatible(pack: dict[str, Any], era: str) -> bool:
    if pack["legacy_namespace"]:
        return False
    eras = pack["eras"]
    normalized_era = era.replace("_", "-")
    return not eras or normalized_era in {str(item).replace("_", "-") for item in eras}


def campaign_source_packs(
    session: Session, settings: Settings, campaign_id: UUID
) -> dict[str, Any]:
    campaign = session.get(CampaignRecord, str(campaign_id))
    if campaign is None:
        raise DeliveryValidationError("campaign not found")
    packs = _catalog_packs(settings)
    by_id = {pack["pack_id"]: pack for pack in packs}
    stored = set(campaign.enabled_source_pack_ids)
    if stored - set(by_id) or any(
        not _compatible(by_id[pack_id], campaign.era) for pack_id in stored
    ):
        raise DeliveryValidationError("campaign contains invalid stored source packs")
    required = {
        pack["pack_id"]
        for pack in packs
        if pack["default_enabled"] and _compatible(pack, campaign.era)
    }
    enabled = stored | required
    return {
        "campaign_id": campaign.id,
        "campaign_version": campaign.version,
        "enabled_source_pack_ids": sorted(enabled),
        "packs": [
            {
                **pack,
                "compatible": _compatible(pack, campaign.era),
                "required_default": pack["pack_id"] in required,
                "enabled": pack["pack_id"] in enabled,
            }
            for pack in packs
        ],
    }


def validated_campaign_source_pack_ids(
    settings: Settings, era: CampaignEra | str, requested_ids: list[str]
) -> list[str]:
    era_value = era.value if isinstance(era, CampaignEra) else CampaignEra(era).value
    packs = _catalog_packs(settings)
    by_id = {pack["pack_id"]: pack for pack in packs}
    requested = set(requested_ids)
    unknown = requested - set(by_id)
    if unknown:
        raise DeliveryValidationError("unknown COC7 source pack: " + ", ".join(sorted(unknown)))
    incompatible = {pack_id for pack_id in requested if not _compatible(by_id[pack_id], era_value)}
    if incompatible:
        raise DeliveryValidationError(
            "source pack is incompatible with campaign era: " + ", ".join(sorted(incompatible))
        )
    required = {
        pack["pack_id"]
        for pack in packs
        if pack["default_enabled"] and _compatible(pack, era_value)
    }
    return sorted(requested | required)


def replace_campaign_source_packs(
    session: Session,
    settings: Settings,
    campaign_id: UUID,
    *,
    expected_version: int,
    enabled_source_pack_ids: list[str],
) -> dict[str, Any]:
    campaign = session.get(CampaignRecord, str(campaign_id))
    if campaign is None:
        raise DeliveryValidationError("campaign not found")
    before_pack_ids = list(campaign.enabled_source_pack_ids)
    after_pack_ids = validated_campaign_source_pack_ids(
        settings, campaign.era, enabled_source_pack_ids
    )
    result = cast(
        CursorResult[Any],
        session.execute(
            update(CampaignRecord)
            .where(
                CampaignRecord.id == str(campaign_id),
                CampaignRecord.version == expected_version,
            )
            .values(
                enabled_source_pack_ids=after_pack_ids,
                version=expected_version + 1,
            )
        ),
    )
    if result.rowcount != 1:
        session.rollback()
        raise DeliveryConflictError("campaign version conflict")
    session.add(
        StateAuditRecord(
            campaign_id=campaign.id,
            action="replace_source_packs",
            entity_type="campaign",
            entity_id=campaign.id,
            expected_version=expected_version,
            before_data={"enabled_source_pack_ids": before_pack_ids},
            after_data={"enabled_source_pack_ids": after_pack_ids},
        )
    )
    session.commit()
    return campaign_source_packs(session, settings, campaign_id)


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    return value


def _campaign_ids(session: Session, campaign_id: str) -> dict[str, set[str]]:
    ids: dict[str, set[str]] = {"campaigns": {campaign_id}}
    for table_name in EXPORT_TABLES:
        table = Base.metadata.tables[table_name]
        if table_name == "campaigns":
            continue
        if "campaign_id" in table.c:
            condition = table.c.campaign_id == campaign_id
        elif table_name in {"investigator_skills", "investigator_backstories"}:
            condition = table.c.investigator_id.in_(ids.get("investigators", set()))
        elif table_name == "proposal_audits":
            condition = table.c.proposal_id.in_(ids.get("ai_proposals", set()))
        else:
            continue
        primary_column = table.c.id if "id" in table.c else list(table.primary_key)[0]
        rows = session.execute(select(primary_column).where(condition))
        ids[table_name] = {str(value) for value in rows.scalars()}
    return ids


def export_campaign(session: Session, campaign_id: UUID) -> dict[str, Any]:
    campaign = session.get(CampaignRecord, str(campaign_id))
    if campaign is None:
        raise DeliveryValidationError("campaign not found")
    ids = _campaign_ids(session, campaign.id)
    tables: dict[str, list[dict[str, Any]]] = {}
    for table_name in EXPORT_TABLES:
        table = Base.metadata.tables[table_name]
        if table_name == "campaigns":
            condition = table.c.id == campaign.id
        elif "campaign_id" in table.c:
            condition = table.c.campaign_id == campaign.id
        elif table_name in {"investigator_skills", "investigator_backstories"}:
            condition = table.c.investigator_id.in_(ids.get("investigators", set()))
        elif table_name == "proposal_audits":
            condition = table.c.proposal_id.in_(ids.get("ai_proposals", set()))
        else:  # pragma: no cover - table whitelist is exhaustively classified
            raise AssertionError(f"unclassified export table {table_name}")
        rows = session.execute(select(table).where(condition)).mappings()
        tables[table_name] = [
            {key: _serialize(value) for key, value in row.items()} for row in rows
        ]
    return {
        "product": PRODUCT_NAMESPACE,
        "ruleset": RULESET_NAMESPACE,
        "schema_version": EXPORT_SCHEMA_VERSION,
        "namespace": f"{PRODUCT_NAMESPACE}/{RULESET_NAMESPACE}",
        "exported_at": datetime.now(UTC).isoformat(),
        "campaign_id": campaign.id,
        "tables": tables,
    }


def _validate_uuid(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise DeliveryValidationError(f"{label} must be a UUID")
    try:
        UUID(value)
    except ValueError as error:
        raise DeliveryValidationError(f"{label} must be a UUID") from error
    return value


def _validate_json_value(value: Any, label: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DeliveryValidationError(f"{label} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise DeliveryValidationError(f"{label} contains a non-string key")
            _validate_json_value(item, f"{label}.{key}")
        return
    raise DeliveryValidationError(f"{label} is not valid JSON")


def _validate_database_row(table_name: str, row: dict[str, Any]) -> None:
    table = Base.metadata.tables[table_name]
    expected_columns = set(table.c.keys())
    if set(row) != expected_columns:
        raise DeliveryValidationError(
            f"{table_name} must contain exactly the exported database columns"
        )
    for column in table.c:
        label = f"{table_name}.{column.name}"
        value = row[column.name]
        if value is None:
            if not column.nullable:
                raise DeliveryValidationError(f"{label} cannot be null")
            continue
        if isinstance(column.type, Boolean):
            if not isinstance(value, bool):
                raise DeliveryValidationError(f"{label} must be a boolean")
        elif isinstance(column.type, Integer):
            if isinstance(value, bool) or not isinstance(value, int):
                raise DeliveryValidationError(f"{label} must be an integer")
        elif isinstance(column.type, DateTime):
            if not isinstance(value, str):
                raise DeliveryValidationError(f"{label} must be an ISO datetime")
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError as error:
                raise DeliveryValidationError(f"{label} must be an ISO datetime") from error
            if parsed.tzinfo is None:
                raise DeliveryValidationError(f"{label} must include a timezone")
        elif isinstance(column.type, (String, Text)):
            if not isinstance(value, str):
                raise DeliveryValidationError(f"{label} must be a string")
            if isinstance(column.type, String) and column.type.length is not None:
                if len(value) > column.type.length:
                    raise DeliveryValidationError(f"{label} exceeds its maximum length")
                if column.type.length == 36:
                    _validate_uuid(value, label)
        elif isinstance(column.type, JSON):
            _validate_json_value(value, label)


def _require_string_list(value: Any, label: str, *, max_length: int = 2_000) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or len(item) > max_length for item in value
    ):
        raise DeliveryValidationError(f"{label} must be an array of bounded strings")
    return value


def _validate_import_semantics(
    validated: dict[str, list[dict[str, Any]]],
    campaign_id: str,
    settings: Settings,
) -> None:
    campaign = validated["campaigns"][0]
    try:
        CampaignCreate.model_validate(
            {
                "title": campaign["title"],
                "ruleset": campaign["ruleset"],
                "era": campaign["era"],
                "custom_era_label": campaign["custom_era_label"],
                "in_world_date": campaign["in_world_date"],
                "starting_location": campaign["starting_location"],
                "enabled_source_pack_ids": campaign["enabled_source_pack_ids"],
                "house_rules": campaign["house_rules"],
                "keeper_notes": campaign["keeper_notes"],
            },
        )
    except ValidationError as error:
        raise DeliveryValidationError("campaign contains invalid COC7 domain data") from error
    if isinstance(campaign["version"], bool) or campaign["version"] < 1:
        raise DeliveryValidationError("campaign.version must be positive")
    _require_string_list(
        campaign["enabled_source_pack_ids"],
        "campaign.enabled_source_pack_ids",
        max_length=80,
    )
    _require_string_list(campaign["house_rules"], "campaign.house_rules", max_length=2_000)

    catalog = _catalog_packs(settings)
    by_id = {item["pack_id"]: item for item in catalog}
    requested = set(campaign["enabled_source_pack_ids"])
    if requested - set(by_id):
        raise DeliveryValidationError("campaign enables an unknown source pack")
    era = CampaignEra(campaign["era"]).value
    if any(not _compatible(by_id[pack_id], era) for pack_id in requested):
        raise DeliveryValidationError("campaign enables an era-incompatible source pack")
    required = {
        item["pack_id"] for item in catalog if item["default_enabled"] and _compatible(item, era)
    }
    if not required.issubset(requested):
        raise DeliveryValidationError("campaign omits a required default source pack")

    skills_by_investigator: dict[str, list[dict[str, Any]]] = {}
    for skill in validated["investigator_skills"]:
        skills_by_investigator.setdefault(skill["investigator_id"], []).append(skill)
        if skill["specialization_key"] != (skill["specialization"] or ""):
            raise DeliveryValidationError("investigator skill specialization identity is invalid")
    backstory_by_investigator = {
        item["investigator_id"]: item for item in validated["investigator_backstories"]
    }
    if len(backstory_by_investigator) != len(validated["investigator_backstories"]):
        raise DeliveryValidationError("investigator backstories contain duplicates")
    if set(backstory_by_investigator) != {item["id"] for item in validated["investigators"]}:
        raise DeliveryValidationError("every investigator must have exactly one backstory")
    for investigator in validated["investigators"]:
        backstory_row = backstory_by_investigator[investigator["id"]]
        backstory_payload = {
            key: _require_string_list(value, f"investigator_backstories.{key}")
            for key, value in backstory_row.items()
            if key != "investigator_id"
        }
        skill_payloads = []
        for skill in skills_by_investigator.get(investigator["id"], []):
            if (
                skill["source_pack_id"] is not None
                and skill["source_pack_id"] not in requested
            ):
                raise DeliveryValidationError(
                    "investigator skill references a disabled source pack"
                )
            skill_payloads.append(
                {
                    "skill_key": skill["skill_key"],
                    "display_name": skill["display_name"],
                    "specialization": skill["specialization"],
                    "base_value": skill["base_value"],
                    "current_value": skill["current_value"],
                    "improvement_mark": skill["improvement_mark"],
                    "source_pack_id": skill["source_pack_id"],
                }
            )
        try:
            profile = InvestigatorCreate(
                name=investigator["name"],
                player_name=investigator["player_name"],
                occupation=investigator["occupation"],
                age=investigator["age"],
                gender=investigator["gender"],
                residence=investigator["residence"],
                birthplace=investigator["birthplace"],
                era=investigator["era"],
                characteristics=CoreCharacteristics(
                    strength=investigator["strength"],
                    constitution=investigator["constitution"],
                    size=investigator["size"],
                    dexterity=investigator["dexterity"],
                    appearance=investigator["appearance"],
                    intelligence=investigator["intelligence"],
                    power=investigator["power"],
                    education=investigator["education"],
                ),
                luck=investigator["luck"],
                move_rate=investigator["move_rate"],
                damage_bonus=investigator["damage_bonus"],
                build=investigator["build"],
                credit_rating=investigator["credit_rating"],
                spending_level=investigator["spending_level"],
                cash=investigator["cash"],
                assets=investigator["assets"],
                skills=tuple(SkillEntry.model_validate(item) for item in skill_payloads),
                backstory=InvestigatorBackstory.model_validate(backstory_payload),
            )
            InvestigatorState(
                investigator_id=UUID(investigator["id"]),
                campaign_id=UUID(campaign_id),
                profile=profile,
                hit_points=investigator["hit_points"],
                magic_points=investigator["magic_points"],
                sanity=investigator["sanity"],
                mythos=investigator["mythos"],
                conditions=frozenset(
                    InvestigatorCondition(item)
                    for item in _require_string_list(
                        investigator["conditions"], "investigator.conditions", max_length=40
                    )
                ),
                version=investigator["version"],
            )
        except (ValidationError, ValueError) as error:
            raise DeliveryValidationError(
                "investigator contains invalid COC7 domain data"
            ) from error

    case_tables = (
        "case_sessions",
        "case_people",
        "case_locations",
        "case_scenes",
        "case_clues",
        "case_relationships",
        "case_handouts",
        "case_timeline_events",
    )
    valid_case_statuses = {
        "planned",
        "active",
        "inactive",
        "draft",
        "complete",
        "completed",
        "discovered",
        "revealed",
        "archived",
    }
    for table_name in case_tables:
        for row in validated[table_name]:
            if not row["title"].strip() or row["status"] not in valid_case_statuses:
                raise DeliveryValidationError(f"{table_name} contains invalid title/status")
            if row["version"] < 1:
                raise DeliveryValidationError(f"{table_name}.version must be positive")
    for relationship in validated["case_relationships"]:
        if relationship["source_clue_id"] == relationship["target_clue_id"]:
            raise DeliveryValidationError("case relationship cannot point to itself")

    for roll in validated["roll_records"]:
        if not roll["label"].strip():
            raise DeliveryValidationError("roll label cannot be empty")
        try:
            request = RollRequest.model_validate(roll["request_data"])
            resolution = RollResolution.model_validate(roll["resolution_data"])
        except ValidationError as error:
            raise DeliveryValidationError(
                "roll record contains invalid deterministic data"
            ) from error
        if resolution != resolve_percentile_roll(request):
            raise DeliveryValidationError("roll resolution does not match its request")

    for operation in validated["rule_operation_logs"]:
        if not operation["operation_type"].strip():
            raise DeliveryValidationError("rule operation type cannot be empty")
        valid_operation_subjects = {item["id"] for item in validated["investigators"]} | {
            item["id"] for item in validated["chases"]
        }
        if operation["subject_id"] not in valid_operation_subjects:
            raise DeliveryValidationError("rule operation subject is outside the campaign")
        for field in ("input_data", "output_data", "citation_data"):
            if not isinstance(operation[field], dict):
                raise DeliveryValidationError(f"rule operation {field} must be an object")

    for chase in validated["chases"]:
        if (
            not chase["title"].strip()
            or chase["status"] not in {"active", "caught", "escaped"}
            or chase["round"] < 1
            or chase["escape_distance"] < 1
            or chase["track_length"] < 1
            or chase["escape_distance"] > chase["track_length"]
            or chase["version"] < 1
            or not isinstance(chase["participants"], list)
            or not 2 <= len(chase["participants"]) <= 20
        ):
            raise DeliveryValidationError("chase contains invalid COC7 state")
        try:
            participants = [
                ChaseParticipantState.model_validate(item) for item in chase["participants"]
            ]
        except ValidationError as error:
            raise DeliveryValidationError("chase participants are invalid") from error
        if len({item.investigator_id for item in participants}) != len(participants):
            raise DeliveryValidationError("chase participants must be unique")
        investigator_ids = {item["id"] for item in validated["investigators"]}
        if any(str(item.investigator_id) not in investigator_ids for item in participants):
            raise DeliveryValidationError("chase participant is not an investigator")
        if any(item.position > chase["track_length"] for item in participants):
            raise DeliveryValidationError("chase participant exceeds the track")

    for proposal in validated["ai_proposals"]:
        if (
            proposal["proposal_type"] not in {"case_state_create", "case_state_replace"}
            or proposal["case_kind"]
            not in {
                "sessions",
                "people",
                "locations",
                "scenes",
                "clues",
                "relationships",
                "handouts",
                "timeline-events",
            }
            or proposal["status"] not in {"pending", "confirmed", "rejected"}
            or proposal["campaign_version"] < 1
            or proposal["version"] < 1
            or not isinstance(proposal["payload"], dict)
            or not isinstance(proposal["model_metadata"], dict)
            or not isinstance(proposal["evidence"], list)
            or any(not isinstance(item, dict) for item in proposal["evidence"])
            or proposal["model_name"] != COMPLETION_MODEL
        ):
            raise DeliveryValidationError("AI proposal contains invalid state")
        citation_ids = _require_string_list(
            proposal["citation_ids"], "ai_proposals.citation_ids"
        )
        for citation_id in citation_ids:
            _validate_uuid(citation_id, "ai_proposals.citation_ids")
        if proposal["proposal_type"] == "case_state_create" and (
            proposal["target_entity_id"] is not None or proposal["target_version"] is not None
        ):
            raise DeliveryValidationError("create proposal cannot target an entity")
        if proposal["proposal_type"] == "case_state_replace" and (
            proposal["target_entity_id"] is None
            or proposal["target_version"] is None
            or proposal["target_version"] < 1
        ):
            raise DeliveryValidationError("replace proposal target is invalid")
        table_for_kind = {
            "sessions": "case_sessions",
            "people": "case_people",
            "locations": "case_locations",
            "scenes": "case_scenes",
            "clues": "case_clues",
            "relationships": "case_relationships",
            "handouts": "case_handouts",
            "timeline-events": "case_timeline_events",
        }[proposal["case_kind"]]
        target_ids = {item["id"] for item in validated[table_for_kind]}
        if (
            proposal["target_entity_id"] is not None
            and proposal["target_entity_id"] not in target_ids
        ):
            raise DeliveryValidationError("AI proposal target is outside its case kind")
        if (
            proposal["applied_entity_id"] is not None
            and proposal["applied_entity_id"] not in target_ids
        ):
            raise DeliveryValidationError("AI proposal applied entity is outside its case kind")
        created_at = datetime.fromisoformat(proposal["created_at"])
        expires_at = datetime.fromisoformat(proposal["expires_at"])
        resolved_at = (
            datetime.fromisoformat(proposal["resolved_at"])
            if proposal["resolved_at"] is not None
            else None
        )
        if expires_at <= created_at:
            raise DeliveryValidationError("AI proposal expiry is invalid")
        if proposal["status"] == "pending" and (
            resolved_at is not None
            or proposal["rejection_reason"] is not None
            or proposal["applied_entity_id"] is not None
        ):
            raise DeliveryValidationError("pending AI proposal contains resolved state")
        if proposal["status"] == "confirmed" and (
            resolved_at is None
            or proposal["applied_entity_id"] is None
            or proposal["rejection_reason"] is not None
        ):
            raise DeliveryValidationError("confirmed AI proposal state is incomplete")
        if proposal["status"] == "rejected" and (
            resolved_at is None
            or proposal["applied_entity_id"] is not None
            or not (proposal["rejection_reason"] or "").strip()
        ):
            raise DeliveryValidationError("rejected AI proposal state is incomplete")
    for audit in validated["proposal_audits"]:
        if audit["action"] not in {"confirm", "reject"}:
            raise DeliveryValidationError("proposal audit action is invalid")
        if (
            audit["expected_version"] < 1
            or not isinstance(audit["before_data"], dict)
            or not isinstance(audit["after_data"], dict)
        ):
            raise DeliveryValidationError("proposal audit state is invalid")
    for audit in validated["state_audits"]:
        if not audit["action"].strip() or not audit["entity_type"].strip():
            raise DeliveryValidationError("state audit identity is invalid")
        if audit["expected_version"] is not None and audit["expected_version"] < 1:
            raise DeliveryValidationError("state audit version is invalid")
        if audit["before_data"] is not None and not isinstance(audit["before_data"], dict):
            raise DeliveryValidationError("state audit before_data must be an object")
        if audit["after_data"] is not None and not isinstance(audit["after_data"], dict):
            raise DeliveryValidationError("state audit after_data must be an object")


def _validated_import(
    bundle: dict[str, Any], settings: Settings
) -> tuple[str, dict[str, list[dict[str, Any]]]]:
    expected_bundle_keys = {
        "product",
        "ruleset",
        "schema_version",
        "namespace",
        "exported_at",
        "campaign_id",
        "tables",
    }
    if set(bundle) != expected_bundle_keys:
        raise DeliveryValidationError("export bundle contains missing or unknown fields")
    if bundle.get("product") != PRODUCT_NAMESPACE:
        raise DeliveryValidationError("export product namespace is not local-coc-kp-assistant")
    if bundle.get("ruleset") != RULESET_NAMESPACE:
        raise DeliveryValidationError("export ruleset must be coc7e")
    if bundle.get("schema_version") != EXPORT_SCHEMA_VERSION:
        raise DeliveryValidationError("unsupported export schema version")
    if bundle.get("namespace") != f"{PRODUCT_NAMESPACE}/{RULESET_NAMESPACE}":
        raise DeliveryValidationError("export namespace is invalid")
    exported_at = bundle.get("exported_at")
    if not isinstance(exported_at, str):
        raise DeliveryValidationError("exported_at must be an ISO datetime")
    try:
        parsed_exported_at = datetime.fromisoformat(exported_at)
    except ValueError as error:
        raise DeliveryValidationError("exported_at must be an ISO datetime") from error
    if parsed_exported_at.tzinfo is None:
        raise DeliveryValidationError("exported_at must include a timezone")
    campaign_id = _validate_uuid(bundle.get("campaign_id"), "campaign_id")
    tables = bundle.get("tables")
    if not isinstance(tables, dict) or set(tables) != set(EXPORT_TABLES):
        raise DeliveryValidationError("export table set is incomplete or unknown")
    validated: dict[str, list[dict[str, Any]]] = {}
    known_ids: dict[str, set[str]] = {}
    for table_name in EXPORT_TABLES:
        table = Base.metadata.tables[table_name]
        raw_rows = tables[table_name]
        if not isinstance(raw_rows, list):
            raise DeliveryValidationError(f"{table_name} must be an array")
        rows: list[dict[str, Any]] = []
        ids: set[str] = set()
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                raise DeliveryValidationError(f"{table_name} rows must be objects")
            row = dict(raw_row)
            _validate_database_row(table_name, row)
            if "ruleset" in table.c and row.get("ruleset") != RULESET_NAMESPACE:
                raise DeliveryValidationError(f"{table_name} contains a foreign ruleset")
            if "campaign_id" in table.c and row.get("campaign_id") != campaign_id:
                raise DeliveryValidationError(
                    f"{table_name} contains an invalid campaign reference"
                )
            primary = next(iter(table.primary_key.columns))
            primary_value = _validate_uuid(row.get(primary.name), f"{table_name}.{primary.name}")
            if primary_value in ids:
                raise DeliveryValidationError(f"{table_name} contains duplicate primary keys")
            ids.add(primary_value)
            rows.append(row)
        known_ids[table_name] = ids
        validated[table_name] = rows
    if len(validated["campaigns"]) != 1 or known_ids["campaigns"] != {campaign_id}:
        raise DeliveryValidationError("export must contain exactly one matching campaign")

    # Validate every exported foreign-key reference before opening the write transaction.
    target_by_table = {
        "campaigns": known_ids["campaigns"],
        "case_sessions": known_ids["case_sessions"],
        "case_people": known_ids["case_people"],
        "case_locations": known_ids["case_locations"],
        "investigators": known_ids["investigators"],
        "case_scenes": known_ids["case_scenes"],
        "case_clues": known_ids["case_clues"],
        "ai_proposals": known_ids["ai_proposals"],
    }
    for table_name, rows in validated.items():
        table = Base.metadata.tables[table_name]
        for row in rows:
            for column in table.c:
                for foreign_key in column.foreign_keys:
                    value = row.get(column.name)
                    if value is None:
                        continue
                    target_table = foreign_key.column.table.name
                    if (
                        target_table in target_by_table
                        and value not in target_by_table[target_table]
                    ):
                        raise DeliveryValidationError(
                            f"{table_name}.{column.name} contains an invalid reference"
                        )
    _validate_import_semantics(validated, campaign_id, settings)
    return campaign_id, validated


def import_campaign(session: Session, settings: Settings, bundle: dict[str, Any]) -> str:
    campaign_id, tables = _validated_import(bundle, settings)
    if session.get(CampaignRecord, campaign_id) is not None:
        raise DeliveryConflictError("campaign already exists; overwrite is disabled")
    try:
        for table_name in EXPORT_TABLES:
            table = Base.metadata.tables[table_name]
            rows = tables[table_name]
            for row in rows:
                converted = dict(row)
                for column in table.c:
                    value = converted.get(column.name)
                    if isinstance(column.type, DateTime) and isinstance(value, str):
                        converted[column.name] = datetime.fromisoformat(value)
                session.execute(insert(table).values(**converted))
        session.add(
            StateAuditRecord(
                campaign_id=campaign_id,
                action="import_campaign",
                entity_type="campaign",
                entity_id=campaign_id,
                before_data=None,
                after_data={
                    "product": PRODUCT_NAMESPACE,
                    "ruleset": RULESET_NAMESPACE,
                    "schema_version": EXPORT_SCHEMA_VERSION,
                },
            )
        )
        session.commit()
    except DeliveryValidationError:
        raise
    except Exception as error:
        session.rollback()
        raise DeliveryValidationError("campaign import failed atomically") from error
    return campaign_id


def _safe_backup_root(settings: Settings, destination: str | None) -> Path:
    if destination is None:
        root = settings.backup_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
    else:
        requested = Path(destination).expanduser()
        if not requested.is_absolute() or requested.is_symlink() or not requested.is_dir():
            raise DeliveryValidationError(
                "backup destination must be an existing absolute non-symlink directory"
            )
        root = requested.resolve()
    vector_root = settings.vector_root.expanduser().resolve()
    if root == vector_root or root.is_relative_to(vector_root):
        raise DeliveryValidationError("backup destination cannot be inside the vector index")
    return root


def _snapshot_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise DeliveryValidationError("vector index cannot contain symbolic links")
        if path.is_file():
            files.append(path)
    return sorted(files)


def _reject_symlink_components(path: Path, label: str) -> Path:
    lexical = path.expanduser()
    if not lexical.is_absolute():
        lexical = Path.cwd() / lexical
    for component in reversed((lexical, *lexical.parents)):
        if component.is_symlink():
            raise DeliveryValidationError(f"{label} cannot contain symbolic links")
    return lexical.resolve()


def create_backup(
    engine: Engine, settings: Settings, destination: str | None = None
) -> dict[str, Any]:
    database_path_value = engine.url.database
    if not database_path_value or database_path_value == ":memory:":
        raise DeliveryValidationError("online backup requires a file-backed SQLite database")
    database_path = Path(database_path_value).expanduser().resolve()
    if not database_path.is_file():
        raise DeliveryValidationError("SQLite database file is missing")
    root = _safe_backup_root(settings, destination)
    backup_name = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    staging = root / f".{backup_name}.staging"
    final = root / backup_name
    if staging.exists() or final.exists():
        raise DeliveryConflictError("backup destination already exists")
    staging.mkdir()
    try:
        database_backup = staging / "database.sqlite3"
        with sqlite3.connect(database_path) as source, sqlite3.connect(database_backup) as target:
            source.backup(target)

        vector_destination = staging / "vector-index"
        vector_files_before: dict[str, str] = {}
        vector_root = _reject_symlink_components(settings.vector_root, "vector index")
        if vector_root.is_dir():
            for source_file in _snapshot_files(vector_root):
                vector_files_before[str(source_file.relative_to(vector_root))] = _sha256(
                    source_file
                )
            shutil.copytree(vector_root, vector_destination)
            vector_files_after = {
                str(source_file.relative_to(vector_destination)): _sha256(source_file)
                for source_file in _snapshot_files(vector_destination)
            }
            current_source = {
                str(source_file.relative_to(vector_root)): _sha256(source_file)
                for source_file in _snapshot_files(vector_root)
            }
            if vector_files_before != vector_files_after or vector_files_before != current_source:
                raise DeliveryConflictError("vector index changed during backup; retry")

        files = {
            str(path.relative_to(staging)): _sha256(path)
            for path in sorted(path for path in staging.rglob("*") if path.is_file())
        }
        manifest = {
            "product": PRODUCT_NAMESPACE,
            "ruleset": RULESET_NAMESPACE,
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "database_method": "sqlite_online_backup",
            "vector_snapshot_consistent": True,
            "files": files,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(final)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {"path": str(final), "manifest": manifest}


def verify_backup(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise DeliveryValidationError("backup path must be an absolute non-symlink directory")
    root = _reject_symlink_components(path, "backup path")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink():
        raise DeliveryValidationError("backup manifest cannot be a symbolic link")
    manifest = _read_json(manifest_path)
    if (
        manifest is None
        or manifest.get("product") != PRODUCT_NAMESPACE
        or manifest.get("ruleset") != RULESET_NAMESPACE
        or manifest.get("schema_version") != 1
    ):
        raise DeliveryValidationError("backup manifest is missing or incompatible")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise DeliveryValidationError("backup checksum manifest is invalid")
    expected_files: dict[str, str] = {}
    for relative, expected in files.items():
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not isinstance(expected, str)
            or len(expected) != 64
            or any(character not in "0123456789abcdef" for character in expected)
            or relative == "manifest.json"
        ):
            raise DeliveryValidationError("backup checksum path is unsafe")
        expected_files[relative] = expected
    actual_files: dict[str, Path] = {}
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise DeliveryValidationError("backup cannot contain symbolic links")
        if candidate.is_file() and candidate != manifest_path:
            actual_files[str(candidate.relative_to(root))] = candidate
    expected_names = set(expected_files)
    actual_names = set(actual_files)
    mismatches = sorted(expected_names ^ actual_names)
    for relative in sorted(expected_names & actual_names):
        candidate = root / relative
        if (
            not candidate.resolve().is_relative_to(root)
            or _sha256(candidate) != expected_files[relative]
        ):
            mismatches.append(relative)
    return {
        "valid": not mismatches,
        "mismatches": mismatches,
        "restore_performed": False,
        "product": PRODUCT_NAMESPACE,
        "ruleset": RULESET_NAMESPACE,
    }
