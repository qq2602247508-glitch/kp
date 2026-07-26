import argparse
import hashlib
import json
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from coc_kp_assistant.domain import SourcePackManifest

APPROVED_DEFAULT_PACK_IDS = frozenset(
    {
        "coc7e.core.zh-v1.2.1",
        "coc7e.investigator-handbook.zh-v1.21",
    }
)


def default_enabled_for_pack(pack_id: str, *, requested: bool) -> bool:
    """Return whether a catalog pack is enabled in the default COC7 corpus."""
    return requested and pack_id in APPROVED_DEFAULT_PACK_IDS


_SUPPORTED_FORMATS = frozenset({"pdf", "docx", "xlsx", "xlsm"})
_SUFFIX_BY_FORMAT = {"pdf": ".pdf", "docx": ".docx", "xlsx": ".xlsx", "xlsm": ".xlsm"}
_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_OFFICE_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PACKAGE_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def ingest_catalog(
    catalog_path: Path,
    *,
    output_root: Path,
    dry_run: bool = False,
) -> dict[str, object]:
    """Read registered local sources and emit deterministic, local-only records."""
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog_errors = _validate_catalog(catalog)
    previous_checksums = _previous_checksums(output_root)
    pack_reports: list[dict[str, object]] = []
    records: list[tuple[str, dict[str, object]]] = []

    for item in sorted(catalog.get("packs", []), key=lambda pack: str(pack["manifest"]["pack_id"])):
        pack_report, record = _ingest_pack(item, previous_checksums)
        pack_reports.append(pack_report)
        if record is not None:
            records.append((str(record["pack_id"]), record))

    all_errors = catalog_errors or any(pack["status"] == "rejected" for pack in pack_reports)
    report: dict[str, object] = {
        "catalog_version": catalog.get("catalog_version"),
        "dry_run": dry_run,
        "packs": pack_reports,
        "ruleset": catalog.get("ruleset"),
        "status": "failed" if all_errors else "ready",
    }
    if catalog_errors:
        report["errors"] = catalog_errors

    if not dry_run:
        _write_outputs(output_root, records, report)
    return report


def _validate_catalog(catalog: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if catalog.get("ruleset") != "coc7e":
        errors.append({"code": "unsupported_ruleset", "message": "catalog ruleset must be coc7e"})
    policy = catalog.get("import_policy")
    if not isinstance(policy, dict):
        errors.append({"code": "invalid_policy", "message": "catalog import_policy is required"})
    elif (
        policy.get("execute_office_macros") is not False
        or policy.get("xlsm_macro_handling") != "never_execute"
        or policy.get("external_links") != "never_follow"
    ):
        errors.append({"code": "unsafe_policy", "message": "catalog must disable macros and links"})
    if not isinstance(catalog.get("packs"), list):
        errors.append({"code": "invalid_catalog", "message": "catalog packs must be a list"})
    return errors


def _previous_checksums(output_root: Path) -> dict[str, str]:
    report_path = output_root / "ingestion-report.json"
    if not report_path.is_file():
        return {}
    try:
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        checksums: dict[str, str] = {}
        for pack in previous.get("packs", []):
            if not isinstance(pack, dict) or not isinstance(pack.get("pack_id"), str):
                continue
            checksum = (
                pack.get("sha256") if pack.get("status") == "ready" else pack.get("expected_sha256")
            )
            if isinstance(checksum, str):
                checksums[pack["pack_id"]] = checksum
        return checksums
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def _ingest_pack(
    item: dict[str, Any], previous_checksums: dict[str, str]
) -> tuple[dict[str, object], dict[str, object] | None]:
    manifest_data = item.get("manifest")
    source = item.get("source")
    if not isinstance(manifest_data, dict) or not isinstance(source, dict):
        return (
            _rejected_report(
                "unknown", "invalid_catalog_entry", "manifest and source are required"
            ),
            None,
        )
    try:
        manifest = SourcePackManifest.model_validate(manifest_data)
    except ValueError as error:
        pack_id = str(manifest_data.get("pack_id", "unknown"))
        return _rejected_report(pack_id, "invalid_manifest", str(error)), None

    source_path_value = source.get("original_absolute_path")
    source_format = source.get("format")
    if not isinstance(source_path_value, str) or not Path(source_path_value).is_absolute():
        return (
            _rejected_report(
                manifest.pack_id, "invalid_source_path", "source path must be absolute"
            ),
            None,
        )
    if source_format not in _SUPPORTED_FORMATS:
        return (
            _rejected_report(
                manifest.pack_id, "unsupported_source", "source format is unsupported"
            ),
            None,
        )
    source_path = Path(source_path_value)
    if source_path.suffix.lower() != _SUFFIX_BY_FORMAT[source_format]:
        return (
            _rejected_report(
                manifest.pack_id, "catalog_mismatch", "source suffix does not match format"
            ),
            None,
        )
    if not source_path.is_file():
        return _rejected_report(
            manifest.pack_id, "missing_source", "source file does not exist"
        ), None

    checksum = _sha256(source_path)
    expected_checksum = source.get("sha256") or previous_checksums.get(manifest.pack_id)
    if expected_checksum is not None and expected_checksum != checksum:
        return (
            {
                "actual_sha256": checksum,
                "errors": [
                    {"code": "changed_source", "message": "source checksum differs from baseline"}
                ],
                "expected_sha256": expected_checksum,
                "pack_id": manifest.pack_id,
                "status": "rejected",
            },
            None,
        )
    try:
        content = _extract(source_path, source_format)
    except (
        BadZipFile,
        ElementTree.ParseError,
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
    ) as error:
        return _rejected_report(manifest.pack_id, "unreadable_source", str(error)), None

    record: dict[str, object] = {
        "content": content,
        "default_enabled": default_enabled_for_pack(
            manifest.pack_id, requested=manifest.default_enabled
        ),
        "edition": manifest.edition,
        "kind": manifest.kind.value,
        "pack_id": manifest.pack_id,
        "provenance": {
            "filename": source_path.name,
            "format": source_format,
            "sha256": checksum,
            "source_path": str(source_path),
        },
        "ruleset": manifest.ruleset,
        "title": manifest.title,
        "version": manifest.version,
    }
    return (
        {
            "default_enabled": record["default_enabled"],
            "pack_id": manifest.pack_id,
            "sha256": checksum,
            "status": "ready",
        },
        record,
    )


def _rejected_report(pack_id: str, code: str, message: str) -> dict[str, object]:
    return {
        "errors": [{"code": code, "message": message}],
        "pack_id": pack_id,
        "status": "rejected",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _extract(path: Path, source_format: str) -> dict[str, object]:
    if source_format == "pdf":
        return _extract_pdf(path)
    if source_format == "docx":
        return _extract_docx(path)
    if source_format in {"xlsx", "xlsm"}:
        return _extract_workbook(path)
    raise ValueError(f"source format is unsupported: {source_format}")


def _extract_docx(path: Path) -> dict[str, object]:
    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{_WORD_NS}body")
    if body is None:
        raise ValueError("DOCX document body is missing")
    paragraphs = [_word_text(element) for element in body.findall(f"{_WORD_NS}p")]
    tables = []
    for table in body.findall(f"{_WORD_NS}tbl"):
        rows = []
        for row in table.findall(f"{_WORD_NS}tr"):
            rows.append([_word_text(cell) for cell in row.findall(f"{_WORD_NS}tc")])
        tables.append(rows)
    return {"paragraphs": paragraphs, "tables": tables}


def _word_text(element: ElementTree.Element) -> str:
    return "".join(text.text or "" for text in element.iter(f"{_WORD_NS}t"))


def _extract_pdf(path: Path) -> dict[str, object]:
    pdfinfo = shutil.which("pdfinfo")
    pdftotext = shutil.which("pdftotext")
    if pdfinfo is None or pdftotext is None:
        raise RuntimeError("pdfinfo and pdftotext are required for PDF text extraction")
    info = subprocess.run([pdfinfo, str(path)], capture_output=True, text=True, check=False)
    if info.returncode != 0:
        raise ValueError("PDF cannot be read")
    details = dict(line.split(":", 1) for line in info.stdout.splitlines() if ":" in line)
    if details.get("Encrypted", "").strip().lower() == "yes":
        raise ValueError("encrypted PDF is not accepted")
    try:
        page_count = int(details["Pages"].strip())
    except (KeyError, ValueError) as error:
        raise ValueError("PDF page count is unavailable") from error
    pages = []
    for page_number in range(1, page_count + 1):
        text_result = subprocess.run(
            [pdftotext, "-f", str(page_number), "-l", str(page_number), str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        page_text = text_result.stdout.strip()
        if text_result.returncode != 0 or not page_text:
            raise ValueError(f"PDF page {page_number} has no readable text layer")
        pages.append({"page_number": page_number, "text": page_text})
    return {"pages": pages}


def _extract_workbook(path: Path) -> dict[str, object]:
    with ZipFile(path) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = _workbook_relationships(archive)
        shared_strings = _shared_strings(archive)
        sheets = []
        for sheet in workbook.findall(f".//{_SHEET_NS}sheet"):
            relationship_id = sheet.get(f"{_OFFICE_REL_NS}id")
            target = relationships.get(relationship_id or "")
            if target is None:
                raise ValueError("worksheet relationship is missing")
            sheet_root = ElementTree.fromstring(archive.read(target))
            cells = [
                _cell_value(cell, shared_strings) for cell in sheet_root.findall(f".//{_SHEET_NS}c")
            ]
            sheets.append({"cells": cells, "name": sheet.get("name", "")})
        external_links_ignored = any(
            name.startswith("xl/externalLinks/") for name in archive.namelist()
        )
    return {"external_links_ignored": external_links_ignored, "sheets": sheets}


def _workbook_relationships(archive: ZipFile) -> dict[str, str]:
    root = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relationships: dict[str, str] = {}
    for relation in root.findall(f"{_PACKAGE_REL_NS}Relationship"):
        target = relation.get("Target")
        if target is not None and relation.get("TargetMode") != "External":
            relationships[relation.get("Id", "")] = _normalize_workbook_target(target)
    return relationships


def _normalize_workbook_target(target: str) -> str:
    if target.startswith("/"):
        return target.removeprefix("/")
    return f"xl/{target.removeprefix('./')}"


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(text.text or "" for text in item.iter(f"{_SHEET_NS}t")) for item in root]


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> dict[str, object]:
    cell_type = cell.get("t")
    value_element = cell.find(f"{_SHEET_NS}v")
    raw_value = value_element.text if value_element is not None else None
    if cell_type == "s" and raw_value is not None:
        value: str | None = shared_strings[int(raw_value)]
    elif cell_type == "inlineStr":
        value = "".join(text.text or "" for text in cell.iter(f"{_SHEET_NS}t"))
    elif cell_type == "b" and raw_value is not None:
        value = "true" if raw_value == "1" else "false"
    else:
        value = raw_value
    formula = cell.find(f"{_SHEET_NS}f")
    result: dict[str, object] = {"coordinate": cell.get("r", ""), "value": value}
    if formula is not None and formula.text is not None:
        result["formula"] = formula.text
    return result


def _write_outputs(
    output_root: Path, records: Iterable[tuple[str, dict[str, object]]], report: dict[str, object]
) -> None:
    records_root = output_root / "records"
    records_root.mkdir(parents=True, exist_ok=True)
    for pack_id, record in records:
        _write_json(records_root / f"{pack_id}.json", record)
        (records_root / f"{pack_id}.md").write_text(_record_markdown(record), encoding="utf-8")
    _write_json(output_root / "ingestion-report.json", report)


def _write_json(path: Path, content: object) -> None:
    path.write_text(
        json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _record_markdown(record: dict[str, object]) -> str:
    provenance = record["provenance"]
    assert isinstance(provenance, dict)
    lines = [
        f"# {record['title']}",
        "",
        f"- Pack: `{record['pack_id']}`",
        f"- SHA-256: `{provenance['sha256']}`",
        f"- Source: `{provenance['filename']}`",
        "",
        "## Extracted content",
        "",
        "```json",
        json.dumps(record["content"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read registered local COC7 source files safely.")
    parser.add_argument("--catalog", type=Path, required=True, help="source catalog JSON path")
    parser.add_argument(
        "--output-root", type=Path, required=True, help="generated record directory"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="validate and report without writing files"
    )
    arguments = parser.parse_args(argv)
    report = ingest_catalog(
        arguments.catalog,
        output_root=arguments.output_root,
        dry_run=arguments.dry_run,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
