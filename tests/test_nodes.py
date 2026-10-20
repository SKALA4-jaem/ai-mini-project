from agent.nodes import gate_node, plan_node, replan_check_node, validate_node
from agent.nodes.writing import MAX_VALIDATION_ATTEMPTS, ungrounded_percentages

from .conftest import StubClassifier


class StubResolver:
    def __init__(self, system):
        self.system = system

    async def resolve(self, query):
        return {"system": self.system, "score": 0.9}, {"usd": 0.001}


def _state(**kw):
    return {"query": "q", "events": [], "cost_usd": 0.0, **kw}


async def test_gate_removes_contradicting_analysis_task(make_deps):
    tasks = [{"agent": "research"}, {"agent": "analysis"}]
    out = await gate_node(_state(tasks=tasks, needs_analysis=False), make_deps())
    assert out["gate_removed"] == 1 and all(t["agent"] == "research" for t in out["tasks"])


async def test_replan_adds_gap_task_per_incident_type(make_deps):
    deps = make_deps(incident_classifier=StubClassifier(["cpu-spike", "memory-leak"]))
    out = await replan_check_node(_state(tasks=[], collected=[]), deps)
    assert [t["target"] for t in out["tasks"]] == ["cpu-spike", "memory-leak"]
    assert out["replan_rounds"] == 1 and out["events"][-1]["classifier"] == "stub"


async def test_replan_stops_after_one_round(make_deps):
    deps = make_deps(incident_classifier=StubClassifier(["cpu-spike"]))
    out = await replan_check_node(_state(tasks=[], collected=[], replan_rounds=1), deps)
    assert out["events"][-1]["is_sufficient"] is True   # research ⇄ replan 무한 루프 방지


async def test_plan_keeps_model_targets_when_system_mentioned(make_deps):
    deps = make_deps(system_resolver=StubResolver("order-service"))
    out = await plan_node(_state(query="payments-service CPU 급증 장애"), deps)
    assert "payments-service" in out["events"][-1]["targets"]
    assert out["resolved_system"] is None   # 언급이 있으면 resolver를 부르지 않는다


async def test_plan_uses_resolver_when_no_system_mentioned(make_deps, mcp):
    deps = make_deps(system_resolver=StubResolver("payments-service"))
    out = await plan_node(_state(query="결제가 자꾸 실패하는 장애"), deps)
    assert out["events"][-1]["targets"] == ["payments-service"]
    assert mcp.calls[0] == ("get_prompt", {"system_name": "payments-service",
                                           "symptom": "결제가 자꾸 실패하는 장애"})
    assert out["cost_usd"] > 0.001 - 1e-9   # resolver 임베딩 비용도 누적


async def test_plan_investigates_unknown_system_instead_of_default(make_deps):
    deps = make_deps(system_resolver=StubResolver("auth-service"))
    out = await plan_node(_state(query="billing-service 응답이 느려요"), deps)
    assert out["events"][-1]["targets"] == ["billing-service"]
    assert out["resolved_system"] == {"unknown_systems": ["billing-service"]}


def test_ungrounded_percentages():
    collected = [{"source": "monitoring", "data": {"cpu_percent": 91.3, "alerts": ["CPU 91% (threshold 80%)"]}}]
    assert ungrounded_percentages("CPU 91.3%, 임계치 80%", collected) == []
    assert ungrounded_percentages("CPU 53.5%로 급증", collected) == ["53.5"]


async def test_validate_rejects_ungrounded_numbers(make_deps):
    collected = [{"source": "monitoring", "data": {"cpu_percent": 91.3, "alerts": []}}]
    draft = "진단 결과입니다. 1) CPU 53.5%로 급증했습니다. 2) 재시작하세요."
    on = await validate_node(_state(draft=draft, collected=collected), make_deps(grounding_check=True))
    off = await validate_node(_state(draft=draft, collected=collected), make_deps(grounding_check=False))
    assert on["validation_feedback"] and "53.5%" in on["validation_feedback"]
    assert off["validation_feedback"] is None


async def test_validate_passes_after_max_attempts(make_deps):
    out = await validate_node(_state(draft="짧음", validation_attempts=MAX_VALIDATION_ATTEMPTS - 1),
                              make_deps())
    assert out["validation_feedback"] is None and "최대 시도" in out["events"][-1]["verdict"]
