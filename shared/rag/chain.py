"""LCEL 로 조립하는 답변 체인.

STEP 03 의 핵심이다. 검색 → 근거 정리 → 프롬프트 → 모델 → 문자열을 `|` 로 잇는다.
**직접 호출 순서를 짜지 않는다.** 이어 붙인 것이 그대로 실행 계획이 된다.
"""
from __future__ import annotations

from collections.abc import Sequence

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import Runnable, RunnablePassthrough

ANSWER_PROMPT = ChatPromptTemplate.from_template(
    "너는 산업장비 기술문서를 읽고 답하는 보조자다.\n"
    "아래 근거 안에서만 답한다. 근거에 없으면 없다고 말한다.\n\n"
    "근거:\n{context}\n\n"
    "질문: {question}\n"
)


def format_documents(documents: Sequence[Document]) -> str:
    """검색 결과를 프롬프트에 넣을 한 덩어리로 만든다.

    출처를 함께 적는다. 근거가 어디서 왔는지 모르면 답을 검증할 수 없다.
    """
    lines = []
    for document in documents:
        section = document.metadata.get("section", "?")
        source = document.metadata.get("source", "?")
        lines.append(f"[{source} §{section}] {document.page_content}")
    return "\n\n".join(lines)


def answer_chain(retriever: BaseRetriever, model: BaseChatModel) -> Runnable:
    """질문 하나를 받아 답변 문자열을 내는 체인.

    `{"context": ..., "question": ...} | prompt | model | parser` 가 전부다.
    각 조각이 `Runnable` 이라 `|` 로 이어진다.
    """
    return (
        {"context": retriever | format_documents, "question": RunnablePassthrough()}
        | ANSWER_PROMPT
        | model
        | StrOutputParser()
    )
