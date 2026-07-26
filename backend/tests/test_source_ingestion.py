import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from coc_kp_assistant.ingestion import default_enabled_for_pack, ingest_catalog


def test_default_enablement_allows_only_core_and_approved_p1_handbook() -> None:
    assert default_enabled_for_pack("coc7e.core.zh-v1.2.1", requested=True) is True
    assert default_enabled_for_pack("coc7e.investigator-handbook.zh-v1.21", requested=True) is True
    assert default_enabled_for_pack("coc7e.quickstart.zh-db-noart", requested=True) is False
    assert default_enabled_for_pack("coc7e.magic-compendium.zh-v1.1", requested=False) is False


def _write_docx(path: Path) -> None:
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>调查员档案</w:t></w:r></w:p>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>姓名</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>阿卡姆</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
  </w:body>
</w:document>"""
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)


def _write_catalog(path: Path, packs: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "catalog_version": 1,
                "ruleset": "coc7e",
                "import_policy": {
                    "execute_office_macros": False,
                    "xlsm_macro_handling": "never_execute",
                    "external_links": "never_follow",
                },
                "packs": packs,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_pdf(path: Path, page_texts: list[str]) -> None:
    objects = ["<< /Type /Catalog /Pages 2 0 R >>"]
    page_object_numbers = [3 + page_index * 2 for page_index in range(len(page_texts))]
    objects.append(
        "<< /Type /Pages /Kids ["
        + " ".join(f"{number} 0 R" for number in page_object_numbers)
        + f"] /Count {len(page_texts)} >>"
    )
    for page_text in page_texts:
        stream = f"BT /F1 12 Tf 72 720 Td ({page_text}) Tj ET"
        page_number = len(objects) + 1
        content_number = page_number + 1
        objects.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {2 * len(page_texts) + 3} 0 R >> >> "
            f"/Contents {content_number} 0 R >>"
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    output = "%PDF-1.4\n"
    offsets = [0]
    for number, content in enumerate(objects, start=1):
        offsets.append(len(output.encode("ascii")))
        output += f"{number} 0 obj\n{content}\nendobj\n"
    xref_offset = len(output.encode("ascii"))
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    output += "".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:])
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    )
    path.write_bytes(output.encode("ascii"))


def _write_xlsm(path: Path) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="调查员" sheetId="1" r:id="rId1"/></sheets></workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/>
<Relationship Id="rId2" Target="externalLinks/externalLink1.xml"
TargetMode="External" Type="externalLink"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            """<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>姓名</t></si></sst>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData><row r="1">
<c r="A1" t="s"><v>0</v></c><c r="B1"><v>42</v></c>
<c r="C1"><f>SUM(B1:B1)</f><v>42</v></c><c r="D1" t="inlineStr"><is><t>守秘人</t></is></c>
</row></sheetData></worksheet>""",
        )
        archive.writestr("xl/externalLinks/externalLink1.xml", "<externalLink/>")
        archive.writestr("xl/vbaProject.bin", b"VBA-NEVER-EXECUTE")


def test_full_run_writes_deterministic_docx_record_with_table_and_checksum(tmp_path: Path) -> None:
    source_path = tmp_path / "quickstart.docx"
    _write_docx(source_path)
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.quickstart.zh-db-noart",
                    "title": "快速开始",
                    "version": "test",
                    "edition": "7e",
                    "kind": "quickstart",
                    "default_enabled": True,
                },
                "source": {
                    "original_absolute_path": str(source_path),
                    "format": "docx",
                    "contains_macros": False,
                },
            }
        ],
    )
    output_root = tmp_path / "generated-content" / "coc7"

    report = ingest_catalog(catalog_path, output_root=output_root)

    record_path = output_root / "records" / "coc7e.quickstart.zh-db-noart.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert report["status"] == "ready"
    assert record["default_enabled"] is False
    assert record["provenance"]["sha256"] == hashlib.sha256(source_path.read_bytes()).hexdigest()
    assert record["content"]["paragraphs"][0]["text"] == "调查员档案"
    assert record["content"]["paragraphs"][0]["provenance"]["locator"] == "paragraph:1"
    assert record["content"]["tables"][0]["rows"] == [["姓名", "阿卡姆"]]
    assert record["content"]["tables"][0]["provenance"]["locator"] == "table:1"
    assert "调查员档案" in (output_root / "records" / "coc7e.quickstart.zh-db-noart.md").read_text(
        encoding="utf-8"
    )

    first_output = record_path.read_bytes()
    assert ingest_catalog(catalog_path, output_root=output_root)["status"] == "ready"
    assert record_path.read_bytes() == first_output


def test_full_run_extracts_pdf_text_by_page_with_page_provenance(tmp_path: Path) -> None:
    source_path = tmp_path / "core.pdf"
    _write_pdf(source_path, ["First page", "Second page"])
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.core.zh-v1.2.1",
                    "title": "核心规则",
                    "version": "test",
                    "edition": "7e",
                    "kind": "core",
                    "default_enabled": True,
                },
                "source": {
                    "original_absolute_path": str(source_path),
                    "format": "pdf",
                    "contains_macros": False,
                },
            }
        ],
    )

    report = ingest_catalog(catalog_path, output_root=tmp_path / "generated-content" / "coc7")

    assert report["status"] == "ready"
    assert report["packs"] == [
        {
            "default_enabled": True,
            "pack_id": "coc7e.core.zh-v1.2.1",
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "status": "ready",
        }
    ]
    record_path = tmp_path / "generated-content" / "coc7" / "records" / "coc7e.core.zh-v1.2.1.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert [page["text"] for page in record["content"]["pages"]] == ["First page", "Second page"]
    assert [page["provenance"]["locator"] for page in record["content"]["pages"]] == [
        "page:1",
        "page:2",
    ]


def test_full_run_reads_xlsm_cells_without_running_macros_or_external_links(tmp_path: Path) -> None:
    source_path = tmp_path / "future.xlsm"
    _write_xlsm(source_path)
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.time-travel.sheet.future-v1.5",
                    "title": "未来角色卡",
                    "version": "test",
                    "edition": "7e-supplement",
                    "kind": "era",
                    "default_enabled": False,
                },
                "source": {
                    "original_absolute_path": str(source_path),
                    "format": "xlsm",
                    "contains_macros": True,
                },
            }
        ],
    )

    report = ingest_catalog(catalog_path, output_root=tmp_path / "generated-content" / "coc7")

    assert report["status"] == "ready"
    record_path = (
        tmp_path
        / "generated-content"
        / "coc7"
        / "records"
        / "coc7e.time-travel.sheet.future-v1.5.json"
    )
    record_text = record_path.read_text(encoding="utf-8")
    record = json.loads(record_text)
    assert record["content"]["external_links_ignored"] is True
    sheet = record["content"]["sheets"][0]
    assert sheet["name"] == "调查员"
    assert sheet["provenance"]["locator"] == "sheet:调查员"
    assert [
        {key: value for key, value in cell.items() if key != "provenance"}
        for cell in sheet["cells"]
    ] == [
        {"coordinate": "A1", "value": "姓名"},
        {"coordinate": "B1", "value": "42"},
        {"coordinate": "C1", "formula": "SUM(B1:B1)", "value": "42"},
        {"coordinate": "D1", "value": "守秘人"},
    ]
    assert sheet["cells"][0]["provenance"]["locator"] == "sheet:调查员!A1"
    assert "VBA-NEVER-EXECUTE" not in record_text


def test_changed_source_is_rejected_with_machine_readable_checksum_report(tmp_path: Path) -> None:
    source_path = tmp_path / "quickstart.docx"
    _write_docx(source_path)
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.quickstart.zh-db-noart",
                    "title": "快速开始",
                    "version": "test",
                    "edition": "7e",
                    "kind": "quickstart",
                },
                "source": {
                    "original_absolute_path": str(source_path),
                    "format": "docx",
                    "sha256": "0" * 64,
                    "contains_macros": False,
                },
            }
        ],
    )

    report = ingest_catalog(catalog_path, output_root=tmp_path / "generated-content" / "coc7")

    assert report["status"] == "failed"
    assert report["packs"] == [
        {
            "actual_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "errors": [
                {"code": "changed_source", "message": "source checksum differs from baseline"}
            ],
            "expected_sha256": "0" * 64,
            "pack_id": "coc7e.quickstart.zh-db-noart",
            "status": "rejected",
        }
    ]


def test_full_run_rejects_a_source_changed_since_its_last_recorded_import(tmp_path: Path) -> None:
    source_path = tmp_path / "quickstart.docx"
    _write_docx(source_path)
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.quickstart.zh-db-noart",
                    "title": "快速开始",
                    "version": "test",
                    "edition": "7e",
                    "kind": "quickstart",
                },
                "source": {
                    "original_absolute_path": str(source_path),
                    "format": "docx",
                    "contains_macros": False,
                },
            }
        ],
    )
    output_root = tmp_path / "generated-content" / "coc7"

    assert ingest_catalog(catalog_path, output_root=output_root)["status"] == "ready"
    source_path.write_bytes(source_path.read_bytes() + b"changed")
    report = ingest_catalog(catalog_path, output_root=output_root)

    assert report["status"] == "failed"
    assert report["packs"][0]["errors"][0]["code"] == "changed_source"
    assert ingest_catalog(catalog_path, output_root=output_root)["status"] == "failed"


def test_rejected_source_removes_stale_record_and_preserves_literal_docx_provenance(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "quickstart.docx"
    _write_docx(source_path)
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.quickstart.zh-db-noart",
                    "title": "快速开始",
                    "version": "test",
                    "edition": "7e",
                    "kind": "quickstart",
                    "eras": ["gaslight"],
                },
                "source": {
                    "original_absolute_path": str(source_path),
                    "format": "docx",
                    "page_count": None,
                    "text_extraction": "ooxml",
                    "contains_macros": False,
                },
            }
        ],
    )
    output_root = tmp_path / "generated-content" / "coc7"
    record_path = output_root / "records" / "coc7e.quickstart.zh-db-noart.json"

    assert ingest_catalog(catalog_path, output_root=output_root)["status"] == "ready"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["provenance"] == {
        "edition": "7e",
        "eras": ["gaslight"],
        "filename": "quickstart.docx",
        "format": "docx",
        "locator": "source",
        "module": "quickstart",
        "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "source_pack": "coc7e.quickstart.zh-db-noart",
        "source_path": str(source_path),
    }
    assert record["content"]["paragraphs"] == [
        {
            "provenance": {
                "edition": "7e",
                "eras": ["gaslight"],
                "filename": "quickstart.docx",
                "format": "docx",
                "locator": "paragraph:1",
                "module": "quickstart",
                "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                "source_pack": "coc7e.quickstart.zh-db-noart",
            },
            "text": "调查员档案",
        }
    ]
    assert record["content"]["tables"][0]["provenance"]["locator"] == "table:1"

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["packs"][0]["source"]["sha256"] = "0" * 64
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")

    assert ingest_catalog(catalog_path, output_root=output_root)["status"] == "failed"
    assert not record_path.exists()
    assert not record_path.with_suffix(".md").exists()


def test_source_declaration_mismatches_are_rejected_before_record_output(tmp_path: Path) -> None:
    source_path = tmp_path / "quickstart.docx"
    _write_docx(source_path)
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.quickstart.zh-db-noart",
                    "title": "快速开始",
                    "version": "test",
                    "edition": "7e",
                    "kind": "quickstart",
                },
                "source": {
                    "original_absolute_path": str(source_path),
                    "format": "docx",
                    "page_count": 1,
                    "text_extraction": "direct",
                    "contains_macros": True,
                },
            }
        ],
    )

    report = ingest_catalog(catalog_path, output_root=tmp_path / "generated-content" / "coc7")

    assert report["status"] == "failed"
    assert [error["code"] for error in report["packs"][0]["errors"]] == [
        "page_count_mismatch",
        "text_extraction_mismatch",
        "macro_declaration_mismatch",
    ]


def test_checksum_read_failure_is_saved_as_an_unreadable_source_report(tmp_path: Path) -> None:
    source_path = tmp_path / "quickstart.docx"
    _write_docx(source_path)
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.quickstart.zh-db-noart",
                    "title": "快速开始",
                    "version": "test",
                    "edition": "7e",
                    "kind": "quickstart",
                },
                "source": {
                    "original_absolute_path": str(source_path),
                    "format": "docx",
                    "contains_macros": False,
                },
            }
        ],
    )
    source_path.chmod(0)
    output_root = tmp_path / "generated-content" / "coc7"
    try:
        report = ingest_catalog(catalog_path, output_root=output_root)
    finally:
        source_path.chmod(0o600)

    assert report["status"] == "failed"
    assert report["packs"][0]["errors"][0]["code"] == "unreadable_source"
    assert (
        json.loads((output_root / "ingestion-report.json").read_text(encoding="utf-8"))["status"]
        == "failed"
    )


def test_pdf_with_a_blank_page_preserves_the_blank_page_when_other_text_exists(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "core.pdf"
    _write_pdf(source_path, ["Readable page", ""])
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.core.zh-v1.2.1",
                    "title": "核心规则",
                    "version": "test",
                    "edition": "7e",
                    "kind": "core",
                },
                "source": {
                    "original_absolute_path": str(source_path),
                    "format": "pdf",
                    "page_count": 2,
                    "text_extraction": "direct",
                    "contains_macros": False,
                },
            }
        ],
    )

    report = ingest_catalog(catalog_path, output_root=tmp_path / "generated-content" / "coc7")

    assert report["status"] == "ready"
    record_path = tmp_path / "generated-content" / "coc7" / "records" / "coc7e.core.zh-v1.2.1.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["content"]["pages"][1]["text"] == ""
    assert record["content"]["pages"][1]["provenance"]["locator"] == "page:2"


def test_pdf_without_text_on_any_page_is_rejected(tmp_path: Path) -> None:
    source_path = tmp_path / "core.pdf"
    _write_pdf(source_path, ["", ""])
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.core.zh-v1.2.1",
                    "title": "核心规则",
                    "version": "test",
                    "edition": "7e",
                    "kind": "core",
                },
                "source": {
                    "original_absolute_path": str(source_path),
                    "format": "pdf",
                    "contains_macros": False,
                },
            }
        ],
    )

    report = ingest_catalog(catalog_path, output_root=tmp_path / "generated-content" / "coc7")

    assert report["status"] == "failed"
    assert report["packs"][0]["errors"][0]["code"] == "unreadable_source"


def test_malformed_catalog_is_a_saved_machine_readable_failure(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text("{invalid", encoding="utf-8")
    output_root = tmp_path / "generated-content" / "coc7"

    report = ingest_catalog(catalog_path, output_root=output_root)

    assert report == {
        "catalog_version": None,
        "dry_run": False,
        "errors": [{"code": "invalid_catalog_json", "message": "catalog JSON is unreadable"}],
        "packs": [],
        "ruleset": None,
        "status": "failed",
    }
    assert json.loads((output_root / "ingestion-report.json").read_text(encoding="utf-8")) == report


def test_non_object_catalog_top_level_is_a_machine_readable_failure(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text("[]", encoding="utf-8")

    report = ingest_catalog(catalog_path, output_root=tmp_path / "generated-content" / "coc7")

    assert report["status"] == "failed"
    assert report["errors"] == [
        {"code": "invalid_catalog", "message": "catalog top level must be an object"}
    ]


def test_removed_pack_cannot_leave_a_previous_generated_record_usable(tmp_path: Path) -> None:
    source_path = tmp_path / "quickstart.docx"
    _write_docx(source_path)
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.quickstart.zh-db-noart",
                    "title": "快速开始",
                    "version": "test",
                    "edition": "7e",
                    "kind": "quickstart",
                },
                "source": {
                    "original_absolute_path": str(source_path),
                    "format": "docx",
                    "contains_macros": False,
                },
            }
        ],
    )
    output_root = tmp_path / "generated-content" / "coc7"
    record_path = output_root / "records" / "coc7e.quickstart.zh-db-noart.json"
    assert ingest_catalog(catalog_path, output_root=output_root)["status"] == "ready"
    _write_catalog(catalog_path, [])

    assert ingest_catalog(catalog_path, output_root=output_root)["status"] == "ready"
    assert not record_path.exists()
    assert not record_path.with_suffix(".md").exists()


def test_cli_dry_run_and_full_run_report_missing_unsupported_and_unreadable_sources(
    tmp_path: Path,
) -> None:
    unreadable_path = tmp_path / "unreadable.docx"
    unreadable_path.write_text("not an OOXML archive", encoding="utf-8")
    unsupported_path = tmp_path / "unsupported.txt"
    unsupported_path.write_text("unsupported", encoding="utf-8")
    catalog_path = tmp_path / "catalog.json"
    _write_catalog(
        catalog_path,
        [
            {
                "manifest": {
                    "pack_id": "coc7e.keeper-deck.bystanders.zh",
                    "title": "缺失来源",
                    "version": "test",
                    "edition": "7e",
                    "kind": "card_deck",
                },
                "source": {
                    "original_absolute_path": str(tmp_path / "missing.pdf"),
                    "format": "pdf",
                    "contains_macros": False,
                },
            },
            {
                "manifest": {
                    "pack_id": "coc7e.keeper-deck.misfortunes.zh",
                    "title": "不支持来源",
                    "version": "test",
                    "edition": "7e",
                    "kind": "card_deck",
                },
                "source": {
                    "original_absolute_path": str(unsupported_path),
                    "format": "txt",
                    "contains_macros": False,
                },
            },
            {
                "manifest": {
                    "pack_id": "coc7e.keeper-deck.phobias.zh",
                    "title": "不可读来源",
                    "version": "test",
                    "edition": "7e",
                    "kind": "card_deck",
                },
                "source": {
                    "original_absolute_path": str(unreadable_path),
                    "format": "docx",
                    "contains_macros": False,
                },
            },
        ],
    )
    output_root = tmp_path / "generated-content" / "coc7"
    command = [
        sys.executable,
        "-m",
        "coc_kp_assistant.ingestion",
        "--catalog",
        str(catalog_path),
        "--output-root",
        str(output_root),
    ]
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}

    dry_run = subprocess.run(
        [*command, "--dry-run"], capture_output=True, text=True, check=False, env=environment
    )

    assert dry_run.returncode == 1
    assert json.loads(dry_run.stdout)["status"] == "failed"
    assert not output_root.exists()

    full_run = subprocess.run(command, capture_output=True, text=True, check=False, env=environment)

    assert full_run.returncode == 1
    assert [pack["errors"][0]["code"] for pack in json.loads(full_run.stdout)["packs"]] == [
        "missing_source",
        "unsupported_source",
        "unreadable_source",
    ]
    saved_report = json.loads((output_root / "ingestion-report.json").read_text(encoding="utf-8"))
    assert saved_report["status"] == "failed"
