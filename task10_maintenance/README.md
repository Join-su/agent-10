# 과제 10 — 제조 설비 이상 대응 지원 Agent

캡스톤 과제 10 을 주제로 한 학습 자료입니다. `agent-workflow-lab-v2`(STEP 03~06)와 같은 구조입니다. **실제로 도는 앱이 하나 있고, 그 앱을 읽기 전에 앱에 쓰인 기법을 Notebook 으로 먼저 익힙니다.** 키 없이도 합성 데이터로 끝까지 돕니다.

```
ML 이상 이벤트 카드(EventCard)
  → [매뉴얼 근거 검색 ∥ 정비 이력 조회(Tool·MCP)]   병렬로 모음
  → 합치기 → 판정 기준 대조 → 처리 경로(grounded_draft · escalation · inspect_only)
  → (grounded_draft 만) LLM 초안 → 인용 검사 → 틀리면 한 번 더
  → 사람 검토 앞에서 멈춤 → 승인·수정 요청·상위 보고·반려 → 정비 보고서
```

## 시작하기

```bash
uv sync --frozen
uv run python -m pytest task10_maintenance/tests -q                  # 과제 10 Test
uv run jupyter lab task10_maintenance/notebooks                      # Notebook 01 부터
uv run uvicorn task10_maintenance.app:app --port 8035 --env-file .env
uv run streamlit run streamlit_app.py                                # 화면: 메뉴의 '과제 10 · 설비 이상 대응'
docker compose --env-file .env up -d --build                         # 또는 컨테이너로 한 번에 (Postgres·API 8035·화면 8501)
```

권하는 순서: **Notebook 01~12 → 앱 코드(`review.py` 의 그래프 그림부터) → 화면에서 대표 사례 S01~S10 처리.** Notebook 끝의 "실제 app 연결"이 앱의 어느 코드가 같은 기법을 쓰는지 알려 줍니다.

| 모드 | 무엇이 진짜인가 |
|---|---|
| 기본(키 없음) | 판정·경로·이력·검사·멈춤 전부 진짜. 매뉴얼 의미 검색은 **녹화된 실제 임베딩**이라 순위도 진짜. 이력 Agent 가 무엇을 부를지 고르는 것과 초안 문장만 정해진 규칙(`drafted_by = fixture_script`) |
| `APP_MODE=live` | 임베딩·Tool 선택·초안 문장을 실제 OpenAI 가 맡는다 (비용 발생) |
| `MCP_MODE=on` | 정비 이력 Tool 을 별도 Process(MCP 서버)에서 가져온다 |
| `THREAD_DB=경로` | 검토 대기 건이 서버 재시작을 넘긴다 (compose 는 기본으로 켠다) |
| `VECTOR_BACKEND=pgvector`, `HISTORY_BACKEND=postgres` | 매뉴얼 vector 와 정비 이력을 Postgres 에서 읽는다 (선택, compose 는 기본으로 켠다). 적재는 `scripts/task10/ingest_manuals.py --backend pgvector`, `scripts/task10/load_history.py` |

> 모든 데이터는 UCI AI4I 2020(CC BY 4.0)에서 파생한 **합성 데이터**입니다. 매뉴얼과 정비 이력은 학습용으로 만든 것이며 실제 설비의 절차나 기록이 아닙니다. ML 단계는 학습 범위 밖이고, Agent 는 **ML 을 거쳐 이미 만들어진 EventCard** 를 입력으로 받습니다.

## Notebook — 앱을 읽기 전에

앱의 처리 순서대로 놓았습니다. Notebook 하나에 기법 하나이고, 완성된 앱을 import 하지 않고 작은 연습 데이터로 같은 기법을 직접 조립합니다. 단계마다 결과 해설이, 끝에 직접 해 볼 과제가 있습니다. STEP 03~06 에서 배운 기법도 이 앱을 이해하는 데 필요하면 설비 정비 상황으로 다시 다룹니다.

| # | Notebook | 기법 | 앱에서 쓰는 곳 | STEP |
|---|---|---|---|---|
| 01 | `01_eventcard_and_criteria` | Pydantic 계약, ML 예측과 판정 기준 대조 | `domain.py`, `criteria.py` | — |
| 02 | `02_section_chunking` | MarkdownHeaderTextSplitter, 머리말 경로, 절 번호 인용, PDF 구조 손실 | `scripts/task10/ingest_manuals.py` | 03 |
| 03 | `03_recorded_embeddings` | 임베딩·FAISS, CacheBackedEmbeddings 녹화와 재생 | `evidence.py` | 03 |
| 04 | `04_hybrid_search` | 카드 → 질의, BM25 + 의미 검색, EnsembleRetriever | `evidence.py` | 04 |
| 05 | `05_history_tool` | `@tool`, Literal enum, 시점 경계, 읽기 전용 DB | `tools.py`, `history.py` | 05 |
| 06 | `06_lookup_agent` | `create_agent`, 호출 상한, 실행 기록 감사 | `lookup.py` | 05 |
| 07 | `07_mcp_history_server` | FastMCP, MultiServerMCPClient, 오류가 글자로 오는 문제 | `mcp_server.py`, `lookup.py` | 05 |
| 08 | `08_draft_chain` | `prompt \| model \| PydanticOutputParser`, 인용·단정 표현 검사 | `drafting.py`, `routing.py` | 03·04 |
| 09 | `09_route_and_retry` | SOP 규칙 경로, 조건 엣지, 횟수 제한 재작성 | `routing.py`, `review.py` | 06 |
| 10 | `10_parallel_collectors` | 병렬 분기, reducer, 중복 제거 | `review.py` | 06 |
| 11 | `11_review_pause` | `interrupt`·`Command`, 체크포인터, 다시 묻기 | `review.py`, `app.py` | 06 |
| 12 | `12_end_to_end_evaluation` | 한 그래프로 잇기, 시스템 재현율 (통합) | `evaluation.py` | — |

Notebook 은 `scripts/notebook_specs_task10.py` 에서 생성합니다. 직접 고치지 말고 spec 을 고친 뒤 생성합니다. Jupyter 에서 실행해 생긴 출력은 다시 생성하면 지워집니다.

```bash
uv run python scripts/build_notebooks.py
```

## 앱

| 파일 | 하는 일 |
|---|---|
| `app.py` | FastAPI. 아래 endpoint |
| `review.py` | **본체 그래프**: 병렬 수집 → merge → 경로 → 초안·검사 루프 → 검토 멈춤 → 보고서 |
| `evidence.py` | 매뉴얼 근거: 카드 → 질의, 녹화 임베딩 vector(FAISS 또는 pgvector) + BM25 하이브리드, 절 번호로 바로 꺼내기 |
| `lookup.py` | 이력 담당 Agent: fixture 대본, 실행 기록 감사(의존 순서·빠진 유형), MCP 경로 |
| `tools.py` · `mcp_server.py` | 읽기 전용 Tool 4개와 그것을 여는 MCP 서버 |
| `criteria.py` · `history.py` | 판정 기준 계산, 정비 이력 조회(조회마다 읽기 전용 연결, SQLite 또는 Postgres) |
| `postgres.py` | Postgres 선택 기능: 설정 읽기와 읽기 전용 연결 |
| `routing.py` | 처리 경로(SOP-EA-01 6·9장), 준비 부품, 초안 검사 |
| `drafting.py` | 초안 프롬프트와 파서. **LLM 이 하는 유일한 일** |
| `report.py` | 검토 결과로 보고서 만들기 |
| `evaluation.py` | 대표 사례 경로 검사, 경로별 실제 고장·오탐, 시스템 재현율 |
| `domain.py` | 데이터 계약과 API 요청·응답(Pydantic). `schemas/` 는 여기서 생성 |

| endpoint | 하는 일 |
|---|---|
| `POST /cases` | `event_id` 또는 `card`(+ `completed_repairs`) → 근거를 모아 검토 앞에서 멈춘다 |
| `GET /cases/{case_id}` | 멈춘 건의 상태와 검토 packet |
| `POST /cases/{case_id}/decision` | `approve`·`revise`·`escalate`·`reject` 로 재개 |
| `GET /cards` | 카드 목록. 대표 사례 S01~S10 표시 |
| `GET /evaluate` | 대표 사례 10건 경로 검사, 경로별 실제 고장·오탐, 시스템 재현율 |
| `GET /diagnostics` | 모드·임베딩 출처·Tool 출처·상한·저장소 (키는 돌려주지 않음) |

```bash
curl -s -X POST localhost:8035/cases -H 'content-type: application/json' -d '{"event_id":"EVT-2025-0034"}'
curl -s -X POST localhost:8035/cases/<case_id>/decision -H 'content-type: application/json' \
     -d '{"decision":"approve","reviewer_role":"정비 기술자"}'
```

| 결정 | 결과 | 막는 조건 |
|---|---|---|
| `approve` | 보고서 | 검사 오류가 있으면 할 수 없음 |
| `revise` | 초안을 다시 쓰고 다시 멈춤 | grounded_draft 만, 2번까지 |
| `escalate` | escalation 사유가 붙은 보고서 | — |
| `reject` | 보고서 없이 끝 | — |

- 받을 수 없는 결정은 앱이 **재개 전에** 422 로 돌려보내고, 그래프 안에서는 예외 대신 **다시 묻습니다.** 예외로 막으면 그 결정값이 저장되어 건이 굳습니다(Notebook 11 이 재현).
- 이미 끝난 건에 결정을 넣으면 409, 없는 건은 404, 녹화에 없는 새 카드는 503 과 고치는 방법입니다.
- 이력 Agent 가 필요한 유형을 빠뜨리면 감사가 찾고 코드가 채웁니다(`filled_history_types`). 2026-10-07 live(gpt-4.1-mini) 3건 중 2건에서 실제로 일어났습니다.
- live 초안 10건은 모두 검사를 통과했지만, 그중 S02 는 인용이 맞는데 매뉴얼의 다른 갈래 절차를 섞었습니다. **검사 통과는 맞는 내용이라는 뜻이 아닙니다.** 그래서 사람이 검토합니다.
- 평가: 대표 사례 10건 모두 기대 경로대로. 운영 기간 실제 고장 99건 중 ML 경보로 Agent 에게 온 것 74건, **시스템 재현율 74.7%**. 나머지 25건은 Agent 가 볼 수 없었습니다.

## 폴더

| 경로 | 내용 | Agent 가 봐도 되는가 |
|---|---|---|
| `*.py` | 앱 (위 표) | — |
| `notebooks/` | 기법 Notebook 12개 | — |
| `tests/test_maintenance_agent.py` | 과제 10 Test | — |
| `schemas/` | 계약에서 생성한 JSON Schema | — |
| `docs/curriculum-plan.md` | 확정한 결정과 실측 기록 | — |
| `data/eventcards/eventcards.jsonl` | 이상 이벤트 111장 | **예 (입력)** |
| `data/eventcards/scenarios.jsonl` | 경로별 대표 사례 10건 (카드 + 맥락) | **예 (입력)** |
| `data/history/` | MC-01 정비 이력 410건 (JSONL·SQLite) | **예 (근거)** |
| `data/manuals/md/` · `pdf/` | 매뉴얼 3종 정본과 PDF 변환본 | **예 (근거)** |
| `data/index/manual_chunks.jsonl` | 청크 69개와 메타데이터 | **예 (근거)** |
| `data/index/recorded_embeddings/` | 녹화된 실제 임베딩 | — |
| `data/eval/` | 정답·놓친 고장·사례별 기대 경로 | **아니오 (평가 전용)** |
| `data/model/model_card.json` | 모델 계수·임계값·검증 지표 | 아니오 (재현용) |
| `data/source/ai4i2020.csv` | 원본 사본 (정답 라벨 포함) | **아니오** |

데이터 생성·적재 스크립트는 앱 실행과 무관하므로 저장소 루트의 `scripts/task10/` 에 있습니다. 화면은 루트의 `app_pages/task10_maintenance.py`, 컨테이너는 루트의 `Dockerfile`·`compose.yml`(서비스 `db`·`init`·`task10`·`ui`) 입니다. `data/eval/` 과 `data/source/` 에는 정답이 들어 있습니다. Agent 나 검색 대상에 넣으면 평가가 성립하지 않습니다.

## EventCard

ML이 고장 가능성을 감지했을 때 만드는 카드입니다. **정답(실제 고장 여부)은 들어 있지 않습니다.**

| 필드 | 내용 |
|---|---|
| `sensor_snapshot` | 센서 값 5개와 파생 값 2개(온도 차, 기계 출력) |
| `prediction.probabilities` | 유형별 확률 (TWF·HDF·PWF·OSF). RNF는 예측하지 않음 |
| `prediction.candidates` | 경보 기준을 넘은 유형 전부. 둘 이상이면 복합 의심 |
| `prediction.confidence_level` | high / medium / low |
| `prediction.top_signals` | 예측에 가장 크게 기여한 입력 3개 (원인이 아니라 모델의 근거) |
| `severity` | alarm(확률 0.5 이상) / warning |

구성 (운영 기간 2025-07-26 ~ 09-27)

| 예측 유형 | 장수 | 확신도 high / medium / low | 오탐 |
|---|---:|---|---:|
| PWF | 38 | 18 / 14 / 6 | 7 |
| HDF | 32 | 0 / 12 / 20 | 11 |
| OSF | 23 | 6 / 12 / 5 | 5 |
| TWF | 18 | 0 / 0 / 18 | 14 |
| 합계 | **111** | 24 / 38 / 49 | **37** |

- 복합 후보(candidates 2개 이상) 13장
- 이벤트가 만들어지지 않은 실제 고장(놓친 고장) 25건은 `data/eval/missed_failures.jsonl`에만 있습니다.

### 모델은 어떻게 만들었나

- AI4I 1만 행을 **공구 교체 주기 120개 단위**로 나눴습니다(이력 70%, 운영 30%). HDF는 원본 앞쪽 6천 행에만 있어서 행 순서로 자르면 운영 기간에 HDF가 생기지 않습니다. 그래서 유형이 고르게 들어가도록 주기를 층별로 나눴습니다.
- 이력 기간 데이터로만 numpy 로지스틱 회귀(유형별 4개)를 학습했습니다. 운영 기간 정답은 학습과 검증 어디에도 쓰지 않았습니다.
- **일부러 완벽하지 않습니다.** TWF는 확률이 0.12를 넘지 않아 경보 기준을 0.10으로 낮췄고, 그래서 TWF 이벤트는 대부분 낮은 확신의 오탐입니다. 이 약점은 `ML-GUIDE-01` 4장에 적혀 있고, Agent가 이력·매뉴얼로 확인해야 하는 이유가 됩니다.

## 정비 이력

| record_type | 건수 | 내용 |
|---|---:|---|
| `failure_repair` | 240 | 고장 수리. ML 알람으로 시작(`ml_alarm`)했거나 운전자가 발견(`operator_report`) |
| `false_alarm_check` | 86 | ML 알람을 점검했는데 고장이 아니었던 기록 |
| `tool_change` | 84 | 공구 교체. 이력 기간 48건 + 운영 기간 36건(운영 기간에는 이 기록만 있고 교체 사유는 적지 않음) |

- 증상·진단·조치·교체 부품·정지 시간·매뉴얼 참조(`MC01-MM 4.2.3` 등)가 있습니다. 진단 문장의 수치는 매뉴얼 판정 기준과 맞춰져 있습니다.
- SQLite에는 `maintenance_record`와 `part_usage` 두 표가 있습니다.

```sql
-- 같은 유형의 최근 기록 3건 (SOP-EA-01 5.2의 1번 근거)
SELECT record_id, occurred_at, diagnosis, action FROM maintenance_record
WHERE failure_types LIKE '%HDF%' ORDER BY occurred_at DESC LIMIT 3;

-- 같은 예측 유형의 과거 오탐 (5.2의 3번 근거)
SELECT record_id, past_alarm_probability, diagnosis FROM maintenance_record
WHERE record_type = 'false_alarm_check' AND past_alarm_type = 'TWF';
```

이력은 숫자 위주의 기록이라 벡터 DB에 넣지 않았습니다. 설비·유형·기간 조건과 센서 값 거리로 찾는 것이 맞습니다.

## 매뉴얼

| 문서 | 내용 | 청크 |
|---|---|---:|
| `MC01-MM` 정비 매뉴얼 | 사양, 안전(LOTO), 점검 주기, 고장 유형별 판정 기준·점검·조치, 부품 교체, 부품 목록 | 42 |
| `SOP-EA-01` 대응 절차서 (rev 1.5) | 이벤트 접수, 확신도별 대응, 근거 확인·인용 규칙, escalation 조건 ESC-1~7, 보고서 항목, 오탐 처리, Agent 처리 경로 | 15 |
| `ML-GUIDE-01` 모델 안내서 | 출력 필드 읽는 법, 검증 결과(실측), 알려진 약점, 사용 원칙 | 12 |

- 판정 기준은 AI4I의 고장 생성 조건과 같습니다. 예: HDF는 온도 차 8.6 K 미만이면서 회전수 1,380 rpm 미만.
- 부품 번호(`PN-FL-3120` 등)와 고장 코드처럼 **글자가 정확히 맞아야 찾히는 단어**를 넣었습니다. BM25가 쓸모 있는 이유입니다.
- `ML-GUIDE-01.md`는 `scripts/task10/ml_guide_template.md`에 검증 지표를 채워 생성합니다. 직접 고치지 않습니다.

## 출력 계약과 처리 경로

판정은 코드가 하고 LLM은 문장만 씁니다(`domain.py`의 `AgentResponse`).

| 필드 | 누가 | 근거 |
|---|---|---|
| `criteria_check` | 코드 (`criteria.py`) | MC01-MM 부록 A |
| `evidence` | 코드 (매뉴얼 검색, `history.py`) | SOP-EA-01 5.2 |
| `route`, `escalation_reasons` | 코드 (`routing.py`) | SOP-EA-01 6·9장 |
| `parts_to_prepare` | 코드 (근거에 나온 부품 번호만) | — |
| `cause_candidates`, `inspection_steps` | LLM (근거 ID 필수, `validate_response` 통과해야 함) | SOP-EA-01 5.3·7.2 |

| 경로 | 조건 | 111장 중 |
|---|---|---:|
| `grounded_draft` | 판정 기준 성립, escalation 조건 없음 | 75 |
| `escalation` | ESC-2 복합, ESC-3 불일치, ESC-4 근거 없음, ESC-5 조치 후 재발, ESC-7 경보인데 기준 미해당 | 17 |
| `inspect_only` | 어떤 기준에도 해당하지 않는 경고 | 19 |

판정 기준 코드는 AI4I 원본 1만 행의 HDF·PWF·OSF 라벨과 한 행도 다르지 않습니다(테스트로 확인). 그래서 HDF·PWF·OSF는 규칙만으로 정탐과 오탐이 갈리고, **TWF는 기준이 성립해도 오탐(16장 중 12장)이라 사람 검토가 필요합니다.**

```bash
uv run python -m pytest task10_maintenance/tests -q
```

## 다시 만들기

```bash
# 1. 데이터와 대표 사례 (seed 고정, 결과가 같음)
uv run python scripts/task10/build_dataset.py --source <ai4i2020.csv 경로>   # 처음 한 번
uv run python scripts/task10/build_dataset.py                                # 이후에는 사본 사용

# 2. PDF 변환본 (pandoc + Chrome 필요)
uv run python scripts/task10/build_manual_pdfs.py

# 3. 청크 → 임베딩 녹화 (녹화는 OpenAI 비용 발생, 매우 적음)
uv run python scripts/task10/ingest_manuals.py
uv run --env-file .env python scripts/task10/record_embeddings.py
```

## 청크화와 저장소 적재

```bash
uv run python scripts/task10/ingest_manuals.py                    # fixture, FAISS (기본)
uv run python scripts/task10/ingest_manuals.py --backend chroma
uv run --env-file .env python scripts/task10/ingest_manuals.py    # live 임베딩 (OpenAI 비용 발생)
uv run --env-file .env python scripts/task10/ingest_manuals.py --backend pgvector   # DB 필요
```

- 머리말(#~####)로 먼저 나누고, 긴 절만 600자(겹침 80자)로 다시 자릅니다. 청크 앞에 머리말 경로를 붙이고, 청크마다 `citation`(예: `MC01-MM 4.2.3`)이 붙습니다.
- 매뉴얼을 고치면 PDF 와 청크를 다시 만들고 임베딩을 다시 녹화합니다(`build_manual_pdfs.py` → `ingest_manuals.py` → `record_embeddings.py`).
- 벡터 저장소는 `data/index/<backend>-<md|pdf>-<mode>-<차원>/` 에 생깁니다. git 에는 올리지 않습니다. 앱은 이것을 쓰지 않고 시작할 때 녹화 임베딩으로 FAISS 를 메모리에 만듭니다.
- `--pdf` 는 PDF 변환본을 읽습니다(`manual_chunks_pdf.jsonl`, 33개). 표의 열 구분과 절 번호가 사라져 인용이 쪽 단위(`MC01-MM p.8`)로만 됩니다. md 를 정본으로 둔 이유입니다(Notebook 02).
