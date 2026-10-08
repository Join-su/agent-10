"""fixture 와 live 를 가르는 한 곳.

**같은 코드가 두 모드에서 돈다.** 바뀌는 것은 임베딩과 LLM 뿐이다. LCEL 체인,
벡터스토어, 리트리버는 그대로다. 그래야 fixture 로 배운 것이 live 에서 그대로
쓰이고, CI 가 키 없이도 진짜 경로를 검증한다.
"""
from __future__ import annotations

import os


def is_live_mode() -> bool:
    return os.getenv("APP_MODE", "fixture").strip().lower() == "live"
