from sqlalchemy import inspect


def campaign_payload(title: str = "雾港失踪案") -> dict[str, object]:
    return {
        "title": title,
        "ruleset": "coc7e",
        "era": "1920s",
        "enabled_source_pack_ids": [],
        "house_rules": [],
    }


def create_campaign(client: object, title: str = "雾港失踪案") -> dict[str, object]:
    response = client.post("/api/v1/campaigns", json=campaign_payload(title))  # type: ignore[attr-defined]
    assert response.status_code == 201
    return response.json()


def create_entry(
    client: object,
    campaign_id: str,
    kind: str,
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": f"测试{kind}",
        "player_visible_text": "调查员已经知道的事实",
        "keeper_truth": "只有 KP 能看到的真相",
    }
    payload.update(overrides)
    response = client.post(  # type: ignore[attr-defined]
        f"/api/v1/campaigns/{campaign_id}/case-state/{kind}",
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_case_schema_is_normalized_and_separates_public_from_private(client) -> None:
    expected_tables = {
        "case_sessions",
        "case_people",
        "case_locations",
        "case_scenes",
        "case_clues",
        "case_relationships",
        "case_handouts",
        "case_timeline_events",
    }
    table_names = set(inspect(client.app.state.engine).get_table_names())

    assert expected_tables <= table_names
    for table_name in expected_tables:
        columns = {
            column["name"]
            for column in inspect(client.app.state.engine).get_columns(table_name)
        }
        assert {"player_visible_text", "keeper_truth", "version"} <= columns


def test_full_case_state_workflow_and_player_safe_projection(client) -> None:
    campaign = create_campaign(client)
    campaign_id = str(campaign["campaign_id"])
    session = create_entry(
        client,
        campaign_id,
        "sessions",
        title="第一幕：雨夜抵达",
        time_label="1927-10-14 20:00",
        status="planned",
    )
    person = create_entry(client, campaign_id, "people", title="艾达·马什", role="证人")
    location = create_entry(client, campaign_id, "locations", title="旧港档案馆")
    scene = create_entry(
        client,
        campaign_id,
        "scenes",
        title="封闭阅览室",
        session_id=session["entity_id"],
        location_id=location["entity_id"],
        status="active",
    )
    first_clue = create_entry(
        client,
        campaign_id,
        "clues",
        title="潮湿航海日志",
        scene_id=scene["entity_id"],
        person_id=person["entity_id"],
        location_id=location["entity_id"],
        discovered=True,
    )
    second_clue = create_entry(
        client,
        campaign_id,
        "clues",
        title="被撕去的末页",
        scene_id=scene["entity_id"],
    )
    relationship = create_entry(
        client,
        campaign_id,
        "relationships",
        title="日志指向末页",
        source_clue_id=first_clue["entity_id"],
        target_clue_id=second_clue["entity_id"],
        relationship_type="supports",
    )
    handout = create_entry(
        client,
        campaign_id,
        "handouts",
        title="日志复印件",
        clue_id=first_clue["entity_id"],
        revealed=True,
    )
    timeline = create_entry(
        client,
        campaign_id,
        "timeline-events",
        title="档案馆停电",
        session_id=session["entity_id"],
        scene_id=scene["entity_id"],
        time_label="20:43",
        sort_order=10,
    )

    for kind, entry in (
        ("sessions", session),
        ("people", person),
        ("locations", location),
        ("scenes", scene),
        ("clues", first_clue),
        ("relationships", relationship),
        ("handouts", handout),
        ("timeline-events", timeline),
    ):
        listed = client.get(f"/api/v1/campaigns/{campaign_id}/case-state/{kind}")
        assert listed.status_code == 200
        assert entry["entity_id"] in {item["entity_id"] for item in listed.json()}

    projection = client.get(
        f"/api/v1/campaigns/{campaign_id}/case-state/clues/{first_clue['entity_id']}/player-view"
    )
    assert projection.status_code == 200
    assert projection.json()["player_visible_text"] == "调查员已经知道的事实"
    assert "keeper_truth" not in projection.json()


def test_case_state_updates_require_current_version_and_are_audited(client) -> None:
    campaign = create_campaign(client)
    campaign_id = str(campaign["campaign_id"])
    clue = create_entry(client, campaign_id, "clues", title="银色钥匙")

    payload = {
        "title": "银色钥匙（已辨认）",
        "player_visible_text": "钥匙刻着陌生纹章",
        "keeper_truth": "纹章属于守门人",
        "discovered": True,
        "expected_version": clue["version"],
    }
    updated = client.put(
        f"/api/v1/campaigns/{campaign_id}/case-state/clues/{clue['entity_id']}",
        json=payload,
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    stale = client.put(
        f"/api/v1/campaigns/{campaign_id}/case-state/clues/{clue['entity_id']}",
        json=payload,
    )
    assert stale.status_code == 409

    audits = client.get(f"/api/v1/campaigns/{campaign_id}/audits")
    assert audits.status_code == 200
    clue_audits = [
        entry for entry in audits.json() if entry["entity_id"] == clue["entity_id"]
    ]
    assert [entry["action"] for entry in clue_audits] == ["create", "replace"]
    assert clue_audits[-1]["expected_version"] == 1
    assert clue_audits[-1]["before"]["keeper_truth"] == "只有 KP 能看到的真相"


def test_clue_relationship_rejects_cross_case_references(client) -> None:
    first_campaign = create_campaign(client, "雾港失踪案")
    second_campaign = create_campaign(client, "山庄低语")
    first_clue = create_entry(client, str(first_campaign["campaign_id"]), "clues")
    second_clue = create_entry(client, str(second_campaign["campaign_id"]), "clues")

    response = client.post(
        f"/api/v1/campaigns/{first_campaign['campaign_id']}/case-state/relationships",
        json={
            "title": "非法跨案关联",
            "player_visible_text": "",
            "keeper_truth": "",
            "source_clue_id": first_clue["entity_id"],
            "target_clue_id": second_clue["entity_id"],
            "relationship_type": "supports",
        },
    )

    assert response.status_code == 422


def test_case_state_delete_requires_current_version(client) -> None:
    campaign = create_campaign(client)
    campaign_id = str(campaign["campaign_id"])
    person = create_entry(client, campaign_id, "people", title="码头管理员")
    path = (
        f"/api/v1/campaigns/{campaign_id}/case-state/people/{person['entity_id']}"
    )

    stale = client.delete(path, params={"expected_version": 2})
    assert stale.status_code == 409
    deleted = client.delete(path, params={"expected_version": 1})
    assert deleted.status_code == 204
    assert client.get(path).status_code == 404
