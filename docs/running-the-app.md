# 실행 가이드 — 과제 10 을 띄우고 확인하기

## 0. 한눈에 보는 구조

Process 들이 HTTP 로만 이야기한다. 화면은 서버 내부를 import 하지 않는다.

```mermaid
flowchart LR
    subgraph browser["브라우저"]
        U["팀원"]
    end

    subgraph front["프론트엔드 · Streamlit :8501"]
        UI["streamlit_app.py<br/>app_pages/task10_maintenance.py"]
    end

    subgraph back["백엔드 · FastAPI :8035"]
        API["task10_maintenance/app.py<br/>review.py 그래프"]
    end

    subgraph data["데이터·외부"]
        MEM["매뉴얼 vector: FAISS<br/>프로세스 메모리 (기본)"]
        SQL[("정비 이력: SQLite<br/>파일, 읽기 전용 (기본)")]
        PG[("Postgres + pgvector<br/>:5434 (선택)")]
        OAI["OpenAI<br/>Embeddings · Chat"]
        MCPS["이력 MCP 서버<br/>별도 Process"]
        TDB[("threads.sqlite<br/>선택")]
    end

    U --> UI
    UI -- "HTTP JSON" --> API
    API --> MEM
    API --> SQL
    API -. "VECTOR_BACKEND=pgvector<br/>HISTORY_BACKEND=postgres" .-> PG
    API -. "APP_MODE=live" .-> OAI
    API -. "MCP_MODE=on" .-> MCPS
    API -. "THREAD_DB 지정 시" .-> TDB
```

**읽는 법**

- 실선은 항상 일어나는 연결, 점선은 설정을 켰을 때만 생기는 연결이다.
- **기본값은 아무것도 필요 없다.** 키도 DB 도 없이 끝까지 돈다.
- 매뉴얼 의미 검색은 기본으로도 **진짜 순위**다. 실제 OpenAI 임베딩을 녹화해 둔 것을 재생한다.
- Postgres 는 선택이다. 컨테이너로 한 번에 띄우면(§5) Postgres 를 쓴다.
- MCP 서버는 앱이 필요할 때 **자식 Process 로 직접 띄운다.** 따로 실행하지 않는다.

---

## 1. 준비물

> **Windows 를 쓴다면 먼저 읽는다.** 이 문서의 명령은 환경 변수를 명령 앞에
> 붙이지 **않는다.** 그 문법은 macOS·Linux 에서만 동작한다. 대신 **필요한
> 값은 전부 `.env` 에 적고** 아래 명령을 그대로 쓴다. 세 운영체제에서 같다.

| 필요한 것 | 확인 |
|---|---|
| Python 3.13 | `uv` 가 알아서 맞춘다 |
| `uv` | `uv --version` |
| Docker | `docker ps` — 컨테이너로 띄우거나 Postgres 를 쓸 때만 |
| OpenAI API 키 | `live` 모드에서만 |

```bash
git clone <이 저장소>
cd agent-10
uv sync --frozen        # lockfile 그대로 설치한다. 여기서 막히면 그 다음은 볼 것도 없다.
```

### uv 없이 pip 으로

`uv` 를 쓸 수 없는 환경이면 `requirements.txt` 를 쓴다. 두 파일 모두
`uv.lock` 에서 생성한 것이라 버전이 같다.

```bash
python3.13 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt        # 실행만
pip install -r requirements-dev.txt    # 테스트·Jupyter 까지
```

이 뒤의 명령은 `uv run ...` 으로 적었다. pip 으로 설치했다면 가상환경을
활성화한 뒤 `uv run` 을 떼고 실행하면 된다.

### 설정 파일 만들기

```bash
cp .env.example .env
```

`.env` 를 열어 채운다. **`.env` 는 Git 에 올라가지 않는다. 실제 키는 여기에만 둔다.**

| 변수 | 무엇 | 언제 필요한가 |
|---|---|---|
| `APP_MODE` | `fixture` 또는 `live` | 항상 (기본 `fixture`) |
| `OPENAI_API_KEY` | 실제 키 | `live` 일 때만 |
| `OPENAI_MODEL` | 초안·Tool 선택 모델 (기본 `gpt-4.1-mini`) | `live` 에서 바꿀 때 |
| `OPENAI_EMBEDDING_DIMENSIONS` | live 임베딩 차원 (기본 1536) | 적재와 질의가 **같아야** 한다. fixture 는 녹화된 256 차원 |
| `VECTOR_BACKEND` | `faiss`(기본)·`chroma`·`pgvector` | 매뉴얼 vector 를 Postgres 에 둘 때 `pgvector` |
| `HISTORY_BACKEND` | `sqlite`(기본)·`postgres` | 정비 이력을 Postgres 에 둘 때 `postgres` |
| `POSTGRES_PASSWORD` | 아무 강한 문자열 | Postgres 를 쓰거나 컨테이너로 띄울 때 |
| `DATABASE_URL` | `...@127.0.0.1:5434/task10` | 호스트에서 직접 실행하며 Postgres 를 쓸 때 |
| `THREAD_DB` | 파일 경로 | 검토 대기 건을 재시작 뒤에도 남길 때 |
| `MCP_MODE` | `off`/`on` | 이력 Tool 을 MCP 서버에서 가져올 때 |

---

## 2. 제일 빠른 길 — fixture 모드

**Docker 도 API 키도 필요 없다.** 처음이라면 여기서 시작한다.

```bash
# 터미널 1 — API
uv run uvicorn task10_maintenance.app:app --port 8035 --env-file .env
# 터미널 2 — 화면
uv run streamlit run streamlit_app.py
```

`--env-file .env` 가 모드와 설정을 읽는다. 그래서 명령 앞에 환경 변수를 붙일
필요가 없고, Windows 에서도 그대로 동작한다.

브라우저에서 **http://127.0.0.1:8501** 을 연다. 대표 사례 S01~S10 중 하나를 골라
"처리 시작" → 정비 기술자 결정 → 보고서까지 가 본다. '평가' 탭에서 시스템 재현율을 본다.

화면 없이 API 만 볼 수도 있다. **http://127.0.0.1:8035/docs** 가 OpenAPI 화면이다.

```bash
curl -s -X POST localhost:8035/cases -H "content-type: application/json" -d "{\"event_id\":\"EVT-2025-0034\"}"
curl -s -X POST localhost:8035/cases/<case_id>/decision -H "content-type: application/json" -d "{\"decision\":\"approve\",\"reviewer_role\":\"정비 기술자\"}"
```

### fixture 에서 무엇이 진짜이고 무엇이 대본인가

| 부분 | fixture | 이유 |
|---|---|---|
| **판정 기준·처리 경로·초안 검사** | **진짜** | 코드가 계산한다 |
| **정비 이력 조회(Tool 실행)** | **진짜** | 실제 이력 DB 를 읽는다 |
| **매뉴얼 검색 순위** | **진짜** | 실제 OpenAI 임베딩을 녹화해 두고 재생한다 |
| **멈춤·재개·보고서** | **진짜** | LangGraph 가 실제로 멈추고 이어 간다 |
| 이력 Agent 가 무엇을 부를지 고르는 것 | 대본 | 모델 대신 정해진 순서로 부른다 |
| 초안 문장 | 대본 | 근거에서 정해진 규칙으로 쓴다(`drafted_by = fixture_script`) |

`GET /diagnostics` 가 이것을 그대로 알려 준다(`tool_choice`, `drafted_by`, `embedding_source`).

---

## 3. 진짜로 — live 모드

실제 OpenAI 임베딩과 모델을 쓴다(비용이 든다). **`.env` 에 두 줄이면 된다.**

```
APP_MODE=live
OPENAI_API_KEY=sk-...
```

§2 와 같은 명령으로 띄운다.

```bash
curl -s localhost:8035/health
# {"status":"ok","project":"task10","mode":"live"}
```

`mode` 가 `live` 가 아니면 `--env-file .env` 를 빠뜨렸거나, 셸에 `APP_MODE` 가
이미 설정되어 있는 것이다. **셸 환경 변수가 `.env` 보다 우선한다.**

live 에서는 이력 Agent 가 스스로 Tool 을 고르고 초안을 실제 모델이 쓴다. 응답의
`filled_history_types` 가 비어 있지 않으면 모델이 필요한 이력을 빠뜨려 코드가 채운 것이다.

---

## 4. 저장소를 프로세스 밖에 두기 — Postgres (선택)

기본은 매뉴얼 vector 가 **프로세스 메모리(FAISS)**, 정비 이력이 **SQLite 파일**이다.
둘을 Postgres(pgvector) 로 옮길 수 있다. 앱은 **읽기만** 하고, 적재는 스크립트가 한 번 한다.

```bash
docker compose --env-file .env up -d db          # Postgres 16 + pgvector 가 127.0.0.1:5434 에 뜬다
docker compose ps db                             # healthy 가 될 때까지
uv run --env-file .env python scripts/task10/ingest_manuals.py --backend pgvector
uv run --env-file .env python scripts/task10/load_history.py
```

그다음 `.env` 에 두 줄을 바꾸고 §2 와 같은 명령으로 띄운다.

```
VECTOR_BACKEND=pgvector
HISTORY_BACKEND=postgres
```

```mermaid
flowchart LR
    MD["매뉴얼 md 3종"] --> CH["절 단위 청크 69개"]
    CH --> EM["임베딩<br/>fixture: 녹화본 / live: OpenAI"]
    EM --> C{"VECTOR_BACKEND"}
    C -- "faiss (기본)" --> MEM["켤 때 메모리에 만든다"]
    C -- "pgvector" --> PG[("Postgres :5434<br/>task10-manuals-recorded-256")]
    SQ[("history.sqlite<br/>410건")] -- "load_history.py" --> PGT[("Postgres 표<br/>maintenance_record · part_usage")]
```

- 컬렉션 이름은 임베딩 출처와 차원마다 다르다(`task10-manuals-recorded-256`, `task10-manuals-live-1536`). live 로 바꾸면 live 로 다시 적재한다.
- 이력 연결은 **읽기 전용 세션**이다. 쓰기 문장은 DB 가 거부한다(SQLite 의 `mode=ro` 와 같은 역할).
- 메모리와 Postgres 는 같은 카드에 **같은 근거·같은 경로·같은 평가**를 낸다. 111장 중 8장은 근거 절의 순서만 다르다. FAISS 는 L2 거리, pgvector 는 코사인 거리를 써서 점수가 거의 같은 절끼리 순서가 바뀐다.
- 매뉴얼을 고쳤는데 다시 적재하지 않으면, 앱이 청크 수가 다르다며 503 과 적재 명령을 돌려준다.

---

## 5. 컨테이너로 한 번에

```bash
docker compose --env-file .env up -d --build
docker compose ps
```

네 서비스가 순서대로 뜬다. 전부 `127.0.0.1` 에만 바인딩한다.

| 서비스 | 하는 일 | 포트 |
|---|---|---|
| `db` | Postgres 16 + pgvector | 5434 |
| `init` | 매뉴얼 청크와 정비 이력을 Postgres 에 적재하고 끝난다 | — |
| `task10` | 과제 10 API. **Postgres 를 쓴다**(`VECTOR_BACKEND=pgvector`, `HISTORY_BACKEND=postgres`) | 8035 |
| `ui` | 화면 | 8501 |

`.env` 에 `POSTGRES_PASSWORD` 가 있어야 한다. 컨테이너끼리는 서비스 이름(`db`)으로 붙으므로
`.env` 의 `DATABASE_URL` 은 컨테이너에서 쓰지 않는다. 검토 대기 건은 `task10_threads` 볼륨에 남아
`docker compose restart task10` 뒤에도 이어 간다. 컨테이너에서 live 를 쓰려면 `.env` 에
`APP_MODE=live`, `OPENAI_API_KEY` 를 넣고 다시 띄운다(`init` 이 live 임베딩으로 다시 적재한다).

내릴 때:

```bash
docker compose down            # 볼륨은 남는다
docker compose down -v         # Postgres 데이터와 검토 대기 건까지 지운다
```

---

## 6. 선택 기능 두 가지

### MCP — 이력 Tool 을 별도 Process 에서 가져오기

`.env` 에 `MCP_MODE=on` 을 적고 평소대로 띄운다. 앱이 `task10_maintenance.mcp_server` 를
자식 Process 로 띄워 읽기 전용 Tool 4개를 받아 온다. `GET /diagnostics` 의 `tool_source` 가
`mcp` 로 바뀐다. 결과는 내부 경로와 같다(Test 가 확인한다).

### 검토 대기 건을 파일에 남기기

`.env` 에 `THREAD_DB=<파일 경로>` 를 적고 평소대로 띄운다.

```bash
uv run uvicorn task10_maintenance.app:app --port 8035 --env-file .env
```

서버를 껐다 켜도 `GET /cases/{case_id}` 가 검토 대기 상태를 돌려주고, 결정을 넣으면 이어 간다.
비우면 프로세스가 사는 동안만 유지되고, `/diagnostics` 가 그 사실을 경고로 돌려준다.

---

## 7. 주소와 확인 방법

| 주소 | 무엇 | 확인 |
|---|---|---|
| http://127.0.0.1:8501 | **화면** | 브라우저로 연다 |
| http://127.0.0.1:8035 | 과제 10 API | `curl localhost:8035/health` |
| http://127.0.0.1:8035/docs | OpenAPI 화면 | 브라우저로 연다 |
| 127.0.0.1:5434 | Postgres (선택) | `docker compose ps db` |

### endpoint

| App | endpoint | 하는 일 |
|---|---|---|
| 과제 10 | `POST /cases` | 이상 이벤트 카드로 근거를 모으고 경로를 정해 검토 앞에서 멈춘다 |
| 과제 10 | `GET /cases/{case_id}` | 멈춘 건의 현재 상태와 검토 packet |
| 과제 10 | `POST /cases/{case_id}/decision` | 사람 결정을 넣어 재개한다 (승인·수정 요청·상위 보고·반려) |
| 과제 10 | `GET /cards` | 고를 수 있는 카드와 대표 사례 S01~S10 |
| 과제 10 | `GET /evaluate` | 대표 사례 경로 검사와 놓친 고장까지 센 시스템 재현율 |
| 과제 10 | `GET /diagnostics` | 모드·임베딩·저장소·Tool 출처·상한 (**키는 절대 안 돌려준다**) |

---

## 8. 동작 흐름

```mermaid
sequenceDiagram
    participant UI as 화면
    participant API as 과제 10 API
    participant G as review.py 그래프
    participant M as 매뉴얼 검색
    participant H as 이력 Agent (Tool·MCP)

    UI->>API: POST /cases {event_id}
    API->>G: 시작
    par 병렬 수집
        G->>M: 카드 → 질의 → 하이브리드 검색
        G->>H: 판정 먼저, 이력은 다음 턴
    end
    G->>G: merge → 판정 기준 대조 → 경로
    G->>G: (grounded_draft) 초안 → 인용 검사 → 틀리면 한 번 더
    G-->>API: 검토 앞에서 멈춤(interrupt)
    API-->>UI: awaiting_review + packet
    UI->>API: POST /cases/{id}/decision {approve}
    API->>G: 재개(Command)
    G-->>API: 보고서
    API-->>UI: reported + 보고서
```

받을 수 없는 결정(검사 오류가 있는 초안의 승인 등)은 앱이 **재개 전에** 422 로 돌려보내고,
그래프 안에서는 예외 대신 **다시 묻는다.** 예외로 막으면 그 결정값이 저장되어 건이 굳는다.

---

## 9. 안 될 때

| 증상 | 원인과 조치 |
|---|---|
| `/health` 가 `mode: fixture` | 셸에 `APP_MODE` 가 export 되어 `.env` 를 덮었다. 셸에서 지우고 다시 실행 |
| **503** `case_unavailable` — `OPENAI_API_KEY` | `.env` 가 없거나 안 읽혔다. `cp .env.example .env` 후 키를 넣는다 |
| **503** — `녹화되지 않은 문장` | 새 카드라 녹화본에 질의가 없다. live 로 돌리거나 다시 녹화한다 |
| **503** — `DATABASE_URL 이 필요합니다` | Postgres 를 골랐는데 주소가 없다. 메시지의 명령을 그대로 친다 |
| **503** — `Postgres 에 붙을 수 없습니다` | DB 가 안 떠 있거나 포트가 틀렸다(호스트는 **5434**) |
| **503** — `매뉴얼 청크가 없습니다` / `정비 이력이 없습니다` | 적재 전이다. §4 의 적재 명령 두 개 |
| UI 가 "API 에 연결할 수 없습니다" | API 가 안 떠 있다. `curl localhost:8035/health` |
| `password authentication failed for user "task10"` | 볼륨을 만든 뒤 `POSTGRES_PASSWORD` 를 바꿨다. 비밀번호를 되돌리거나 `docker compose down -v` 후 다시 띄운다 |
| 검토 대기 건이 재시작 후 사라짐 | `THREAD_DB` 를 주지 않았다. §6 |
| **409** `not_awaiting_review` | 이미 결정이 들어간 건이다 |
| **404** `case_not_found` | case_id 가 틀렸거나, 메모리 저장소인데 서버를 재시작했다 |
| API 가 **500** | 설정 문제가 아니라 버그다. 서버 로그를 남겨 알려 준다 |

**`/diagnostics` 는 설정이 빠져도 200 으로 답한다.** 무엇이 잘못됐는지 물어볼 곳까지 막히면
진단할 수가 없기 때문이다. **API 키는 값을 한 조각도 내보내지 않는다.**

---

## 10. 검증과 Notebook

```bash
uv run pytest -q          # 전체 (fixture, Docker·키 필요 없음)
```

Postgres Test 는 `DATABASE_URL` 로 DB 에 닿지 않으면 건너뛴다. §4 대로 DB 를 띄우고 적재한 뒤
`.env` 를 읽어 돌리면 함께 돈다.

```bash
uv run --env-file .env pytest -q
```

Notebook 은 Jupyter 로 연다.

```bash
uv run jupyter lab task10_maintenance/notebooks
```

`01_...` 부터 번호순으로 본다. 전부 12개다. Notebook 은 완성된 앱을 import 하지 않고
같은 기법을 작게 직접 조립한다. **Notebook 이 가르치는 기법은 전부 앱에서 실제로 돈다.**
Notebook 끝의 "실제 app 연결"이 앱의 어느 코드인지 알려 준다.
