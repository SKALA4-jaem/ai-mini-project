# AI Mini-Project — 운영 인시던트 대응 에이전트 개선 (광주_1반_G030_최재은)

**선택 과제: 1번 — Base AI Agent 기능 개선/추가.** 베이스 프로그램 설명서는 [doc/README.md](doc/README.md)에 있어요.

## 무엇을 바꿨나

| 영역 | Before (베이스) | After |
|---|---|---|
| RAG | 전체 알림을 합쳐 키워드 1개로 incident_type 매핑, 매칭 실패 시 `db-down`으로 폴백 | runbook 청크를 임베딩하고 `incident_type`을 메타데이터로 저장. 저하된 시스템마다 의미 검색으로 runbook 결정 (`agent/rag/`, `agent/classifier.py`) |
| 하드코딩 | 시스템명이 없으면 무조건 `auth-service` | 시스템 카탈로그(`data/systems.json`)를 검색해 대상 결정. 미등록 시스템은 다른 시스템을 대신 조사하지 않고 "모니터링 대상 아님"으로 노출 |
| 모듈화 | `graph.py` 단일 파일, KNOWN_SYSTEMS 로더가 3곳에 중복 | `agent/nodes/` 역할별 모듈 + `agent/state.py`. `graph.py`는 배선만 담당 (52줄) |
| 검증 | 30자 이상이고 "1)"만 포함하면 합격 | 답변의 % 수치가 수집된 사실에 실제로 있는지 코드로 검사하고, 없으면 반려해 재작성 (최대 3회) |
| 데이터 | 시스템 6개, runbook 6종 | 시스템 3개(order/search/notification), runbook 2종(error-rate-spike, cert-expiry) 추가 |
| 평가 | 키워드 매칭만 | 라벨 데이터셋 24건 자동 평가와 LLM-as-judge (`eval/`) |
| 테스트 | 없음 | pytest 28개. 의존성 주입으로 MCP를 InMemoryMCP로 교체해 네트워크 없이 실행 (`tests/`) |

## Before / After (OpenAI gpt-4o-mini·gpt-4o, 같은 데이터셋 24건)

| 지표 | Before | After |
|---|---|---|
| 조사 대상 재현율 | 65.0% | 95.0% |
| 조사 대상 정밀도 | 65.8% | 100% |
| runbook 재현율 | 34.2% | 84.2% |
| runbook 정밀도 | 52.6% | 91.7% |
| 비용 (24건) | $0.0637 | $0.0680 |
| incident 판별 1회 지연 | 0.34ms (keyword) | 233ms (RAG) |

전체 비교: `python eval/compare.py openai-before openai-after-keyword openai-after-v1 openai-after`.
한계와 트레이드오프는 발표자료의 "05 · 한계" 장에 정리했어요. 실행 화면 캡처는 `doc/presentation/img/`에 있어요.

## 실행

```bash
bash sh/setup_venv.sh                 # 최초 1회
cp .env.example .env                  # OPENAI_API_KEY 입력
bash sh/run_agent_openai.sh           # 에이전트 :8100 (과금 확인 y)
bash sh/run_frontend.sh               # 채팅 UI http://localhost:8600

.venv/bin/python3 -m pytest -q        # 단위/통합 테스트 (네트워크·API 키 불필요)
.venv/bin/python3 eval/run_eval.py --help   # 평가 실행 옵션
```

개선 항목 토글 (`.env` 또는 환경변수): `INCIDENT_CLASSIFIER=keyword|rag`, `EMBEDDING_BACKEND=openai|hash`,
`VALIDATE_GROUNDING=0|1`, `RAG_MIN_SCORE`, `RESOLVER_MIN_SCORE`. 설명은 `.env.example`에 있어요.

## 문서

- 발표자료: [doc/presentation/AI_MiniProject_G030_최재은.pdf](doc/presentation/AI_MiniProject_G030_최재은.pdf)
- 진행 계획표: [doc/improvement_plan.md](doc/improvement_plan.md)
- 코드 설명서: [doc/presentation/코드설명.md](doc/presentation/코드설명.md)
