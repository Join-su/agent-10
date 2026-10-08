"""STEP 06 이 쌓는 그래프 계층.

STEP 03·04 가 `shared/rag` 에 검색을, STEP 05 가 `shared/tools` 에 Tool 을
놓았다. 여기서는 **여러 담당이 병렬로 보고, 모자라면 되돌아가고, 사람이
결정하는 흐름**을 놓는다.

**하나도 손으로 만들지 않는다.**

| 하는 일 | 쓰는 것 |
|---|---|
| 그래프 조립·순환·병렬 | `langgraph.graph.StateGraph` |
| 실행 중단과 재개 | `langgraph.types.interrupt` · `Command` |
| Thread 저장 | `langgraph.checkpoint.sqlite.SqliteSaver` |

마지막 항목은 한때 손으로 만들었다. `langgraph-checkpoint-sqlite` 2.0.10 이
`langgraph-checkpoint` 4.2.0 의 직렬화 API 와 맞지 않아 `BaseCheckpointSaver` 를
237줄로 직접 구현했고, 그 근거를 파일에 적어 두었다. **3.1.1 에서 고쳐졌다.**
근거가 사라졌으므로 수제 구현을 지우고 라이브러리를 쓴다.
"""
from shared.graph.checkpoint import (
    ThreadStoreError,
    close_thread_store,
    graph_config,
    thread_store,
    thread_store_durability,
)
from shared.graph.hitl import (
    DECISIONS,
    HumanDecision,
    ask_human,
    resume_with,
)

__all__ = [
    "ThreadStoreError", "graph_config", "thread_store", "thread_store_durability",
    "close_thread_store",
    "DECISIONS", "HumanDecision", "ask_human", "resume_with",
]
