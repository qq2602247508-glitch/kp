from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import DateTime, Engine, insert, select, text
from sqlalchemy.orm import Session

from coc_kp_assistant.config import Settings
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
        pack_id = manifest.get("pack_id")
        if (
            not isinstance(pack_id, str)
            or not pack_id.startswith(("coc7e.", "coc-classic."))
            or pack_id in seen
        ):
            raise DeliveryValidationError("COC7 source pack identity is invalid")
        seen.add(pack_id)
        packs.append(
            {
                "pack_id": pack_id,
                "title": str(manifest.get("title", pack_id)),
                "version": str(manifest.get("version", "")),
                "edition": str(manifest.get("edition", "")),
                "kind": str(manifest.get("kind", "")),
                "default_enabled": bool(manifest.get("default_enabled", False)),
                "eras": [
                    str(era) for era in manifest.get("eras", []) if isinstance(era, str)
                ],
                "priority": int(manifest.get("priority", 100)),
                "legacy_namespace": pack_id.startswith("coc-classic."),
            }
        )
    return sorted(packs, key=lambda item: (item["priority"], item["pack_id"]))


def _compatible(pack: dict[str, Any], era: str) -> bool:
    if pack["legacy_namespace"]:
        return False
    eras = pack["eras"]
    normalized_era = era.replace("_", "-")
    return not eras or normalized_era in {
        str(item).replace("_", "-") for item in eras
    }


def campaign_source_packs(
    session: Session, settings: Settings, campaign_id: UUID
) -> dict[str, Any]:
    campaign = session.get(CampaignRecord, str(campaign_id))
    if campaign is None:
        raise DeliveryValidationError("campaign not found")
    packs = _catalog_packs(settings)
    required = {
        pack["pack_id"]
        for pack in packs
        if pack["default_enabled"] and _compatible(pack, campaign.era)
    }
    enabled = set(campaign.enabled_source_pack_ids) | required
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
    if campaign.version != expected_version:
        raise DeliveryConflictError("campaign version conflict")
    packs = _catalog_packs(settings)
    by_id = {pack["pack_id"]: pack for pack in packs}
    requested = set(enabled_source_pack_ids)
    unknown = requested - set(by_id)
    if unknown:
        raise DeliveryValidationError("unknown COC7 source pack: " + ", ".join(sorted(unknown)))
    incompatible = {
        pack_id
        for pack_id in requested
        if not _compatible(by_id[pack_id], campaign.era)
    }
    if incompatible:
        raise DeliveryValidationError(
            "source pack is incompatible with campaign era: "
            + ", ".join(sorted(incompatible))
        )
    required = {
        pack["pack_id"]
        for pack in packs
        if pack["default_enabled"] and _compatible(pack, campaign.era)
    }
    before_pack_ids = list(campaign.enabled_source_pack_ids)
    campaign.enabled_source_pack_ids = sorted(requested | required)
    campaign.version += 1
    session.add(
        StateAuditRecord(
            campaign_id=campaign.id,
            action="replace_source_packs",
            entity_type="campaign",
            entity_id=campaign.id,
            expected_version=expected_version,
            before_data={"enabled_source_pack_ids": before_pack_ids},
            after_data={
                "enabled_source_pack_ids": list(campaign.enabled_source_pack_ids)
            },
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


def _validated_import(bundle: dict[str, Any]) -> tuple[str, dict[str, list[dict[str, Any]]]]:
    if bundle.get("product") != PRODUCT_NAMESPACE:
        raise DeliveryValidationError("export product namespace is not local-coc-kp-assistant")
    if bundle.get("ruleset") != RULESET_NAMESPACE:
        raise DeliveryValidationError("export ruleset must be coc7e")
    if bundle.get("schema_version") != EXPORT_SCHEMA_VERSION:
        raise DeliveryValidationError("unsupported export schema version")
    if bundle.get("namespace") != f"{PRODUCT_NAMESPACE}/{RULESET_NAMESPACE}":
        raise DeliveryValidationError("export namespace is invalid")
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
        allowed_columns = set(table.c.keys())
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict) or set(raw_row) - allowed_columns:
                raise DeliveryValidationError(f"{table_name} contains unknown columns")
            row = dict(raw_row)
            if "ruleset" in table.c and row.get("ruleset") != RULESET_NAMESPACE:
                raise DeliveryValidationError(f"{table_name} contains a foreign ruleset")
            if "campaign_id" in table.c and row.get("campaign_id") not in {
                campaign_id,
                None,
            }:
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
    return campaign_id, validated


def import_campaign(session: Session, bundle: dict[str, Any]) -> str:
    campaign_id, tables = _validated_import(bundle)
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
        if settings.vector_root.is_dir():
            for source_file in _snapshot_files(settings.vector_root):
                vector_files_before[str(source_file.relative_to(settings.vector_root))] = _sha256(
                    source_file
                )
            shutil.copytree(settings.vector_root, vector_destination)
            vector_files_after = {
                str(source_file.relative_to(vector_destination)): _sha256(source_file)
                for source_file in _snapshot_files(vector_destination)
            }
            current_source = {
                str(source_file.relative_to(settings.vector_root)): _sha256(source_file)
                for source_file in _snapshot_files(settings.vector_root)
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
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise DeliveryValidationError("backup path must be an absolute non-symlink directory")
    root = path.resolve()
    manifest = _read_json(root / "manifest.json")
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
    mismatches: list[str] = []
    for relative, expected in files.items():
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not isinstance(expected, str)
        ):
            raise DeliveryValidationError("backup checksum path is unsafe")
        candidate = root / relative
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or not candidate.resolve().is_relative_to(root)
            or _sha256(candidate) != expected
        ):
            mismatches.append(relative)
    return {
        "valid": not mismatches,
        "mismatches": mismatches,
        "restore_performed": False,
        "product": PRODUCT_NAMESPACE,
        "ruleset": RULESET_NAMESPACE,
    }
