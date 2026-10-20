"""임베딩 백엔드 2종 — LLM 백엔드와 같은 방식으로 갈아 끼운다(의존성 주입).

- OpenAIEmbedder: text-embedding-3-small 실호출. 실제 과금이 발생하며 토큰 수는 응답의
  usage.total_tokens(실측)를 쓴다.
- HashEmbedder  : 네트워크 없이 동작하는 결정론적 문자 n-gram 해싱 임베더. fake 백엔드와
  단위 테스트용 — 의미 이해는 못 하고 표면 문자열 겹침만 본다.

두 임베더 모두 L2 정규화된 벡터를 돌려주므로 내적이 곧 코사인 유사도다.
"""
import hashlib
import math
import os
import re

import httpx
from langsmith import traceable

OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class OpenAIEmbedder:
    def __init__(self, model: str = "text-embedding-3-small",
                 usd_per_1k_tokens: float = 0.00002):
        self.model = model
        self.name = f"openai:{model}"
        self.usd_per_1k = usd_per_1k_tokens
        self.api_key = os.environ.get("OPENAI_API_KEY", "")

    @traceable(run_type="embedding", name="openai.embed")
    async def embed(self, texts: list[str]) -> tuple[list[list[float]], dict]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다 — .env를 확인하세요.")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                OPENAI_EMBED_URL,
                json={"model": self.model, "input": texts},
                headers={"Authorization": f"Bearer {self.api_key}"})
        resp.raise_for_status()
        data = resp.json()
        vectors = [_normalize(d["embedding"])
                   for d in sorted(data["data"], key=lambda d: d["index"])]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        return vectors, {"model": self.name, "tokens": tokens,
                         "usd": round(tokens / 1000 * self.usd_per_1k, 8)}


class HashEmbedder:
    def __init__(self, dim: int = 512):
        self.dim = dim
        self.name = f"hash-ngram-{dim}"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        text = re.sub(r"\s+", " ", text.lower())
        for n in (2, 3):
            for i in range(len(text) - n + 1):
                gram = text[i:i + n]
                if gram.strip():
                    h = int(hashlib.md5(gram.encode()).hexdigest(), 16)
                    vec[h % self.dim] += 1.0
        return _normalize(vec)

    async def embed(self, texts: list[str]) -> tuple[list[list[float]], dict]:
        return [self._vector(t) for t in texts], {"model": self.name, "tokens": 0, "usd": 0.0}
