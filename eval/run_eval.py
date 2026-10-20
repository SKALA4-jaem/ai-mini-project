"""라벨 데이터셋(eval/dataset.jsonl)으로 에이전트를 돌려 개선 전/후를 같은 잣대로 측정한다.

    python eval/run_eval.py --label after                         # 이 프로젝트
    python eval/run_eval.py --label before --project /path/to/baseline  # 개선 전 스냅샷
    python eval/run_eval.py --label after --judge                 # + LLM-as-judge 채점

--project로 다른 코드베이스(개선 전 원본)를 지정할 수 있다. 그 폴더의 server.py를 import해
lifespan을 그대로 띄우고 _handle_chat()을 직접 호출하므로, HTTP 응답에 없는 최종
상태(tasks·collected)까지 꺼내 채점할 수 있다. 백엔드·판별기 등은 환경변수로 고른다
(LLM_BACKEND, INCIDENT_CLASSIFIER, VALIDATE_GROUNDING ...).

측정 지표(질의 1건 단위 → 집계):
- route_acc       : route가 라벨과 일치하는 비율
- target_recall   : 라벨의 조사 대상 시스템을 실제로 조사한 비율
- target_precision: 실제로 조사한 시스템 중 라벨에 있는 비율(불필요한 조회 측정)
- type_recall     : 라벨의 incident_type runbook을 실제로 가져온 비율
- type_precision  : 가져온 runbook 중 라벨(+허용) 유형인 비율
- ungrounded_rate : 수집된 사실에 없는 % 수치가 최종 답변에 들어간 질의 비율
- latency_s / cost_usd / validation_attempts / retry_count
- judge_*         : (--judge) gpt-4o-mini가 1~5점으로 매긴 수치 인용 정확도·조치 적합도
"""
import argparse
import asyncio
import importlib
import json
import os
import re
import statistics
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def load_dataset(path: Path, sets: list[str] | None) -> list[dict]:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    return [r for r in rows if not sets or r["set"] in sets]


def ungrounded(draft: str, collected: list[dict]) -> list[str]:
    """agent/nodes/writing.py의 검증 규칙과 동일 — 개선 전 코드에도 같은 잣대를 대기 위해 복제."""
    source = " ".join(json.dumps(c["data"], ensure_ascii=False) if isinstance(c["data"], dict)
                      else str(c["data"]) for c in collected)
    known = {float(n) for n in _NUMBER_RE.findall(source)}
    return [m for m in dict.fromkeys(_PERCENT_RE.findall(draft)) if float(m) not in known]


def _ratio(hit: int, total: int) -> float | None:
    return None if total == 0 else hit / total


def score_row(row: dict, state: dict) -> dict:
    tasks = state.get("tasks", [])
    investigated = list(dict.fromkeys(t["target"] for t in tasks
                                      if t["agent"] == "research" and t["kind"] == "monitoring"))
    runbooks = list(dict.fromkeys(t["target"] for t in tasks
                                  if t["agent"] == "research" and t["kind"] == "runbook"))
    exp_targets = set(row.get("targets", []))
    exp_types = set(row.get("types", []))
    ok_types = exp_types | set(row.get("allowed_types", []))
    is_incident = row["route"] == "incident"
    collected = state.get("collected", [])
    bad_numbers = ungrounded(state.get("final", ""), collected) if is_incident else []
    return {
        "route_ok": state.get("route") == row["route"],
        "investigated": investigated,
        "runbooks": runbooks,
        "target_recall": _ratio(len(exp_targets & set(investigated)), len(exp_targets)) if is_incident else None,
        "target_precision": _ratio(len(exp_targets & set(investigated)), len(investigated)) if is_incident and investigated else None,
        "type_recall": _ratio(len(exp_types & set(runbooks)), len(exp_types)) if is_incident else None,
        "type_precision": _ratio(len(ok_types & set(runbooks)), len(runbooks)) if is_incident and runbooks else None,
        "ungrounded": bad_numbers,
    }


JUDGE_SYSTEM = (
    "당신은 장애 대응 보고서 채점자다. '수집된 사실'과 '답변'을 비교해 JSON으로만 답하라. "
    '스키마: {"numeric_accuracy": 1~5 정수, "action_relevance": 1~5 정수, "reason": 한 문장}. '
    "numeric_accuracy: 답변의 수치(CPU·메모리·지연시간 등)가 수집된 사실을 정확히 인용했는가 "
    "(지어낸 수치가 하나라도 있으면 2 이하). action_relevance: 권장 조치가 수집된 증상·runbook에 "
    "맞는가.")


async def judge(answer: str, collected: list[dict], query: str) -> dict:
    import httpx
    facts = "\n".join(json.dumps(c["data"], ensure_ascii=False) if isinstance(c["data"], dict)
                      else str(c["data"])[:1500] for c in collected)
    payload = {"model": os.environ.get("JUDGE_MODEL", "gpt-4o-mini"), "temperature": 0,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": JUDGE_SYSTEM},
                            {"role": "user", "content":
                             f"## 질문\n{query}\n\n## 수집된 사실\n{facts}\n\n## 답변\n{answer}"}]}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post("https://api.openai.com/v1/chat/completions", json=payload,
                                 headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


def _mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 4) if values else None


def summarize(results: list[dict]) -> dict:
    incident = [r for r in results if r["expected_route"] == "incident"]
    summary = {
        "n": len(results),
        "route_acc": _mean([float(r["route_ok"]) for r in results]),
        "target_recall": _mean([r["target_recall"] for r in incident]),
        "target_precision": _mean([r["target_precision"] for r in incident]),
        "type_recall": _mean([r["type_recall"] for r in incident]),
        "type_precision": _mean([r["type_precision"] for r in incident]),
        "ungrounded_rate": _mean([float(bool(r["ungrounded"])) for r in incident
                                  if r["route"] == "incident"]),
        "latency_s_mean": _mean([r["latency_s"] for r in results]),
        "latency_s_incident_mean": _mean([r["latency_s"] for r in incident]),
        "cost_usd_total": round(sum(r["cost_usd"] for r in results), 6),
        "validation_attempts_mean": _mean([r["validation_attempts"] for r in incident
                                           if r["route"] == "incident"]),
        "retry_total": sum(r["retry_count"] for r in results),
    }
    if any("judge" in r for r in results):
        summary["judge_numeric_mean"] = _mean([r["judge"].get("numeric_accuracy") for r in results if "judge" in r])
        summary["judge_action_mean"] = _mean([r["judge"].get("action_relevance") for r in results if "judge" in r])
    return summary


async def run(args) -> dict:
    project = Path(args.project).resolve()
    os.chdir(project)
    sys.path.insert(0, str(project))
    from dotenv import load_dotenv
    load_dotenv(project / ".env")
    load_dotenv(HERE.parent / ".env")   # 스냅샷 폴더에 .env가 없으면 이 프로젝트 것을 쓴다
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
    server = importlib.import_module("server")
    rows = load_dataset(Path(args.dataset), args.sets)
    results = []
    async with server.lifespan(server.app):
        health = await server.health()
        for row in rows:
            started = time.perf_counter()
            state, _ = await server._handle_chat(row["query"], f"eval-{uuid.uuid4().hex[:8]}")
            latency = round(time.perf_counter() - started, 3)
            scored = score_row(row, state)
            result = {"id": row["id"], "set": row["set"], "query": row["query"],
                      "expected_route": row["route"], "route": state.get("route"),
                      **scored, "latency_s": latency,
                      "cost_usd": state.get("cost_usd", 0.0),
                      "validation_attempts": state.get("validation_attempts", 0),
                      "retry_count": state.get("retry_count", 0),
                      "final": state.get("final", "")}
            if args.judge and row["route"] == "incident" and state.get("route") == "incident":
                result["judge"] = await judge(state.get("final", ""), state.get("collected", []),
                                              row["query"])
            results.append(result)
            print(f"[{row['id']}] route={result['route']:<8} targets={scored['investigated']} "
                  f"runbooks={scored['runbooks']} {latency:.2f}s"
                  + (f" ungrounded={scored['ungrounded']}" if scored["ungrounded"] else ""),
                  flush=True)
    by_set = {s: summarize([r for r in results if r["set"] == s])
              for s in dict.fromkeys(r["set"] for r in results)}
    return {"label": args.label, "project": str(project),
            "config": {k: os.environ.get(k) for k in
                       ("LLM_BACKEND", "INCIDENT_CLASSIFIER", "EMBEDDING_BACKEND",
                        "VALIDATE_GROUNDING", "OPENAI_FAST_MODEL", "OPENAI_QUALITY_MODEL")},
            "health": health, "summary": summarize(results), "by_set": by_set,
            "results": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--project", default=str(HERE.parent))
    parser.add_argument("--dataset", default=str(HERE / "dataset.jsonl"))
    parser.add_argument("--sets", nargs="*", help="base natural extended chat 중 일부만")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--out", default=str(HERE / "results"))
    args = parser.parse_args()
    args.dataset = str(Path(args.dataset).resolve())
    out_dir = Path(args.out).resolve()
    report = asyncio.run(run(args))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.label}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
