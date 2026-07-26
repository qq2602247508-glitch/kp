import json
from pathlib import Path

import pytest

from coc_kp_assistant.rag import PRODUCT_NAMESPACE, load_ingested_corpus


def _record(pack_id: str, checksum: str) -> dict[str, object]:
    return {
        "content": {
            "pages": [
                {
                    "page_number": 1,
                    "provenance": {
                        "edition": "7e",
                        "eras": [],
                        "filename": "core.pdf",
                        "format": "pdf",
                        "locator": "page:1",
                        "module": "core",
                        "sha256": checksum,
                        "source_pack": pack_id,
                    },
                    "text": "Core rules",
                }
            ]
        },
        "default_enabled": True,
        "edition": "7e",
        "kind": "core",
        "pack_id": pack_id,
        "provenance": {
            "edition": "7e",
            "eras": [],
            "filename": "core.pdf",
            "format": "pdf",
            "locator": "source",
            "module": "core",
            "sha256": checksum,
            "source_pack": pack_id,
            "source_path": "/read-only/core.pdf",
        },
        "ruleset": "coc7e",
        "title": "Core",
        "version": "test",
    }


def _write_generated(root: Path, *, checksum: str = "a" * 64) -> None:
    pack_id = "coc7e.core.test"
    records = root / "records"
    records.mkdir(parents=True)
    (records / f"{pack_id}.json").write_text(
        json.dumps(_record(pack_id, checksum)),
        encoding="utf-8",
    )
    (root / "ingestion-report.json").write_text(
        json.dumps(
            {
                "catalog_version": 1,
                "dry_run": False,
                "packs": [
                    {
                        "default_enabled": True,
                        "pack_id": pack_id,
                        "sha256": "a" * 64,
                        "status": "ready",
                    }
                ],
                "ruleset": "coc7e",
                "status": "ready",
            }
        ),
        encoding="utf-8",
    )


def test_load_ingested_corpus_accepts_complete_task_one_outputs(tmp_path: Path) -> None:
    _write_generated(tmp_path)

    corpus = load_ingested_corpus(tmp_path)

    assert corpus.product == PRODUCT_NAMESPACE
    assert [record["pack_id"] for record in corpus.records] == ["coc7e.core.test"]


@pytest.mark.parametrize("mutation", ["failed_report", "missing_record", "checksum_mismatch"])
def test_load_ingested_corpus_fails_closed_on_incomplete_outputs(
    tmp_path: Path, mutation: str
) -> None:
    _write_generated(tmp_path, checksum="b" * 64 if mutation == "checksum_mismatch" else "a" * 64)
    if mutation == "failed_report":
        report_path = tmp_path / "ingestion-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["status"] = "failed"
        report_path.write_text(json.dumps(report), encoding="utf-8")
    elif mutation == "missing_record":
        (tmp_path / "records" / "coc7e.core.test.json").unlink()

    with pytest.raises(ValueError, match="ingestion"):
        load_ingested_corpus(tmp_path)


def test_load_ingested_corpus_refuses_a_foreign_product_namespace(tmp_path: Path) -> None:
    _write_generated(tmp_path)

    with pytest.raises(ValueError, match="COC"):
        load_ingested_corpus(tmp_path, product="foreign-assistant")
