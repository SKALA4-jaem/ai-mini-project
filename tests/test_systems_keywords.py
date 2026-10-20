from agent.keywords import looks_like_incident
from agent.systems import DEFAULT_SYSTEM, KNOWN_SYSTEMS, find_mentioned_systems, guess_target, guess_targets


def test_known_systems_follow_monitoring_json():
    assert {"auth-service", "payments-service", "order-service"} <= KNOWN_SYSTEMS


def test_find_mentioned_systems_keeps_order():
    q = "gateway-service에서 payments-service로 가는 요청이 타임아웃"
    assert find_mentioned_systems(q) == ["gateway-service", "payments-service"]


def test_guess_falls_back_to_default():
    assert guess_target("로그인이 느려요") == DEFAULT_SYSTEM
    assert guess_targets("로그인이 느려요") == [DEFAULT_SYSTEM]


def test_routing_keywords_catch_common_symptoms():
    # 기존 정규식이 놓치던 표현들 (fake 백엔드 기준 chat으로 오분류되던 회귀 쿼리)
    for q in ["결제 응답이 느려지고 CPU가 치솟았어요", "요청이 타임아웃 나고 있어요",
              "로그인 응답이 느려요", "검색이 자꾸 죽어요", "500 에러가 떠요"]:
        assert looks_like_incident(q), q


def test_routing_keywords_leave_small_talk():
    for q in ["안녕, 너는 누구야?", "오늘 점심 뭐 먹을까?", "제 이름은 민수입니다"]:
        assert not looks_like_incident(q), q


def test_describe_metrics_hides_placeholder_for_unknown_system():
    from agent.systems import describe_metrics
    assert describe_metrics({"status": "degraded", "cpu_percent": 91.3, "memory_percent": 40.0}) \
        == "CPU 91.3%, 메모리 40.0%"
    assert "0.0" not in describe_metrics({"status": "unknown", "cpu_percent": 0.0, "memory_percent": 0.0})
