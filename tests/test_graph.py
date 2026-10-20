"""그래프 전체 경로 — fake LLM + InMemoryMCP로 결정론적으로 끝까지 돌린다."""
from agent.graph import build_graph

from .conftest import StubClassifier


def _initial(query):
    return {"query": query, "thread_id": "t", "history": [], "events": [], "cost_usd": 0.0}


async def test_chat_route_skips_pipeline(make_deps):
    result = await build_graph(make_deps()).ainvoke(_initial("안녕, 너는 누구야?"))
    assert result["route"] == "chat" and not result.get("tasks")


async def test_incident_pipeline_fetches_classified_runbooks(make_deps, mcp):
    deps = make_deps(incident_classifier=StubClassifier(["cpu-spike", "memory-leak"]),
                     grounding_check=True)
    result = await build_graph(deps).ainvoke(
        _initial("payments-service랑 cache-service 둘 다 저하됐는데 원인 분석해줘"))
    types = [e["type"] for e in result["events"]]
    assert types[0] == "RouteDecided" and types[-1] == "Finalize"
    runbook_uris = [c[1] for c in mcp.calls if c[0] == "read_resource"]
    assert runbook_uris == ["runbook://incident-response/cpu-spike",
                            "runbook://incident-response/memory-leak"]
    assert result["validation_attempts"] == 2      # fake 1차 초안은 의도적으로 반려된다
    assert "1)" in result["final"]
