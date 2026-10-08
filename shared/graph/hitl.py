"""사람이 결정할 때까지 멈춘다.

**승인 packet 을 만드는 것과 실제로 멈추는 것은 다르다.** 앞의 것은 화면에
글자를 띄우는 일이고, 뒤의 것은 실행이 끊기고 상태가 저장되는 일이다. 전자만
하면 "사람이 결정합니다"라고 적힌 자동 승인이 된다.

`interrupt` 와 `Command` 는 LangGraph 가 준다. 여기서는 **무엇을 물을지와
무엇을 답으로 받을지**를 계약으로 굳힌다. 자유 문자열을 받으면 오타 하나가
승인이 된다.
"""
from __future__ import annotations

from typing import Any, Literal

from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

DECISIONS = ("approve", "reject", "revise")


class HumanDecision(BaseModel):
    """사람이 돌려주는 답. **세 가지뿐이다.**

    `revise` 는 "다시 보라"이고 `reject` 는 "안 된다"다. 둘을 한 값으로 묶으면
    되돌아가는 길과 끝내는 길을 구분할 수 없다.
    """

    decision: Literal["approve", "reject", "revise"]
    decided_by: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=400)


def ask_human(packet: dict[str, Any]) -> HumanDecision:
    """여기서 실행이 끊긴다. 돌아온 값은 반드시 계약대로여야 한다.

    `interrupt` 가 돌려주는 것은 재개할 때 넣은 값 그대로다. 검증하지 않으면
    `{"decision": "approvee"}` 같은 오타가 조용히 흘러간다. 그래서 여기서 막는다.
    """
    answer = interrupt(packet)
    if isinstance(answer, HumanDecision):
        return answer
    if not isinstance(answer, dict):
        raise ValueError(f"사람 결정은 dict 여야 합니다. 받은 것: {type(answer).__name__}")
    return HumanDecision.model_validate(answer)


def resume_with(decision: HumanDecision) -> Command:
    """멈춘 지점부터 이어 간다. 앞 단계는 다시 돌지 않는다."""
    return Command(resume=decision.model_dump())
