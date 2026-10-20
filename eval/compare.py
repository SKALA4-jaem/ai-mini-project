"""eval/results/*.json 여러 개를 나란히 놓고 Before/After 표(markdown)를 만든다.

    python eval/compare.py openai-before openai-after openai-after-keyword
"""
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"

METRICS = [
    ("route_acc", "라우팅 정확도", "{:.1%}"),
    ("target_recall", "조사 대상 재현율", "{:.1%}"),
    ("target_precision", "조사 대상 정밀도", "{:.1%}"),
    ("type_recall", "runbook 재현율", "{:.1%}"),
    ("type_precision", "runbook 정밀도", "{:.1%}"),
    ("ungrounded_rate", "근거 없는 수치 포함률", "{:.1%}"),
    ("judge_numeric_mean", "Judge 수치 인용(1~5)", "{:.2f}"),
    ("judge_action_mean", "Judge 조치 적합도(1~5)", "{:.2f}"),
    ("latency_s_incident_mean", "장애 질의 평균 지연(s)", "{:.2f}"),
    ("validation_attempts_mean", "평균 작성 시도 횟수", "{:.2f}"),
    ("cost_usd_total", "총 비용(USD, 24건)", "{:.4f}"),
]


def fmt(value, pattern):
    return "-" if value is None else pattern.format(value)


def table(labels: list[str], scope: str | None = None) -> str:
    reports = [json.loads((RESULTS / f"{l}.json").read_text()) for l in labels]
    head = "| 지표 | " + " | ".join(labels) + " |\n|---|" + "---|" * len(labels)
    rows = []
    for key, name, pattern in METRICS:
        values = [(r["by_set"].get(scope, {}) if scope else r["summary"]).get(key) for r in reports]
        rows.append(f"| {name} | " + " | ".join(fmt(v, pattern) for v in values) + " |")
    return head + "\n" + "\n".join(rows)


if __name__ == "__main__":
    labels = sys.argv[1:]
    print("## 전체\n" + table(labels))
    for scope in ("base", "natural", "extended", "chat"):
        print(f"\n## {scope}\n" + table(labels, scope))
