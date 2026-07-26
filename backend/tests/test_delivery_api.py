from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from coc_kp_assistant.app import create_app
from coc_kp_assistant.config import Settings
from coc_kp_assistant.infrastructure.models import Base


@contextmanager
def _client(tmp_path: Path) -> Iterator[TestClient]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'state.db'}",
        source_catalog_path=tmp_path / "catalog.json",
        generated_content_root=tmp_path / "generated",
        vector_root=tmp_path / "vectors",
        backup_root=tmp_path / "backups",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        yield client
    app.state.engine.dispose()


def _campaign(client: TestClient, title: str = "雾港档案") -> dict[str, object]:
    response = client.post(
        "/api/v1/campaigns",
        json={
            "title": title,
            "ruleset": "coc7e",
            "era": "1920s",
            "enabled_source_pack_ids": [],
            "house_rules": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_delivery_readiness_is_explicit_and_never_downloads(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/delivery/readiness")
        assert response.status_code == 200
        body = response.json()
        assert body["product"] == "local-coc-kp-assistant"
        assert body["ruleset"] == "coc7e"
        assert body["database"]["status"] == "ready"
        assert body["sources"]["status"] == "missing"
        assert body["vector_index"]["status"] == "missing"
        assert body["models"]["embedding"]["name"] == "bge-m3:latest"
        assert body["models"]["completion"]["name"] == "qwen3:30b-instruct"
        assert body["models"]["embedding"]["download_attempted"] is False
        assert body["models"]["completion"]["download_attempted"] is False


def test_campaign_pack_toggle_validates_existence_compatibility_and_version(
    tmp_path: Path,
) -> None:
    catalog = {
        "catalog_version": 1,
        "ruleset": "coc7e",
        "import_policy": {
            "execute_office_macros": False,
            "xlsm_macro_handling": "never_execute",
            "external_links": "never_follow",
        },
        "packs": [
            {
                "manifest": {
                    "pack_id": "coc7e.core.test",
                    "title": "核心规则",
                    "version": "1",
                    "edition": "7e",
                    "kind": "core",
                    "default_enabled": True,
                    "eras": [],
                },
                "source": {},
            },
            {
                "manifest": {
                    "pack_id": "coc7e.future.test",
                    "title": "未来扩展",
                    "version": "1",
                    "edition": "7e",
                    "kind": "era",
                    "default_enabled": False,
                    "eras": ["future"],
                },
                "source": {},
            },
        ],
    }
    (tmp_path / "catalog.json").write_text(__import__("json").dumps(catalog), encoding="utf-8")
    with _client(tmp_path) as client:
        campaign = _campaign(client)
        campaign_id = campaign["campaign_id"]
        listed = client.get(f"/api/v1/campaigns/{campaign_id}/source-packs")
        assert listed.status_code == 200
        assert listed.json()["enabled_source_pack_ids"] == ["coc7e.core.test"]

        incompatible = client.put(
            f"/api/v1/campaigns/{campaign_id}/source-packs",
            json={
                "expected_version": 1,
                "enabled_source_pack_ids": ["coc7e.future.test"],
            },
        )
        assert incompatible.status_code == 422

        unknown = client.put(
            f"/api/v1/campaigns/{campaign_id}/source-packs",
            json={"expected_version": 1, "enabled_source_pack_ids": ["dnd.core"]},
        )
        assert unknown.status_code == 422


def test_export_import_is_namespaced_atomic_and_non_overwriting(tmp_path: Path) -> None:
    with _client(tmp_path / "source") as source, _client(tmp_path / "target") as target:
        campaign = _campaign(source)
        campaign_id = str(campaign["campaign_id"])
        scene = source.post(
            f"/api/v1/campaigns/{campaign_id}/case-state/scenes",
            json={
                "title": "旧仓库",
                "player_visible_text": "门上有海盐。",
                "keeper_truth": "地下室藏有祭坛。",
                "status": "planned",
            },
        )
        assert scene.status_code == 201

        exported = source.get(f"/api/v1/campaigns/{campaign_id}/export")
        assert exported.status_code == 200
        bundle = exported.json()
        assert bundle["product"] == "local-coc-kp-assistant"
        assert bundle["ruleset"] == "coc7e"
        assert bundle["schema_version"] == 1
        assert bundle["tables"]["case_scenes"][0]["keeper_truth"] == "地下室藏有祭坛。"

        imported = target.post("/api/v1/imports/campaign", json=bundle)
        assert imported.status_code == 201, imported.text
        assert imported.json()["campaign_id"] == campaign_id
        scenes = target.get(f"/api/v1/campaigns/{campaign_id}/case-state/scenes")
        assert scenes.json()[0]["title"] == "旧仓库"

        conflict = target.post("/api/v1/imports/campaign", json=bundle)
        assert conflict.status_code == 409

        wrong = dict(bundle)
        wrong["product"] = "local-dnd-dm-assistant"
        rejected = target.post("/api/v1/imports/campaign", json=wrong)
        assert rejected.status_code == 422
        assert len(target.get("/api/v1/campaigns").json()) == 1

        broken = __import__("copy").deepcopy(bundle)
        broken["tables"]["case_scenes"][0]["campaign_id"] = str(uuid4())
        with _client(tmp_path / "invalid") as invalid_reference:
            rejected_reference = invalid_reference.post(
                "/api/v1/imports/campaign", json=broken
            )
            assert rejected_reference.status_code == 422
            assert invalid_reference.get("/api/v1/campaigns").json() == []


def test_consistent_backup_has_checksums_and_verify_only_restore(tmp_path: Path) -> None:
    (tmp_path / "vectors").mkdir()
    (tmp_path / "vectors" / "manifest.json").write_text(
        '{"product":"local-coc-kp-assistant","ruleset":"coc7e"}',
        encoding="utf-8",
    )
    with _client(tmp_path) as client:
        _campaign(client)
        created = client.post("/api/v1/delivery/backups", json={})
        assert created.status_code == 201, created.text
        backup = created.json()
        manifest = Path(backup["path"]) / "manifest.json"
        assert manifest.is_file()
        verified = client.post(
            "/api/v1/delivery/backups/verify", json={"path": backup["path"]}
        )
        assert verified.status_code == 200
        assert verified.json()["valid"] is True
        assert verified.json()["restore_performed"] is False

        unsafe_destination = tmp_path / "vectors" / "nested"
        unsafe_destination.mkdir()
        refused = client.post(
            "/api/v1/delivery/backups",
            json={"destination": str(unsafe_destination)},
        )
        assert refused.status_code == 422
