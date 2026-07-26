import json
from pathlib import Path

from coc_kp_assistant.domain import SourcePackManifest

CATALOG_PATH = Path(__file__).parents[2] / "config" / "source-packs.example.json"


def test_source_catalog_manifests_match_domain_contract() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    packs = catalog["packs"]
    manifests = [SourcePackManifest.model_validate(item["manifest"]) for item in packs]

    assert catalog["ruleset"] == "coc7e"
    assert len(manifests) == 20
    assert len({manifest.pack_id for manifest in manifests}) == len(manifests)
    assert all(item["source"]["original_absolute_path"].startswith("/Volumes/") for item in packs)


def test_source_catalog_enforces_macro_and_legacy_isolation() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    assert catalog["import_policy"]["execute_office_macros"] is False
    assert catalog["import_policy"]["xlsm_macro_handling"] == "never_execute"
    for item in catalog["packs"]:
        source = item["source"]
        manifest = item["manifest"]
        if source["format"] == "xlsm":
            assert source["contains_macros"] is True
            assert source["text_extraction"] == "ooxml-without-vba"
        if manifest["edition"] == "classic-40th":
            assert manifest["kind"] == "legacy"
            assert manifest["default_enabled"] is False
            assert manifest["priority"] >= 900
