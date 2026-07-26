from sqlalchemy import inspect

from coc_kp_assistant.application.rule_engine_service import _citation_items


def campaign_payload() -> dict[str, object]:
    return {
        "title": "黑潮观测记录",
        "ruleset": "coc7e",
        "era": "1920s",
        "enabled_source_pack_ids": [],
        "house_rules": [],
    }


def investigator_payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "occupation": "记者",
        "age": 31,
        "era": "1920s",
        "characteristics": {
            "strength": 50,
            "constitution": 60,
            "size": 50,
            "dexterity": 65,
            "appearance": 50,
            "intelligence": 70,
            "power": 60,
            "education": 70,
        },
        "luck": 50,
        "move_rate": 8,
        "damage_bonus": "0",
        "build": 0,
        "skills": [
            {
                "skill_key": "fighting_brawl",
                "display_name": "格斗（斗殴）",
                "base_value": 25,
                "current_value": 55,
                "improvement_mark": False,
            }
        ],
    }


def setup_pair(client: object) -> tuple[str, dict[str, object], dict[str, object]]:
    campaign_response = client.post("/api/v1/campaigns", json=campaign_payload())  # type: ignore[attr-defined]
    assert campaign_response.status_code == 201
    campaign_id = campaign_response.json()["campaign_id"]
    first_response = client.post(  # type: ignore[attr-defined]
        f"/api/v1/campaigns/{campaign_id}/investigators",
        json=investigator_payload("林雾"),
    )
    second_response = client.post(  # type: ignore[attr-defined]
        f"/api/v1/campaigns/{campaign_id}/investigators",
        json=investigator_payload("周启"),
    )
    assert first_response.status_code == second_response.status_code == 201
    return campaign_id, first_response.json(), second_response.json()


def assert_cited(response: dict[str, object]) -> None:
    citations = response["citations"]
    assert isinstance(citations, list) and citations
    for citation in citations:
        assert citation["source_pack_id"] == "coc7e.core.zh-v1.2.1"
        assert citation["page"] is not None
        assert citation["section"]
        assert citation["edition"] == "7e"
        assert citation["module"] == "core"
        assert citation["era"] == []
        assert citation["checksum"] == (
            "22f5f56b7a0989cbded695d39c7d5eddddd809cfc9d2c47e4cf4c5d7edea6815"
        )
    # Compatibility primary citation always mirrors the first fully-provenanced item.
    assert response["citation"] == citations[0]


def test_legacy_single_citation_data_is_read_as_a_one_item_list() -> None:
    legacy = {
        "citation_id": "coc7e.core.sanity-loss-and-insanity",
        "source_pack_id": "coc7e.core.zh-v1.2.1",
        "filename": "COC7th核心规则书v1.2.1.pdf",
        "page": 367,
        "section": "第十六章附录／理智规则摘要",
    }
    assert [item.citation_id for item in _citation_items(legacy)] == [
        "0d626519-a343-5a71-998c-9b0b56f76232"
    ]


def create_case_session(client: object, campaign_id: str) -> str:
    response = client.post(  # type: ignore[attr-defined]
        f"/api/v1/campaigns/{campaign_id}/case-state/sessions",
        json={"title": "第一夜", "player_visible_text": "", "keeper_truth": "测试"},
    )
    assert response.status_code == 201
    return response.json()["entity_id"]


def test_sanity_loss_is_deterministic_versioned_cited_and_logged(client) -> None:
    campaign_id, investigator, _ = setup_pair(client)
    investigator_id = investigator["investigator_id"]
    case_session_id = create_case_session(client, campaign_id)
    intelligence_roll = client.post(
        "/api/v1/rolls",
        json={
            "campaign_id": campaign_id,
            "case_session_id": case_session_id,
            "investigator_id": investigator_id,
            "skill_key": "intelligence",
            "label": "INT",
            "target": 70,
            "dice": {"units_digit": 1, "tens_digits": [2]},
        },
    )
    assert intelligence_roll.status_code == 201

    first = client.post(
        f"/api/v1/campaigns/{campaign_id}/investigators/{investigator_id}/sanity-loss",
        json={
            "expected_version": investigator["version"],
            "loss": 5,
            "reason": "目睹深海遗骸",
            "case_session_id": case_session_id,
            "intelligence_roll_id": intelligence_roll.json()["roll_id"],
        },
    )
    assert first.status_code == 200, first.text
    first_result = first.json()
    assert first_result["investigator"]["sanity"] == 55
    assert "temporary_insanity" in first_result["investigator"]["conditions"]
    assert first_result["session_sanity_loss"] == 5
    assert_cited(first_result)

    stale = client.post(
        f"/api/v1/campaigns/{campaign_id}/investigators/{investigator_id}/sanity-loss",
        json={
            "expected_version": investigator["version"],
            "loss": 1,
            "reason": "过期写入",
            "case_session_id": case_session_id,
        },
    )
    assert stale.status_code == 409

    second = client.post(
        f"/api/v1/campaigns/{campaign_id}/investigators/{investigator_id}/sanity-loss",
        json={
            "expected_version": first_result["investigator"]["version"],
            "loss": 7,
            "reason": "听见不可名状的低语",
            "case_session_id": case_session_id,
            "intelligence_roll_id": intelligence_roll.json()["roll_id"],
        },
    )
    assert second.status_code == 200, second.text
    second_result = second.json()
    assert second_result["session_sanity_loss"] == 12
    assert "indefinite_insanity" in second_result["investigator"]["conditions"]

    logs = client.get(f"/api/v1/campaigns/{campaign_id}/rule-operations")
    assert logs.status_code == 200
    sanity_logs = [entry for entry in logs.json() if entry["operation_type"] == "sanity_loss"]
    assert len(sanity_logs) == 2
    assert sanity_logs[-1]["citations"] == second_result["citations"]


def test_injury_recovery_and_combat_use_native_weapon_policy(client) -> None:
    campaign_id, attacker, target = setup_pair(client)
    target_id = target["investigator_id"]
    case_session_id = create_case_session(client, campaign_id)

    weapons = client.get("/api/v1/rule-engines/weapons")
    assert weapons.status_code == 200
    assert {item["weapon_key"] for item in weapons.json()} >= {"unarmed", "handgun_38"}
    assert all(
        item["citations"] and item["citation"] == item["citations"][0]
        for item in weapons.json()
    )

    injury = client.post(
        f"/api/v1/campaigns/{campaign_id}/investigators/{target_id}/injury",
        json={
            "expected_version": target["version"],
            "damage": 6,
            "reason": "坠落",
            "case_session_id": case_session_id,
        },
    )
    assert injury.status_code == 200, injury.text
    injury_result = injury.json()
    assert injury_result["investigator"]["hit_points"] == 5
    assert "major_wound" in injury_result["investigator"]["conditions"]
    assert_cited(injury_result)

    recovery = client.post(
        f"/api/v1/campaigns/{campaign_id}/investigators/{target_id}/recovery",
        json={
            "expected_version": injury_result["investigator"]["version"],
            "care_type": "first_aid",
            "injury_id": injury_result["injury_id"],
            "case_session_id": case_session_id,
        },
    )
    assert recovery.status_code == 200, recovery.text
    recovery_result = recovery.json()
    assert recovery_result["healed"] == 1
    assert recovery_result["investigator"]["hit_points"] == 6
    assert_cited(recovery_result)

    repeated_first_aid = client.post(
        f"/api/v1/campaigns/{campaign_id}/investigators/{target_id}/recovery",
        json={
            "expected_version": recovery_result["investigator"]["version"],
            "care_type": "first_aid",
            "injury_id": injury_result["injury_id"],
            "case_session_id": case_session_id,
        },
    )
    assert repeated_first_aid.status_code == 422

    roll = client.post(
        "/api/v1/rolls",
        json={
            "campaign_id": campaign_id,
            "case_session_id": case_session_id,
            "investigator_id": attacker["investigator_id"],
            "skill_key": "fighting_brawl",
            "label": "斗殴攻击",
            "target": 55,
            "difficulty": "regular",
            "bonus_penalty": 0,
            "dice": {"units_digit": 2, "tens_digits": [3]},
        },
    )
    assert roll.status_code == 201, roll.text

    combat = client.post(
        f"/api/v1/campaigns/{campaign_id}/combat/resolve",
        json={
            "attacker_id": attacker["investigator_id"],
            "target_id": target_id,
            "target_expected_version": recovery_result["investigator"]["version"],
            "attack_roll_id": roll.json()["roll_id"],
            "weapon_key": "unarmed",
            "rolled_damage": 3,
            "case_session_id": case_session_id,
        },
    )
    assert combat.status_code == 200, combat.text
    combat_result = combat.json()
    assert combat_result["hit"] is True
    assert combat_result["damage_applied"] == 3
    assert [item["citation_id"] for item in combat_result["citations"]] == [
        "69bcc3eb-67af-5d76-8e42-005fbbfc8358",
        "2ce1026d-07ef-5146-a22a-58cf4f9f9c17",
    ]
    assert combat_result["target"]["hit_points"] == 3
    assert_cited(combat_result)


def test_rule_engines_reject_forged_rolls_replays_and_zero_injuries(client) -> None:
    campaign_id, attacker, target = setup_pair(client)
    case_session_id = create_case_session(client, campaign_id)
    target_id = target["investigator_id"]

    zero = client.post(
        f"/api/v1/campaigns/{campaign_id}/investigators/{target_id}/injury",
        json={
            "expected_version": target["version"],
            "damage": 0,
            "reason": "伪造",
            "case_session_id": case_session_id,
        },
    )
    assert zero.status_code == 422

    forged_target = client.post(
        "/api/v1/rolls",
        json={
            "campaign_id": campaign_id,
            "case_session_id": case_session_id,
            "investigator_id": attacker["investigator_id"],
            "skill_key": "fighting_brawl",
            "label": "伪造 100",
            "target": 100,
            "dice": {"units_digit": 1, "tens_digits": [1]},
        },
    )
    assert forged_target.status_code == 201
    forged_combat = {
        "attacker_id": attacker["investigator_id"],
        "target_id": target_id,
        "target_expected_version": target["version"],
        "attack_roll_id": forged_target.json()["roll_id"],
        "weapon_key": "unarmed",
        "rolled_damage": 1,
        "case_session_id": case_session_id,
    }
    combat_url = f"/api/v1/campaigns/{campaign_id}/combat/resolve"
    assert client.post(combat_url, json=forged_combat).status_code == 422

    valid_roll = client.post(
        "/api/v1/rolls",
        json={
            "campaign_id": campaign_id,
            "case_session_id": case_session_id,
            "investigator_id": attacker["investigator_id"],
            "skill_key": "fighting_brawl",
            "label": "斗殴",
            "target": 55,
            "dice": {"units_digit": 1, "tens_digits": [1]},
        },
    )
    valid_combat = {**forged_combat, "attack_roll_id": valid_roll.json()["roll_id"]}
    assert client.post(combat_url, json=valid_combat).status_code == 200
    assert client.post(combat_url, json=valid_combat).status_code == 422


def test_chase_uses_stored_mov_actions_roll_binding_and_completion(client) -> None:
    campaign_id, first, second = setup_pair(client)
    case_session = client.post(
        f"/api/v1/campaigns/{campaign_id}/case-state/sessions",
        json={
            "title": "第二夜",
            "player_visible_text": "",
            "keeper_truth": "码头伏击",
        },
    )
    assert case_session.status_code == 201
    created = client.post(
        f"/api/v1/campaigns/{campaign_id}/chases",
        json={
            "title": "雨夜码头追逐",
            "session_key": "night-2",
            "case_session_id": case_session.json()["entity_id"],
            "participants": [
                {
                    "investigator_id": first["investigator_id"],
                    "role": "pursuer",
                    "position": 0,
                },
                {
                    "investigator_id": second["investigator_id"],
                    "role": "fleeing",
                    "position": 1,
                },
            ],
            "escape_distance": 2,
            "track_length": 5,
        },
    )
    assert created.status_code == 201, created.text
    chase = created.json()
    assert chase["version"] == 1
    assert chase["case_session_id"] == case_session.json()["entity_id"]
    assert chase["round"] == 1
    assert all(
        entry["move_rate"] == 8 and entry["actions_remaining"] == 1
        for entry in chase["participants"]
    )
    assert_cited(chase)

    advanced = client.post(
        f"/api/v1/campaigns/{campaign_id}/chases/{chase['chase_id']}/advance",
        json={
            "expected_version": chase["version"],
            "action": {"investigator_id": first["investigator_id"], "action": "move"},
        },
    )
    assert advanced.status_code == 200, advanced.text
    result = advanced.json()
    assert result["version"] == 2
    assert result["round"] == 1
    positions = {entry["investigator_id"]: entry["position"] for entry in result["participants"]}
    assert positions[first["investigator_id"]] == 1
    assert positions[second["investigator_id"]] == 1
    assert result["status"] == "caught"
    assert_cited(result)

    stale = client.post(
        f"/api/v1/campaigns/{campaign_id}/chases/{chase['chase_id']}/advance",
        json={
            "expected_version": 1,
            "action": {"investigator_id": first["investigator_id"], "action": "move"},
        },
    )
    assert stale.status_code == 409

    completed = client.post(
        f"/api/v1/campaigns/{campaign_id}/chases/{chase['chase_id']}/advance",
        json={
            "expected_version": result["version"],
            "action": {"investigator_id": second["investigator_id"], "action": "move"},
        },
    )
    assert completed.status_code == 422
    assert (
        client.post(
            f"/api/v1/campaigns/{campaign_id}/chases/{chase['chase_id']}/advance",
            json={
                "expected_version": result["version"],
                "action": {"investigator_id": second["investigator_id"], "action": "move"},
            },
        ).status_code
        == 422
    )

    tables = set(inspect(client.app.state.engine).get_table_names())
    assert {"rule_operation_logs", "chases"} <= tables


def test_chase_hazard_roll_is_bound_and_escape_completes(client) -> None:
    campaign_id, first, second = setup_pair(client)
    case_session_id = create_case_session(client, campaign_id)
    created = client.post(
        f"/api/v1/campaigns/{campaign_id}/chases",
        json={
            "title": "巷战",
            "case_session_id": case_session_id,
            "escape_distance": 1,
            "participants": [
                {"investigator_id": first["investigator_id"], "role": "pursuer", "position": 0},
                {"investigator_id": second["investigator_id"], "role": "fleeing", "position": 0},
            ],
        },
    )
    assert created.status_code == 201
    chase = created.json()
    chase_url = f"/api/v1/campaigns/{campaign_id}/chases/{chase['chase_id']}/advance"
    forged = client.post(
        chase_url,
        json={
            "expected_version": 1,
            "action": {
                "investigator_id": second["investigator_id"],
                "action": "hazard",
                "roll_id": "00000000-0000-0000-0000-000000000000",
                "skill_key": "fighting_brawl",
            },
        },
    )
    assert forged.status_code == 422
    roll = client.post(
        "/api/v1/rolls",
        json={
            "campaign_id": campaign_id,
            "case_session_id": case_session_id,
            "investigator_id": second["investigator_id"],
            "skill_key": "fighting_brawl",
            "label": "斗殴",
            "target": 55,
            "dice": {"units_digit": 1, "tens_digits": [1]},
        },
    )
    assert roll.status_code == 201
    escaped = client.post(
        chase_url,
        json={
            "expected_version": 1,
            "action": {
                "investigator_id": second["investigator_id"],
                "action": "hazard",
                "roll_id": roll.json()["roll_id"],
                "skill_key": "fighting_brawl",
            },
        },
    )
    assert escaped.status_code == 200, escaped.text
    assert escaped.json()["status"] == "escaped"
    assert [item["citation_id"] for item in escaped.json()["citations"]] == [
        "b5ac21aa-0b22-50a2-848d-ba61e674c993",
        "eeb778d6-5e69-5af7-9f38-511c5f4827a7",
        "2b7817b9-a2da-5ba9-8315-c10421bca87d",
        "28bb7282-3718-5ddc-b91a-3e5eca7bca05",
    ]
    logs = client.get(f"/api/v1/campaigns/{campaign_id}/rule-operations").json()
    hazard_log = next(item for item in logs if item["operation_type"] == "chase_advanced")
    assert hazard_log["citations"] == escaped.json()["citations"]
