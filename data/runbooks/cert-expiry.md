# Runbook: 인증서 만료(TLS Certificate Expiry) 대응 절차

- incident_type: cert-expiry
- 주요 증상: TLS/SSL 인증서가 만료됐거나 만료가 임박해 보안 연결(핸드셰이크)이 실패하고 HTTPS 접속이 거부된다.

1. get_monitoring_status로 핸드셰이크 실패 추이와 만료 예정 인증서의 도메인을 확인한다.
2. 인증서 관리 도구(ACM, cert-manager 등)에서 해당 도메인 인증서의 만료 일시와 자동 갱신 상태를 점검한다.
3. 자동 갱신이 실패했다면 인증서를 수동으로 재발급해 로드밸런서/인그레스에 교체 적용한다.
4. 중간 인증서 체인이 누락되지 않았는지 외부에서 openssl s_client로 검증한다.
5. 정상화 후 만료 30일·7일 전 알림을 추가하고 자동 갱신 실패 시 경보가 오도록 조정한다.
