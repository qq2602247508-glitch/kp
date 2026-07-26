from fastapi.testclient import TestClient

from coc_kp_assistant.rules import (
    GroundedAnswerUnavailableError,
    RuleAnswer,
    RuleCitation,
    RuleQuery,
)


def _citation() -> RuleCitation:
    return RuleCitation(
        citation_id="chunk-1",
        chunk_id="chunk-1",
        excerpt="困难成功需要不高于技能值的一半。",
        score=0.93,
        source_pack="coc7e.core.zh-v1.2.1",
        edition="7e",
        module="core",
        era=("1920s",),
        filename="COC7核心规则书v1.2.1.pdf",
        page=88,
        section="技能检定",
        checksum="a" * 64,
    )


class StubRulesService:
    def __init__(self) -> None:
        self.search_queries: list[RuleQuery] = []
        self.answer_queries: list[RuleQuery] = []

    def search(self, query: RuleQuery) -> tuple[RuleCitation, ...]:
        self.search_queries.append(query)
        return (_citation(),)

    def answer(self, query: RuleQuery) -> RuleAnswer:
        self.answer_queries.append(query)
        return RuleAnswer(
            answer="困难成功需要不高于技能值的一半。",
            citations=(_citation(),),
            abstained=False,
            reason=None,
        )


def test_rules_search_api_returns_structured_locations_and_filters(
    client: TestClient,
) -> None:
    service = StubRulesService()
    client.app.state.rules_service = service

    response = client.get(
        "/api/v1/rules/search",
        params=[
            ("q", "困难成功"),
            ("source_pack", "coc7e.core.zh-v1.2.1"),
            ("edition", "7e"),
            ("module", "core"),
            ("era", "1920s"),
            ("limit", "5"),
        ],
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["page"] == 88
    assert response.json()["results"][0]["section"] == "技能检定"
    assert service.search_queries == [
        RuleQuery(
            query="困难成功",
            source_pack_ids=("coc7e.core.zh-v1.2.1",),
            editions=("7e",),
            modules=("core",),
            eras=("1920s",),
            limit=5,
        )
    ]


def test_rules_answer_api_returns_validated_citations(client: TestClient) -> None:
    service = StubRulesService()
    client.app.state.rules_service = service

    response = client.post(
        "/api/v1/rules/answer",
        json={
            "question": "困难成功如何判定？",
            "source_pack_ids": [],
            "editions": ["7e"],
            "modules": [],
            "eras": [],
            "limit": 8,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["abstained"] is False
    assert body["citations"][0]["citation_id"] == "chunk-1"
    assert service.answer_queries[0].query == "困难成功如何判定？"


def test_rules_answer_api_reports_local_model_unavailable(client: TestClient) -> None:
    class UnavailableRulesService(StubRulesService):
        def answer(self, query: RuleQuery) -> RuleAnswer:
            raise GroundedAnswerUnavailableError("local model timed out")

    client.app.state.rules_service = UnavailableRulesService()

    response = client.post(
        "/api/v1/rules/answer",
        json={"question": "困难成功如何判定？"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "本地 qwen3:30b-instruct 模型不可用或响应超时"
