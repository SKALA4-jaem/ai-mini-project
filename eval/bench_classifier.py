"""판별기 단독 지연·비용 측정 — 그래프 전체 지연에 묻히는 RAG 오버헤드를 따로 잰다.

    python eval/bench_classifier.py            # EMBEDDING_BACKEND=openai 기준
측정: 인덱스 최초 구축(캐시 미스) 비용·시간, 캐시 히트 기동 시간,
     keyword / rag 판별 1회당 지연(ms)과 임베딩 비용, 시스템 해석 1회당 지연.
"""
import asyncio
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from agent.classifier import KeywordIncidentClassifier, RagIncidentClassifier, SystemResolver  # noqa: E402
from agent.rag import KnowledgeBase, OpenAIEmbedder  # noqa: E402

MONITORING = json.loads((ROOT / "data" / "monitoring.json").read_text())
CASES = [["payments-service"], ["cache-service"], ["gateway-service", "payments-service"],
         ["payments-service", "cache-service"], ["order-service"], ["search-service"],
         ["notification-service"], ["order-service", "notification-service"]]
QUERIES = ["결제가 자꾸 실패하고 너무 느려요", "푸시 알림이 하나도 안 와요", "로그인 응답이 느려요"]
REPEAT = 3


def collected(systems):
    return [{"source": "monitoring", "data": {"system_name": s, **MONITORING[s]}} for s in systems]


async def timed(coro):
    started = time.perf_counter()
    result = await coro
    return result, (time.perf_counter() - started) * 1000


async def main():
    embedder = OpenAIEmbedder()
    with tempfile.TemporaryDirectory() as tmp:
        cold, cold_ms = await timed(KnowledgeBase(embedder, index_dir=Path(tmp)).build())
        kb = KnowledgeBase(embedder, index_dir=Path(tmp))
        warm, warm_ms = await timed(kb.build())
    keyword, rag, resolver = KeywordIncidentClassifier(), RagIncidentClassifier(kb), SystemResolver(kb)
    kw_ms, rag_ms, rag_usd, res_ms = [], [], [], []
    for _ in range(REPEAT):
        for systems in CASES:
            _, ms = await timed(keyword.classify("", collected(systems)))
            kw_ms.append(ms)
            (_, usage), ms = await timed(rag.classify("", collected(systems)))
            rag_ms.append(ms)
            rag_usd.append(usage["usd"])
        for q in QUERIES:
            _, ms = await timed(resolver.resolve(q))
            res_ms.append(ms)
    report = {
        "index_cold_build": {"ms": round(cold_ms), **cold},
        "index_warm_build": {"ms": round(warm_ms), **warm},
        "keyword_classify_ms_median": round(statistics.median(kw_ms), 3),
        "rag_classify_ms_median": round(statistics.median(rag_ms), 1),
        "rag_classify_ms_p90": round(sorted(rag_ms)[int(len(rag_ms) * 0.9)], 1),
        "rag_classify_usd_mean": statistics.mean(rag_usd),
        "resolver_ms_median": round(statistics.median(res_ms), 1),
    }
    out = ROOT / "eval" / "results" / "bench_classifier.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
