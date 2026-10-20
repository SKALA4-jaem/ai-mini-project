"""공용 픽스처 — 네트워크·subprocess 없이 그래프와 노드를 테스트하기 위한 mock 의존성.

SupervisorDeps가 모든 의존성을 명시적으로 받기 때문에(Wave 13) MCP 클라이언트를
아래 InMemoryMCP로 갈아 끼우기만 하면 노드/그래프 코드를 그대로 실행할 수 있다.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

from agent.deps import SupervisorDeps  # noqa: E402
from agent.fake_llm import FastLLM, QualityLLM  # noqa: E402


class InMemoryMCP:
    """MCPClient와 같은 인터페이스를 data/ 파일로 흉내 낸다(jitter 없음 → 결정론)."""

    def __init__(self):
        self.monitoring = json.loads((DATA / "monitoring.json").read_text())
        self.calls: list[tuple] = []

    async def find_prompt(self, name):
        return "ops"

    async def get_prompt(self, name, arguments, server="ops"):
        self.calls.append(("get_prompt", arguments))
        return f"시스템: {arguments['system_name']}\n증상: {arguments['symptom']}"

    async def call_tool(self, name, arguments, server="ops"):
        self.calls.append(("call_tool", arguments))
        system = arguments["system_name"]
        if system not in self.monitoring:
            return {"system_name": system, "status": "unknown", "cpu_percent": 0.0,
                    "memory_percent": 0.0, "last_checked": "-",
                    "alerts": [f"System '{system}' not found in monitoring"]}
        d = self.monitoring[system]
        return {"system_name": system, "status": d["status"], "cpu_percent": d["cpu_base"],
                "memory_percent": d["memory_base"], "last_checked": "-", "alerts": d["alerts"]}

    async def find_resource_template(self, name):
        return "ops", "runbook://incident-response/{incident_type}"

    async def read_resource(self, uri, server):
        self.calls.append(("read_resource", uri))
        return (DATA / "runbooks" / f"{uri.rsplit('/', 1)[1]}.md").read_text()


class StubClassifier:
    name = "stub"

    def __init__(self, types):
        self.types = types

    async def classify(self, query, collected):
        return [{"incident_type": t, "system": None, "score": 1.0} for t in self.types], \
            {"usd": 0.0, "latency_ms": 0.0}


@pytest.fixture
def mcp():
    return InMemoryMCP()


@pytest.fixture
def make_deps(mcp):
    def _make(**overrides):
        base = dict(fast_llm=FastLLM("fast", 0.00015), quality_llm=QualityLLM("quality", 0.005),
                    mcp=mcp, session_store=None, version="v2")
        return SupervisorDeps(**{**base, **overrides})
    return _make
