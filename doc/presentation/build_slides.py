"""발표자료 생성기 — eval/results/*.json 수치를 읽어 HTML 슬라이드를 만들고 Chrome으로 PDF 출력.

    .venv/bin/python3 doc/presentation/build_slides.py
    → doc/presentation/slides.html, doc/presentation/AI_MiniProject_G030_최재은.pdf
"""
import html
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RESULTS = ROOT / "eval" / "results"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PDF_NAME = "AI_MiniProject_G030_최재은.pdf"

BEFORE, AFTER = "openai-before", "openai-after"


def load(label):
    path = RESULTS / f"{label}.json"
    return json.loads(path.read_text()) if path.exists() else None


B, A = load(BEFORE), load(AFTER)
BENCH = json.loads((RESULTS / "bench_classifier.json").read_text())


def m(report, key, scope=None):
    if report is None:
        return None
    src = report["by_set"].get(scope, {}) if scope else report["summary"]
    return src.get(key)


def pct(v):
    return "-" if v is None else f"{v * 100:.0f}%"


def num(v, d=2):
    return "-" if v is None else f"{v:.{d}f}"


def delta(b, a, kind="pct", lower_better=False):
    if b is None or a is None:
        return ""
    diff = a - b
    good = diff < 0 if lower_better else diff > 0
    if abs(diff) < 1e-9:
        return '<span class="d flat">±0</span>'
    text = (f"{diff * 100:+.0f}%p" if kind == "pct" else f"{diff:+.4f}" if kind == "num4"
            else f"{diff:+.2f}")
    return f'<span class="d {"up" if good else "down"}">{text}</span>'


def bars(rows, max_value=1.0, fmt=pct):
    """rows: [(label, before, after)] → 가로 막대 SVG (Before 회색 / After 강조색)."""
    width, label_w, bar_w, row_h = 1060, 230, 700, 62
    height = row_h * len(rows) + 30
    out = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">']
    for i, (label, b, a) in enumerate(rows):
        y = 10 + i * row_h
        out.append(f'<text x="0" y="{y + 24}" class="cl">{html.escape(label)}</text>')
        for j, (val, cls) in enumerate(((b, "bb"), (a, "ba"))):
            w = 0 if val is None else max(2, bar_w * val / max_value)
            yy = y + j * 24
            out.append(f'<rect x="{label_w}" y="{yy}" width="{w:.1f}" height="20" rx="3" class="{cls}"/>')
            out.append(f'<text x="{label_w + w + 8:.1f}" y="{yy + 15}" class="cv {cls}t">{fmt(val)}</text>')
    out.append("</svg>")
    return "".join(out)


def slide(body, cls=""):
    return f'<section class="slide {cls}">{body}<div class="foot">광주_1반_G030_최재은 · AI Mini-Project</div></section>'


def header(kicker, title):
    return f'<div class="kicker">{kicker}</div><h2>{title}</h2>'


SLIDES = []


def shot(src, caption, cls=""):
    return f'<figure class="shot {cls}"><img src="img/{src}"><figcaption>{caption}</figcaption></figure>'


def ui(name, caption):
    """채팅 UI 캡처를 '진행 단계'(확대)와 '답변'으로 나눠 배치 — 슬라이드에서 글씨가 읽히도록."""
    return (f'<figure class="shot ui"><figcaption>{caption}</figcaption>'
            f'<img class="steps" src="img/ui-{name}-steps.png"><img class="ans" src="img/ui-{name}-ans.png"></figure>')


# 0. 표지
SLIDES.append(f'''<section class="slide cover">
  <div class="cover-kicker">SKALA AI Mini-Project · 과제 1 (Base AI Agent 개선)</div>
  <h1>장애 대응 에이전트,<br>키워드에서 의미 검색으로</h1>
  <p class="cover-sub">RAG 기반 runbook 판별 · 하드코딩 제거 · 근거 검증 · 모듈화 · 자동 평가</p>
  <div class="cover-meta">광주_1반_G030_최재은 &nbsp;|&nbsp; 2026.10.22</div>
</section>''')

# 1. 주제
SLIDES.append(slide(header("01 · 주제", "운영 인시던트 대응 에이전트") + '''
<p class="lead">운영자가 장애 증상을 채팅으로 물으면, 에이전트가 <b>모니터링 지표</b>와 <b>대응 매뉴얼(runbook)</b>을 직접 조사해 번호 절차로 조치를 답한다.</p>
<div class="pipe">
  <span>route<small>잡담/장애</small></span><i>→</i><span>plan<small>MCP Prompt</small></span><i>→</i><span>gate</span><i>→</i>
  <span>research<small>MCP Tool·Resource</small></span><i>⇄</i><span class="hl">replan_check<small>runbook 판별</small></span><i>→</i>
  <span>analysis</span><i>→</i><span>write</span><i>⇄</i><span class="hl">validate</span><i>→</i><span>finalize</span>
</div>
<div class="grid2">
  <div><h3>베이스 구성</h3><ul>
    <li>FastAPI + LangGraph StateGraph, SSE 스트리밍, Vue 채팅 UI</li>
    <li>MCP 서버 2개(ops/docs) — 모니터링 Tool, runbook Resource, 진단 Prompt</li>
    <li>LLM: OpenAI gpt-4o-mini(판단) / gpt-4o(답변 작성)</li></ul></div>
  <div><h3>직접 돌려보며 찾은 약점</h3><ul>
    <li>runbook을 <b>키워드 첫 매칭 1개</b>로 선택, 모르는 표현은 전부 <b>db-down</b></li>
    <li>시스템명이 없으면 <b>무조건 auth-service</b> 진단</li>
    <li>검증은 "30자 이상 + 1) 포함"만 확인</li>
    <li>graph.py 단일 파일, 중복 코드 3곳, 테스트 0개</li></ul></div>
</div>'''))

# 2. 개선·추가 포인트
SLIDES.append(slide(header("02 · 기능 개선 및 추가 포인트", "무엇을 바꾸고 무엇을 더했나") + '''
<table class="t">
<tr><th>구분</th><th>항목</th><th>Before → After</th><th>위치</th></tr>
<tr><td><span class="tag up">개선</span></td><td><b>RAG 기반 incident 판별</b></td><td>키워드 첫 매칭 1개 → runbook 임베딩 의미 검색, 저하된 시스템마다 판별</td><td><code>agent/rag/</code> <code>classifier.py</code></td></tr>
<tr><td><span class="tag up">개선</span></td><td><b>하드코딩 제거</b></td><td>시스템명 없으면 auth-service → 시스템 카탈로그 검색, 미등록 시스템은 "모니터링 대상 아님"</td><td><code>nodes/planning.py</code></td></tr>
<tr><td><span class="tag up">개선</span></td><td><b>근거 검증</b></td><td>형식만 검사 → 답변의 % 수치가 수집된 사실에 있는지 코드로 검사, 없으면 재작성</td><td><code>nodes/writing.py</code></td></tr>
<tr><td><span class="tag up">개선</span></td><td><b>모듈화</b></td><td>graph.py 단일 파일 → 역할별 5개 모듈, 3곳 중복 코드 단일화</td><td><code>agent/nodes/</code> <code>systems.py</code></td></tr>
<tr><td><span class="tag add">추가</span></td><td><b>데이터 보강</b></td><td>시스템 3종, 장애유형 2종(에러율 급증·인증서 만료), 시스템 카탈로그</td><td><code>data/</code></td></tr>
<tr><td><span class="tag add">추가</span></td><td><b>자동 평가</b></td><td>라벨 24건 — 검색 정확도·지연·비용·retry + LLM-as-judge</td><td><code>eval/</code></td></tr>
<tr><td><span class="tag add">추가</span></td><td><b>단위 테스트</b></td><td>28개, 가짜 MCP 주입으로 네트워크 없이 1초</td><td><code>tests/</code></td></tr>
</table>'''))

# 2-1. RAG 상세
SLIDES.append(slide(header("02 · 핵심 개선", "runbook 판별: 키워드 규칙 → 의미 검색") + '''
<div class="grid2">
<div><h3>Before — KeywordIncidentClassifier</h3>
<pre>text = 모든 시스템 알림을 한 문자열로 합침
for kw, type in RULES:      # latency, pool, cpu ...
    if kw in text: return [type]   # 첫 매칭 1개
return ["db-down"]          # 그 외 전부</pre>
<h3>After — RagIncidentClassifier</h3>
<pre>probes = [시스템별 알림 문장]  (없으면 사용자 질문)
hits = kb.search(probes, kind="runbook", k=1)  # 임베딩 1회 batch
→ 시스템마다 top-1 청크의 metadata.incident_type
→ 중복 제거, 최대 3개 runbook을 MCP Resource로 조회</pre></div>
<div><h3>지식베이스 (agent/rag)</h3><ul>
<li>runbook 8종 → <b>요약 청크</b> + <b>절차 청크</b>, metadata에 incident_type</li>
<li>text-embedding-3-small, 코사인 검색 (청크 55개라 외부 벡터DB 없이 구현)</li>
<li>인덱스 디스크 캐시: 키 = (임베더, 코퍼스 해시) → 재기동 시 비용 0, runbook 수정 시 자동 재색인</li>
<li>새 장애 유형 = <b>.md 파일 추가만</b> (코드 수정 없음)</li>
<li><code>INCIDENT_CLASSIFIER=keyword|rag</code> 토글 → 같은 코드로 A/B 측정</li></ul></div>
</div>'''))

# 3. 기술 요소
SLIDES.append(slide(header("03 · 사용한 기술 요소", "기술 요소별 적용 내용") + '''
<table class="t tech">
<tr><th>기술</th><th>상태</th><th>이번 과제에서 한 일</th></tr>
<tr><td><b>RAG</b></td><td><span class="tag add">신규</span></td><td>runbook·시스템 카탈로그 임베딩 검색. 검색 결과의 <b>메타데이터(incident_type)</b>만 쓰고 본문은 MCP로 조회</td></tr>
<tr><td><b>MCP</b></td><td><span class="tag up">확장</span></td><td>Tool(모니터링)·Resource(runbook)·Prompt(진단 절차) 실호출. 보강한 시스템·runbook을 MCP 서버 데이터로 추가</td></tr>
<tr><td><b>의존성 주입</b></td><td><span class="tag up">확장</span></td><td><code>SupervisorDeps</code>에 판별기·시스템 해석기·검증 토글 추가 → 환경변수로 교체, 테스트에서 가짜 MCP 주입</td></tr>
<tr><td><b>모듈화</b></td><td><span class="tag add">신규</span></td><td>graph.py는 배선만(52줄), 노드는 <code>agent/nodes/</code> 5개 파일, RAG는 <code>agent/rag/</code> 3계층</td></tr>
<tr><td><b>단위 테스트</b></td><td><span class="tag add">신규</span></td><td>pytest 28개 — 노드·RAG·그래프 전체 경로, 무한 루프 방지·미등록 시스템 처리</td></tr>
<tr><td><b>Multi-Agent</b></td><td><span class="tag keep">기존 활용</span></td><td>Supervisor 그래프가 계획→조사→분석→작성→검수 역할에 task 분배, 판단(mini)·작성(4o) 모델 분리. RAG 판별기를 조사 단계에 연결</td></tr>
<tr><td><b>LangSmith</b></td><td><span class="tag keep">기존 유지</span></td><td>모든 노드·LLM 호출에 <code>@traceable</code>. API 키가 없어 실측은 자체 평가 도구(eval/)로 지연·비용·정확도를 기록</td></tr>
</table>'''))

# 3-1. 구현 화면 ①
SLIDES.append(slide(header("03 · 구현 기능 화면 ①", "RAG 판별 — 시스템명 없는 질문, 신규 장애유형") + '<div class="grid2 shots">' +
    ui("after-1", "“로그 저장 서버 용량이 꽉 찼대요” → 카탈로그 검색으로 <b>log-service</b>, RAG 판별로 <b>disk-full</b>") +
    ui("after-2", "“order-service 배포하고 나서 에러가 엄청 나요” → 신규 runbook <b>error-rate-spike</b> (rag 판별)") +
    '</div>'))

# 3-2. 구현 화면 ②
SLIDES.append(slide(header("03 · 구현 기능 화면 ②", "미등록 시스템 처리 · 단위 테스트") + '<div class="grid2 shots">' +
    ui("after-3", "“billing-service 응답이 느려요” → 다른 시스템을 대신 진단하지 않고 <b>모니터링 대상 아님</b>, runbook 생략") +
    shot("term-pytest.png", "<code>pytest -v</code> — 28 passed, 0.9초 (네트워크·API 키 없이 실행)", "tall") +
    '</div>'))

# 3-3. 최종 실행 화면
SLIDES.append(slide(header("03 · 최종 실행 화면", "OpenAI 백엔드 + Vue 채팅 UI (localhost:8600)") + '<div class="final">' +
    shot("ui-after-1.png", "채팅 UI — 진행 단계(계획·조사·RAG 판별·검수)가 SSE로 실시간 표시") +
    shot("term-health.png", "서버 상태 — <code>incident_classifier: rag</code>, 청크 55개, 인덱스 캐시 사용") +
    '</div>'))

# 4-1, 4-2. 같은 입력 Before / After 화면
for before, after, query, b_note, a_note in [
        ("before-1", "after-1", "로그 저장 서버 용량이 꽉 찼대요",
         "auth-service를 조사하고 high-latency runbook으로 <b>엉뚱한 진단</b>",
         "log-service · disk-full — 디스크 정리 절차로 답변"),
        ("before-2", "after-2", "order-service 배포하고 나서 에러가 엄청 나요",
         "키워드 미매칭 → <b>db-down</b> 폴백, DB failover 권고",
         "RAG가 <b>error-rate-spike</b> 판별 → 직전 버전 롤백 권고")]:
    SLIDES.append(slide(header("04 · Before / After — 같은 입력", f"“{query}”") + '<div class="grid2 shots">' +
        ui(before, f'<span class="tag keep">Before 원본</span> {b_note}') +
        ui(after, f'<span class="tag add">After</span> {a_note}') + '</div>'))


# 4-3. 수치
def card(label, b, a, unit_note):
    return f'<div class="mcard"><div class="ml">{label}</div><div class="mv">{b} → <b>{a}</b></div><div class="mn">{unit_note}</div></div>'


SLIDES.append(slide(header("04 · Before / After — 수치", "같은 24건, 같은 모델로 실측") + '<div class="nums">' +
    shot("term-compare.png", "<code>eval/compare.py</code> 실행 결과 (가운데 열 = RAG만 끈 ablation)") +
    '<div class="mcards">' +
    card("검색 정확도 · runbook 재현율", pct(m(B, "type_recall")), pct(m(A, "type_recall")), f'정밀도 {pct(m(B, "type_precision"))} → {pct(m(A, "type_precision"))}') +
    card("조사 대상 재현율", pct(m(B, "target_recall")), pct(m(A, "target_recall")), f'정밀도 {pct(m(B, "target_precision"))} → {pct(m(A, "target_precision"))}') +
    card("장애 질의 평균 지연", f'{num(m(B, "latency_s_incident_mean"))}s', f'{num(m(A, "latency_s_incident_mean"))}s', f'RAG 판별 1회 +{BENCH["rag_classify_ms_median"]:.0f}ms (편차 범위)') +
    card("비용 (24건)", f'${num(m(B, "cost_usd_total"), 4)}', f'${num(m(A, "cost_usd_total"), 4)}', f'+{(m(A, "cost_usd_total") / m(B, "cost_usd_total") - 1) * 100:.1f}% (runbook을 더 많이 읽음)') +
    card("retry · 재작성", f'{m(B, "retry_total")} · {num(m(B, "validation_attempts_mean"))}', f'{m(A, "retry_total")} · {num(m(A, "validation_attempts_mean"))}', 'MCP 재시도 횟수 · 평균 작성 시도') +
    '</div></div>'))

# 4-4. 세트별 + 비용 벤치
SLIDES.append(slide(header("04 · Before / After — 세트별", "어디서 좋아졌고, 그 대가는 얼마인가") + '''
<div class="legend"><span class="lb"></span>Before <span class="la"></span>After</div>''' + bars([
    ("natural · runbook", m(B, "type_recall", "natural"), m(A, "type_recall", "natural")),
    ("extended · runbook", m(B, "type_recall", "extended"), m(A, "type_recall", "extended")),
    ("natural · 조사 대상", m(B, "target_recall", "natural"), m(A, "target_recall", "natural")),
    ("extended · 조사 대상", m(B, "target_recall", "extended"), m(A, "target_recall", "extended")),
]) + f'''
<div class="grid3 tight">
  <div class="card"><div class="mid">{BENCH["rag_classify_ms_median"]:.0f} ms</div><div class="cap">RAG 판별 1회 중앙값 (p90 {BENCH["rag_classify_ms_p90"]:.0f}ms) · 키워드 {BENCH["keyword_classify_ms_median"]}ms</div></div>
  <div class="card"><div class="mid">${BENCH["rag_classify_usd_mean"]:.7f}</div><div class="cap">판별 1회 임베딩 비용 — 질의당 LLM 비용(약 $0.003) 대비 무시 가능</div></div>
  <div class="card"><div class="mid">{pct(m(load("openai-after-keyword"), "type_recall"))}</div><div class="cap">RAG만 끄면 runbook 재현율이 원본과 같음 → 개선분은 전부 RAG 기여</div></div>
</div>'''))

# 5-1. 실패 사례
SLIDES.append(slide(header("05 · 한계", "실측에서 드러난 실패 사례") + '''
<table class="t">
<tr><th>사례</th><th>무슨 일이 있었나</th><th>원인 · 조치</th></tr>
<tr><td>게이트웨이 504<br>(B04 · N03)</td><td>"upstream timeout (504)"을 <b>error-rate-spike</b>로 판별 — 정답은 network-timeout</td><td>임베딩이 "504"를 5xx 에러와 가깝게 봄. runbook 문구를 평가셋에 맞추면 과적합이라 <b>고치지 않고 기록</b> → hybrid 검색 과제</td></tr>
<tr><td>billing-service<br>(After v1)</td><td>미등록 시스템에 질문 문장만으로 runbook을 붙여 <b>없는 서비스에 롤백 권고</b></td><td>평가로 발견 → 조사 대상이 전부 미등록이면 runbook 생략, 테스트 추가 (정밀도 86.8→91.7%)</td></tr>
<tr><td>"푸시 알림이<br>하나도 안 와요"</td><td>gpt-4o-mini 라우터가 잡담으로 분류 — Before/After 동일</td><td>라우팅은 이번 개선 범위 밖. 라우터 few-shot 보강 여지</td></tr>
<tr><td>근거 없는 수치</td><td>Before/After 모두 0건 — gpt-4o는 수치를 지어내지 않음</td><td>grounding 검증 효과는 <b>실측 불가</b>, 단위 테스트로만 확인. 소형 로컬 모델로 재측정 필요</td></tr>
<tr><td>LLM-judge</td><td>틀린 runbook을 쓴 답변에도 5점 — 점수가 천장에 붙음</td><td>정답 라벨 기반 지표(재현율·정밀도)를 주 지표로 사용</td></tr>
</table>'''))

# 5-2. 트레이드오프 + 다음 단계
SLIDES.append(slide(header("05 · 한계 및 트레이드오프", "개선이 새로 만든 약점") + '''
<table class="t compact">
<tr><th>영역</th><th>새 약점</th><th>대응 / 현재 상태</th></tr>
<tr><td>지연·비용</td><td>장애 질의마다 임베딩 호출 추가 (판별 1회 + 시스템 해석 최대 1회)</td><td>시스템 여러 개를 1회 batch로 묶고 인덱스 캐시. 비용은 무시 가능하나 왕복 약 230ms는 남음</td></tr>
<tr><td>임계값</td><td>top-1을 항상 채택 → 엉뚱한 질문도 가장 가까운 runbook에 억지 매칭</td><td>RAG_MIN_SCORE 제공(기본 0) — 라벨 데이터로 보정 필요</td></tr>
<tr><td>임베딩 의존</td><td>오프라인 hash 임베더는 영어 알림↔한국어 runbook 매칭 실패</td><td>임베딩 품질이 곧 판별 품질 — 다국어 로컬 임베딩으로 교체 여지</td></tr>
<tr><td>루프 안전성</td><td>runbook 여러 개 조회 · 반려 시 재작성 → 루프 경로 증가</td><td>replan 1라운드, runbook 최대 3개, 재작성 최대 3회 상한</td></tr>
<tr><td>평가셋</td><td>24건 · 본인 라벨링 · 1회 실행 — 통계적으로 약함</td><td>runbook에 알림 원문을 넣지 않아 누출 방지. 반복 실행·제3자 라벨 필요</td></tr>
</table>
<h3 class="next">다음 단계</h3>
<p class="nextp">Human-in-the-loop 승인(<code>interrupt()</code>) · research를 전문 서브에이전트로 분리(Multi-Agent) · LangSmith 추적 연결 · hybrid 검색(BM25 + 임베딩)</p>'''))

SLIDES.append('''<section class="slide cover end"><h1>감사합니다</h1>
<p class="cover-sub">코드 · 평가 결과 · 문서: all_total_vue_student (README.md, eval/results, doc/)</p>
<div class="cover-meta">광주_1반_G030_최재은</div></section>''')

CSS = (HERE / "slides.css").read_text()
HTML = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>AI Mini-Project 발표</title>
<style>{CSS}</style></head><body>{"".join(SLIDES)}</body></html>'''


def main():
    out_html = HERE / "slides.html"
    out_html.write_text(HTML)
    out_pdf = HERE / PDF_NAME
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={out_pdf}", out_html.as_uri()],
                   check=True, capture_output=True)
    print(out_pdf)


if __name__ == "__main__":
    main()
