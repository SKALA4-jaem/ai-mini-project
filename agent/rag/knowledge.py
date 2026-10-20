"""런북·시스템 카탈로그 지식베이스 — 서버 기동 시(lifespan) 1회 인덱싱해 재사용한다.

문서 단위:
- runbook 요약 청크: 제목 + "주요 증상" 줄 (incident_type 판별의 핵심 근거)
- runbook 절차 청크: 제목 + 번호 절차 한 줄씩 (증상 설명에 없는 단어도 잡히게)
- system 청크     : data/systems.json의 시스템 설명 (시스템명 없는 질의 해석용)

모든 청크는 metadata에 kind(runbook/system)와 incident_type 또는 system을 들고 있다 —
검색 결과에서 본문이 아니라 이 메타정보를 꺼내 쓰는 것이 핵심이다.
"""
import re
from pathlib import Path

from langsmith import traceable

from ..systems import DATA_DIR, SYSTEM_CATALOG
from .store import Document, Hit, VectorStore, corpus_hash

INDEX_DIR = DATA_DIR / "vector_index"


def load_runbook_documents(runbook_dir: Path) -> list[Document]:
    docs = []
    for path in sorted(runbook_dir.glob("*.md")):
        incident_type = path.stem
        lines = [l.strip() for l in path.read_text().splitlines() if l.strip()]
        title = lines[0].lstrip("# ").strip()
        symptom = next((l.split(":", 1)[1].strip() for l in lines
                        if l.startswith("- 주요 증상:")), "")
        docs.append(Document(f"{incident_type}#summary", f"{title}\n{symptom}",
                             {"kind": "runbook", "incident_type": incident_type,
                              "section": "summary"}))
        for line in lines:
            if m := re.match(r"^(\d+)\.\s+(.*)", line):
                docs.append(Document(f"{incident_type}#step{m.group(1)}",
                                     f"{title}\n{m.group(2)}",
                                     {"kind": "runbook", "incident_type": incident_type,
                                      "section": f"step{m.group(1)}"}))
    return docs


def load_system_documents(catalog: dict[str, str]) -> list[Document]:
    return [Document(f"system#{name}", f"{name}: {desc}", {"kind": "system", "system": name})
            for name, desc in sorted(catalog.items())]


class KnowledgeBase:
    def __init__(self, embedder, runbook_dir: Path = DATA_DIR / "runbooks",
                 catalog: dict[str, str] | None = None, index_dir: Path | None = INDEX_DIR):
        self.embedder = embedder
        self.runbook_dir = runbook_dir
        self.catalog = SYSTEM_CATALOG if catalog is None else catalog
        self.index_dir = index_dir
        self.store = VectorStore()
        self.build_info: dict = {}

    async def build(self) -> dict:
        """인덱스를 만든다. 캐시가 유효하면 임베딩 API를 호출하지 않는다."""
        docs = load_runbook_documents(self.runbook_dir) + load_system_documents(self.catalog)
        key = f"{self.embedder.name}:{corpus_hash(docs)}"
        cache = (self.index_dir / f"{re.sub(r'[^a-z0-9-]', '_', self.embedder.name)}.json"
                 if self.index_dir else None)
        cached = VectorStore.load(cache, key) if cache else None
        if cached is not None:
            self.store = cached
            self.build_info = {"docs": len(docs), "cache_hit": True, "usd": 0.0}
            return self.build_info
        vectors, usage = await self.embedder.embed([d.text for d in docs])
        self.store = VectorStore()
        self.store.add(docs, vectors)
        if cache:
            self.store.save(cache, key)
        self.build_info = {"docs": len(docs), "cache_hit": False, "usd": usage["usd"],
                           "tokens": usage["tokens"]}
        return self.build_info

    @traceable(run_type="retriever", name="kb.search")
    async def search(self, texts: list[str], kind: str, k: int = 3) -> tuple[list[list[Hit]], dict]:
        """여러 질의를 임베딩 API 1회(batch)로 묶어 검색한다."""
        vectors, usage = await self.embedder.embed(texts)
        return [self.store.search(v, k=k, where={"kind": kind}) for v in vectors], usage
