"""plan(MCP Prompt 절차 반영) → gate(권위 게이트) (Wave 4·6)."""
import re

from langsmith import traceable

from ..deps import SupervisorDeps
from ..state import AgentState, add_cost
from ..systems import DEFAULT_SYSTEM, KNOWN_SYSTEMS, find_mentioned_systems


# 시스템명처럼 생긴 토큰(xxx-service, web-01 등) — KNOWN_SYSTEMS에 없는 이름을 잡아낸다.
# \b는 한글 조사("billing-service에서")와 붙으면 경계로 안 잡혀서 lookaround로 쓴다
_SYSTEM_NAME_RE = re.compile(r"(?<![a-z0-9-])[a-z][a-z0-9]*(?:-[a-z0-9]+)*-(?:service|\d+)(?![a-z0-9-])")


async def _resolve_targets(state: AgentState, deps: SupervisorDeps) -> tuple[str, list[str] | None, dict | None, dict]:
    """조사 대상 시스템을 정한다 → (MCP Prompt용 대표 시스템, 강제 target 목록, 해석 근거, usage).

    1) 쿼리에 KNOWN_SYSTEMS가 언급되면 그대로 — 모델의 계획을 존중(강제 없음)
    2) 모니터링 목록에 없는 시스템명(예: billing-service)을 명시했으면 그 이름 그대로
       조사시킨다 — MCP Tool이 status=unknown을 돌려주므로 답변이 "모니터링 대상 아님"을
       솔직히 말하게 된다(기존엔 auth-service를 조용히 대신 조사해 엉뚱한 진단을 냈다)
    3) 시스템명이 전혀 없으면 system_resolver(시스템 카탈로그 RAG)로 해석
    4) 그래도 없으면 DEFAULT_SYSTEM (기존의 하드코딩 "auth-service" 폴백 자리)"""
    query = state["query"]
    mentioned = find_mentioned_systems(query)
    if mentioned:
        return mentioned[0], None, None, {"usd": 0.0}
    unknown = list(dict.fromkeys(n for n in _SYSTEM_NAME_RE.findall(query)
                                 if n not in KNOWN_SYSTEMS))
    if unknown:
        return unknown[0], unknown, {"unknown_systems": unknown}, {"usd": 0.0}
    if deps.system_resolver is not None:
        resolved, usage = await deps.system_resolver.resolve(query)
        if resolved is not None:
            return resolved["system"], [resolved["system"]], resolved, usage
        return DEFAULT_SYSTEM, None, None, usage
    return DEFAULT_SYSTEM, None, None, {"usd": 0.0}


def _override_research_targets(tasks: list[dict], targets: list[str]) -> list[dict]:
    """모델이 세운 research task들을 코드가 확정한 targets로 교체한다(W6 정신)."""
    kept = [t for t in tasks if t["agent"] != "research"]
    research = [{"id": f"task-{i}", "agent": "research", "kind": "monitoring",
                 "target": target, "status": "pending"} for i, target in enumerate(targets)]
    return research + kept


@traceable(name="plan_node")
async def plan_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 4 — Plan/Task 분해. Wave 2의 MCP Prompt가 표준 절차를 깔아준다.

    resource와 마찬가지로 이름을 어느 서버가 들고 있는지 미리 가정하지 않고,
    find_prompt()로 연결된 서버들을 먼저 조회해 찾은 뒤에만 get_prompt를 보낸다."""
    system_name, forced, resolution, resolve_usage = await _resolve_targets(state, deps)
    prompt_server = await deps.mcp.find_prompt("incident_analysis_prompt")
    procedure = await deps.mcp.get_prompt(
        "incident_analysis_prompt",
        {"system_name": system_name, "symptom": state["query"]},
        server=prompt_server,
    )
    result, usage = deps.fast_llm.plan(state["query"], procedure)
    tasks = result["tasks"] if forced is None else _override_research_targets(result["tasks"], forced)
    targets = [t["target"] for t in tasks if t["agent"] == "research" and t.get("target")]
    event = {"type": "PlanCreated", "task_count": len(tasks), "targets": targets}
    if resolution is not None:
        event["resolution"] = resolution
    cost = round(add_cost(state, usage) + resolve_usage["usd"], 6)
    return {"tasks": tasks, "needs_analysis": result["needs_analysis"],
            "resolved_system": resolution, "cost_usd": cost,
            "events": state["events"] + [event]}


@traceable(name="gate_node")
async def gate_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 6 — 권위 게이트. needs_analysis=False인데 섞여 들어온 analysis task를
    프롬프트가 아니라 코드로 강제 제거한다."""
    tasks = state["tasks"]
    if not state.get("needs_analysis", False):
        kept = [t for t in tasks if t["agent"] != "analysis"]
        removed = len(tasks) - len(kept)
    else:
        kept, removed = tasks, 0
    event = {"type": "GateApplied", "removed_analysis_tasks": removed}
    return {"tasks": kept, "gate_removed": removed,
            "events": state["events"] + [event]}
