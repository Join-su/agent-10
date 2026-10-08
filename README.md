# agent-10 — 캡스톤 과제 10 실습 자료

**제조 설비 이상 대응 지원 Agent.** ML 이 만든 이상 이벤트 카드(EventCard)를 받아 매뉴얼과
정비 이력에서 근거를 모으고, SOP 규칙으로 처리 경로를 정하고, 초안을 검사한 뒤 **사람 검토
앞에서 멈춥니다.** 정비 기술자가 결정하면 보고서를 만듭니다.

이 저장소는 `agent-workflow-lab-v2`(한화시스템 ICT STEP 03~06)에서 과제 10 부분만 떼어 낸
것입니다. 구조와 실행 방법은 v2 와 같습니다. **실제로 도는 앱 하나가 있고, 그 앱을 읽기 전에
앱에 쓰인 기법을 Notebook 으로 먼저 익힙니다.** 키 없이도 합성 데이터로 끝까지 돕니다.

| 문서 | 언제 |
|---|---|
| [`docs/running-the-app.md`](docs/running-the-app.md) | 띄우고 싶을 때 — fixture · live · Postgres · Docker |
| [`task10_maintenance/README.md`](task10_maintenance/README.md) | 앱·데이터·Notebook 을 자세히 볼 때 |
| [`task10_maintenance/docs/curriculum-plan.md`](task10_maintenance/docs/curriculum-plan.md) | 왜 이렇게 만들었는지, 실제로 잰 숫자 |

---

## 바로 시작하기

**DB 는 Postgres(pgvector 확장 포함) 하나입니다.** 매뉴얼 vector, 정비 이력, 검토 대기 건이 모두
여기 있습니다. Docker 로 DB 를 띄우고 한 번 적재한 뒤 앱을 띄웁니다. API 키는 필요 없습니다(fixture).

```bash
uv sync --frozen
cp .env.example .env
docker compose --env-file .env up -d db
uv run --env-file .env python scripts/task10/ingest_manuals.py
uv run --env-file .env python scripts/task10/load_history.py
uv run pytest -q
```

| 하고 싶은 것 | 명령 |
|---|---|
| API (fixture) | `uv run uvicorn task10_maintenance.app:app --port 8035 --env-file .env --loop task10_maintenance.loop:selector_loop_factory` |
| 화면 | `uv run streamlit run streamlit_app.py` → http://127.0.0.1:8501 |
| Notebook (DB 필요 없음) | `uv run jupyter lab task10_maintenance/notebooks` |
| 컨테이너로 한 번에 (DB·적재·API·화면) | `docker compose --env-file .env up -d --build` |

API 명령 끝의 `--loop task10_maintenance.loop:selector_loop_factory` 는 **Windows 에서 꼭 필요합니다**
(DB 연결 라이브러리가 Windows 기본 이벤트 루프를 거부합니다). macOS·Linux 에서도 같은 명령을 씁니다.

자세한 순서와 문제 해결은 [`docs/running-the-app.md`](docs/running-the-app.md).

## 공부하는 순서

1. **Notebook 01~12** — 앱의 처리 순서대로 기법을 하나씩 익힙니다.
2. **앱 코드** — `task10_maintenance/review.py` 의 그래프 그림부터 봅니다.
3. **화면** — 대표 사례 S01~S10 을 하나씩 처리하고, '평가' 탭에서 시스템 재현율을 봅니다.

| # | Notebook | 기법 |
|---|---|---|
| 01 | EventCard 와 판정 기준 | Pydantic 계약, ML 예측 ≠ 판정 |
| 02 | 절 단위로 자르기 | 머리말 분할, 절 번호 인용, PDF 구조 손실 |
| 03 | 임베딩 녹화와 재생 | 벡터 저장소, CacheBackedEmbeddings |
| 04 | 하이브리드 검색 | BM25 + 의미 검색, EnsembleRetriever |
| 05 | 시점 경계가 있는 조회 Tool | `@tool`, Literal enum, 읽기 전용 DB |
| 06 | 조회 Agent 와 실행 감사 | `create_agent`, 호출 상한, 기록 감사 |
| 07 | MCP 로 이력 Tool 열기 | FastMCP, 읽기 전용 목록 |
| 08 | 초안 체인과 인용 검증 | prompt \| model \| parser, 인용 검사 |
| 09 | 경로 분기와 재작성 | SOP 규칙, 조건 엣지, 횟수 상한 |
| 10 | 병렬 수집과 합치기 | 병렬 분기, reducer |
| 11 | 검토 멈춤과 다시 묻기 | interrupt · Command |
| 12 | 전체 흐름과 종단 평가 | 한 그래프, 시스템 재현율 |

## 선행 과정

`hanwha_0902` (Python 기초) → `agent-workflow-lab` (Pydantic·FastAPI·기본 RAG·LangGraph 기초)
→ `agent-workflow-lab-v2` (STEP 03~06) → **이 저장소**

STEP 03~06 에서 배운 기법도 이 앱을 이해하는 데 필요하면 설비 정비 상황으로 다시 다룹니다.

## 폴더

| 폴더 | 무엇 |
|---|---|
| `task10_maintenance/` | **과제 10** — 앱, Notebook 12개, 데이터, Test |
| `shared/` | 앱이 조립하는 공용 계층 — `rag`(검색), `tools`(Tool Agent·MCP), `graph`(멈춤·재개) |
| `app_pages/`, `streamlit_app.py` | 화면. API 를 HTTP 로만 부른다 |
| `scripts/task10/` | 데이터 생성·임베딩 녹화·DB 적재(매뉴얼 → pgvector, 정비 이력 → Postgres 표) |
| `scripts/build_notebooks.py`, `scripts/notebook_specs_task10.py` | Notebook 생성기와 내용 |
| `tests/` | 정본·Notebook·화면·컨테이너·보안 검사 |
| `Dockerfile`, `compose.yml` | 컨테이너 (db → init(적재) → task10 → ui) |

## 규칙

1. Notebook 1개 = 기법 1개. 문법만이 아니라 시나리오와 의미 있는 출력까지
2. `app.py` 는 진짜 동작 코드 — 화면, 실제 문서로 만든 검색, 실제 LLM 호출(live)
3. **Notebook 이 가르치는 기법은 앱에서 실제로 돈다**
4. **라이브러리가 제공하는 것을 손으로 만들지 않는다**
5. 판정은 코드가 하고 LLM 은 문장만 쓴다. 보고서는 사람이 결정해야 만들어진다

## 정본

`curriculum_manifest.yaml` 과 `notebook_contracts.yaml` 이 정본이다. 이 파일을 고치지 않고
Project·Endpoint·Symbol·Notebook 이름을 바꿀 수 없다. Test 가 막는다.

Notebook 은 손으로 고치지 않는다. `scripts/notebook_specs_task10.py` 를 고친 뒤 다시 생성한다.

```bash
uv run python scripts/build_notebooks.py
```

> 모든 데이터는 UCI AI4I 2020(CC BY 4.0)에서 파생한 **합성 데이터**입니다. 매뉴얼과 정비 이력은
> 학습용으로 만든 것이며 실제 설비의 절차나 기록이 아닙니다.
