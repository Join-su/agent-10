"""답변을 만드는 모델을 고르는 한 곳."""
from __future__ import annotations

import asyncio
import os
import weakref
from collections.abc import Sequence
from itertools import cycle
from typing import Any

from langchain_core.language_models import BaseChatModel, GenericFakeChatModel

from shared.rag.mode import is_live_mode

DEFAULT_LIVE_MODEL = "gpt-4.1-mini"


class ChatConfigurationError(RuntimeError):
    """LLM 설정이 잘못됐다. 운영자가 고칠 수 있는 상태다."""


def chat_model(fixture_reply: str | Sequence[str] | None = None) -> BaseChatModel:
    """fixture 는 정해진 문장을 돌려주고, live 는 실제 모델을 부른다.

    fixture 가 모델을 흉내 내지 않는 것이 중요하다. 흉내 내면 체인이 진짜로
    도는지 알 수 없다. 여기서는 **체인이 LLM 자리에 무엇을 넣어 부르는지**만
    보이면 된다.

    STEP 04 부터는 한 요청 안에서 모델을 여러 번 부른다(질의 확장, 근거 판정,
    답변 생성). 그래서 대본을 여러 줄 받고 `cycle` 로 돌린다. 대본이 떨어져
    `StopIteration` 으로 죽으면 학습자는 리트리버가 고장 난 줄 안다.
    """
    if not is_live_mode():
        replies = (
            [fixture_reply] if isinstance(fixture_reply, str)
            else list(fixture_reply) if fixture_reply
            else ["근거를 바탕으로 정리한 답변입니다."]
        )
        return GenericFakeChatModel(messages=cycle(replies))

    from langchain_openai import ChatOpenAI

    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise ChatConfigurationError("live 모드에는 환경 변수 OPENAI_API_KEY 가 필요합니다.")
    return ChatOpenAI(api_key=key, model=os.getenv("OPENAI_MODEL", DEFAULT_LIVE_MODEL).strip(),
                      temperature=0, **_async_transport())


# 이벤트 루프마다 HTTP client 를 따로 둔다. 루프가 사라지면 함께 사라진다.
_CLIENTS: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def _async_transport() -> dict[str, Any]:
    """지금 도는 루프에 묶인 client 를 준다. 없으면 아무것도 주지 않는다.

    OpenAI SDK 는 비동기 client 를 **루프와 무관하게** 재사용한다. 그래서 루프가
    바뀌면 앞 루프에 묶인 연결을 다시 쓰려다 `Event loop is closed` 로 죽는다.
    측정하면 이렇게 나온다 — 새 루프 1번째 성공, 2번째 실패, 3번째 다시 성공.

    uvicorn 은 루프가 하나라 운영에서는 보이지 않는다. 그러나 `TestClient` 는
    요청마다 루프를 새로 만들므로, live 로 Test 를 두 번 돌리면 두 번째가
    깨진다. 원인을 찾기 어려운 형태라 여기서 막는다.

    동기 경로(도는 루프가 없음)에서는 기본값을 그대로 둔다. 그쪽은 비동기
    client 를 쓰지 않는다.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return {}

    import httpx

    client = _CLIENTS.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient()
        _CLIENTS[loop] = client
    return {"http_async_client": client}
