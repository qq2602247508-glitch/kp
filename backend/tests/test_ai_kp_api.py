from typing import Any

from coc_kp_assistant.application.ai_kp_service import AIKPOrchestrator
from coc_kp_assistant.domain.ai_kp import (
    AIKPDraft,
    AIKPProposalDraft,
    AIKPResponseDraft,
)
from coc_kp_assistant.domain.case_state import CaseEntityKind


class FakeProvider:
    model_name = "qwen3:30b-instruct"

    def generate(self, payload: dict[str, Any]) -> AIKPDraft:
        return AIKPDraft(
            response=AIKPResponseDraft(
                answer="建议调查仓库。",
                keeper_private_hints=("地下有祭坛。",),
                scene_suggestions=("先让灯熄灭。",),
                citation_ids=("rule-1",),
            ),
            proposals=(
                AIKPProposalDraft(
                    proposal_type="case_state_create",
                    case_kind=CaseEntityKind.SCENES,
                    payload={
                        "title": "封闭仓库",
                        "player_visible_text": "铁门上有盐渍。",
                        "keeper_truth": "地下有祭坛。",
                        "status": "planned",
                    },
                    citation_ids=("rule-1",),
                ),
            ),
        )


def _campaign(client: Any) -> dict[str, Any]:
    response = client.post(
        "/api/v1/campaigns",
        json={
            "title": "雾港失踪案",
            "ruleset": "coc7e",
            "era": "1920s",
            "enabled_source_pack_ids": [],
            "house_rules": [],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_ai_kp_endpoints_fail_503_when_local_model_is_unavailable(client: Any) -> None:
    campaign = _campaign(client)
    response = client.post(
        f"/api/v1/campaigns/{campaign['campaign_id']}/ai-kp/ask",
        json={"question": "下一幕如何推进？", "mode": "private_hint"},
    )
    assert response.status_code == 503


def test_proposal_list_is_a_real_empty_collection(client: Any) -> None:
    campaign = _campaign(client)
    response = client.get(
        f"/api/v1/campaigns/{campaign['campaign_id']}/ai-kp/proposals"
    )
    assert response.status_code == 200
    assert response.json() == []


def test_ai_proposal_api_requires_explicit_confirmation_before_case_write(
    client: Any,
) -> None:
    campaign = _campaign(client)
    campaign_id = campaign["campaign_id"]
    client.app.state.ai_kp_orchestrator = AIKPOrchestrator(
        provider=FakeProvider(),
        rules_reader=lambda _: [
            {
                "citation_id": "rule-1",
                "excerpt": "场景检定证据",
                "filename": "core.pdf",
                "page": 88,
                "section": "技能检定",
            }
        ],
    )

    asked = client.post(
        f"/api/v1/campaigns/{campaign_id}/ai-kp/ask",
        json={"question": "下一幕如何推进？", "mode": "scenario_draft"},
    )
    assert asked.status_code == 200, asked.text
    proposal = asked.json()["proposals"][0]
    assert proposal["status"] == "pending"
    before = client.get(
        f"/api/v1/campaigns/{campaign_id}/case-state/scenes"
    )
    assert before.json() == []

    confirmed = client.post(
        f"/api/v1/campaigns/{campaign_id}/ai-kp/proposals/"
        f"{proposal['proposal_id']}/decision",
        json={"expected_version": 1, "decision": "confirm"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    after = client.get(
        f"/api/v1/campaigns/{campaign_id}/case-state/scenes"
    )
    assert [item["title"] for item in after.json()] == ["封闭仓库"]
