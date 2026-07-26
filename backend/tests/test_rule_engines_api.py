from sqlalchemy import inspect


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
    citation = response["citation"]
    assert isinstance(citation, dict)
    assert citation["source_pack_id"] == "coc7e.core.zh-v1.2.1"
    assert citation["page"] is not None
    assert citation["section"]
    assert citation["citation_id"].startswith("coc7e.core.")


def test_sanity_loss_is_deterministic_versioned_cited_and_logged(client) -> None:
    campaign_id, investigator, _ = setup_pair(client)
    investigator_id = investigator["investigator_id"]

    first = client.post(
        f"/api/v1/campaigns/{campaign_id}/investigators/{investigator_id}/sanity-loss",
        json={
            "expected_version": investigator["version"],
            "loss": 5,
            "reason": "目睹深海遗骸",
            "session_key": "night-1",
            "intelligence_check_passed": True,
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
            "session_key": "night-1",
            "intelligence_check_passed": False,
        },
    )
    assert stale.status_code == 409

    second = client.post(
        f"/api/v1/campaigns/{campaign_id}/investigators/{investigator_id}/sanity-loss",
        json={
            "expected_version": first_result["investigator"]["version"],
            "loss": 7,
            "reason": "听见不可名状的低语",
            "session_key": "night-1",
            "intelligence_check_passed": True,
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
    assert sanity_logs[-1]["citation"]["citation_id"] == second_result["citation"]["citation_id"]


def test_injury_recovery_and_combat_use_native_weapon_policy(client) -> None:
    campaign_id, attacker, target = setup_pair(client)
    target_id = target["investigator_id"]

    weapons = client.get("/api/v1/rule-engines/weapons")
    assert weapons.status_code == 200
    assert {item["weapon_key"] for item in weapons.json()} >= {"unarmed", "handgun_38"}
    assert all(item["citation"]["source_pack_id"].startswith("coc7e.") for item in weapons.json())

    injury = client.post(
        f"/api/v1/campaigns/{campaign_id}/investigators/{target_id}/injury",
        json={
            "expected_version": target["version"],
            "damage": 6,
            "reason": "坠落",
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
        },
    )
    assert repeated_first_aid.status_code == 422

    roll = client.post(
        "/api/v1/rolls",
        json={
            "campaign_id": campaign_id,
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
        },
    )
    assert combat.status_code == 200, combat.text
    combat_result = combat.json()
    assert combat_result["hit"] is True
    assert combat_result["damage_applied"] == 3
    assert combat_result["target"]["hit_points"] == 3
    assert_cited(combat_result)


def test_chase_state_uses_optimistic_lock_and_logs_cited_advances(client) -> None:
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
                    "position": 2,
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    chase = created.json()
    assert chase["version"] == 1
    assert chase["case_session_id"] == case_session.json()["entity_id"]
    assert_cited(chase)

    advanced = client.post(
        f"/api/v1/campaigns/{campaign_id}/chases/{chase['chase_id']}/advance",
        json={
            "expected_version": chase["version"],
            "moves": [
                {"investigator_id": first["investigator_id"], "move_units": 1},
                {"investigator_id": second["investigator_id"], "move_units": 1},
            ],
        },
    )
    assert advanced.status_code == 200, advanced.text
    result = advanced.json()
    assert result["version"] == 2
    positions = {
        entry["investigator_id"]: entry["position"] for entry in result["participants"]
    }
    assert positions[first["investigator_id"]] == 1
    assert positions[second["investigator_id"]] == 3
    assert_cited(result)

    stale = client.post(
        f"/api/v1/campaigns/{campaign_id}/chases/{chase['chase_id']}/advance",
        json={
            "expected_version": 1,
            "moves": [
                {"investigator_id": first["investigator_id"], "move_units": 1}
            ],
        },
    )
    assert stale.status_code == 409

    tables = set(inspect(client.app.state.engine).get_table_names())
    assert {"rule_operation_logs", "chases"} <= tables
