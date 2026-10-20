# AI Mini-Project 진행 계획 — 광주_1반_G030_최재은

**선택 과제: 1번 — Base AI Agent 기능 개선/추가**

| 순번 | 영역 | 무엇을 바꾸나 | 추가 설명 | 상태 |
|---|---|---|---|---|
| 1 | RAG | Keyword 기반 incident_type 매핑 → RAG 기반 의미 검색 | runbook을 요약/절차 청크로 나눠 임베딩(text-embedding-3-small)하고 metadata에 incident_type을 저장. 저하된 시스템마다 알림 문장으로 검색해 시스템별 runbook을 조회(기존: 전체 알림을 합쳐 첫 키워드 1개만, 미매칭 시 db-down 폴백). 인덱스는 코퍼스 해시로 디스크 캐시 | 완료 |
| 2 | RAG | 시스템명 미언급 질의 해석 (하드코딩 개선) | "로그인이 느려요"처럼 시스템명이 없으면 시스템 카탈로그(data/systems.json) 검색으로 대상 결정(기존: 무조건 auth-service). 목록에 없는 시스템(billing-service)은 다른 시스템을 대신 조사하지 않고 "모니터링 대상 아님"을 그대로 노출 | 완료 |
| 3 | 모듈화 | graph.py 단일 파일 → agent/nodes/ 역할별 모듈 | routing/planning/research/analysis/writing + state.py. 3곳에 복붙된 KNOWN_SYSTEMS 로더를 agent/systems.py로 단일화, 라우팅 fallback 키워드를 agent/keywords.py로 공통화 | 완료 |
| 4 | 그래프 개선 | Validator 근거 검증(grounding) | 답변의 % 수치가 수집된 사실(모니터링·runbook)에 실제로 있는지 코드로 검사, 없으면 반려·재작성 (기존: 30자 이상 + "1)" 포함만 검사) | 완료 |
| 5 | 데이터 보강 | 신규 시스템 3종 + 신규 장애유형 2종 | order/search/notification-service, error-rate-spike·cert-expiry runbook. 키워드 규칙은 코드 수정 없이는 새 유형을 인식 못 함 → RAG는 .md 추가만으로 인식 | 완료 |
| 6 | 평가 | 라벨 데이터셋 기반 자동 평가 + LLM-as-judge | eval/dataset.jsonl 24건(base/natural/extended/chat). route·target·runbook 정확도, 근거 없는 수치 비율, 지연, 비용, 재작성 횟수 + gpt-4o-mini 채점 | 완료 |
| 7 | 테스트 | pytest 단위/통합 테스트 | DI 구조를 활용해 MCP를 InMemoryMCP로 교체 — 네트워크 없이 노드·그래프 검증 (28개) | 완료 |
| 8 | 그래프 개선 (선택) | Human-in-the-loop 승인 노드 | 재시작·롤백 등 위험 조치 포함 시 LangGraph interrupt()로 승인 요청 | Day2 예정 |

**Before/After 측정 방법**: 개선 전 원본(`../baseline_original`, 데이터만 보강본으로 교체)과 개선 후 코드를
같은 데이터셋·같은 백엔드(OpenAI gpt-4o-mini/gpt-4o)로 실행해 `eval/results/*.json`으로 비교.
INCIDENT_CLASSIFIER / VALIDATE_GROUNDING 토글로 항목별 기여도(ablation)도 분리 측정.

## 실측 결과 (OpenAI, 24건, 1회 실행)

| 지표 | Before | After |
|---|---|---|
| 조사 대상 재현율 | 65.0% | 95.0% |
| runbook 재현율 | 34.2% | 84.2% |
| runbook 정밀도 | 52.6% | 91.7% |
| LLM-judge 조치 적합도 | 4.84 | 5.00 |
| 비용(24건) | $0.0637 | $0.0680 |
| RAG 판별 1회 지연 | 0.34ms(keyword) | 233ms |

전체 표: `python eval/compare.py openai-before openai-after-keyword openai-after-v1 openai-after`
발표자료: `doc/presentation/AI_MiniProject_G030_최재은.pdf` (재생성: `python doc/presentation/build_slides.py`)
