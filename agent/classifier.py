"""incident_type 판별기 2종 — replan_check가 어떤 runbook을 추가로 조회할지 정한다.

INCIDENT_CLASSIFIER 환경변수(keyword|rag)로 재배포 없이 전환된다. 같은 코드베이스에서
개선 전/후를 같은 입력으로 비교할 수 있게 하려는 의도다.

- KeywordIncidentClassifier: 기존(개선 전) 로직 그대로. 모든 모니터링 알림을 한 문자열로
  합친 뒤 규칙 목록 순서대로 첫 번째로 걸리는 키워드 하나만 쓴다 → 시스템이 여러 개
  저하돼도 runbook은 1개, 규칙에 없는 표현은 전부 db-down으로 폴백.
- RagIncidentClassifier   : 저하된 시스템마다 알림 문장을 임베딩해 가장 가까운 runbook
  청크의 metadata.incident_type을 고른다 → 시스템별로 서로 다른 runbook을 조회할 수 있고,
  새 runbook은 .md 파일만 추가하면 코드 수정 없이 인식된다.

두 판별기 모두 (판정 목록, usage) 를 돌려준다. 판정 하나는
{"incident_type", "system", "score"} 형태다.
"""
import time

from langsmith import traceable

INCIDENT_TYPE_RULES = [
    ("latency", "high-latency"),
    ("pool", "high-latency"),
    ("cpu", "cpu-spike"),
    ("memory", "memory-leak"),
    ("heap", "memory-leak"),
    ("timeout", "network-timeout"),
    ("network", "network-timeout"),
    ("disk", "disk-full"),
    ("down", "db-down"),
]
FALLBACK_INCIDENT_TYPE = "db-down"


def _monitoring(collected: list[dict]) -> list[dict]:
    return [c["data"] for c in collected if c.get("source") == "monitoring"]


class KeywordIncidentClassifier:
    name = "keyword"

    @traceable(name="classify.keyword")
    async def classify(self, query: str, collected: list[dict]) -> tuple[list[dict], dict]:
        text = " ".join(f"{d.get('status', '')} " + " ".join(d.get("alerts", []))
                        for d in _monitoring(collected)).lower()
        incident_type = next((t for kw, t in INCIDENT_TYPE_RULES if kw in text),
                             FALLBACK_INCIDENT_TYPE)
        return [{"incident_type": incident_type, "system": None, "score": None}], \
            {"usd": 0.0, "tokens": 0, "latency_ms": 0.0}


class RagIncidentClassifier:
    name = "rag"

    def __init__(self, kb, max_types: int = 3, min_score: float = 0.0):
        self.kb = kb
        self.max_types = max_types      # 한 요청에서 조회할 runbook 상한 — 프롬프트 비대화 방지
        self.min_score = min_score      # 이 점수 미만 판정은 버린다(근거 약한 runbook 주입 방지)

    @traceable(name="classify.rag")
    async def classify(self, query: str, collected: list[dict]) -> tuple[list[dict], dict]:
        monitored = [d for d in _monitoring(collected) if d.get("status") != "unknown"]
        if collected and not monitored:
            # 조사한 시스템이 전부 모니터링 미등록(status=unknown)이면 근거가 없다 — 질문
            # 문장만으로 runbook을 붙이면 존재하지 않는 시스템에 롤백 등을 권하게 된다
            # (평가에서 billing-service 질의로 실측된 사례).
            return [], {"usd": 0.0, "tokens": 0, "latency_ms": 0.0}
        # 알림이 있는(=이상 징후가 있는) 시스템마다 질의 1개. 그런 시스템이 하나도 없으면
        # 사용자가 쓴 증상 문장 자체로 검색한다.
        probes = [(d["system_name"], "; ".join(d["alerts"]))
                  for d in monitored if d.get("alerts")]
        if not probes:
            probes = [(None, query)]
        started = time.perf_counter()
        results, usage = await self.kb.search([text for _, text in probes], kind="runbook", k=1)
        usage = {**usage, "latency_ms": round((time.perf_counter() - started) * 1000, 1)}

        verdicts, seen = [], set()
        for (system, _), hits in zip(probes, results):
            if not hits or hits[0].score < self.min_score:
                continue
            incident_type = hits[0].doc.metadata["incident_type"]
            if incident_type in seen:
                continue
            seen.add(incident_type)
            verdicts.append({"incident_type": incident_type, "system": system,
                             "score": round(hits[0].score, 4)})
        if not verdicts:   # 전부 임계치 미만 — 기존 동작과 같은 폴백
            verdicts = [{"incident_type": FALLBACK_INCIDENT_TYPE, "system": None, "score": None}]
        return verdicts[:self.max_types], usage


class SystemResolver:
    """시스템명이 하나도 언급되지 않은 질의("로그인이 느려요")를 시스템 카탈로그 검색으로
    해석한다. 점수가 min_score 미만이면 None — 호출측이 기존 기본값으로 폴백한다."""

    def __init__(self, kb, min_score: float = 0.0):
        self.kb = kb
        self.min_score = min_score

    @traceable(name="resolve_system.rag")
    async def resolve(self, query: str) -> tuple[dict | None, dict]:
        results, usage = await self.kb.search([query], kind="system", k=1)
        hits = results[0]
        if not hits or hits[0].score < self.min_score:
            return None, usage
        return {"system": hits[0].doc.metadata["system"], "score": round(hits[0].score, 4)}, usage
