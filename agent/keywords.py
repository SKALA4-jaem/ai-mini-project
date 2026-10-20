"""LLM 라우터가 실패했을 때(또는 fake 백엔드에서) 쓰는 incident 판별 키워드.

기존 정규식 `장애|진단|다운|지연|급증|incident|티켓`은 "느려요", "치솟았어요", "타임아웃",
"에러" 같은 가장 흔한 운영 표현을 못 잡아 장애 질의가 chat으로 새어 나갔다
(fake 백엔드 기준 회귀 쿼리 8개 중 7개 오분류). 세 백엔드가 이 한 곳을 공유한다.
"""
import re

INCIDENT_HINT_RE = re.compile(
    r"장애|진단|다운|지연|급증|incident|티켓"
    r"|느려|느립|느리|치솟|타임아웃|timeout|에러|오류|실패|안 ?돼|안 ?됩|끊|먹통"
    r"|죽|멈춰|멈췄|안 ?와|저하|부족|누수|폭증|과부하|응답이? ?없|원인|cpu|메모리|디스크|커넥션|인증서|5\d\d",
    re.IGNORECASE)


def looks_like_incident(query: str) -> bool:
    return bool(INCIDENT_HINT_RE.search(query))
