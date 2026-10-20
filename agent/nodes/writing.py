"""write → validate(반려 시 재작성) → finalize (Wave 8·10a)."""
import json
import re

from langgraph.config import get_stream_writer
from langsmith import traceable

from ..deps import SupervisorDeps
from ..state import AgentState, add_cost

MAX_VALIDATION_ATTEMPTS = 3
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def ungrounded_percentages(draft: str, collected: list[dict]) -> list[str]:
    """답변에 등장한 'N%' 수치 중 수집된 사실(모니터링 값·알림·runbook 본문) 어디에도
    없는 것을 돌려준다 — 모델이 수치를 지어내는 할루시네이션을 코드로 잡는 방어선."""
    source = " ".join(json.dumps(c["data"], ensure_ascii=False) if isinstance(c["data"], dict)
                      else str(c["data"]) for c in collected)
    known = {float(n) for n in _NUMBER_RE.findall(source)}
    return [m for m in dict.fromkeys(_PERCENT_RE.findall(draft)) if float(m) not in known]


@traceable(name="write_node")
async def write_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 8/10a — 고품질 모델로 초안 작성 (1차는 의도적 저품질).

    토큰마다 attempt 번호를 같이 실어 보낸다 — validate가 반려해 재작성(attempt 증가)
    될 때 프론트가 새 말풍선으로 끊어서 보여줄 수 있게 하기 위함(Wave 8 재작성 루프를
    그대로 노출)."""
    attempt = state.get("validation_attempts", 0) + 1
    writer = get_stream_writer()
    draft, usage = await deps.quality_llm.write(
        state["query"], state.get("collected", []),
        attempt, state.get("validation_feedback"),
        on_token=lambda piece: writer(
            {"type": "AnswerToken", "attempt": attempt, "delta": piece}))
    return {"draft": draft, "last_prompt": usage.get("prompt"),
            "cost_usd": add_cost(state, usage),
            "events": state["events"] + [{"type": "DraftWritten", "attempt": attempt,
                                          "length": len(draft)}]}


@traceable(name="validate_node")
async def validate_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 8 — 코드 기준 검증: 30자 이상 + 절차 번호 포함이어야 합격.

    deps.grounding_check가 켜져 있으면 답변 속 % 수치가 수집된 사실에 실제로 있는지도
    검사한다(형식만 보던 기존 검증의 보강)."""
    draft = state["draft"]
    attempts = state.get("validation_attempts", 0) + 1
    problems = []
    if len(draft) < 30 or "1)" not in draft:
        problems.append(f"응답이 너무 짧거나 번호 절차가 없습니다({len(draft)}자, 최소 30자). "
                        f"절차를 1) 2) 3) 번호로 구체적으로 설명하세요.")
    ungrounded = (ungrounded_percentages(draft, state.get("collected", []))
                  if deps.grounding_check else [])
    if ungrounded:
        problems.append(f"수집된 사실에 없는 수치가 있습니다: {', '.join(u + '%' for u in ungrounded)}. "
                        f"수치는 수집된 값을 그대로 인용하고, 없는 값은 쓰지 마세요.")
    ok = not problems
    verdict = "합격" if ok else "불합격"
    if not ok and attempts >= MAX_VALIDATION_ATTEMPTS:   # 실모델 무한 재작성 방지
        ok, verdict = True, "합격(최대 시도 도달 — 통과 처리)"
    event = {"type": "Validation", "attempt": attempts, "verdict": verdict}
    if ungrounded:
        event["ungrounded"] = ungrounded
    return {"validation_attempts": attempts,
            "validation_feedback": None if ok else " ".join(problems),
            "events": state["events"] + [event]}


@traceable(name="finalize_node")
async def finalize_node(state: AgentState, deps: SupervisorDeps) -> dict:
    return {"final": state["draft"],
            "events": state["events"] + [{"type": "Finalize", "pipeline": "incident-v2"}]}


def after_validate(state: AgentState) -> str:
    return "finalize" if state.get("validation_feedback") is None else "write"
