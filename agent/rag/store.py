"""최소 구현 벡터 스토어 — 문서 수십 개 규모라 외부 벡터 DB 없이 순수 파이썬으로 충분하다.

인덱스는 data/vector_index/<embedder>.json에 캐시한다. 캐시 키는 (임베더 이름, 코퍼스
해시)라서 runbook을 하나라도 고치면 자동으로 재임베딩되고, 안 고쳤으면 서버를 다시
켜도 임베딩 API를 호출하지 않는다(기동 비용 0).
"""
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Document:
    id: str
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Hit:
    doc: Document
    score: float


def corpus_hash(docs: list[Document]) -> str:
    h = hashlib.sha256()
    for d in docs:
        h.update(d.id.encode())
        h.update(d.text.encode())
    return h.hexdigest()[:16]


class VectorStore:
    def __init__(self):
        self.docs: list[Document] = []
        self.vectors: list[list[float]] = []

    def add(self, docs: list[Document], vectors: list[list[float]]) -> None:
        self.docs.extend(docs)
        self.vectors.extend(vectors)

    def search(self, query_vec: list[float], k: int = 5,
               where: dict | None = None) -> list[Hit]:
        """코사인 유사도 상위 k개. where는 metadata 일치 필터(예: {"kind": "runbook"})."""
        hits = []
        for doc, vec in zip(self.docs, self.vectors):
            if where and any(doc.metadata.get(key) != val for key, val in where.items()):
                continue
            hits.append(Hit(doc, sum(a * b for a, b in zip(query_vec, vec))))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    def save(self, path: Path, key: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"key": key, "docs": [
            {"id": d.id, "text": d.text, "metadata": d.metadata, "vector": v}
            for d, v in zip(self.docs, self.vectors)]}
        path.write_text(json.dumps(payload, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path, key: str) -> "VectorStore | None":
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("key") != key:
            return None
        store = cls()
        store.add([Document(d["id"], d["text"], d["metadata"]) for d in payload["docs"]],
                  [d["vector"] for d in payload["docs"]])
        return store
