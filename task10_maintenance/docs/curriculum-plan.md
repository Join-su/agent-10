# 과제 10 학습 자료 — 구성 계획

v2(STEP 03~06)와 같은 구조로 과제 10 학습 자료를 만든다. **실제로 도는 앱 하나**가 있고, 그 앱을 읽기 전에 **기법 Notebook**으로 앱에 쓰인 기법을 먼저 익히며, 모든 것이 **합성 데이터로 끝까지 돈다.** 화면(Streamlit)과 컨테이너(compose)도 STEP 03~06 과 같은 방식으로 붙는다.

## 1. 확정한 결정 (2026-10-07)

| # | 결정 | 내용 |
|---|---|---|
| ① | 출력 계약 | 판정은 코드, 문장은 LLM. 경로는 `grounded_draft` / `escalation` / `inspect_only` 세 가지. 보고서는 사람 검토(approve·escalate) 뒤에만 만든다 |
| ② | 구성 | ~~한 도메인 안에서 4단계, 단계마다 앱~~ → **앱 하나 + Notebook 12개** (2026-10-08 재편, §3) |
| ③ | 대표 사례 | 실제 카드에서 경로별 10건을 고른다. 자연 데이터에 없는 조치 후 재발(ESC-5)만 맥락을 가정한다 |
| ④ | 놓친 고장 | Agent 입력에 넣지 않는다. 마지막 평가 Notebook에서 시스템 재현율을 보여 주는 데만 쓴다 |

v2 분석에서 채택한 보완점: **통합 Notebook**(12), **결과 해설과 직접 해 볼 과제**(모든 Notebook).

## 2. 왜 판정을 코드에 두는가

v2 Notebook 중 가장 잘 된 것은 가짜 데이터에서도 결과가 진짜인 것들이었다(Chunking, BM25 지표, Function Calling, 순환 그래프). 그래서 이 자료는 대본을 LLM 문장 하나로 줄인다.

실제로 돌려 본 결과 (EventCard 111장)

| 경로 | 장수 | 실제 고장 / 오탐 |
|---|---:|---|
| grounded_draft | 75 | HDF·PWF·OSF 59장은 전부 실제 고장. TWF 16장 중 12장이 오탐 |
| inspect_only | 19 | 전부 오탐 |
| escalation | 17 | ESC-2 복합 13, ESC-3 불일치 2, ESC-7 3 (일부 중복) |

- HDF·PWF·OSF는 판정 기준만으로 정탐과 오탐이 갈린다. AI4I가 조건식으로 만든 데이터이기 때문이다. **이것을 숨기지 않고 가르친다.** "규칙으로 되는 부분은 규칙으로" 하는 것이 Agent 설계의 첫 판단이다.
- TWF는 기준이 성립해도 고장이 아닐 수 있다. **사람 검토가 실제로 필요한 자리**가 여기다.

## 3. 구성 — 앱 하나 + Notebook (2026-10-08 재편)

처음에는 STEP 03~06 의 폴더 4개를 겉모양으로 따라 한 과제를 4단계(`stage1~4`)로 쪼갰고, 단계마다 앱이 생겼다(8041~8044). 그런데 STEP 03~06 의 구조는 **폴더 하나 = 완성된 앱 하나 + 그 앱의 기법 Notebook** 이다. 4단계 그래프가 이미 1~3단계를 모두 부르고 있었으므로 그것을 앱 본체로 삼고 단계 폴더를 걷어냈다.

| 무엇 | 어디 |
|---|---|
| 앱 | `task10_maintenance/app.py` 하나(8035). 본체 그래프 `review.py` |
| Notebook | `task10_maintenance/notebooks/` 12개. spec 은 `scripts/notebook_specs_task10.py` |
| 화면 | `app_pages/task10_maintenance.py` (통합 UI 메뉴 하나) |
| 컨테이너 | 루트 `Dockerfile`·`compose.yml` 의 `task10` 서비스 |
| 데이터 생성·적재 | `scripts/task10/` (앱 실행과 무관) |
| 정본 등록 | `curriculum_manifest.yaml`(`status: capstone`), `notebook_contracts.yaml` |

**STEP 03~06 기법의 중복을 허용한다.** 과제 10 은 나중에 별도 저장소로 옮겨 혼자 읽혀야 하므로, 앱을 이해하는 데 필요하면 STEP 03~06 기법도 설비 정비 상황으로 다시 다룬다. manifest 의 `revisits` 에 어떤 STEP 개념을 다시 다루는지 적었다. 개념 이름은 과제 10 상황에 맞춰 새로 붙여 "같은 개념을 두 프로젝트에서 도입하지 않는다" 검사는 그대로 둔다.

## 4. Notebook (12개)

앱의 처리 순서대로. Notebook 하나에 기법 하나, 완성된 앱을 import 하지 않고 `practice_` 연습 데이터로 직접 조립한다(데이터 파일은 02 의 PDF 하나만 읽는다). STEP 03~06 의 Notebook 계약(필수 머리말·assert·성공/실패 fixture·주석)을 그대로 따른다.

| # | Notebook | 기법 | 앱 | 다시 다루는 STEP |
|---|---|---|---|---|
| 01 | EventCard 와 판정 기준 | Pydantic 계약, 예측 ≠ 판정 | `domain.py`·`criteria.py` | — |
| 02 | 절 단위로 자르기 | 머리말 분할, 머리말 경로, 절 번호 인용, PDF 구조 손실 | `scripts/task10/ingest_manuals.py` | 03 |
| 03 | 임베딩 녹화와 재생 | FAISS, CacheBackedEmbeddings | `evidence.py` | 03 |
| 04 | 하이브리드 검색 | 카드 → 질의, BM25 + 의미, EnsembleRetriever | `evidence.py` | 04 |
| 05 | 시점 경계가 있는 조회 Tool | `@tool`, Literal enum, 시점 경계, 읽기 전용 | `tools.py` | 05 |
| 06 | 조회 Agent 와 실행 감사 | `create_agent`, 호출 상한, 기록 감사 | `lookup.py` | 05 |
| 07 | MCP 로 이력 Tool 열기 | FastMCP, 읽기 전용 목록, 오류가 글자로 옴 | `mcp_server.py` | 05 |
| 08 | 초안 체인과 인용 검증 | prompt \| model \| parser, 인용·단정 검사 | `drafting.py`·`routing.py` | 03·04 |
| 09 | 경로 분기와 재작성 | SOP 규칙, 조건 엣지, 횟수 상한 | `routing.py`·`review.py` | 06 |
| 10 | 병렬 수집과 합치기 | 병렬 분기, reducer, 중복 제거 | `review.py` | 06 |
| 11 | 검토 멈춤과 다시 묻기 | interrupt·Command, 예외로 막으면 굳음 | `review.py`·`app.py` | 06 |
| 12 | 전체 흐름과 종단 평가 (통합) | 한 그래프, 시스템 재현율 | `evaluation.py` | — |

모든 Notebook 끝에는 다음을 둔다.

- **결과 해설**: 방금 나온 출력이 왜 그렇게 나왔는지. 예상과 다른 출력(가짜 임베딩의 순위 등)은 반드시 설명한다.
- **직접 해 볼 과제**: 값을 바꿔 결과가 어떻게 달라지는지 확인하는 과제와, 정답을 확인하는 셀.

### (재편 전) 1단계에서 실제로 잰 것

| 측정 | 결과 | 어디서 |
|---|---|---|
| 글자 수로 자른 청크 중 절이 섞인 것 | 19개 중 17개 (머리말 기준은 0개) | 01 |
| 머리말 경로를 붙였을 때 BM25 가 놓친 유형 질의 | 126개 중 40 → 24 | 01 해설, 계획 수립 시 측정 |
| PDF 에서 숫자로 시작하는 줄 중 머리말이 아닌 것 | 105줄 중 59줄. 코드 `ESC-3` 이 줄바꿈에서 쪼개짐 | 02 |
| 코드 질의 / 상황 질의 정답 (9자리씩) | BM25 8 / 5 · 의미 검색 5 / 6 · 하이브리드 7 / 5 | 03 |
| 카드 질의에서 유형 절을 찾은 비율 | 126개 중 125개 (하이브리드). 놓친 1건은 근거 신호가 예측 유형 것뿐이라서 | 04, 테스트 |

**계획에서 바꾼 것 — 녹화된 실제 임베딩.** 계획에서는 의미 검색이 가짜 임베딩이라 "절반만 진짜"로 예상했다. v2 의 같은 약점(04-3)을 피하려고 실제 OpenAI 임베딩(text-embedding-3-small, 256차원)을 한 번 녹화해 저장소에 두었다(`data/index/recorded_embeddings/`, `CacheBackedEmbeddings`). 녹화에 없는 문장은 가짜로 넘어가지 않고 멈춘다. 매뉴얼이나 질의 규칙을 바꾸면 `build/record_embeddings.py` 로 다시 녹화한다.

### (재편 전) 2단계에서 실제로 잰 것

| 측정 | 결과 |
|---|---|
| 한 턴에 다 부를 때 / 턴을 나눌 때 빠진 이력 (S08) | TWF 빠짐 / 없음 |
| 이벤트 시점 조건을 빼고 과거 이벤트를 다시 돌릴 때 | 근거 3건이 모두 미래 기록 |
| 로컬 Tool 과 MCP 서버의 결과 | 같음 (테스트로 확인) |
| live(gpt-4.1-mini, S01·S08·S07) | 순서는 3건 모두 지킴. 필요한 이력 유형은 2건에서 하나씩 빠뜨림 → `missing_history_types` 가 잡음 |

**2단계에서 찾아 고친 결함**

- Tool 을 병렬로 부르자 SQLite 연결을 여러 스레드가 나눠 써서 실패했다. 조회마다 읽기 전용 연결을 열도록 `core/history.py` 를 고쳤다.
- 운영 기간(7월 말~9월)에 공구 교체 기록이 없어, 9월 이벤트의 "마지막 공구 교체"가 7월 이력 끝으로 나왔다(마모 20분짜리 공구와 어긋남). 운영 기간의 공구 교체 기록만 이력에 더했다. 고장 수리 기록은 정답과 겹쳐 넣지 않았다.
- MCP 는 서버 쪽 오류를 예외가 아니라 "Error executing tool …" 글자로 돌려준다. 상태만 보던 `read_run` 이 실패를 성공으로 셀 수 있었다. 결과 모양까지 확인하도록 고쳤다.

### (재편 전) 3단계에서 실제로 잰 것

| 측정 | 결과 |
|---|---|
| 재발(ESC-5)을 직전 경보로 셀 때 / 조치 완료로 셀 때 escalation | 70장 / 17장 |
| 사례 10건 경로 (그래프 끝까지) | 10건 모두 기대 경로·사유, 검사 통과 |
| live(gpt-4.1-mini) 초안 10건 | 10건 모두 첫 초안에서 검사 통과. 지어낸 ID·단정 표현 없음 |
| 검사를 통과했지만 틀린 초안 | S02(출력 과다)에 출력 부족 갈래의 단계(단자대·퓨즈)를 섞음. 같은 입력을 다시 돌리면 초안이 달라짐 |

**3단계 설계 결정**

- 경로·판정·근거·부품은 코드, LLM 은 grounded_draft 의 문장만. escalation·inspect_only 는 문장까지 코드가 쓰고 `drafted_by = code` 로 밝힌다(계약에 `code` 추가).
- 2단계 Agent 가 빠뜨린 이력은 3단계가 코드로 채우고 `filled_history_types` 에 남긴다.
- 판정 기준 절·점검 절차 절은 검색하지 않고 ID 로 가져온다. 검색이 놓쳐도 초안이 인용할 근거가 있어야 한다.
- 검사에 걸린 초안은 오류를 받고 한 번만 다시 쓴다(`MAX_ATTEMPTS = 2`). 형식이 깨진 출력도 같게 다룬다.

### (재편 전) 4단계에서 실제로 잰 것

| 측정 | 결과 |
|---|---|
| 재개 시 멈췄던 노드의 실행 횟수 | 2번 (처음부터 다시 돈다) |
| 받을 수 없는 결정을 예외로 막을 때 | 올바른 결정을 넣어도 같은 예외 — 건이 굳음 |
| 같은 경우를 다시 묻기로 처리할 때 | 거부 사유와 함께 다시 기다리고, 올바른 결정으로 끝남 |
| 두 담당을 동시에 / 차례로 (각 0.3초) | 0.31초 / 0.61초 |
| 시스템 재현율 (운영 기간 실제 고장 99건) | 74건(74.7%)만 Agent 에게 도달. 놓친 25건 중 TWF 10건 |
| 확신도별 실제 고장 비율 | high 100% · medium 92% · low 31% |
| 서버 재시작 (THREAD_DB) | 검토 대기 건을 재시작 뒤 이어 결정함 |
| live 끝까지 (EVT-2025-0015) | LLM 초안 검사 통과 → 승인 → 보고서 |

**4단계에서 찾아 고친 결함**

- review 노드가 받을 수 없는 결정을 예외로 막고 있었다. 앱이 재개 전에 막아서 드러나지 않았지만, 그래프를 바로 부르면 건이 굳는다. 다시 묻는 방식으로 고쳤다.
- 멈춘 상태를 저장소에 넣고 꺼낼 때 LangGraph 가 "등록되지 않은 타입, 다음 버전부터 차단"을 경고했다. `with_allowlist` 는 기본(관대) 모드에서 아무것도 바꾸지 않아, 허용 타입을 명시한 엄격 직렬화기를 단 저장소 사본을 쓴다(공용 저장소는 그대로).

## 5. v2 분석에서 가져온 주의

| v2에서 발견한 것 | 이 자료에서 |
|---|---|
| 05-3 MCP Notebook이 Jupyter에서 실패(`asyncio.run`) | 실제 Jupyter 커널로도 실행해 본다. 07 은 별도 스레드에서 돌려 Jupyter·Test 양쪽에서 돈다 |
| 05-2가 대본 결과를 "모델이 판단했다"고 설명 | 대본인 곳은 대본이라고 쓴다. `drafted_by` 필드가 응답에 그 사실을 남긴다 |
| 06-2에서 `ask` 노드가 두 번 실행되는데 설명 없음 | Notebook 11 에서 그 동작을 직접 센다 |
| 통합 Notebook이 기법 하나만 다룸 | 통합 Notebook(12)이 앞의 조각을 한 그래프로 잇는다 |
| 코드가 모두 완성되어 학습자가 손댈 곳이 없음 | 모든 Notebook에 직접 해 볼 과제 |

## 6. 대표 사례 (`data/eventcards/scenarios.jsonl`)

| 사례 | 경로 | 사유 | 정답 | 학습 포인트 |
|---|---|---|---|---|
| S01 | grounded_draft | — | 정탐 | HDF 두 조건 모두 성립 |
| S02 | grounded_draft | — | 정탐 | PWF 높은 확신, 출력 범위 이탈 |
| S03 | grounded_draft | — | 정탐 | OSF 부하 지수 초과 |
| S04 | grounded_draft | — | 정탐 | TWF 낮은 확신. 확률보다 마모 시간과 교체 기록 |
| S05 | grounded_draft | — | 오탐 | TWF 기준은 성립하나 고장 아님. 사람이 걸러야 함 |
| S06 | inspect_only | SOP-EA-01 8 | 오탐 | 어떤 기준에도 해당하지 않는 경고 |
| S07 | escalation | ESC-2 | 정탐 | 복합 후보(PWF + OSF) |
| S08 | escalation | ESC-3 | 오탐 | 예측 유형과 판정 불일치 |
| S09 | escalation | ESC-7 | 오탐 | 경보인데 기준 미해당 |
| S10 | escalation | ESC-5 | 정탐 | 조치 후 23시간 만에 재발 (조치 완료는 가정) |

ESC-4(근거 없음)는 데이터로 만들 수 없어 테스트에서 근거를 비워 확인한다. ESC-1·ESC-6은 현장 확인 사항이라 Agent가 판단하지 않는다.

## 7. 상태 (2026-10-08 재편 후)

| 항목 | 상태 |
|---|---|
| 앱 하나로 합치기 | **완료**. 과제 10 Test 91개 통과 |
| Notebook 12개 | **완료**. Test 의 위→아래 실행과 실제 Jupyter 커널 실행 모두 통과 |
| 화면(Streamlit) | **완료**. 카드 고르기 → 검토 대기 → 결정 → 보고서, 평가 탭. 화면 Test 통과 |
| 컨테이너 | `compose.yml` 의 `task10` 서비스(8035, 검토 대기 볼륨). `docker compose config` 통과, **이미지 빌드는 아직 안 해 봄** |
| 정본 등록 | manifest·contracts 등록, 과정 Test 통과 |
| live LLM 확인 | 재편 전에 2단계 3건·3단계 초안 10건·4단계 끝까지 1건. **재편 뒤에는 다시 돌리지 않음** |
| 별도 저장소로 이전 | v2 에서 검증한 뒤. `shared/` 와 루트 화면·컨테이너 뼈대를 함께 가져가야 한다 |

## 8. agent-10 — 팀원 공유용 독립 저장소 (2026-10-08)

v2 에서 과제 10 만 떼어 `agent-10` 으로 만들었다. 실행 방법(fixture · live · FastAPI · Streamlit · Docker compose)은 v2 와 같다. **이후 과제 10 은 agent-10 만 고친다.**

### DB 를 Postgres(pgvector) 하나로 통일 (2026-10-08 결정)

처음에는 v2 처럼 "설치 없이 도는 기본값(메모리 FAISS·SQLite)"과 "Postgres 선택"을 함께 두었다. 그러자 DB 종류가 FAISS·Chroma·SQLite·Postgres 로 늘어 팀원이 헷갈렸고, 현업에서도 한 역할에 저장소를 여러 개 바꿔 끼우지는 않는다. 그래서 **앱의 DB 를 Postgres 하나로 통일**했다. pgvector 는 Postgres 안의 확장이라 따로 세지 않는다.

| 데이터 | 전 | 후 |
|---|---|---|
| 매뉴얼 vector | 메모리 FAISS (선택 pgvector) | pgvector 표. `ingest_manuals.py` 가 녹화 임베딩으로 적재 |
| 정비 이력 | SQLite 파일 (선택 Postgres) | Postgres 표. `load_history.py` 가 **JSONL 원본**에서 적재(SQLite 파일은 지웠다) |
| 검토 대기 건 | 메모리 또는 SQLite 파일(`THREAD_DB`) | Postgres 표(`langgraph-checkpoint-postgres`) |

- 의존성: `langgraph-checkpoint-postgres` 추가, `langgraph-checkpoint-sqlite`·`langchain-chroma` 제거(하위 패키지 40개가 함께 빠졌다).
- 앱은 업무 데이터를 읽기만 한다. 정비 이력은 읽기 전용 세션(`default_transaction_read_only`)으로 연다.
- **Notebook 은 그대로 둔다(사용자 결정).** 03·04 의 메모리 vector 저장소, 05 의 임시 SQLite 는 기법을 작게 보여 주는 연습용이다. Notebook 은 DB 없이 돈다.
- Test 는 DB 가 필요하다. DB 가 없으면 건너뛰지 않고 안내와 함께 실패한다(앱의 유일한 저장소라, DB 없이 통과하면 아무것도 검사하지 않은 것이다). CI 도 같은 Postgres 이미지를 띄우고 적재한 뒤 돌린다.

| 확인한 것 (2026-10-08) | 결과 |
|---|---|
| 메모리(FAISS)와 pgvector 의 근거 비교, 카드 111장 (통일 전에 잼) | 절 집합은 모두 같음. 8장에서 순서만 다름(FAISS L2 와 pgvector 코사인의 근소한 차이) |
| 평가 (pgvector·Postgres) | 대표 사례 10건 통과, 시스템 재현율 74.7% — 통일 전과 같음 |
| JSONL 적재 | 정비 이력 410건 · 교체 부품 325행. SQLite 에서 옮겼을 때와 같음 |
| Test | DB 를 붙여 221 통과 |

### Windows 로컬 실행 (2026-10-08)

팀원이 Windows 에서 로컬 실행하자 "검토 대기 건 저장소를 열 수 없습니다 (InterfaceError)" 503 이 났다. Docker(Linux)와 macOS 에서는 나지 않았다. 원인: uvicorn 이 Windows 에서 기본으로 `ProactorEventLoop` 를 쓰고, psycopg 비동기 연결(검토 대기 건 저장소)이 그 루프를 거부한다. 고친 것:

- API 실행 명령에 `--loop task10_maintenance.loop:selector_loop_factory` 를 붙인다(모든 OS 같은 명령, Dockerfile·compose 포함)
- 503 메시지에 원인 문장과 고치는 명령을 넣었다(전에는 오류 종류만 보여 원인을 못 찾았다)
- Test 는 Windows 에서 Selector 루프 정책을 쓰고, MCP 서버를 띄우는 Test·Notebook 07 은 하위 Process 용 루프를 직접 고른다
- 제약: Windows 로컬 실행에서는 `MCP_MODE=on` 불가(Selector 루프는 하위 Process 를 못 띄움). 앱이 이유를 담은 503 을 낸다. Docker 에서는 된다
- Windows 에서 실제로 풀리는지는 이 저장소의 CI(Linux)로 확인할 수 없다. 원인과 해결은 psycopg·uvicorn 코드로 확인했다
