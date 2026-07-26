from copy import deepcopy

from fastapi.testclient import TestClient


def campaign_payload() -> dict[str, object]:
    return {
        "title": "雾港疑案",
        "era": "1920s",
        "starting_location": "雾港",
        "enabled_source_pack_ids": ["coc7e.core.zh-v1.2.1"],
        "house_rules": [],
    }


def investigator_payload() -> dict[str, object]:
    return {
        "name": "林雾",
        "player_name": "测试玩家",
        "occupation": "记者",
        "age": 29,
        "era": "1920s",
        "characteristics": {
            "strength": 50,
            "constitution": 60,
            "size": 50,
            "dexterity": 70,
            "appearance": 55,
            "intelligence": 75,
            "power": 65,
            "education": 80,
        },
        "luck": 55,
        "move_rate": 8,
        "damage_bonus": "0",
        "build": 0,
        "credit_rating": 35,
        "skills": [
            {
                "skill_key": "library_use",
                "display_name": "图书馆使用",
                "base_value": 20,
                "current_value": 65,
            }
        ],
        "backstory": {
            "ideology_and_beliefs": ["真相值得付出代价"],
            "significant_people": ["导师周先生"],
        },
    }


def create_campaign(client: TestClient) -> dict[str, object]:
    response = client.post("/api/v1/campaigns", json=campaign_payload())
    assert response.status_code == 201
    return response.json()


def create_investigator(client: TestClient, campaign_id: str) -> dict[str, object]:
    response = client.post(
        f"/api/v1/campaigns/{campaign_id}/investigators",
        json=investigator_payload(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_campaign_crud_and_stale_write_protection(client: TestClient) -> None:
    created = create_campaign(client)
    campaign_id = created["campaign_id"]

    listed = client.get("/api/v1/campaigns")
    assert listed.status_code == 200
    assert [item["campaign_id"] for item in listed.json()] == [campaign_id]

    replacement = campaign_payload()
    replacement["title"] = "雾港疑案：第二夜"
    replacement["expected_version"] = 1
    updated = client.put(f"/api/v1/campaigns/{campaign_id}", json=replacement)
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    stale = client.put(f"/api/v1/campaigns/{campaign_id}", json=replacement)
    assert stale.status_code == 409
    assert client.get(f"/api/v1/campaigns/{campaign_id}").json()["title"] == "雾港疑案：第二夜"

    conflict_delete = client.delete(
        f"/api/v1/campaigns/{campaign_id}", params={"expected_version": 1}
    )
    assert conflict_delete.status_code == 409
    deleted = client.delete(
        f"/api/v1/campaigns/{campaign_id}", params={"expected_version": 2}
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/campaigns/{campaign_id}").status_code == 404


def test_investigator_crud_skills_backstory_and_audit(client: TestClient) -> None:
    campaign = create_campaign(client)
    campaign_id = str(campaign["campaign_id"])
    created = create_investigator(client, campaign_id)
    investigator_id = str(created["investigator_id"])

    assert created["hit_points"] == 11
    assert created["magic_points"] == 13
    assert created["sanity"] == 65
    assert created["skills"][0]["current_value"] == 65

    skills = client.put(
        f"/api/v1/campaigns/{campaign_id}/investigators/{investigator_id}/skills",
        json={
            "expected_version": 1,
            "skills": [
                {
                    "skill_key": "spot_hidden",
                    "display_name": "侦查",
                    "base_value": 25,
                    "current_value": 70,
                }
            ],
        },
    )
    assert skills.status_code == 200, skills.text
    assert skills.json()["version"] == 2
    assert skills.json()["skills"][0]["skill_key"] == "spot_hidden"

    backstory = client.put(
        f"/api/v1/campaigns/{campaign_id}/investigators/{investigator_id}/backstory",
        json={
            "expected_version": 2,
            "backstory": {
                "phobias_and_manias": ["深海恐惧"],
                "strange_encounters": ["在码头听见不属于人的歌声"],
            },
        },
    )
    assert backstory.status_code == 200, backstory.text
    assert backstory.json()["version"] == 3
    assert backstory.json()["backstory"]["phobias_and_manias"] == ["深海恐惧"]

    replacement = deepcopy(investigator_payload())
    replacement.update(
        {
            "expected_version": 3,
            "hit_points": 8,
            "magic_points": 10,
            "sanity": 60,
            "mythos": 2,
            "conditions": ["major_wound"],
        }
    )
    updated = client.put(
        f"/api/v1/campaigns/{campaign_id}/investigators/{investigator_id}",
        json=replacement,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 4
    assert updated.json()["hit_points"] == 8

    stale = client.put(
        f"/api/v1/campaigns/{campaign_id}/investigators/{investigator_id}",
        json=replacement,
    )
    assert stale.status_code == 409

    audits = client.get(f"/api/v1/campaigns/{campaign_id}/audits")
    assert audits.status_code == 200
    assert [item["action"] for item in audits.json()] == [
        "create",
        "create",
        "replace_skills",
        "replace_backstory",
        "replace",
    ]


def test_recorded_roll_supports_replayable_dice_and_audit(client: TestClient) -> None:
    campaign = create_campaign(client)
    campaign_id = str(campaign["campaign_id"])
    investigator = create_investigator(client, campaign_id)

    response = client.post(
        "/api/v1/rolls",
        json={
            "campaign_id": campaign_id,
            "investigator_id": investigator["investigator_id"],
            "skill_key": "library_use",
            "label": "检索港务记录",
            "target": 65,
            "difficulty": "hard",
            "bonus_penalty": -1,
            "dice": {"units_digit": 7, "tens_digits": [6, 1]},
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["roll"] == 17
    assert body["selected_tens"] == 1
    assert body["outcome"] == "hard"
    assert body["passed"] is True

    audits = client.get(f"/api/v1/campaigns/{campaign_id}/audits").json()
    assert audits[-1]["action"] == "roll_recorded"
    assert audits[-1]["after"]["roll"] == 17


def test_investigator_is_campaign_scoped(client: TestClient) -> None:
    first = create_campaign(client)
    second_payload = campaign_payload()
    second_payload["title"] = "另一案件"
    second = client.post("/api/v1/campaigns", json=second_payload).json()
    investigator = create_investigator(client, str(first["campaign_id"]))

    response = client.get(
        f"/api/v1/campaigns/{second['campaign_id']}/investigators/"
        f"{investigator['investigator_id']}"
    )

    assert response.status_code == 404
