"""Tool 을 부를 수 있는 모델을 고르는 한 곳.

`shared/rag/llm.py` 의 `chat_model` 은 답변용이라 Tool 을 부르지 않는다. Agent 는
**모델이 Tool 을 고를 수 있어야** 성립하므로 여기를 따로 둔다. live 경로는
`chat_model` 을 그대로 쓴다. 같은 모델을 두 번 설정하면 한쪽만 바뀐다.
"""
from __future__ import annotations

from collections.abc import Sequence
from itertools import cycle

from langchain_core.language_models import BaseChatModel, GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage

from shared.rag.llm import chat_model
from shared.rag.mode import is_live_mode


class ScriptedToolModel(GenericFakeChatModel):
    """대본대로 Tool 을 부르는 시험용 모델.

    LangChain 이 주는 가짜 모델 중 `bind_tools` 를 구현한 것이 없다. 그래서
    `create_agent` 에 넣으면 `NotImplementedError` 가 난다. 여기서 덮는 것은
    그 한 가지뿐이다. **무엇을 부를지는 대본이 이미 정해 두었으므로** Tool
    목록을 볼 필요가 없다.

    이것은 라이브러리 기능을 다시 만든 것이 아니라 **시험용 대역**이다.
    fixture 에서도 Tool 은 진짜로 실행된다. 대본인 것은 "모델이 무엇을 부를지
    고르는 것" 하나뿐이다.
    """

    def bind_tools(self, tools, **kwargs):          # noqa: ARG002 - 대본이 이미 정했다
        return self


def agent_model(script: Sequence[BaseMessage] | None = None) -> BaseChatModel:
    """fixture 는 대본대로, live 는 실제 모델이 스스로 고른다."""
    if is_live_mode():
        return chat_model()
    turns = list(script) if script else [AIMessage(content="확인했습니다.")]
    return ScriptedToolModel(messages=cycle(turns))
