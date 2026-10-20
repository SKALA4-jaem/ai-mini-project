"""시스템 카탈로그 단일 소스.

기존에는 graph.py/ollama_llm.py/openai_llm.py 세 파일에 _load_known_systems()·
_guess_target() 같은 함수가 복붙돼 있었고, 시스템명이 하나도 안 걸리면 세 곳 모두
"auth-service"로 하드코딩 폴백했다. 이 모듈이 그 역할을 한 곳으로 모은다.

- KNOWN_SYSTEMS : data/monitoring.json의 키 (모니터링 가능한 시스템)
- SYSTEM_CATALOG: data/systems.json의 시스템 설명 — 시스템명이 언급되지 않은 질의
                  ("로그인이 느려요")를 RAG로 해석할 때 검색 대상이 된다
- DEFAULT_SYSTEM: 최후 폴백. 코드 하드코딩 대신 DEFAULT_TARGET_SYSTEM 환경변수로 바꿀 수 있다
"""
import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_json_keys(path: Path, fallback: dict) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return fallback


KNOWN_SYSTEMS: set[str] = set(_load_json_keys(
    DATA_DIR / "monitoring.json", {"auth-service": {}, "web-01": {}}))
SYSTEM_CATALOG: dict[str, str] = {
    name: desc for name, desc in _load_json_keys(DATA_DIR / "systems.json", {}).items()
    if name in KNOWN_SYSTEMS
}
DEFAULT_SYSTEM = os.environ.get("DEFAULT_TARGET_SYSTEM", "auth-service")


def find_mentioned_systems(query: str) -> list[str]:
    """쿼리에 등장하는 KNOWN_SYSTEMS를 등장 순서대로 반환한다(없으면 빈 리스트)."""
    return [s for _, s in sorted((query.index(s), s) for s in KNOWN_SYSTEMS if s in query)]


def guess_target(query: str) -> str:
    """쿼리에서 가장 먼저 등장하는 시스템. 하나도 없으면 DEFAULT_SYSTEM."""
    mentioned = find_mentioned_systems(query)
    return mentioned[0] if mentioned else DEFAULT_SYSTEM


def guess_targets(query: str) -> list[str]:
    """쿼리에 등장하는 시스템 전부(계획 붕괴 시 복구용). 하나도 없으면 [DEFAULT_SYSTEM]."""
    return sorted(find_mentioned_systems(query)) or [DEFAULT_SYSTEM]
