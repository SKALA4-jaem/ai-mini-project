"""그래프 공유 상태(AgentState)와 상태 갱신 헬퍼 — 모든 노드 모듈이 이것만 import한다."""
from typing import TypedDict


class AgentState(TypedDict, total=False):
    query: str
    thread_id: str
    history: list[dict]
    route: str
    needs_analysis: bool
    resolved_system: dict | None
    tasks: list[dict]
    gate_removed: int
    collected: list[dict]
    replan_rounds: int
    incident_types: list[dict]
    retry_count: int
    parallel_elapsed: float
    draft: str
    validation_attempts: int
    validation_feedback: str
    final: str
    last_prompt: str
    cost_usd: float
    events: list[dict]


def add_cost(state: AgentState, usage: dict) -> float:
    return round(state.get("cost_usd", 0.0) + usage["usd"], 6)
