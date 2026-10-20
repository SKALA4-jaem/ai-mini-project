"""research(가드+병렬+재시도) ⇄ replan_check(부족 시 gap task 후 재조사) (Wave 2·7·9·10b·15)."""
import asyncio
import time

from langsmith import traceable

from ..classifier import KeywordIncidentClassifier
from ..deps import SupervisorDeps
from ..retry import with_retry
from ..state import AgentState, add_cost


@traceable(name="research_node")
async def research_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 15 가드 + Wave 10b 병렬 + Wave 9 재시도 + Wave 2 Tool/Resource 실호출."""
    tasks = state["tasks"]
    research_indices = [i for i, t in enumerate(tasks)
                        if t["agent"] == "research" and t["status"] == "pending"]
    # Wave 15 — 객체가 아니라 '실행할 목록'을 검사한다 (not research_agent 버그의 수정판)
    if not research_indices:
        return {"events": state["events"] +
                [{"type": "ResearchSkipped", "reason": "pending research task 0개"}]}

    retry_total = state.get("retry_count", 0)

    # URI를 코드에 하드코딩하지 않는다. 여러 MCP 서버가 연결돼 있고 그중 어느 서버가
    # "get_incident_runbook" resource를 제공하는지 모른다고 가정하고, 먼저 연결된
    # 서버들을 조회(list)해 유효한 서버를 찾은 뒤에만 그 서버로 요청한다.
    needs_runbook = any(tasks[i]["kind"] != "monitoring" for i in research_indices)
    runbook_server = runbook_uri_template = None
    if needs_runbook:
        runbook_server, runbook_uri_template = await deps.mcp.find_resource_template(
            "get_incident_runbook")

    async def run_one(idx: int) -> dict:
        task = tasks[idx]
        await asyncio.sleep(0.35)   # 태스크당 고정 지연 — 병렬 효과를 실측하기 위함
        if task["kind"] == "monitoring":
            data, retries = await with_retry(
                deps.mcp.call_tool, "get_monitoring_status",
                {"system_name": task["target"]})
            return {"idx": idx, "source": "monitoring", "data": data, "retries": retries}
        uri = runbook_uri_template.format(incident_type=task["target"])
        data = await deps.mcp.read_resource(uri, server=runbook_server)
        return {"idx": idx, "source": "runbook", "data": data, "retries": 0}

    started = time.perf_counter()
    results = await asyncio.gather(*(run_one(i) for i in research_indices))
    elapsed = round(time.perf_counter() - started, 2)

    new_tasks = [dict(t) for t in tasks]
    collected = list(state.get("collected", []))
    events = list(state["events"])
    for r in results:
        new_tasks[r["idx"]]["status"] = "done"
        collected.append({"source": r["source"], "data": r["data"]})
        retry_total += r["retries"]
        events.append({"type": "TaskCompleted", "id": new_tasks[r["idx"]]["id"],
                       "source": r["source"], "target": new_tasks[r["idx"]]["target"],
                       "retries": r["retries"]})
    return {"tasks": new_tasks, "collected": collected, "retry_count": retry_total,
            "parallel_elapsed": elapsed, "events": events}


@traceable(name="replan_check_node")
async def replan_check_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 7 — 1차 수집 결과 평가. runbook이 없으면 gap task만 추가해 재조사.

    어떤 runbook을 가져올지는 deps.incident_classifier가 정한다(keyword|rag). rag는
    저하된 시스템마다 판정하므로 gap task가 여러 개 생길 수 있다 — 재조사는 여전히
    1라운드로 제한되어 research ⇄ replan_check 루프가 무한히 돌지 않는다."""
    has_runbook = any(c["source"] == "runbook" for c in state.get("collected", []))
    rounds = state.get("replan_rounds", 0)
    if has_runbook or rounds >= 1:
        verdict = {"type": "ReplanCheck", "round": rounds, "is_sufficient": True}
        return {"events": state["events"] + [verdict]}
    classifier = deps.incident_classifier or KeywordIncidentClassifier()
    verdicts, usage = await classifier.classify(state["query"], state.get("collected", []))
    gap_tasks = [{"id": f"task-gap-runbook-{i}", "agent": "research", "kind": "runbook",
                  "target": v["incident_type"], "status": "pending"}
                 for i, v in enumerate(verdicts)]
    verdict = {"type": "ReplanCheck", "round": rounds, "is_sufficient": False,
               "classifier": classifier.name,
               "gap_tasks": [t["id"] for t in gap_tasks],
               "targets": [v["incident_type"] for v in verdicts],
               "verdicts": verdicts, "classify_ms": usage.get("latency_ms", 0.0)}
    return {"tasks": state["tasks"] + gap_tasks, "replan_rounds": rounds + 1,
            "incident_types": verdicts, "cost_usd": add_cost(state, usage),
            "events": state["events"] + [verdict]}


def after_replan_check(state: AgentState) -> str:
    last = state["events"][-1]
    return "analysis" if last.get("is_sufficient") else "research"
