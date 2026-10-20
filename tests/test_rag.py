from agent.classifier import KeywordIncidentClassifier, RagIncidentClassifier, SystemResolver
from agent.rag import HashEmbedder, KnowledgeBase
from agent.rag.knowledge import load_runbook_documents
from agent.rag.store import Document, VectorStore

from .conftest import DATA


def _mon(system, alerts, status="degraded"):
    return {"source": "monitoring", "data": {"system_name": system, "status": status,
                                             "cpu_percent": 0, "memory_percent": 0,
                                             "alerts": alerts}}


class CountingEmbedder(HashEmbedder):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def embed(self, texts):
        self.calls += 1
        return await super().embed(texts)


def test_vector_store_search_and_filter():
    store = VectorStore()
    store.add([Document("a", "a", {"kind": "x"}), Document("b", "b", {"kind": "y"})],
              [[1.0, 0.0], [0.0, 1.0]])
    assert store.search([0.9, 0.1], k=1)[0].doc.id == "a"
    assert store.search([0.9, 0.1], k=1, where={"kind": "y"})[0].doc.id == "b"


def test_vector_store_cache_invalidates_on_key_change(tmp_path):
    store = VectorStore()
    store.add([Document("a", "a")], [[1.0]])
    store.save(tmp_path / "i.json", key="k1")
    assert VectorStore.load(tmp_path / "i.json", key="k1") is not None
    assert VectorStore.load(tmp_path / "i.json", key="k2") is None


def test_runbook_chunks_carry_incident_type_metadata():
    docs = load_runbook_documents(DATA / "runbooks")
    types = {d.metadata["incident_type"] for d in docs}
    assert {"cpu-spike", "error-rate-spike", "cert-expiry"} <= types
    summary = next(d for d in docs if d.id == "disk-full#summary")
    assert "디스크" in summary.text and summary.metadata["section"] == "summary"


async def test_knowledge_base_reuses_cached_index(tmp_path):
    embedder = CountingEmbedder()
    first = await KnowledgeBase(embedder, index_dir=tmp_path).build()
    second = await KnowledgeBase(embedder, index_dir=tmp_path).build()
    assert first["cache_hit"] is False and second["cache_hit"] is True
    assert embedder.calls == 1   # 두 번째 기동은 임베딩 API를 호출하지 않는다


async def test_keyword_classifier_keeps_legacy_behavior():
    clf = KeywordIncidentClassifier()
    # 규칙 순서상 첫 매칭 하나만 — 두 시스템이 저하돼도 runbook 1개
    verdicts, _ = await clf.classify("", [_mon("p", ["CPU 91%"]), _mon("c", ["heap near limit"])])
    assert [v["incident_type"] for v in verdicts] == ["cpu-spike"]
    # 규칙에 없는 표현은 db-down 폴백
    verdicts, _ = await clf.classify("", [_mon("o", ["HTTP 5xx error rate 12%"])])
    assert verdicts[0]["incident_type"] == "db-down"


async def test_rag_classifier_one_verdict_per_degraded_system(tmp_path):
    kb = KnowledgeBase(HashEmbedder(), index_dir=tmp_path)
    await kb.build()
    clf = RagIncidentClassifier(kb)
    collected = [_mon("a", ["인증서가 만료되어 핸드셰이크 실패"]),
                 _mon("b", ["디스크 사용률 한계, 파일시스템 쓰기 실패"]),
                 _mon("web-01", [], status="healthy")]
    verdicts, usage = await clf.classify("", collected)
    assert [v["incident_type"] for v in verdicts] == ["cert-expiry", "disk-full"]
    assert [v["system"] for v in verdicts] == ["a", "b"]   # 알림 없는 healthy 시스템은 제외
    assert "latency_ms" in usage


async def test_rag_classifier_falls_back_when_below_threshold(tmp_path):
    kb = KnowledgeBase(HashEmbedder(), index_dir=tmp_path)
    await kb.build()
    verdicts, _ = await RagIncidentClassifier(kb, min_score=0.99).classify(
        "", [_mon("a", ["무언가 이상함"])])
    assert verdicts == [{"incident_type": "db-down", "system": None, "score": None}]


async def test_rag_classifier_uses_query_when_no_alerts(tmp_path):
    kb = KnowledgeBase(HashEmbedder(), index_dir=tmp_path)
    await kb.build()
    verdicts, _ = await RagIncidentClassifier(kb).classify(
        "TLS 인증서 만료로 HTTPS 접속이 거부돼요", [_mon("x", [], status="healthy")])
    assert verdicts[0]["incident_type"] == "cert-expiry"


async def test_system_resolver(tmp_path):
    kb = KnowledgeBase(HashEmbedder(), index_dir=tmp_path)
    await kb.build()
    resolved, _ = await SystemResolver(kb).resolve("푸시 알림 발송이 안 돼요")
    assert resolved["system"] == "notification-service"
    assert (await SystemResolver(kb, min_score=0.99).resolve("푸시 알림"))[0] is None
