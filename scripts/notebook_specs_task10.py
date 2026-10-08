"""과제 10 Notebook 내용. 한 Notebook 은 한 기법만 다룬다.

**과제 10 앱 코드를 읽을 때 모르면 막히는 기법을 앱의 처리 순서대로 놓았다.**
STEP 03~06 에서 배운 기법도 이 앱을 이해하는 데 필요하면 다시 다룬다. 과제 10 은
나중에 별도 저장소로 옮겨 혼자 읽혀야 하기 때문이다. 대신 시나리오는 전부 설비
정비 상황이다.

    01 EventCard 와 판정 기준       domain.py · criteria.py
    02 절 단위로 자르기              scripts/task10/ingest_manuals.py
    03 임베딩 녹화와 재생            evidence.py
    04 하이브리드 검색               evidence.py
    05 시점 경계가 있는 조회 Tool    tools.py
    06 조회 Agent 와 실행 감사       lookup.py
    07 MCP 로 이력 Tool 열기         mcp_server.py
    08 초안 체인과 인용 검증         drafting.py · routing.py
    09 경로 분기와 재작성 루프       review.py
    10 병렬 수집과 합치기            review.py
    11 검토 멈춤과 다시 묻기         review.py · app.py
    12 전체 흐름과 종단 평가         evaluation.py

Notebook 은 완성된 앱을 import 하지 않는다. 작은 연습 데이터로 같은 기법을 직접
조립한다. 데이터 파일을 읽는 것은 02 의 PDF 하나뿐이다(PDF 를 글로 만들 수 없어서).
"""
P = "task10_maintenance"

# --- 여러 Notebook 이 함께 쓰는 연습 데이터 ------------------------------------------

PRACTICE_MANUAL = '''PRACTICE_MANUAL = """# MC-01 정비 매뉴얼
## 4. 고장 유형별 진단
### 4.1 공구 마모 고장 (TWF)
#### 4.1.2 판정 기준
공구 마모 시간이 200분 이상이면 위험 구간이다. 240분을 넘기면 사용 한계다.
#### 4.1.3 점검 절차
1. 공구 홀더에서 공구를 분리한다. 2. 날 끝 마모 폭을 측정한다. 3. 마모 폭이 0.3mm 를 넘으면 공구(PN-TL-1008)를 교체한다.
### 4.2 열 방산 고장 (HDF)
#### 4.2.2 판정 기준
공정 온도와 공기 온도의 차이가 8.6 K 미만이고 회전수가 1,380 rpm 미만이면 해당한다.
#### 4.2.3 점검 절차
1. 흡기 필터(PN-FL-3120)의 압력차 표시를 확인한다. 2. 냉각팬 회전을 확인한다. 3. 방열판 먼지를 제거한다.
#### 4.2.4 권장 조치
필터 압력차가 기준을 넘으면 흡기 필터를 교체한다. 냉각팬이 멈췄으면 냉각팬 모듈(PN-CF-3105)을 교체한다.
"""'''

PRACTICE_SECTIONS = '''# 절 단위로 자르고 머리말 경로를 붙인 매뉴얼 조각입니다(Notebook 02 의 결과).
PRACTICE_SECTIONS = [
    ("MC01-MM 4.1.2", "[정비 매뉴얼 > 4.1 공구 마모 고장 (TWF) > 4.1.2 판정 기준] 공구 마모 시간이 200분 이상이면 위험 구간이다. 240분을 넘기면 사용 한계다."),
    ("MC01-MM 4.1.3", "[정비 매뉴얼 > 4.1 공구 마모 고장 (TWF) > 4.1.3 점검 절차] 날 끝 마모 폭을 측정한다. 마모 폭이 0.3mm 를 넘으면 공구(PN-TL-1008)를 교체한다."),
    ("MC01-MM 4.2.2", "[정비 매뉴얼 > 4.2 열 방산 고장 (HDF) > 4.2.2 판정 기준] 공정 온도와 공기 온도의 차이가 8.6 K 미만이고 회전수가 1,380 rpm 미만이면 해당한다."),
    ("MC01-MM 4.2.3", "[정비 매뉴얼 > 4.2 열 방산 고장 (HDF) > 4.2.3 점검 절차] 흡기 필터(PN-FL-3120)의 압력차 표시를 확인한다. 냉각팬 회전을 확인한다. 방열판 먼지를 제거한다."),
    ("MC01-MM 4.2.4", "[정비 매뉴얼 > 4.2 열 방산 고장 (HDF) > 4.2.4 권장 조치] 필터 압력차가 기준을 넘으면 흡기 필터를 교체한다. 냉각팬이 멈췄으면 냉각팬 모듈(PN-CF-3105)을 교체한다."),
    ("SOP-EA-01 8", "[이상 이벤트 대응 절차 > 8. 오탐 처리] 판정 기준에 해당하지 않는 경고는 육안·청음 점검 후 이상이 없으면 오탐 점검 기록을 남긴다."),
]'''

SCRIPTED_MODEL = '''# 대본대로 Tool 을 부르는 모델입니다. LangChain 이 주는 가짜 모델 중
# bind_tools 를 구현한 것이 없어 그 한 가지만 덮습니다.
from langchain_core.language_models import GenericFakeChatModel

class PracticeScriptedModel(GenericFakeChatModel):
    """무엇을 부를지는 대본이 이미 정했으므로 Tool 목록을 보지 않습니다."""
    def bind_tools(self, tools, **kwargs):
        return self'''

SPECS: list[dict] = []

# =============================================================================
# 01 EventCard 와 판정 기준
# =============================================================================
SPECS.append({
 "project": P, "file": "01_eventcard_and_criteria.ipynb",
 "title": "과제 10 · 01 · ML 예측은 사실이 아니다 — EventCard 와 판정 기준",
 "scenario": "설비 MC-01 의 고장 예측 모델이 \"열 방산 고장(HDF) 확률 0.45\" 라는 이상 이벤트 카드를 보냈습니다. Agent 는 이 카드를 입력으로 받습니다. 그런데 예측은 확률일 뿐입니다. 정비 매뉴얼에는 센서 값으로 고장 유형을 판정하는 기준이 따로 있고, 둘이 어긋나면 사람이 봐야 합니다.",
 "objectives": ["Pydantic 계약으로 EventCard 를 받고, 계약 밖의 값(정답 필드, 없는 유형)을 막는다.",
                "매뉴얼 판정 기준을 센서 값에 적용하는 함수를 만든다.",
                "예측 유형과 판정 기준이 어긋나는 카드를 구별한다."],
 "steps": [
  ("Pydantic 계약으로 카드 받기", '''# EventCard 는 ML 이 만든 결과입니다. Agent 는 이 모양만 믿고 받습니다.
# Literal 은 허용값 목록입니다. "RNF" 처럼 모델이 예측하지 않는 유형은 들어올 수 없습니다.
# 관찰 포인트: extra="forbid" 라서 계약에 없는 필드(정답 같은 것)가 섞이면 받지 않습니다.
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError

FailureType = Literal["TWF", "HDF", "PWF", "OSF"]

class PracticeStrict(BaseModel):
    model_config = ConfigDict(extra="forbid")

class PracticeSensors(PracticeStrict):
    air_temperature_k: float
    process_temperature_k: float
    rotational_speed_rpm: float
    torque_nm: float
    tool_wear_min: float

class PracticePrediction(PracticeStrict):
    predicted_failure_type: FailureType
    probabilities: dict[FailureType, float]
    confidence_level: Literal["high", "medium", "low"]

class PracticeCard(PracticeStrict):
    event_id: str = Field(pattern=r"^EVT-2025-\\d{4}$")
    quality_grade: Literal["L", "M", "H"]
    sensor_snapshot: PracticeSensors
    prediction: PracticePrediction

practice_raw_ok = {
    "event_id": "EVT-2025-0034", "quality_grade": "L",
    "sensor_snapshot": {"air_temperature_k": 301.4, "process_temperature_k": 309.9,
                        "rotational_speed_rpm": 1259, "torque_nm": 63.9, "tool_wear_min": 20},
    "prediction": {"predicted_failure_type": "HDF", "confidence_level": "low",
                   "probabilities": {"TWF": 0.01, "HDF": 0.45, "PWF": 0.02, "OSF": 0.03}},
}
practice_card_ok = PracticeCard.model_validate(practice_raw_ok)
print(practice_card_ok.event_id, "· 예측", practice_card_ok.prediction.predicted_failure_type,
      "· 확률", practice_card_ok.prediction.probabilities["HDF"])

# 정답 필드가 섞이고 없는 유형을 예측한 카드입니다.
practice_raw_bad = {**practice_raw_ok, "machine_failure": True,
                    "prediction": {**practice_raw_ok["prediction"], "predicted_failure_type": "RNF"}}
try:
    PracticeCard.model_validate(practice_raw_bad)
    practice_rejected = []
except ValidationError as error:
    practice_rejected = [".".join(map(str, e["loc"])) for e in error.errors()]
print("받지 않은 곳:", practice_rejected)''',
   "계약에 맞는 카드는 그대로 객체가 되고, 정답 필드(`machine_failure`)가 섞이거나 없는 유형(`RNF`)을 예측한 카드는 두 곳 모두 이름이 찍혀 거부됩니다. **Agent 가 정답을 보고 답하면 평가가 성립하지 않으므로** 계약이 그것을 입구에서 막습니다."),
  ("판정 기준을 함수로", '''# 매뉴얼(MC01-MM 부록 A)의 판정 기준을 센서 값에 그대로 적용합니다. 모델의 확률은 보지 않습니다.
# 온도 차·기계 출력·부하 지수는 센서 값에서 계산합니다.
# 관찰 포인트: 네 유형을 모두 계산합니다. 예측 유형 하나만 보면 다른 유형이 성립한 것을 놓칩니다.
PRACTICE_OSF_LIMIT = {"L": 11000, "M": 12000, "H": 13000}

def practice_criteria(sensors, grade):
    temp_diff = sensors.process_temperature_k - sensors.air_temperature_k
    power = sensors.torque_nm * sensors.rotational_speed_rpm * 2 * 3.141592653589793 / 60
    load = sensors.tool_wear_min * sensors.torque_nm
    return {
        "TWF": sensors.tool_wear_min >= 200,
        "HDF": temp_diff < 8.6 and sensors.rotational_speed_rpm < 1380,
        "PWF": power < 3500 or power > 9000,
        "OSF": load > PRACTICE_OSF_LIMIT[grade],
    }

practice_met_ok = practice_criteria(practice_card_ok.sensor_snapshot, practice_card_ok.quality_grade)
for practice_kind, practice_met in practice_met_ok.items():
    print(f"  {practice_kind}: {'해당' if practice_met else '해당 없음'}")''',
   "온도 차 8.5 K(< 8.6), 회전수 1,259 rpm(< 1,380)이라 HDF 만 성립합니다. 기계 출력은 약 8,425 W 로 PWF 범위 안이고, 공구 마모 20분·부하 지수 1,278 은 TWF·OSF 와 거리가 멉니다. 예측(HDF)과 판정이 같으므로 이 카드는 근거를 붙여 초안을 쓸 수 있는 경우입니다."),
  ("예측과 기준이 어긋날 때", '''# 같은 계약으로 받은 다른 카드입니다. 모델은 과부하 고장(OSF)을 높은 확률로 예측했습니다.
# 판정은 앞 단계 함수를 그대로 씁니다. 카드마다 규칙을 바꾸지 않습니다.
# 관찰 포인트: 확률이 높다고 판정 기준이 성립하는 것은 아닙니다. 둘이 다르면 사람이 봐야 합니다.
practice_mismatch = PracticeCard.model_validate({
    "event_id": "EVT-2025-0106", "quality_grade": "L",
    "sensor_snapshot": {"air_temperature_k": 300.1, "process_temperature_k": 310.4,
                        "rotational_speed_rpm": 1420, "torque_nm": 48.0, "tool_wear_min": 214},
    "prediction": {"predicted_failure_type": "OSF", "confidence_level": "high",
                   "probabilities": {"TWF": 0.31, "HDF": 0.01, "PWF": 0.02, "OSF": 0.62}},
})
practice_met_mismatch = [k for k, v in practice_criteria(
    practice_mismatch.sensor_snapshot, practice_mismatch.quality_grade).items() if v]
practice_predicted = practice_mismatch.prediction.predicted_failure_type
print("예측:", practice_predicted, "· 기준 성립:", practice_met_mismatch)
print("부하 지수:", practice_mismatch.sensor_snapshot.tool_wear_min * practice_mismatch.sensor_snapshot.torque_nm,
      "/ 한계", PRACTICE_OSF_LIMIT["L"])
print("판단:", "근거로 초안" if practice_predicted in practice_met_mismatch else "예측과 판정이 다름 → 사람에게 넘김(ESC-3)")

assert practice_card_ok.prediction.predicted_failure_type == "HDF"
assert "machine_failure" in practice_rejected, "정답 필드가 계약을 통과했습니다"
assert "prediction.predicted_failure_type" in practice_rejected, "없는 유형이 계약을 통과했습니다"
assert [k for k, v in practice_met_ok.items() if v] == ["HDF"]
assert practice_met_mismatch == ["TWF"] and practice_predicted not in practice_met_mismatch''',
   "모델은 OSF 확률 0.62(high)로 예측했지만 부하 지수는 214 × 48 = 10,272 로 L 등급 한계 11,000 에 못 미칩니다. 대신 공구 마모 214분이 TWF 위험 구간(200분 이상)에 들어 있습니다. **확신도가 높은 예측도 판정 기준과 어긋날 수 있고**, SOP 는 이것을 ESC-3(예측과 판정 불일치)으로 사람에게 넘기라고 정합니다."),
 ],
 "exercise": {
  "intro": "토크를 바꿔 보세요. 몇 Nm 부터 OSF 기준이 성립합니까? 그때 판단은 어떻게 바뀝니까? (힌트: 부하 지수 = 공구 마모 시간 × 토크, L 등급 한계 11,000)",
  "code": '''# practice_try_torque 를 바꿔 다시 실행하세요. 예: 51.0, 52.0, 60.0
# 판정 함수와 카드 계약은 그대로 둡니다. 센서 값 하나만 바꿉니다.
practice_try_torque = 48.0
practice_try = practice_mismatch.sensor_snapshot.model_copy(update={"torque_nm": practice_try_torque})
practice_try_met = [k for k, v in practice_criteria(practice_try, "L").items() if v]
print(f"토크 {practice_try_torque} Nm → 부하 지수 {practice_try.tool_wear_min * practice_try_torque:,.0f} · 기준 성립 {practice_try_met}")''',
 },
 "middle": "계약이 거부한 두 곳(정답 필드, 없는 유형), 첫 카드의 유형별 판정, 그리고 둘째 카드에서 예측(OSF)과 판정(TWF)이 갈리는 것을 확인합니다.",
 "failure": "판정 기준을 예측 유형 하나에만 적용하면 둘째 카드는 \"OSF 해당 없음\"으로 끝나고, 실제로 위험한 공구 마모(TWF)를 놓칩니다. 그리고 TWF 는 위험 구간에서 무작위로 일어나므로 기준이 성립해도 고장이 아닐 수 있습니다. 판정 기준은 **근거**이지 정답이 아닙니다.",
 "app_link": "과제 10 App 의 `domain.py::EventCard` 가 같은 계약(정답 없음, extra 금지)이고, `criteria.py::check_criteria` 가 네 유형을 모두 계산해 매뉴얼 절 번호와 함께 돌려줍니다. 둘이 어긋나면 `routing.py::decide_route` 가 ESC-3 으로 escalation 합니다.",
 "next": "다음 `02_section_chunking.ipynb` 에서는 판정의 근거가 될 매뉴얼을 절 단위로 자릅니다.",
})

# =============================================================================
# 02 절 단위로 자르기
# =============================================================================
SPECS.append({
 "project": P, "file": "02_section_chunking.ipynb",
 "title": "과제 10 · 02 · 매뉴얼을 절 단위로 자르고 인용 번호 붙이기",
 "scenario": "보고서는 \"MC01-MM 4.2.3 점검 절차에 따라\"처럼 매뉴얼의 **절 번호**로 근거를 대야 합니다(SOP-EA-01 5.3). 그런데 매뉴얼을 글자 수로만 자르면 한 조각에 여러 절이 섞이고, 어느 절을 인용해야 할지 알 수 없습니다.",
 "objectives": ["글자 수로 자르면 절이 섞이는 것을 숫자로 본다.",
                "`MarkdownHeaderTextSplitter` 로 절 단위로 자르고, 머리말에서 인용 번호를 만든다.",
                "청크 앞에 머리말 경로를 붙이면 BM25 가 절을 찾는 것을 확인한다.",
                "PDF 에서 읽은 글자로는 같은 일을 할 수 없는 것을 확인한다."],
 "steps": [
  ("글자 수로만 자르기", '''# 연습용 매뉴얼입니다. 실제 매뉴얼(MC01-MM)의 4장 일부를 줄인 것입니다.
# RecursiveCharacterTextSplitter 는 글자 수를 지키며 문단·줄·공백에서 자릅니다.
# 관찰 포인트: 절 번호가 정확히 하나인 조각만 "이 절"이라고 인용할 수 있습니다. 둘이거나 없으면 인용할 수 없습니다.
import re
from langchain_text_splitters import RecursiveCharacterTextSplitter

''' + PRACTICE_MANUAL + '''

practice_length_chunks = RecursiveCharacterTextSplitter(chunk_size=120, chunk_overlap=0).split_text(PRACTICE_MANUAL)
practice_mixed = 0
for practice_chunk in practice_length_chunks:
    practice_numbers = sorted(set(re.findall(r"\\b\\d\\.\\d\\.\\d\\b", practice_chunk)))
    practice_mixed += len(practice_numbers) != 1
    print(f"  절 번호 {practice_numbers or '없음'} · {practice_chunk[:40]!r}")
print(f"조각 {len(practice_length_chunks)}개 중 인용할 절을 정할 수 없는 조각 {practice_mixed}개")''',
   "120자로 자르면 조각 5개 중 2개는 인용할 절을 정할 수 없습니다. 셋째 조각에는 4.2.2 와 4.2.3 머리말이 함께 들어 있고, 마지막 조각은 머리말 없이 본문(권장 조치)만 남았습니다. 숫자에 안 잡힌 문제도 있습니다. 넷째 조각은 **4.2.3 의 점검 절차 본문**이 4.2.4 머리말과 붙어 있어, 번호만 보면 4.2.4 로 잘못 인용됩니다."),
  ("머리말로 자르고 인용 번호 만들기", '''# MarkdownHeaderTextSplitter 는 머리말(#~####)을 경계로 자르고, 머리말을 메타데이터로 남깁니다.
# 가장 깊은 머리말의 번호가 곧 인용 번호입니다. 예: "4.2.3 점검 절차" → "MC01-MM 4.2.3"
# 관찰 포인트: 청크 앞에 머리말 경로를 붙입니다. 본문에 없는 "HDF" 가 경로에는 있습니다.
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

practice_splitter = MarkdownHeaderTextSplitter([("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")])

def practice_citation(meta):
    deepest = meta.get("h4") or meta.get("h3") or meta.get("h2") or ""
    number = re.match(r"(\\d+(?:\\.\\d+)*)", deepest)
    return f"MC01-MM {number.group(1)}" if number else None

practice_sections = []
for practice_doc in practice_splitter.split_text(PRACTICE_MANUAL):
    practice_path = " > ".join(practice_doc.metadata[k] for k in ("h1", "h2", "h3", "h4") if k in practice_doc.metadata)
    practice_sections.append(Document(page_content=f"[{practice_path}]\\n{practice_doc.page_content}",
                                      metadata={"citation": practice_citation(practice_doc.metadata),
                                                "body": practice_doc.page_content}))
for practice_doc in practice_sections:
    print(f"  {practice_doc.metadata['citation']:14} {practice_doc.page_content.splitlines()[0]}")''',
   "본문이 있는 절 다섯 개가 각각 한 조각이 되고, 조각마다 인용 번호가 붙었습니다. 머리말만 있고 본문이 없는 4장·4.1·4.2 는 조각이 되지 않습니다. 이제 \"이 근거는 어느 절인가\"가 메타데이터 하나로 정해집니다."),
  ("머리말 경로가 검색을 살린다", '''# 같은 조각을 본문만으로, 그리고 머리말 경로를 붙여서 BM25 로 찾아 봅니다.
# 토크나이저는 한글·영문·숫자 덩어리를 단어로 봅니다. "(HDF)" 에서 "HDF" 를 꺼냅니다.
# 관찰 포인트: 점검 절차 본문에는 "HDF" 도 "점검 절차" 도 없습니다. 그 말은 머리말에만 있습니다.
from langchain_community.retrievers import BM25Retriever

def practice_words(text):
    return re.findall(r"[0-9A-Za-z가-힣]+", text)

practice_query = "HDF 점검 절차"
practice_body_only = BM25Retriever.from_documents(
    [Document(page_content=d.metadata["body"], metadata=d.metadata) for d in practice_sections],
    preprocess_func=practice_words, k=1)
practice_with_path = BM25Retriever.from_documents(practice_sections, preprocess_func=practice_words, k=1)

practice_top_body = practice_body_only.invoke(practice_query)[0].metadata["citation"]
practice_top_path = practice_with_path.invoke(practice_query)[0].metadata["citation"]
print(f"본문만        → {practice_top_body}")
print(f"머리말 경로 붙임 → {practice_top_path}")''',
   "본문만으로 찾으면 질의 단어 셋이 어느 본문에도 없어 순위에 근거가 없고, 엉뚱한 4.2.4(권장 조치)가 1위로 나옵니다. 머리말 경로를 붙이면 \"HDF\"·\"점검\"·\"절차\" 가 모두 맞는 4.2.3 이 1위가 됩니다. 실제 매뉴얼에서도 BM25 만으로 유형 절을 놓친 질의가 126개 중 40개에서 24개로 줄었습니다."),
  ("PDF 로 읽으면", '''# 현장에서 받는 매뉴얼은 대부분 PDF 입니다. 이 저장소의 PDF 변환본을 실제로 읽어 봅니다.
# Jupyter 는 Notebook 폴더에서, Test 는 저장소 루트에서 돕니다. 어느 쪽이든 저장소 루트를 찾습니다.
# 관찰 포인트: PDF 글자에는 머리말 표시(#)가 없습니다. 같은 자르기 규칙이 절을 하나도 찾지 못합니다.
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader

practice_root = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "task10_maintenance").is_dir())
practice_pdf_pages = PyPDFLoader(str(practice_root / "task10_maintenance" / "data" / "manuals" / "pdf" / "MC01-MM.pdf")).load()
practice_pdf_text = "\\n".join(page.page_content for page in practice_pdf_pages)
practice_pdf_docs = practice_splitter.split_text(practice_pdf_text)
practice_pdf_cited = [d for d in practice_pdf_docs if practice_citation(d.metadata)]
print("PDF 쪽 수:", len(practice_pdf_pages), "· 첫 쪽 메타데이터:", sorted(practice_pdf_pages[0].metadata)[:4])
print("'#' 로 시작하는 줄:", sum(line.startswith("#") for line in practice_pdf_text.splitlines()))
print("절 번호가 붙은 조각:", len(practice_pdf_cited), "/", len(practice_pdf_docs))

assert practice_mixed >= 1, "글자 수 자르기가 절을 섞지 않았습니다"
assert all(d.metadata["citation"] for d in practice_sections)
assert [d.metadata["citation"] for d in practice_sections] == ["MC01-MM 4.1.2", "MC01-MM 4.1.3", "MC01-MM 4.2.2", "MC01-MM 4.2.3", "MC01-MM 4.2.4"]
assert practice_top_path == "MC01-MM 4.2.3" and practice_top_body != "MC01-MM 4.2.3"
assert len(practice_pdf_pages) >= 1 and practice_pdf_cited == [], "PDF 에서 절 번호가 살아났습니다"''',
   "PDF 는 쪽마다 문서 하나가 되고 메타데이터에는 쪽 번호뿐입니다. 머리말 표시가 사라져 절 번호가 붙은 조각이 0개입니다. 그래서 이 자료는 **md 를 정본으로, PDF 를 변환본으로** 둡니다. PDF 로만 적재하면 인용은 쪽 단위(`MC01-MM p.8`)로 물러나고, 초안 검증이 절 번호를 확인할 수 없습니다."),
 ],
 "exercise": {
  "intro": "`practice_try_query` 를 \"냉각팬 교체\", \"PN-TL-1008\", \"회전수 기준\" 으로 바꿔 보세요. 머리말 경로를 붙인 쪽과 본문만 쓴 쪽이 각각 어느 절을 찾습니까? 어떤 질의에서 둘이 같아집니까?",
  "code": '''# 질의를 바꿔 두 검색기를 비교합니다. 조각과 토크나이저는 그대로입니다.
# 본문에 그 말이 있으면 둘이 같아지고, 머리말에만 있으면 갈립니다.
practice_try_query = "냉각팬 교체"
print("본문만        →", practice_body_only.invoke(practice_try_query)[0].metadata["citation"])
print("머리말 경로 붙임 →", practice_with_path.invoke(practice_try_query)[0].metadata["citation"])''',
 },
 "middle": "글자 수 자르기에서 절이 섞인 조각 수, 절 단위 조각의 인용 번호, 머리말 경로 유무에 따른 BM25 1위, 그리고 PDF 에서 절 번호가 붙은 조각 수(0)를 확인합니다.",
 "failure": "PDF 에서 머리말을 추정하는 규칙(\"숫자로 시작하는 줄\")은 늘 틀립니다. 실제 MC01-MM PDF 에서 숫자로 시작하는 줄 105개 중 59개가 머리말이 아니라 번호 목록이었습니다. 원본이 PDF 뿐이라면 쪽 단위 인용으로 물러서거나, 구조를 복원하는 별도 단계가 필요합니다.",
 "app_link": "과제 10 의 적재 스크립트 `scripts/task10/ingest_manuals.py` 가 같은 방식(머리말 → 600자 재분할 → 머리말 경로 → 인용 번호)으로 매뉴얼 세 권을 69개 청크로 자릅니다. `--pdf` 로 돌리면 33개 청크가 나오고 절 번호가 붙은 것은 0개입니다. 앱은 `evidence.py::load_chunks` 로 md 청크를 읽고, `evidence.py::manual_section` 이 절 번호로 판정 기준 절을 바로 꺼냅니다.",
 "next": "다음 `03_recorded_embeddings.ipynb` 에서는 이 조각을 vector 로 바꾸고, 키 없이도 같은 vector 를 쓰는 방법을 봅니다.",
})

# =============================================================================
# 03 임베딩 녹화와 재생
# =============================================================================
SPECS.append({
 "project": P, "file": "03_recorded_embeddings.ipynb",
 "title": "과제 10 · 03 · 임베딩을 녹화해 두고 키 없이 다시 쓰기",
 "scenario": "의미 검색에는 임베딩 API 가 필요합니다. 그런데 학습자는 키가 없을 수 있고, 키가 있어도 같은 매뉴얼을 매번 다시 임베딩하면 돈과 시간이 듭니다. 가짜 임베딩으로 대신하면 검색 순위가 의미 없어집니다. 실제 임베딩을 **한 번 녹화해 두고 재생**하면 둘 다 피할 수 있습니다.",
 "objectives": ["임베딩이 문장을 정해진 길이의 숫자 목록으로 바꾸는 것을 본다.",
                "FAISS 벡터 저장소에 넣고 찾는다.",
                "`CacheBackedEmbeddings` 로 녹화하고, 두 번째부터 API 를 부르지 않는 것을 확인한다.",
                "녹화에 없는 문장은 가짜로 넘어가지 않고 멈추게 한다."],
 "steps": [
  ("문장을 vector 로", '''# 실제 임베딩 API 대신 부를 때마다 횟수를 세는 대역을 둡니다. 뜻은 담지 않습니다.
# 같은 문장은 언제나 같은 vector 가 됩니다(문장의 sha256 으로 만듭니다).
# 관찰 포인트: 차원(size)이 vector 의 길이입니다. 앱은 256 차원으로 녹화했습니다.
import hashlib
import math
from langchain_core.embeddings import Embeddings

class PracticeEmbeddings(Embeddings):
    def __init__(self, size=256):
        self.size, self.calls = size, 0
    def _vector(self, text):
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [digest[i % 32] - 127.5 for i in range(self.size)]
        norm = math.sqrt(sum(v * v for v in raw))
        return [v / norm for v in raw]
    def embed_documents(self, texts):
        self.calls += len(texts)
        return [self._vector(t) for t in texts]
    def embed_query(self, text):
        self.calls += 1
        return self._vector(text)

''' + PRACTICE_SECTIONS + '''

practice_embeddings = PracticeEmbeddings(size=256)
practice_vector = practice_embeddings.embed_query(PRACTICE_SECTIONS[3][1])
print("길이:", len(practice_vector), "· 앞 3개:", [round(v, 3) for v in practice_vector[:3]])
print("같은 문장은 같은 vector:", practice_vector == practice_embeddings.embed_query(PRACTICE_SECTIONS[3][1]))
print("1536 차원이면 길이:", len(PracticeEmbeddings(size=1536).embed_query("흡기 필터")))''',
   "문장 하나가 256개 숫자가 되고, 같은 문장은 같은 vector 가 됩니다. 차원을 1536 으로 바꾸면 길이만 바뀝니다. 차원이 크면 저장 공간이 늘고, 녹화할 때와 쓸 때의 차원이 다르면 검색이 아예 되지 않습니다."),
  ("FAISS 에 넣고 찾기", '''# 조각과 vector 를 FAISS 에 넣습니다. 메타데이터에 인용 번호를 함께 둡니다.
# 찾을 때는 질의도 같은 임베딩으로 바꿔 가까운 것을 고릅니다.
# 관찰 포인트: 이 대역은 뜻을 모르므로 **여기 순위는 의미가 없습니다.** 세는 것은 API 호출 수입니다.
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

practice_documents = [Document(page_content=text, metadata={"citation": cid}) for cid, text in PRACTICE_SECTIONS]
practice_embeddings.calls = 0
practice_store = FAISS.from_documents(practice_documents, practice_embeddings)
practice_found = practice_store.similarity_search("필터 압력차 확인", k=2)
print("찾은 것:", [d.metadata["citation"] for d in practice_found], "(순위는 대본)")
print("API 호출:", practice_embeddings.calls, "번 = 조각", len(practice_documents), "+ 질의 1")''',
   "조각 6개를 넣으며 6번, 질의 하나로 1번, 모두 7번 불렀습니다. 앱을 켤 때마다 매뉴얼 청크 69개를 다시 임베딩하면 그만큼 부르고, 키가 없으면 아예 시작하지 못합니다."),
  ("녹화해 두고 다시 쓰기", '''# CacheBackedEmbeddings 는 처음 본 문장만 API 로 보내고 결과를 저장소에 남깁니다.
# 키는 namespace + sha256(문장) 입니다. namespace 에 모델과 차원을 넣어 섞이지 않게 합니다.
# 관찰 포인트: 두 번째에는 API 를 한 번도 부르지 않습니다. 저장소에서 꺼냅니다.
import tempfile
from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.storage import LocalFileStore

practice_folder = tempfile.mkdtemp()
practice_api = PracticeEmbeddings(size=256)
practice_recorder = CacheBackedEmbeddings.from_bytes_store(
    practice_api, LocalFileStore(practice_folder), namespace="practice-256-",
    query_embedding_cache=True, key_encoder="sha256")

practice_texts = [text for _, text in PRACTICE_SECTIONS]
practice_recorder.embed_documents(practice_texts)
practice_recorder.embed_query("필터 압력차 확인")
practice_first = practice_api.calls
practice_recorder.embed_documents(practice_texts)
practice_recorder.embed_query("필터 압력차 확인")
practice_second = practice_api.calls - practice_first
practice_keys = list(LocalFileStore(practice_folder).yield_keys())
print("처음:", practice_first, "번 호출 · 다시:", practice_second, "번 호출")
print("녹화된 파일:", len(practice_keys), "개 · 예:", practice_keys[0][:40] + "…")''',
   "처음에는 조각 6개와 질의 1개로 7번 불렀고, 같은 것을 다시 요청하자 0번입니다. 녹화본은 파일 7개로 남습니다. 이 폴더를 저장소에 함께 올리면, 학습자는 키 없이도 **실제 임베딩의 검색 순위**를 봅니다."),
  ("녹화에 없는 문장은 멈춘다", '''# 재생 전용으로 엽니다. 녹화에 없는 문장이 오면 API 대신 이 대역이 불립니다.
# 가짜 vector 를 만들어 넘어가지 않고 예외로 멈춥니다. 가짜 순위를 진짜처럼 내는 것보다 낫습니다.
# 관찰 포인트: 녹화된 문장은 API 없이 같은 vector 가 나오고, 새 문장은 이유를 말하며 멈춥니다.
class PracticeNotRecorded(RuntimeError):
    pass

class PracticeUnrecorded(Embeddings):
    def embed_documents(self, texts):
        raise PracticeNotRecorded(f"녹화되지 않은 문장: {texts[0][:30]!r}. live 로 돌리거나 다시 녹화하세요.")
    def embed_query(self, text):
        return self.embed_documents([text])[0]

practice_replay = CacheBackedEmbeddings.from_bytes_store(
    PracticeUnrecorded(), LocalFileStore(practice_folder), namespace="practice-256-",
    query_embedding_cache=True, key_encoder="sha256")
practice_same = practice_replay.embed_query("필터 압력차 확인") == practice_api.embed_query("필터 압력차 확인")
try:
    practice_replay.embed_query("녹화하지 않은 새 질문")
    practice_stopped = None
except PracticeNotRecorded as error:
    practice_stopped = str(error)
print("녹화된 질의 재생이 원본과 같다:", practice_same)
print("새 질의:", practice_stopped)

assert len(practice_vector) == 256
assert practice_first == len(practice_texts) + 1 and practice_second == 0, "두 번째에도 API 를 불렀습니다"
assert practice_same, "재생한 vector 가 녹화와 다릅니다"
assert practice_stopped and "녹화되지 않은" in practice_stopped, "녹화에 없는 문장이 가짜로 넘어갔습니다"''',
   "녹화된 질의는 API 없이 원본과 같은 vector 로 재생되고, 녹화하지 않은 질의는 무엇이 없는지 말하며 멈춥니다. 앱은 이 예외를 503 으로 바꿔 \"live 로 돌리거나 다시 녹화하라\"고 화면에 알립니다."),
 ],
 "exercise": {
  "intro": "namespace 를 \"practice-1536-\" 으로 바꿔 재생 전용으로 열어 보세요. 같은 문장인데 왜 멈춥니까? 차원이나 모델을 바꾼 뒤 옛 녹화를 그대로 쓰면 어떤 일이 생길지 생각해 보세요.",
  "code": '''# namespace 만 바꿔 같은 폴더를 엽니다. 녹화 키가 namespace 로 시작하므로 찾지 못합니다.
# 다른 모델·차원의 vector 가 섞이지 않게 하는 장치입니다.
practice_try_namespace = "practice-1536-"
practice_try = CacheBackedEmbeddings.from_bytes_store(
    PracticeUnrecorded(), LocalFileStore(practice_folder), namespace=practice_try_namespace,
    query_embedding_cache=True, key_encoder="sha256")
try:
    print(len(practice_try.embed_query("필터 압력차 확인")))
except PracticeNotRecorded as error:
    print("멈춤:", error)''',
 },
 "middle": "vector 길이(256), FAISS 적재 때의 API 호출 수(7), 녹화 후 다시 요청할 때의 호출 수(0), 재생 vector 가 원본과 같은지, 그리고 녹화에 없는 문장이 멈추는지를 확인합니다.",
 "failure": "녹화본은 **녹화한 문장에만** 답합니다. 매뉴얼을 한 글자 고치거나 질의 만드는 규칙을 바꾸면 녹화를 다시 해야 합니다. 그때 녹화에 없는 문장을 가짜 vector 로 채우면 앱은 아무 경고 없이 엉뚱한 순위를 냅니다. 그래서 멈추게 했습니다.",
 "app_link": "과제 10 App 의 `evidence.py::recorded_embeddings` 가 같은 방식(namespace `text-embedding-3-small-256-`, sha256 키)으로 `data/index/recorded_embeddings/` 를 재생하고, `evidence.py::_Unrecorded` 가 녹화에 없는 문장을 멈춥니다. 녹화는 `scripts/task10/record_embeddings.py` 로 한 번 합니다(OpenAI 비용이 듭니다). 앱의 벡터 저장소는 Postgres 의 pgvector 이고, 적재 스크립트 `scripts/task10/ingest_manuals.py` 가 같은 녹화 임베딩으로 `shared/rag/store.py::build_store` 를 불러 한 번 넣습니다. 이 Notebook 의 FAISS 는 메모리에 잠깐 만드는 연습용입니다.",
 "next": "다음 `04_hybrid_search.ipynb` 에서는 EventCard 로 질의를 만들고, 글자 검색과 의미 검색을 함께 씁니다.",
})

# =============================================================================
# 04 하이브리드 검색
# =============================================================================
SPECS.append({
 "project": P, "file": "04_hybrid_search.ipynb",
 "title": "과제 10 · 04 · EventCard 로 질의를 만들고 하이브리드로 찾기",
 "scenario": "근거를 찾으려면 질의가 필요합니다. 그런데 EventCard 는 문장이 아니라 숫자와 코드입니다. 카드에서 질의를 만들어야 하고, 매뉴얼에는 부품 번호(`PN-CF-3105`)처럼 글자가 정확히 맞아야 찾는 것과 \"온도가 안 떨어진다\"처럼 뜻이 통해야 찾는 것이 함께 있습니다.",
 "objectives": ["EventCard 의 후보 유형과 근거 신호로 질의를 만든다. LLM 에게 질의를 쓰게 하지 않는다.",
                "글자 검색(BM25)과 의미 검색이 서로 다른 것을 찾는 것을 본다.",
                "`EnsembleRetriever` 로 두 결과를 합쳐 한쪽만으로 놓치는 것을 함께 잡는다."],
 "steps": [
  ("카드에서 질의 만들기", '''# 후보 유형마다 "판정 기준과 점검 절차" 를 찾는 질의 하나, 그리고 확신도 대응 질의 하나.
# 근거 신호(모델이 가장 크게 본 센서) 두 개를 덧붙여 무엇이 이상했는지를 싣습니다.
# 관찰 포인트: 같은 카드는 언제나 같은 질의가 됩니다. 그래야 결과를 비교하고 녹화할 수 있습니다.
practice_card = {
    "event_id": "EVT-2025-0002", "severity": "alarm",
    "prediction": {"candidates": ["HDF", "PWF"], "confidence_level": "medium",
                   "top_signals": [{"feature": "temp_diff_k"}, {"feature": "rotational_speed_rpm"},
                                   {"feature": "temp_diff_k"}]},
}
PRACTICE_TYPE_NAMES = {"TWF": "공구 마모 고장(TWF)", "HDF": "열 방산 고장(HDF)",
                       "PWF": "전력 고장(PWF)", "OSF": "과부하 고장(OSF)"}
PRACTICE_SIGNAL_NAMES = {"temp_diff_k": "온도 차", "rotational_speed_rpm": "회전수", "torque_nm": "토크"}

def practice_queries(card):
    p = card["prediction"]
    signals = list(dict.fromkeys(PRACTICE_SIGNAL_NAMES[s["feature"]] for s in p["top_signals"]))
    hint = ", ".join(signals[:2])
    queries = [(f"{t} 판정·점검", f"{PRACTICE_TYPE_NAMES[t]} 판정 기준과 점검 절차, 조치 — {hint}")
               for t in p["candidates"]]
    queries.append(("확신도 대응", f"확신도 {p['confidence_level']} {card['severity']} 이벤트 대응 방법"))
    return queries

for practice_label, practice_text in practice_queries(practice_card):
    print(f"  {practice_label:10} {practice_text}")''',
   "후보 유형이 둘(HDF·PWF)이라 유형 질의 둘과 확신도 질의 하나, 모두 셋이 나왔습니다. 근거 신호는 \"온도 차\"가 두 번 있었지만 한 번만 들어갑니다. 질의는 코드가 만들므로 같은 카드는 언제나 같은 질의가 됩니다."),
  ("두 검색기는 서로 다른 것을 찾는다", '''# 글자 검색은 BM25, 의미 검색은 작은 "개념 사전" 임베딩으로 만듭니다.
# 개념 사전은 진짜 의미 모델이 아닙니다. "온도가"·"냉각" 을 같은 '열' 개념으로 묶어 뜻을 흉내 냅니다.
# 관찰 포인트: 부품 번호 질의는 글자 검색만, 상황 질의는 의미 검색만 맞힙니다. 각자 1위 하나씩 봅니다.
import re
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

''' + PRACTICE_SECTIONS + '''

PRACTICE_CONCEPTS = {"열": ["온도", "냉각", "방열", "바람"], "필터": ["필터", "흡기", "압력차"],
                     "공구": ["공구", "마모", "날"], "기준": ["기준", "미만", "이상"]}

class PracticeConceptEmbeddings(Embeddings):
    def _vector(self, text):
        return [1.0] + [float(sum(text.count(w) for w in words)) for words in PRACTICE_CONCEPTS.values()]
    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]
    def embed_query(self, text):
        return self._vector(text)

def practice_words(text):
    return re.findall(r"[0-9A-Za-z가-힣]+", text)

practice_documents = [Document(page_content=text, metadata={"citation": cid}) for cid, text in PRACTICE_SECTIONS]
practice_keyword = BM25Retriever.from_documents(practice_documents, preprocess_func=practice_words, k=1)
practice_dense = InMemoryVectorStore.from_documents(
    practice_documents, PracticeConceptEmbeddings()).as_retriever(search_kwargs={"k": 1})

practice_code_query = "PN-CF-3105 교체"
practice_situation_query = "온도가 잘 안 떨어지고 바람이 약해요"
practice_hits = {}
for practice_name, practice_q in (("부품 번호", practice_code_query), ("상황", practice_situation_query)):
    practice_hits[practice_name] = {
        "글자": [d.metadata["citation"] for d in practice_keyword.invoke(practice_q)],
        "의미": [d.metadata["citation"] for d in practice_dense.invoke(practice_q)]}
    print(f"{practice_name:6} 글자 검색 {practice_hits[practice_name]['글자']} · 의미 검색 {practice_hits[practice_name]['의미']}")''',
   "부품 번호 질의는 BM25 가 `PN-CF-3105` 가 적힌 4.2.4(권장 조치)를 찾고, 개념 사전 임베딩은 이 번호의 뜻을 몰라 오탐 처리 절(SOP-EA-01 8)을 냅니다. 상황 질의는 반대입니다. \"온도가\"·\"바람이\"는 매뉴얼에 그 글자 그대로 없어 BM25 점수가 모두 0인데도 **BM25 는 무언가를 1위로 돌려줍니다**(SOP-EA-01 8). 의미 검색은 '열' 개념으로 HDF 점검 절차(4.2.3)를 찾습니다."),
  ("EnsembleRetriever 로 합치기", '''# EnsembleRetriever 가 두 순위를 RRF(Reciprocal Rank Fusion)로 합칩니다. 융합식을 직접 쓰지 않습니다.
# 앱과 같이 가중치는 0.5 / 0.5 로 둡니다.
# 관찰 포인트: 합친 결과에는 양쪽이 찾은 것이 모두 들어옵니다. 한쪽만 쓰면 둘 중 하나를 잃습니다.
from langchain_classic.retrievers import EnsembleRetriever

practice_hybrid = EnsembleRetriever(retrievers=[practice_dense, practice_keyword], weights=[0.5, 0.5])
practice_fused = {}
for practice_name, practice_q in (("부품 번호", practice_code_query), ("상황", practice_situation_query)):
    practice_fused[practice_name] = [d.metadata["citation"] for d in practice_hybrid.invoke(practice_q)]
    print(f"{practice_name:6} 융합 {practice_fused[practice_name]}")

assert practice_queries(practice_card)[0][1].endswith("온도 차, 회전수")
assert practice_hits["부품 번호"]["글자"] == ["MC01-MM 4.2.4"], "글자 검색이 부품 번호를 못 찾았습니다"
assert practice_hits["부품 번호"]["의미"] != ["MC01-MM 4.2.4"], "의미 검색만으로 부품 번호를 찾았습니다"
assert not practice_hits["상황"]["글자"][0].startswith("MC01-MM 4.2"), "글자 검색만으로 상황 질의를 맞혔습니다"
assert practice_hits["상황"]["의미"][0].startswith("MC01-MM 4.2")
assert "MC01-MM 4.2.4" in practice_fused["부품 번호"]
assert any(c.startswith("MC01-MM 4.2") for c in practice_fused["상황"])''',
   "두 질의 모두 합친 결과 두 개 중 하나가 정답 절입니다. 부품 번호 질의에서는 BM25 의 4.2.4 가, 상황 질의에서는 의미 검색의 4.2.3 이 살아남습니다. 융합은 한쪽 결과를 버리지 않고 순위만 다시 매깁니다. 대신 틀린 쪽의 결과(SOP-EA-01 8)도 함께 들어오므로, 근거를 쓰는 쪽(초안과 검증)이 그것을 걸러야 합니다."),
 ],
 "exercise": {
  "intro": "가중치를 `[0.9, 0.1]`(의미 검색 위주)과 `[0.1, 0.9]`(글자 검색 위주)로 바꿔 보세요. 두 질의의 융합 1위가 어떻게 바뀝니까? 실제 앱은 왜 0.5 / 0.5 로 두었을까요?",
  "code": '''# 가중치만 바꿉니다. 검색기 둘과 질의는 그대로입니다.
# 1위가 어느 쪽 검색기의 1위를 따라가는지 보세요.
practice_try_weights = [0.9, 0.1]
practice_try = EnsembleRetriever(retrievers=[practice_dense, practice_keyword], weights=practice_try_weights)
for practice_name, practice_q in (("부품 번호", practice_code_query), ("상황", practice_situation_query)):
    print(practice_name, [d.metadata["citation"] for d in practice_try.invoke(practice_q)])''',
 },
 "middle": "카드 하나에서 나온 질의 셋, 두 질의에 대한 글자 검색과 의미 검색의 결과, 그리고 융합 결과에 양쪽의 정답이 모두 들어오는 것을 확인합니다.",
 "failure": "여기 의미 검색은 개념 사전으로 뜻을 흉내 낸 것이라 **순위 자체는 대본입니다.** 실제 앱은 녹화된 OpenAI 임베딩을 쓰므로 순위가 진짜입니다. 그래도 하이브리드가 모든 것을 찾지는 못합니다. 실제 카드 111장의 유형 질의 126개 중 1개(EVT-2025-0044 HDF)는 근거 신호가 예측 유형의 것뿐이라 유형 절을 놓칩니다. 그래서 앱은 판정 기준 절을 검색에 맡기지 않고 절 번호로 바로 붙입니다.",
 "app_link": "과제 10 App 의 `evidence.py::card_queries` 가 같은 규칙으로 질의를 만들고, `evidence.py::hybrid` 가 Postgres 의 pgvector 컬렉션(`evidence.py::_pgvector_store`, 녹화된 임베딩으로 적재)과 `shared/rag/retrievers.py::keyword_retriever`(한국어 2글자 묶음 BM25)를 0.5 / 0.5 로 합칩니다. `evidence.py::find_evidence` 가 질의마다 3개씩 찾고 같은 절은 한 번만 남깁니다.",
 "next": "다음 `05_history_tool.ipynb` 에서는 매뉴얼이 아니라 정비 이력을 조회하는 Tool 을 만듭니다.",
})

# =============================================================================
# 05 시점 경계가 있는 조회 Tool
# =============================================================================
PRACTICE_HISTORY_DB = '''# 연습용 정비 이력 DB 를 임시 파일로 만듭니다. 실제 이력(410건)의 모양을 줄인 것입니다.
# 이벤트는 2025-08-22 06:30 에 왔습니다. MR-0103 은 그 **뒤**의 기록입니다.
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

PRACTICE_EVENT_AT = "2025-08-22T06:30:00+09:00"
practice_db = Path(tempfile.mkdtemp()) / "practice_history.sqlite"
with closing(sqlite3.connect(practice_db)) as practice_setup:
    practice_setup.execute("CREATE TABLE record (record_id TEXT, occurred_at TEXT, failure_type TEXT, action TEXT)")
    practice_setup.executemany("INSERT INTO record VALUES (?, ?, ?, ?)", [
        ("MR-0101", "2025-07-02T14:00:00+09:00", "HDF", "냉각팬 모듈(PN-CF-3105) 교체"),
        ("MR-0102", "2025-08-10T09:30:00+09:00", "HDF", "흡기 필터(PN-FL-3120) 교체"),
        ("MR-0103", "2025-08-25T11:00:00+09:00", "HDF", "방열판 청소 — 이벤트 뒤의 기록"),
        ("MR-0104", "2025-08-01T08:00:00+09:00", "TWF", "공구(PN-TL-1008) 교체"),
    ])
    practice_setup.commit()

def practice_connect():
    """조회마다 읽기 전용으로 엽니다. mode=ro 면 쓰기 문장은 DB 가 거부합니다."""
    return sqlite3.connect(f"file:{practice_db}?mode=ro", uri=True)'''

SPECS.append({
 "project": P, "file": "05_history_tool.ipynb",
 "title": "과제 10 · 05 · 정비 이력을 시점 경계가 있는 Tool 로 열기",
 "scenario": "정비 이력에서 \"같은 유형으로 최근에 무엇을 고쳤나\"를 찾아야 합니다. 이력 DB 에는 이벤트 **뒤**에 생긴 기록도 있습니다. 그것을 근거로 쓰면 현장에서는 있을 수 없는 근거(미래의 수리 결과)로 초안을 쓰게 되고, 평가 점수도 부풀려집니다.",
 "objectives": ["함수 시그니처와 docstring 에서 Tool 스키마가 만들어지는 것을 본다(`@tool`).",
                "`Literal` 인자가 허용값 목록이 되어 함수 앞에서 막히는 것을 확인한다.",
                "조회 시점(`before`)으로 이벤트 뒤의 기록을 막고, 시점 형식을 검사한다.",
                "읽기 전용 연결이 쓰기를 거부하는 것을 확인한다."],
 "steps": [
  ("@tool 로 이력 조회를 열기", PRACTICE_HISTORY_DB + '''

# 스키마를 손으로 적지 않습니다. @tool 이 시그니처와 docstring 에서 만듭니다.
# 관찰 포인트: Literal 로 적은 failure_type 은 스키마에 enum(허용값 목록)으로 나타납니다.
import json
from datetime import datetime
from typing import Literal
from langchain_core.tools import tool

def practice_moment(before):
    try:
        datetime.fromisoformat(before)
    except ValueError as error:
        raise ValueError(f"before 는 ISO 시각이어야 합니다. 받은 값: {before!r}") from error
    return before

@tool
def practice_history_tool(failure_type: Literal["TWF", "HDF", "PWF", "OSF"], before: str) -> str:
    """정비 이력에서 이 유형으로 수리한 최근 기록을 찾는다. before 시각보다 앞선 기록만 돌려준다."""
    with closing(practice_connect()) as db:
        rows = db.execute("SELECT record_id, occurred_at, action FROM record WHERE failure_type = ? "
                          "AND occurred_at < ? ORDER BY occurred_at DESC",
                          (failure_type, practice_moment(before))).fetchall()
    return json.dumps({"records": [dict(zip(("id", "at", "action"), r)) for r in rows]}, ensure_ascii=False)

practice_schema = practice_history_tool.args_schema.model_json_schema()
print("Tool 이름:", practice_history_tool.name)
print("failure_type 허용값:", practice_schema["properties"]["failure_type"]["enum"])
print("설명:", practice_history_tool.description[:40], "…")''',
   "Tool 이름과 설명, 인자 스키마가 함수에서 그대로 나왔습니다. `failure_type` 은 네 값만 허용하는 enum 입니다. 모델은 이 스키마를 보고 무엇을 어떤 인자로 부를지 정합니다."),
  ("시점 경계가 미래 기록을 막는다", '''# 경계 없이 같은 유형을 모두 찾는 조회와 비교합니다.
# 같은 DB, 같은 유형입니다. 다른 것은 "before 보다 앞선 기록만" 이라는 조건 하나입니다.
# 관찰 포인트: 경계가 없으면 이벤트 3일 뒤의 수리(MR-0103)가 근거로 들어옵니다.
def practice_leaky(failure_type):
    with closing(practice_connect()) as db:
        return [r[0] for r in db.execute(
            "SELECT record_id FROM record WHERE failure_type = ? ORDER BY occurred_at DESC", (failure_type,))]

practice_bounded = [r["id"] for r in json.loads(
    practice_history_tool.invoke({"failure_type": "HDF", "before": PRACTICE_EVENT_AT}))["records"]]
print("경계 있음:", practice_bounded)
print("경계 없음:", practice_leaky("HDF"))''',
   "경계가 있으면 이벤트 전의 HDF 수리 두 건(MR-0102, MR-0101)만 나옵니다. 경계가 없으면 이벤트 3일 뒤의 MR-0103 이 맨 앞에 옵니다. 최근 순으로 정렬하므로 **미래 기록이 가장 먼저 근거가 됩니다.** 오류도 경고도 없이 일어납니다."),
  ("잘못된 인자와 쓰기는 막힌다", '''# 세 가지를 시도합니다. 없는 유형, 형식이 틀린 시각, 그리고 읽기 전용 연결에서의 삭제.
# 앞의 둘은 Tool 이 막고, 마지막은 DB 가 막습니다.
# 관찰 포인트: 시각은 문자열로 비교하므로 형식이 틀리면 조용히 틀린 결과를 냅니다. 그래서 형식부터 검사합니다.
from pydantic import ValidationError

practice_blocked = {}
for practice_label, practice_args in (("없는 유형", {"failure_type": "XYZ", "before": PRACTICE_EVENT_AT}),
                                      ("틀린 시각", {"failure_type": "HDF", "before": "8월 22일"})):
    try:
        practice_history_tool.invoke(practice_args)
        practice_blocked[practice_label] = None
    except (ValidationError, ValueError) as error:
        practice_blocked[practice_label] = type(error).__name__
try:
    with closing(practice_connect()) as practice_writer:
        practice_writer.execute("DELETE FROM record")
    practice_blocked["삭제"] = None
except sqlite3.OperationalError as error:
    practice_blocked["삭제"] = str(error)
for practice_label, practice_reason in practice_blocked.items():
    print(f"  {practice_label:6} → {practice_reason}")

assert practice_schema["properties"]["failure_type"]["enum"] == ["TWF", "HDF", "PWF", "OSF"]
assert practice_bounded == ["MR-0102", "MR-0101"], "시점 경계가 지켜지지 않았습니다"
assert "MR-0103" in practice_leaky("HDF"), "경계 없는 조회에 미래 기록이 없습니다(비교가 성립하지 않습니다)"
assert practice_blocked["없는 유형"] == "ValidationError"
assert practice_blocked["틀린 시각"] == "ValueError"
assert practice_blocked["삭제"] and "readonly" in practice_blocked["삭제"]''',
   "없는 유형은 함수에 닿기 전에 스키마 검증(`ValidationError`)이 막고, \"8월 22일\" 같은 시각은 함수 첫 줄의 형식 검사가 막습니다. 삭제는 DB 가 \"readonly\" 로 거부합니다. Tool 은 근거를 **읽기만** 합니다."),
 ],
 "exercise": {
  "intro": "`practice_try_before` 를 이벤트 시각보다 이른 \"2025-08-05T00:00:00+09:00\" 이나 더 늦은 \"2025-09-01T00:00:00+09:00\" 으로 바꿔 보세요. 결과가 어떻게 바뀝니까? 앱이 왜 `before` 에 EventCard 의 `detected_at` 을 그대로 넣으라고 Agent 에게 지시하는지 생각해 보세요.",
  "code": '''# 조회 시점만 바꿉니다. 유형과 DB 는 그대로입니다.
# 늦은 시점을 넣으면 경계가 있어도 미래 기록이 들어옵니다. 경계의 값이 맞아야 경계가 의미 있습니다.
practice_try_before = "2025-08-05T00:00:00+09:00"
print(json.loads(practice_history_tool.invoke({"failure_type": "HDF", "before": practice_try_before}))["records"])''',
 },
 "middle": "Tool 스키마의 enum, 시점 경계가 있을 때와 없을 때의 조회 결과, 그리고 없는 유형·틀린 시각·삭제가 각각 무엇에 막히는지 확인합니다.",
 "failure": "시점 경계는 `before` 값이 맞을 때만 의미가 있습니다. 모델이 시각을 지어내거나 \"오늘\"을 넣으면 경계가 있어도 미래 기록이 들어옵니다. 그래서 앱은 Agent 에게 EventCard 의 `detected_at` 을 그대로 넣으라고 지시하고, 결과를 다시 코드로 확인합니다. Test 가 시나리오마다 \"돌려준 기록이 모두 이벤트보다 앞선다\"를 검사합니다.",
 "app_link": "과제 10 App 의 `tools.py::same_type_history` 가 같은 모양의 Tool 이고, `tools.py::_moment` 가 시각 형식을 막습니다. 조회는 `history.py::HistoryStore` 가 Postgres 표에서 맡으며 조회마다 읽기 전용 세션(`postgres.py::connect`)을 새로 엽니다. 이 Notebook 의 임시 SQLite 는 연습용입니다. Tool 은 이것 말고도 판정 기준(`check_criteria`), 과거 오탐 점검, 마지막 공구 교체를 엽니다.",
 "next": "다음 `06_lookup_agent.ipynb` 에서는 이 Tool 들을 Agent 에게 쥐여 주고, Agent 가 실제로 무엇을 불렀는지 기록에서 확인합니다.",
})

# =============================================================================
# 06 조회 Agent 와 실행 감사
# =============================================================================
PRACTICE_LOOKUP_TOOLS = '''# 이력 담당이 쓸 Tool 둘입니다. 판정 기준을 계산하는 것과 같은 유형의 이력을 찾는 것.
# 어느 유형의 이력을 찾을지는 판정 결과를 봐야 압니다. 그래서 둘 사이에 의존이 있습니다.
import json
from typing import Literal
from langchain_core.tools import tool

PRACTICE_HISTORY = {"OSF": ["MR-0201"], "TWF": ["MR-0104", "MR-0188"], "HDF": ["MR-0102"]}

@tool
def check_criteria(tool_wear_min: float, torque_nm: float) -> str:
    """매뉴얼 판정 기준을 센서 값에 적용해 기준이 성립한 유형을 돌려준다."""
    met = (["TWF"] if tool_wear_min >= 200 else []) + (["OSF"] if tool_wear_min * torque_nm > 11000 else [])
    return json.dumps({"met": met})

@tool
def same_type_history(failure_type: Literal["TWF", "HDF", "PWF", "OSF"], before: str) -> str:
    """정비 이력에서 이 유형으로 수리한 기록을 찾는다. before 시각보다 앞선 기록만 돌려준다."""
    return json.dumps({"records": PRACTICE_HISTORY.get(failure_type, [])})'''

SPECS.append({
 "project": P, "file": "06_lookup_agent.ipynb",
 "title": "과제 10 · 06 · 조회 Agent 를 돌리고 실제로 무엇을 불렀는지 감사하기",
 "scenario": "이력 담당 Agent 는 먼저 판정 기준을 확인하고, 그 결과를 본 뒤 **예측 유형과 기준이 성립한 유형 모두**의 이력을 찾아야 합니다. 예측은 OSF 인데 기준은 TWF 가 성립하는 카드에서 OSF 이력만 찾고 끝내면 TWF 이력을 놓칩니다. 실제 모델(gpt-4.1-mini)은 순서는 지켰지만 필요한 유형을 빠뜨린 적이 있습니다.",
 "objectives": ["`create_agent` 에 Tool 을 쥐여 주고 `ModelCallLimitMiddleware` 로 판단 횟수에 상한을 건다.",
                "Agent 가 남긴 메시지 기록에서 턴마다 무엇을 불렀는지 읽는다.",
                "필요한 조회 목록과 대조해 의존 순서 위반과 빠진 유형을 찾는다."],
 "steps": [
  ("Agent 에 Tool 을 쥐여 주고 돌리기", PRACTICE_LOOKUP_TOOLS + '''

# 루프는 create_agent 가 돌리고, 판단 횟수 상한은 ModelCallLimitMiddleware 가 셉니다.
# 관찰 포인트: 대본은 "무엇을 부를지" 만 정합니다. Tool 은 진짜로 실행되어 ToolMessage 를 남깁니다.
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.messages import AIMessage

''' + SCRIPTED_MODEL + '''

PRACTICE_EVENT_AT = "2025-09-14T02:30:00+09:00"
PRACTICE_PREDICTED = "OSF"
PRACTICE_BUDGET = 4

def practice_run(script, budget=PRACTICE_BUDGET):
    agent = create_agent(PracticeScriptedModel(messages=iter(script)), [check_criteria, same_type_history],
                         middleware=[ModelCallLimitMiddleware(run_limit=budget, exit_behavior="end")])
    return agent.invoke({"messages": [("user", "EVT-2025-0106 의 근거를 모아 주세요")]})["messages"]

practice_script = [
    AIMessage(content="", tool_calls=[{"name": "check_criteria", "args": {"tool_wear_min": 214, "torque_nm": 48.0}, "id": "c1"}]),
    AIMessage(content="", tool_calls=[
        {"name": "same_type_history", "args": {"failure_type": "OSF", "before": PRACTICE_EVENT_AT}, "id": "h1"},
        {"name": "same_type_history", "args": {"failure_type": "TWF", "before": PRACTICE_EVENT_AT}, "id": "h2"}]),
    AIMessage(content="판정과 이력 조회를 마쳤습니다."),
]
practice_agent = practice_run(practice_script)
for practice_message in practice_agent:
    practice_calls = [c["name"] + str(c["args"].get("failure_type", "")) for c in getattr(practice_message, "tool_calls", [])]
    print(f"  {type(practice_message).__name__:12} {practice_calls or str(practice_message.content)[:50]}")''',
   "Agent 는 세 번 판단했습니다. 첫 턴에 판정 기준을 부르고, 결과(TWF 성립)를 본 둘째 턴에 OSF 와 TWF 이력을 함께 부르고, 셋째 턴에 끝냈습니다. ToolMessage 가 실제 실행 결과입니다."),
  ("기록에서 감사하기", '''# 대본을 믿지 않고 기록에서 읽습니다. AIMessage 의 tool_calls 마다 몇 번째 턴인지 셉니다.
# 필요한 유형은 "예측 유형 + 판정 기준이 성립한 유형" 입니다. 판정 결과는 ToolMessage 에서 꺼냅니다.
# 관찰 포인트: 의존 순서(이력은 판정 다음 턴)와 빠진 유형을 둘 다 봅니다. 둘은 다른 실패입니다.
from langchain_core.messages import ToolMessage

def practice_audit(messages):
    turn, turns, called, met = 0, {}, [], []
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            turn += 1
            for call in message.tool_calls:
                turns.setdefault(call["name"], []).append(turn)
                if call["name"] == "same_type_history":
                    called.append(call["args"]["failure_type"])
        if isinstance(message, ToolMessage) and '"met"' in str(message.content):
            met = json.loads(message.content)["met"]
    needed = list(dict.fromkeys([PRACTICE_PREDICTED, *met]))
    first_criteria = min(turns.get("check_criteria", [99]))
    return {"needed": needed, "called": called,
            "missing": [t for t in needed if t not in called],
            "dependency_respected": bool(turns.get("same_type_history")) and
                                    all(t > first_criteria for t in turns["same_type_history"])}

practice_ok = practice_audit(practice_agent)
print(practice_ok)''',
   "필요한 유형은 OSF(예측)와 TWF(기준 성립)이고, 둘 다 불렀으며 둘 다 판정 다음 턴이었습니다. 이 감사는 대본이 무엇이었는지 모릅니다. 메시지 기록만 봅니다. 그래서 live 에서 실제 모델이 돌 때도 같은 함수로 확인할 수 있습니다."),
  ("빠뜨리면, 그리고 상한에 걸리면", '''# 실패 둘을 만듭니다. 첫째는 판정을 보기 전에 예측 유형 이력만 부르고 끝내는 대본입니다.
# 둘째는 정상 대본이지만 판단 횟수 상한을 1 로 줄인 경우입니다.
# 관찰 포인트: 둘 다 오류 없이 끝납니다. 감사가 없으면 TWF 이력이 빠진 것을 아무도 모릅니다.
practice_skipping = practice_run([
    AIMessage(content="", tool_calls=[
        {"name": "check_criteria", "args": {"tool_wear_min": 214, "torque_nm": 48.0}, "id": "c1"},
        {"name": "same_type_history", "args": {"failure_type": "OSF", "before": PRACTICE_EVENT_AT}, "id": "h1"}]),
    AIMessage(content="조회를 마쳤습니다."),
])
practice_skip_audit = practice_audit(practice_skipping)
practice_cut = practice_run(practice_script, budget=1)
practice_cut_audit = practice_audit(practice_cut)
print("빠뜨린 대본:", practice_skip_audit)
print("상한 1     :", practice_cut_audit, "· 마지막 메시지:", practice_cut[-1].content[:40])

assert practice_ok == {"needed": ["OSF", "TWF"], "called": ["OSF", "TWF"], "missing": [], "dependency_respected": True}
assert practice_skip_audit["missing"] == ["TWF"] and practice_skip_audit["dependency_respected"] is False
assert practice_cut_audit["missing"] == ["OSF", "TWF"], "상한 1 인데 이력 조회까지 갔습니다"
assert "limit" in practice_cut[-1].content''',
   "빠뜨린 대본은 판정과 같은 턴에 OSF 이력을 불러 의존 순서를 어겼고(`dependency_respected=False`), TWF 를 빠뜨렸습니다. 상한 1 은 판정만 하고 멈춰 이력을 하나도 찾지 못했고, 마지막 메시지가 상한에 걸렸다고 말합니다. **둘 다 예외 없이 끝났습니다.** 그래서 앱은 감사 결과로 빠진 유형을 코드가 채웁니다."),
 ],
 "exercise": {
  "intro": "`practice_try_budget` 을 2, 3 으로 바꿔 정상 대본을 다시 돌려 보세요. 몇부터 빠진 유형이 없어집니까? 정상 경로에 판단이 몇 번 필요한지와 앱이 상한을 4 로 둔 이유를 연결해 보세요.",
  "code": '''# 상한만 바꿔 같은 대본을 돌립니다. 판단 횟수 = AIMessage 를 만든 횟수입니다.
# 상한이 정상 경로보다 작으면 일을 다 못 하고, 너무 크면 헛도는 모델을 오래 둡니다.
practice_try_budget = 2
practice_try = practice_run(practice_script, budget=practice_try_budget)
print("상한", practice_try_budget, "→", practice_audit(practice_try), "· 끝:", practice_try[-1].content[:30])''',
 },
 "middle": "정상 대본의 턴별 호출, 감사 결과(필요한 유형·부른 유형·빠진 유형·의존 순서), 그리고 빠뜨린 대본과 상한 1 에서 감사가 무엇을 잡는지 확인합니다.",
 "failure": "감사는 \"불렀는가\"를 볼 뿐 \"제대로 돌았는가\"는 따로 봐야 합니다. MCP 를 거치면 실패한 호출이 정상 결과 글자로 돌아와, 부른 것만 세면 실패를 성공으로 셉니다(다음 Notebook). 또 상한에 걸린 Agent 는 예외 없이 끝나므로, 응답이 상한 소진을 밝혀야 사람이 압니다.",
 "app_link": "과제 10 App 의 `lookup.py::fixture_plan` 이 같은 순서의 대본(fixture)이고, live 에서는 실제 모델이 스스로 고릅니다. `lookup.py::read_run` 이 기록에서 의존 순서와 빠진 유형을 읽고, `lookup.py::STEP_BUDGET` 이 상한 4 입니다. Agent 조립은 `shared/tools/agent.py::build_agent` 가 맡습니다. 빠진 유형은 `review.py::collect_history` 가 코드로 채우고 응답의 `filled_history_types` 에 남깁니다.",
 "next": "다음 `07_mcp_history_server.ipynb` 에서는 같은 Tool 을 별도 Process 의 MCP 서버로 엽니다.",
})

# =============================================================================
# 07 MCP 로 이력 Tool 열기
# =============================================================================
SPECS.append({
 "project": P, "file": "07_mcp_history_server.ipynb",
 "title": "과제 10 · 07 · 정비 이력 시스템을 MCP 서버로 열기",
 "scenario": "정비 이력 시스템은 설비팀이 운영합니다. 우리 앱 안의 함수가 아니라 **별도 Process** 라고 생각해야 합니다. 그 시스템이 MCP 서버로 Tool 을 열면 우리 Agent 는 import 없이 그 Tool 을 받아 씁니다. 대신 열어 주는 Tool 은 **읽기 전용**이어야 하고, 실패가 어떤 모양으로 오는지 알아야 합니다.",
 "objectives": ["FastMCP 로 서버를 만들고 읽기 전용 목록에 있는 Tool 만 연다.",
                "`MultiServerMCPClient` 로 Tool 을 받아 오고 그것이 LangChain Tool 인 것을 확인한다.",
                "MCP 를 거친 실패가 예외가 아니라 결과 글자로 오는 것을 보고, 결과 모양으로 성공을 판단한다."],
 "steps": [
  ("읽기 전용 Tool 만 여는 서버", '''# 서버는 별도 파일입니다. 같은 Process 가 아니라는 것이 핵심입니다.
# 서버에는 삭제 함수도 있지만 읽기 전용 목록에 없으므로 열지 않습니다.
# 관찰 포인트: 서버 쪽에는 LangChain 이 없습니다. MCP 는 표준이라 서로를 모릅니다.
import sys
import tempfile
from pathlib import Path

practice_server_code = """
import json
from typing import Literal
from mcp.server.fastmcp import FastMCP

HISTORY = {"HDF": [{"id": "MR-0102", "action": "흡기 필터 교체"}], "TWF": [{"id": "MR-0104", "action": "공구 교체"}]}

def same_type_history(failure_type: Literal["TWF", "HDF", "PWF", "OSF"], before: str) -> str:
    \\"\\"\\"정비 이력에서 이 유형으로 수리한 기록을 찾는다. before 시각보다 앞선 기록만 돌려준다.\\"\\"\\"
    return json.dumps({"records": HISTORY.get(failure_type, [])}, ensure_ascii=False)

def delete_record(record_id: str) -> str:
    \\"\\"\\"기록을 지운다. 이 서버는 이 함수를 열지 않는다.\\"\\"\\"
    return "deleted " + record_id

READ_ONLY = ("same_type_history",)
server = FastMCP("practice-history-readonly")
for fn in (same_type_history, delete_record):
    if fn.__name__ in READ_ONLY:
        server.add_tool(fn)

if __name__ == "__main__":
    server.run()
"""
practice_server_path = Path(tempfile.mkdtemp()) / "practice_history_server.py"
practice_server_path.write_text(practice_server_code, encoding="utf-8")
print("서버 파일:", practice_server_path.name, "· 정의된 함수 2개, 읽기 전용 목록 1개")''',
   "서버 파일에는 함수가 둘 있지만 읽기 전용 목록에 있는 `same_type_history` 하나만 서버에 등록합니다. 쓰기 Tool 이 열리지 않는다는 것은 **목록에서 가져다 등록하는 구조**가 보장합니다."),
  ("붙어서 Tool 받아 오기", '''# MultiServerMCPClient 가 서버 Process 를 띄우고 stdio 로 붙어 Tool 목록을 받아 옵니다.
# 세션과 전송을 직접 만들지 않습니다.
# MCP Tool 은 비동기 전용입니다. Jupyter 는 이미 이벤트 루프가 돌고 있어 asyncio.run 을 바로 쓸 수 없으므로,
# 별도 스레드에서 돌립니다(Jupyter 와 일반 Python 양쪽에서 같은 코드가 돕니다).
# Windows 에서 하위 Process(MCP 서버)를 띄우려면 Proactor 루프가 필요해 루프를 직접 고릅니다.
# 관찰 포인트: 받아 온 것은 StructuredTool 이고, Literal 인자는 서버를 건너와도 enum 으로 남습니다.
import asyncio
from concurrent.futures import ThreadPoolExecutor
from langchain_mcp_adapters.client import MultiServerMCPClient

def practice_new_loop():
    return asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.SelectorEventLoop()

def practice_wait(coroutine):
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine, loop_factory=practice_new_loop).result()

practice_servers = {"history": {"command": sys.executable, "args": [str(practice_server_path)], "transport": "stdio"}}

async def practice_fetch():
    return await MultiServerMCPClient(practice_servers).get_tools()

practice_mcp_tools = practice_wait(practice_fetch())
for practice_tool in practice_mcp_tools:
    print(f"  {practice_tool.name} · {type(practice_tool).__name__} · failure_type {practice_tool.args['failure_type'].get('enum')}")''',
   "열린 Tool 은 `same_type_history` 하나이고, 타입은 LangChain 의 `StructuredTool` 입니다. 안에서 만든 Tool 과 똑같이 Agent 에 넣을 수 있습니다. `delete_record` 는 목록에 없습니다."),
  ("실패는 글자로 온다", '''# 정상 인자와 없는 유형("XYZ")으로 각각 불러 봅니다.
# 안에서 만든 Tool 이었다면 없는 유형은 ValidationError 예외였습니다(Notebook 05).
# 관찰 포인트: MCP 를 거치면 서버 쪽 오류가 예외가 아니라 **정상 결과의 글자**로 돌아옵니다.
import json

def practice_text(result):
    return "".join(block.get("text", "") for block in result) if isinstance(result, list) else str(result)

def practice_succeeded(result):
    try:
        return "records" in json.loads(practice_text(result))
    except json.JSONDecodeError:
        return False

async def practice_call(args):
    return await practice_mcp_tools[0].ainvoke(args)

practice_good = practice_wait(practice_call({"failure_type": "HDF", "before": "2025-08-22T06:30:00+09:00"}))
practice_bad = practice_wait(practice_call({"failure_type": "XYZ", "before": "2025-08-22T06:30:00+09:00"}))
print("정상 :", practice_text(practice_good)[:60], "→ 성공으로 셈:", practice_succeeded(practice_good))
print("잘못 :", practice_text(practice_bad)[:60], "→ 성공으로 셈:", practice_succeeded(practice_bad))

assert {t.name for t in practice_mcp_tools} == {"same_type_history"}, "읽기 전용 목록 밖의 Tool 이 열렸습니다"
assert practice_mcp_tools[0].args["failure_type"]["enum"] == ["TWF", "HDF", "PWF", "OSF"]
assert practice_succeeded(practice_good)
assert "Error" in practice_text(practice_bad) and not practice_succeeded(practice_bad), "오류 글자를 성공으로 셌습니다"''',
   "정상 호출은 기록이 담긴 JSON 이고, 없는 유형은 `Error executing tool …` 으로 시작하는 **글자**입니다. 예외가 나지 않았으므로 \"예외가 없으면 성공\"으로 세면 실패를 성공으로 셉니다. 그래서 결과에 기대한 키(`records`)가 있는지로 성공을 판단합니다."),
 ],
 "exercise": {
  "intro": "서버 코드의 `READ_ONLY` 에 \"delete_record\" 를 더해 서버 파일을 다시 쓰고, 2단계부터 다시 실행해 보세요. 무엇이 열립니까? 실제 앱은 이런 실수를 어떻게 막는지 `mcp_server.py` 와 비교해 보세요.",
  "code": '''# 읽기 전용 목록을 바꿔 서버 파일을 다시 씁니다. 실행 후 2단계 셀을 다시 돌리세요.
# 실제 앱은 목록 밖 Tool 을 등록하려 하면 서버가 아예 뜨지 않게 막습니다.
practice_try_read_only = '("same_type_history",)'
practice_server_path.write_text(practice_server_code.replace('("same_type_history",)', practice_try_read_only), encoding="utf-8")
print("서버 파일의 읽기 전용 목록:", practice_try_read_only)''',
 },
 "middle": "서버가 정의한 함수와 실제로 연 Tool, 받아 온 Tool 의 타입과 enum, 그리고 정상 호출과 잘못된 호출이 각각 어떤 모양으로 돌아오는지 확인합니다.",
 "failure": "MCP 서버가 뜨지 않으면 Tool 목록이 비어 옵니다. 그것을 \"Tool 이 없다\"로 넘기면 Agent 가 아무것도 못 하는 이유를 끝까지 모릅니다. 또 MCP 의 시간 초과 취소는 서버까지 가지 않습니다. 요청이 이미 실렸으면 서버는 실행을 마치고, 재시도하면 같은 Tool 이 두 번 돕니다. **쓰기 Tool 을 열지 않는 것**이 업무 데이터가 두 번 바뀌지 않는 유일한 근거입니다.",
 "app_link": "과제 10 App 의 `mcp_server.py::server` 가 `tools.py` 의 읽기 전용 목록에서 Tool 을 가져와 등록하고, 목록 밖 Tool 을 등록하려 하면 뜨지 않습니다. `MCP_MODE=on` 이면 `lookup.py::lookup_tools` 가 `shared/tools/mcp.py::mcp_tools` 로 이 서버를 자식 Process 로 띄워 Tool 을 받습니다. `lookup.py::succeeded` 가 결과 모양까지 보고 성공을 판단합니다.",
 "next": "다음 `08_draft_chain.ipynb` 에서는 모은 근거로 LLM 이 초안을 쓰고, 그 초안을 검사합니다.",
})

# =============================================================================
# 08 초안 체인과 인용 검증
# =============================================================================
SPECS.append({
 "project": P, "file": "08_draft_chain.ipynb",
 "title": "과제 10 · 08 · 초안을 형식으로 받고 인용을 검사하기",
 "scenario": "근거가 모이면 LLM 이 원인 후보와 점검 절차 초안을 씁니다. 그런데 LLM 은 근거 목록에 없는 절 번호를 지어내거나(\"MC01-MM 4.2.5\"), 정비 기술자가 확인하기 전인데 원인을 \"확정\"이라고 쓰거나, 아예 형식을 깨뜨릴 수 있습니다. 이런 초안이 사람에게 그대로 가면 안 됩니다.",
 "objectives": ["`프롬프트 | 모델 | PydanticOutputParser` 로 초안을 형식 있는 객체로 받는다.",
                "근거 목록에 없는 인용과 단정 표현을 코드로 찾는다.",
                "형식이 깨진 출력을 검증 실패와 같게 다룬다."],
 "steps": [
  ("프롬프트 | 모델 | 파서", '''# 초안 형식을 Pydantic 으로 정합니다. 근거 ID 가 하나도 없는 후보·단계는 형식부터 받지 않습니다.
# 파서가 형식 안내문(format_instructions)을 만들어 프롬프트에 넣습니다.
# 관찰 포인트: 세 조각이 | 로 이어져 하나의 Runnable 이 됩니다. 모델은 대본 JSON 을 내는 대역입니다.
import json
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

class PracticeCause(BaseModel):
    rank: int = Field(ge=1)
    failure_type: str
    rationale: str
    evidence_ids: list[str] = Field(min_length=1)

class PracticeStep(BaseModel):
    order: int = Field(ge=1)
    instruction: str
    evidence_ids: list[str] = Field(min_length=1)

class PracticeDraft(BaseModel):
    cause_candidates: list[PracticeCause]
    inspection_steps: list[PracticeStep]

practice_parser = PydanticOutputParser(pydantic_object=PracticeDraft)
practice_prompt = ChatPromptTemplate.from_messages([
    ("system", "근거 목록에 있는 ID 만 인용하세요. 원인은 추정 후보입니다.\\n{format_instructions}"),
    ("human", "근거 목록: {evidence}"),
]).partial(format_instructions=practice_parser.get_format_instructions())

practice_good_json = json.dumps({
    "cause_candidates": [{"rank": 1, "failure_type": "HDF", "rationale": "흡기 필터 막힘 가능성. 같은 유형 최근 수리 MR-0102 참고",
                          "evidence_ids": ["MC01-MM 4.2.2", "MR-0102"]}],
    "inspection_steps": [{"order": 1, "instruction": "4.2.3 의 점검 절차를 따른다", "evidence_ids": ["MC01-MM 4.2.3"]}],
}, ensure_ascii=False)

def practice_chain_with(reply):
    return practice_prompt | GenericFakeChatModel(messages=iter([reply])) | practice_parser

practice_chain = practice_chain_with(practice_good_json)
practice_evidence = ["MC01-MM 4.2.2", "MC01-MM 4.2.3", "MR-0102"]
practice_draft = practice_chain.invoke({"evidence": ", ".join(practice_evidence)})
print("체인:", type(practice_chain).__name__)
print("받은 초안:", type(practice_draft).__name__, "· 후보", [c.failure_type for c in practice_draft.cause_candidates],
      "· 단계", len(practice_draft.inspection_steps))''',
   "체인은 `RunnableSequence` 하나이고, 모델의 JSON 글자는 파서를 지나 `PracticeDraft` 객체가 되었습니다. 이제부터 우리가 쓰는 것은 형식이 맞는 필드뿐입니다."),
  ("인용과 표현을 코드로 검사", '''# 형식이 맞아도 내용은 틀릴 수 있습니다. 인용한 ID 가 근거 목록에 있는지, 단정 표현이 있는지 봅니다.
# 단정 표현 목록은 SOP-EA-01 7.2(정비 기술자 확인 전에는 원인을 단정하지 않는다)에서 왔습니다.
# 관찰 포인트: 지어낸 절 번호는 형식 검사를 통과합니다. 근거 목록과 대조해야 잡힙니다.
PRACTICE_ASSERTIVE = ("확정", "확실", "틀림없", "분명히")

def practice_validate(draft, evidence_ids):
    errors = []
    for label, items in (("원인 후보", draft.cause_candidates), ("점검 단계", draft.inspection_steps)):
        for item in items:
            unknown = [i for i in item.evidence_ids if i not in evidence_ids]
            if unknown:
                errors.append(f"{label}가 근거 목록에 없는 ID 를 인용했습니다: {unknown}")
            text = getattr(item, "rationale", None) or getattr(item, "instruction", "")
            if any(word in text for word in PRACTICE_ASSERTIVE):
                errors.append(f"{label}가 원인을 단정합니다: {text[:30]}")
    return errors

practice_invented = practice_chain_with(json.dumps({
    "cause_candidates": [{"rank": 1, "failure_type": "HDF", "rationale": "흡기 필터 막힘으로 확정",
                          "evidence_ids": ["MC01-MM 4.2.2"]}],
    "inspection_steps": [{"order": 1, "instruction": "필터를 교체한다", "evidence_ids": ["MC01-MM 4.2.5"]}],
}, ensure_ascii=False)).invoke({"evidence": ", ".join(practice_evidence)})
print("좋은 초안 :", practice_validate(practice_draft, practice_evidence))
for practice_error in practice_validate(practice_invented, practice_evidence):
    print("지어낸 초안:", practice_error)''',
   "좋은 초안은 오류가 없습니다. 지어낸 초안은 형식은 통과했지만 두 가지가 잡혔습니다. 원인 후보의 \"확정\"(단정 표현)과, 점검 단계가 인용한 4.2.5(근거 목록에 없는 절)입니다. 이 오류 목록이 그대로 모델에게 다시 쓰라는 피드백이 됩니다."),
  ("형식이 깨진 출력", '''# 모델이 JSON 대신 문장으로 답한 경우와, 근거 ID 를 비운 경우입니다.
# 둘 다 파서가 OutputParserException 을 냅니다. 앱은 이것을 "검사 실패"와 같게 다룹니다.
# 관찰 포인트: 형식 오류를 예외로 흘려보내면 요청 전체가 500 으로 끝납니다. 오류 목록에 넣어 다시 쓰게 합니다.
from langchain_core.exceptions import OutputParserException

practice_broken = {}
for practice_label, practice_reply in (
        ("문장으로 답함", "원인은 아마 흡기 필터 막힘입니다."),
        ("근거를 비움", json.dumps({"cause_candidates": [{"rank": 1, "failure_type": "HDF", "rationale": "필터", "evidence_ids": []}],
                                    "inspection_steps": []}))):
    try:
        practice_chain_with(practice_reply).invoke({"evidence": ", ".join(practice_evidence)})
        practice_broken[practice_label] = None
    except OutputParserException:
        practice_broken[practice_label] = "초안 형식이 맞지 않습니다"
print(practice_broken)

assert type(practice_chain).__name__ == "RunnableSequence"
assert practice_validate(practice_draft, practice_evidence) == []
practice_invented_errors = practice_validate(practice_invented, practice_evidence)
assert any("근거 목록에 없는" in e for e in practice_invented_errors), "지어낸 절 번호를 놓쳤습니다"
assert any("단정" in e for e in practice_invented_errors), "단정 표현을 놓쳤습니다"
assert all(practice_broken.values()), "형식이 깨진 출력이 통과했습니다"''',
   "문장으로 답한 출력과 근거 ID 를 비운 출력 모두 파서에서 막혔습니다. 근거 ID 가 빈 원인 후보는 `min_length=1` 때문에 형식부터 성립하지 않습니다. **형식 검사(파서)와 내용 검사(근거 대조)는 다른 층**이고, 둘 다 있어야 합니다."),
 ],
 "exercise": {
  "intro": "`practice_try_reply` 의 rationale 을 \"필터 막힘이 분명히 원인\" 이나 \"필터 막힘 가능성\" 으로, evidence_ids 를 `[\"MR-0999\"]` 로 바꿔 보세요. 어느 검사가 어떤 문장으로 잡습니까? 단정 표현 목록만으로 막을 수 없는 표현도 생각해 보세요.",
  "code": '''# 모델 출력만 바꿔 같은 체인과 검사를 돌립니다.
# 형식이 깨지면 예외, 형식이 맞으면 검사 오류 목록이 나옵니다.
practice_try_reply = json.dumps({
    "cause_candidates": [{"rank": 1, "failure_type": "HDF", "rationale": "필터 막힘이 분명히 원인", "evidence_ids": ["MR-0999"]}],
    "inspection_steps": [{"order": 1, "instruction": "4.2.3 을 따른다", "evidence_ids": ["MC01-MM 4.2.3"]}],
}, ensure_ascii=False)
print(practice_validate(practice_chain_with(practice_try_reply).invoke({"evidence": ""}), practice_evidence))''',
 },
 "middle": "체인의 타입, 파서가 돌려준 객체, 좋은 초안과 지어낸 초안의 검사 결과, 그리고 형식이 깨진 두 출력이 파서에서 막히는 것을 확인합니다.",
 "failure": "검사를 통과했다고 초안이 맞는 것은 아닙니다. 실제 live 실측에서 gpt-4.1-mini 의 초안 10건이 모두 검사를 통과했지만, 한 건(S02)은 출력 과다(PWF 상한) 카드에 출력 부족 갈래의 점검 절차를 섞었습니다. 인용한 절은 근거 목록에 있었기 때문입니다. 그래서 초안은 사람이 검토하기 전에는 보고서가 되지 않습니다.",
 "app_link": "과제 10 App 의 `drafting.py::write_draft` 가 `PROMPT | model` 다음에 `drafting.py::PARSER`(PydanticOutputParser)로 초안을 받고, 형식 오류는 `DraftParseError` 로 바꿔 검사 실패로 돌립니다. 내용 검사는 `routing.py::validate_response` 가 맡고, 단정 표현 목록은 `routing.py::ASSERTIVE` 입니다. 검사는 이것 말고도 후보 순위·단계 번호가 1부터 이어지는지, 부품 번호가 근거에 있는지를 봅니다.",
 "next": "다음 `09_route_and_retry.ipynb` 에서는 경로를 규칙으로 나누고, 검사에 실패한 초안을 횟수 제한 안에서 다시 쓰게 합니다.",
})

# =============================================================================
# 09 경로 분기와 재작성 루프
# =============================================================================
PRACTICE_ROUTE = '''# SOP-EA-01 6장(escalation 조건)과 9장(처리 경로)을 그대로 함수로 옮깁니다. LLM 에게 묻지 않습니다.
# 카드는 판정 결과까지 붙은 모양입니다. met 은 판정 기준이 성립한 유형입니다.
def practice_route(card):
    reasons = []
    if len(card["candidates"]) >= 2:
        reasons.append("ESC-2")
    if card["met"] and card["predicted"] not in card["met"]:
        reasons.append("ESC-3")
    if card["evidence"] == 0:
        reasons.append("ESC-4")
    if not card["met"] and card["severity"] == "alarm":
        reasons.append("ESC-7")
    if reasons:
        return "escalation", reasons
    if not card["met"]:
        return "inspect_only", ["SOP-EA-01 8"]
    return "grounded_draft", []

practice_cards = {
    "S01 HDF 정탐": {"predicted": "HDF", "candidates": ["HDF"], "met": ["HDF"], "severity": "warning", "evidence": 9},
    "S08 예측≠판정": {"predicted": "OSF", "candidates": ["OSF"], "met": ["TWF"], "severity": "alarm", "evidence": 11},
    "S05 오탐 경고": {"predicted": "HDF", "candidates": ["HDF"], "met": [], "severity": "warning", "evidence": 7},
}'''

SPECS.append({
 "project": P, "file": "09_route_and_retry.ipynb",
 "title": "과제 10 · 09 · 규칙으로 경로를 나누고 초안은 횟수 제한 안에서 다시 쓰기",
 "scenario": "모든 이벤트에 초안을 쓰면 안 됩니다. 예측과 판정이 어긋나면 사람에게 넘기고(escalation), 판정 기준에 해당하지 않는 경고는 점검만 권합니다(inspect_only). 초안을 쓰는 경로에서는 검사에 실패한 초안을 다시 쓰게 하되, 끝없이 다시 쓰게 둘 수는 없습니다.",
 "objectives": ["SOP 의 escalation 조건과 처리 경로를 규칙 함수로 만든다.",
                "`add_conditional_edges` 로 경로마다 다른 노드로 보낸다.",
                "검사 실패 시 초안 노드로 되돌아가되, 횟수 상한에서 멈춘다."],
 "steps": [
  ("경로를 규칙으로", PRACTICE_ROUTE + '''

# 관찰 포인트: 경로는 세 가지뿐이고, escalation 에는 반드시 ESC 코드가 사유로 붙습니다.
for practice_name, practice_card in practice_cards.items():
    print(f"  {practice_name:10} → {practice_route(practice_card)}")''',
   "S01 은 예측(HDF)과 판정이 같아 초안을 쓰고, S08 은 예측 OSF·판정 TWF 라 ESC-3 으로 넘기며, S05 는 판정 기준에 해당하는 것이 없는 경고라 오탐 점검(SOP-EA-01 8)으로 갑니다. 같은 카드는 언제나 같은 경로입니다."),
  ("경로마다 다른 노드, 실패하면 다시 쓰기", '''# decide 뒤에서 경로마다 다른 노드로 갈라지고, 셋 다 validate 로 모입니다.
# validate 가 오류를 내면 draft 로 되돌아갑니다. 초안 대역은 미리 준 순서대로 초안을 냅니다.
# 관찰 포인트: trace 에 draft 와 validate 가 두 번씩 남습니다. 첫 초안은 없는 절(4.2.5)을 인용했습니다.
import operator
from typing import Annotated, TypedDict
from langgraph.graph import END, START, StateGraph

PRACTICE_MAX_ATTEMPTS = 2

class PracticeState(TypedDict, total=False):
    card: dict
    route: str
    reasons: list
    draft: str
    attempts: int
    errors: list
    trace: Annotated[list, operator.add]

def practice_graph(drafts):
    queue = iter(drafts)
    def decide(state):
        route, reasons = practice_route(state["card"])
        return {"route": route, "reasons": reasons, "attempts": 0, "trace": [f"decide:{route}"]}
    def draft(state):
        attempts = state["attempts"] + 1
        return {"draft": next(queue), "attempts": attempts, "trace": [f"draft#{attempts}"]}
    def escalate(state):
        return {"draft": "", "trace": ["escalate"]}
    def inspect(state):
        return {"draft": "SOP-EA-01 8 에 따라 점검", "trace": ["inspect"]}
    def validate(state):
        errors = ["근거 목록에 없는 절: MC01-MM 4.2.5"] if "4.2.5" in state["draft"] else []
        return {"errors": errors, "trace": ["validate:" + ("오류" if errors else "통과")]}
    def after_validate(state):
        if state["errors"] and state["route"] == "grounded_draft" and state["attempts"] < PRACTICE_MAX_ATTEMPTS:
            return "draft"
        return "end"
    graph = StateGraph(PracticeState)
    for name, node in (("decide", decide), ("draft", draft), ("escalate", escalate),
                       ("inspect", inspect), ("validate", validate)):
        graph.add_node(name, node)
    graph.add_edge(START, "decide")
    graph.add_conditional_edges("decide", lambda s: s["route"], {
        "grounded_draft": "draft", "escalation": "escalate", "inspect_only": "inspect"})
    for name in ("draft", "escalate", "inspect"):
        graph.add_edge(name, "validate")
    graph.add_conditional_edges("validate", after_validate, {"draft": "draft", "end": END})
    return graph.compile()

practice_retried = practice_graph(["4.2.5 의 절차를 따른다", "4.2.3 의 절차를 따른다"]).invoke(
    {"card": practice_cards["S01 HDF 정탐"], "trace": []})
print("S01:", " → ".join(practice_retried["trace"]), "· 남은 오류", practice_retried["errors"])
for practice_name in ("S08 예측≠판정", "S05 오탐 경고"):
    practice_other = practice_graph([]).invoke({"card": practice_cards[practice_name], "trace": []})
    print(f"{practice_name[:3]}:", " → ".join(practice_other["trace"]))''',
   "S01 은 첫 초안이 없는 절을 인용해 validate 가 오류를 냈고, draft 로 되돌아가 두 번째 초안이 통과했습니다. S08·S05 는 초안 노드를 거치지 않고 escalate·inspect 에서 바로 validate 로 갑니다. 문장을 쓰는 것은 grounded_draft 경로뿐입니다."),
  ("계속 틀리면 상한에서 멈춘다", '''# 초안 대역이 늘 같은 오류를 냅니다. 되돌아가는 길에 상한이 없으면 끝나지 않습니다.
# 상한에 걸리면 오류를 단 채 끝납니다. 오류를 지우고 통과시키지 않습니다.
# 관찰 포인트: attempts 가 상한(2)에서 멈추고, errors 가 그대로 남아 다음 단계(사람 검토)로 갑니다.
practice_bounded = practice_graph(["4.2.5 의 절차를 따른다"] * 10).invoke(
    {"card": practice_cards["S01 HDF 정탐"], "trace": []})
print("계속 틀린 초안:", " → ".join(practice_bounded["trace"]))
print("시도", practice_bounded["attempts"], "번 · 남은 오류", practice_bounded["errors"])

assert practice_route(practice_cards["S01 HDF 정탐"]) == ("grounded_draft", [])
assert practice_route(practice_cards["S08 예측≠판정"]) == ("escalation", ["ESC-3"])
assert practice_route(practice_cards["S05 오탐 경고"]) == ("inspect_only", ["SOP-EA-01 8"])
assert practice_retried["trace"] == ["decide:grounded_draft", "draft#1", "validate:오류", "draft#2", "validate:통과"]
assert practice_bounded["attempts"] == PRACTICE_MAX_ATTEMPTS and practice_bounded["errors"], "상한에서 멈추지 않았거나 오류가 사라졌습니다"''',
   "늘 틀리는 초안도 두 번 쓰고 멈췄고, 오류는 그대로 남았습니다. 상한에 걸렸다고 오류를 지우면 검사하지 않은 것과 같습니다. 앱은 이렇게 오류가 남은 초안을 사람에게 보내되, **승인은 할 수 없게** 막습니다(Notebook 11)."),
 ],
 "exercise": {
  "intro": "`practice_try_card` 의 값을 바꿔 경로가 어떻게 달라지는지 보세요. 후보를 `[\"HDF\", \"PWF\"]` 로 늘리면? `severity` 를 \"alarm\" 으로 바꾸고 `met` 를 비우면? `evidence` 를 0 으로 만들면? 사유가 둘 이상 붙는 카드도 만들어 보세요.",
  "code": '''# 카드 하나를 바꿔 규칙에 넣습니다. 그래프 없이 규칙만 봅니다.
# 사유는 걸린 조건마다 하나씩 붙습니다.
practice_try_card = {"predicted": "HDF", "candidates": ["HDF"], "met": ["HDF"], "severity": "warning", "evidence": 9}
print(practice_route(practice_try_card))''',
 },
 "middle": "카드 셋의 경로와 사유, 검사 실패 뒤 다시 써서 통과한 흐름, 경로마다 지나간 노드, 그리고 늘 틀리는 초안이 상한에서 오류를 단 채 멈추는 것을 확인합니다.",
 "failure": "ESC-1(현장 안전)과 ESC-6(설비 정지 요구)은 카드만으로 판단할 수 없어 규칙에 없습니다. 이것은 현장에서 사람이 판단합니다. 또 규칙이 grounded_draft 로 보낸 카드가 실제 고장이라는 보장은 없습니다. TWF 는 위험 구간에서 무작위로 일어나 기준이 성립해도 오탐일 수 있습니다(Notebook 12 에서 숫자로 봅니다).",
 "app_link": "과제 10 App 의 `routing.py::decide_route` 가 같은 규칙(ESC-2·3·4·5·7)이고, ESC-5(조치 완료 뒤 24시간 안 재발)는 요청에 함께 온 조치 완료 기록으로 판단합니다. 되돌아가는 조건은 `review.py::after_validate`, 상한은 `review.py::MAX_ATTEMPTS`(2)입니다.",
 "next": "다음 `10_parallel_collectors.ipynb` 에서는 매뉴얼 근거와 이력 근거를 두 담당이 동시에 모으고 합칩니다.",
})

# =============================================================================
# 10 병렬 수집과 합치기
# =============================================================================
SPECS.append({
 "project": P, "file": "10_parallel_collectors.ipynb",
 "title": "과제 10 · 10 · 두 담당이 동시에 근거를 모으고 합치기",
 "scenario": "근거는 두 곳에서 옵니다. 매뉴얼(검색)과 정비 이력(Tool Agent)입니다. 둘은 서로를 기다릴 이유가 없으므로 동시에 돌립니다. 그런데 둘이 같은 칸(evidence)에 결과를 쓰면 어느 쪽을 남길지 정해야 하고, 같은 근거를 둘 다 찾으면 한 번만 남겨야 합니다.",
 "objectives": ["START 에서 두 노드로 갈라 병렬로 돌린다.",
                "reducer 없이 같은 칸에 쓰면 그래프가 거부하는 것을 본다.",
                "`Annotated[list, operator.add]` 로 두 결과를 모두 남기고, 합치는 노드에서 중복을 지운다."],
 "steps": [
  ("reducer 없이 같은 칸에 쓰면", '''# 매뉴얼 담당과 이력 담당이 같은 칸(evidence)에 씁니다. 둘은 같은 단계에서 동시에 돕니다.
# 칸에 합치는 법(reducer)이 없으면 LangGraph 는 둘 중 무엇을 남길지 모릅니다.
# 관찰 포인트: 조용히 하나를 버리지 않고 InvalidUpdateError 로 거부합니다.
from typing import Annotated, TypedDict
from langgraph.errors import InvalidUpdateError
from langgraph.graph import END, START, StateGraph

def practice_manual(state):
    return {"evidence": ["MC01-MM 4.2.2", "MC01-MM 4.2.3"], "trace": ["manual"]}

def practice_history(state):
    return {"evidence": ["MR-0102", "MC01-MM 4.2.2"], "trace": ["history"]}

def practice_build(state_type, merge=None):
    graph = StateGraph(state_type)
    graph.add_node("manual", practice_manual)
    graph.add_node("history", practice_history)
    graph.add_node("merge", merge or (lambda s: {}))
    graph.add_edge(START, "manual")          # 두 담당은 서로를 기다리지 않습니다
    graph.add_edge(START, "history")
    graph.add_edge("manual", "merge")
    graph.add_edge("history", "merge")
    graph.add_edge("merge", END)
    return graph.compile()

class PracticePlain(TypedDict, total=False):
    evidence: list
    trace: list

try:
    practice_build(PracticePlain).invoke({"trace": []})
    practice_refused = None
except InvalidUpdateError as error:
    practice_refused = type(error).__name__
print("reducer 없이:", practice_refused)''',
   "두 담당이 같은 단계에서 같은 칸에 쓰자 그래프가 `InvalidUpdateError` 로 거부했습니다. 한쪽을 조용히 버렸다면 매뉴얼 근거나 이력 근거 중 하나가 소리 없이 사라졌을 것입니다."),
  ("reducer 를 주면 둘 다 남는다", '''# 칸의 타입에 합치는 법을 적습니다. operator.add 는 두 목록을 이어 붙입니다.
# trace 칸에도 같은 reducer 를 줘서 어느 담당이 돌았는지 남깁니다.
# 관찰 포인트: 두 담당의 결과가 모두 남습니다. 둘 다 찾은 4.2.2 는 두 번 들어 있습니다.
import operator

class PracticeMerged(TypedDict, total=False):
    evidence: Annotated[list, operator.add]
    trace: Annotated[list, operator.add]

practice_merged = practice_build(PracticeMerged).invoke({"trace": []})
print("근거:", practice_merged["evidence"])
print("돈 순서:", practice_merged["trace"])''',
   "네 개가 모두 남았고, 두 담당 모두 merge 전에 돌았습니다. 대신 매뉴얼 담당과 이력 담당이 둘 다 찾은 4.2.2 가 두 번 들어 있습니다. 이것을 그대로 초안에 넘기면 같은 근거를 두 번 인용합니다."),
  ("합치는 노드에서 중복 지우기", '''# merge 노드는 두 담당이 모두 끝난 뒤 한 번 돕니다. 여기서 같은 근거를 한 번만 남깁니다.
# 순서는 처음 나온 순서를 지킵니다. 결과는 새 칸(deduped)에 씁니다.
# 관찰 포인트: reducer 가 붙은 칸에 다시 쓰면 또 이어 붙습니다. 정리한 결과는 다른 칸에 둡니다.
class PracticeDeduped(PracticeMerged, total=False):
    deduped: list

def practice_merge(state):
    return {"deduped": list(dict.fromkeys(state["evidence"])), "trace": ["merge"]}

practice_deduped = practice_build(PracticeDeduped, practice_merge).invoke({"trace": []})
print("합친 근거:", practice_deduped["deduped"])
print("돈 순서:", practice_deduped["trace"])

assert practice_refused == "InvalidUpdateError", "reducer 없이도 같은 칸에 쓸 수 있었습니다"
assert sorted(practice_merged["evidence"]) == sorted(["MC01-MM 4.2.2", "MC01-MM 4.2.3", "MR-0102", "MC01-MM 4.2.2"])
assert set(practice_merged["trace"]) == {"manual", "history"}
assert sorted(practice_deduped["deduped"]) == ["MC01-MM 4.2.2", "MC01-MM 4.2.3", "MR-0102"]
assert practice_deduped["trace"][-1] == "merge"''',
   "중복이 사라져 근거가 세 개가 되었고, merge 는 두 담당이 끝난 뒤 마지막에 한 번 돌았습니다. 앱의 merge 는 여기에 더해 판정 기준을 코드로 다시 계산합니다. 이력 담당 Agent 가 판정 결과를 어떻게 읽었든 판정은 코드가 정합니다."),
 ],
 "exercise": {
  "intro": "`practice_try_merge` 를 바꿔 이력 근거(MR-로 시작)를 매뉴얼 근거보다 앞에 두도록 정렬해 보세요. 실제 앱은 이력 근거를 먼저 둡니다. 근거 순서가 초안이나 보고서에 어떤 영향을 줄지 생각해 보세요.",
  "code": '''# merge 노드만 바꿔 같은 그래프를 다시 만듭니다.
# sorted 의 key 로 이력(MR-)을 앞에 둡니다. 같은 종류 안에서는 처음 나온 순서를 지킵니다.
def practice_try_merge(state):
    unique = list(dict.fromkeys(state["evidence"]))
    return {"deduped": sorted(unique, key=lambda i: not i.startswith("MR-")), "trace": ["merge"]}

print(practice_build(PracticeDeduped, practice_try_merge).invoke({"trace": []})["deduped"])''',
 },
 "middle": "reducer 없이 돌렸을 때의 거부, reducer 를 줬을 때 두 담당의 결과가 모두 남는 것(중복 포함), 그리고 merge 노드가 중복을 지우고 마지막에 도는 것을 확인합니다.",
 "failure": "병렬이라고 해서 빨라지는 것은 두 담당이 정말 서로를 기다리지 않을 때뿐입니다. 이력 담당 안에서 판정 → 이력 조회는 순서가 있으므로 그 안은 병렬로 바꿀 수 없습니다(Notebook 06). 또 두 담당 중 하나가 예외를 내면 그래프 전체가 멈춥니다. 앱은 설정이 빠진 경우(키, MCP 서버)를 503 과 이유로 돌려줍니다.",
 "app_link": "과제 10 App 의 `review.py::collect_manual` 과 `review.py::collect_history` 가 START 에서 함께 시작하고, 두 칸(`manual_found`, `history_found`)에 `operator.add` reducer 가 붙어 있습니다(`review.py::CaseState`). `review.py::merge` 가 같은 근거를 한 번만 남기고 판정 기준을 다시 계산합니다.",
 "next": "다음 `11_review_pause.ipynb` 에서는 검사가 끝난 초안 앞에서 그래프를 멈추고 사람의 결정을 기다립니다.",
})

# =============================================================================
# 11 검토 멈춤과 다시 묻기
# =============================================================================
SPECS.append({
 "project": P, "file": "11_review_pause.ipynb",
 "title": "과제 10 · 11 · 사람 검토 앞에서 멈추고, 받을 수 없는 결정은 다시 묻기",
 "scenario": "초안은 정비 기술자가 검토해야 보고서가 됩니다(SOP-EA-01 7.2). 그래프는 검토 앞에서 **실제로 멈춰야** 하고, 결정이 오면 그 자리에서 이어 가야 합니다. 그런데 검사 오류가 있는 초안에 \"승인\"이 오면 어떻게 할까요? 예외로 거절하면 생각지 못한 일이 생깁니다.",
 "objectives": ["`interrupt` 로 실행을 끊고, checkpointer 에 멈춘 상태를 남긴다.",
                "`Command(resume=...)` 로 멈춘 지점부터 이어 가고, 앞 단계가 다시 돌지 않는 것을 확인한다.",
                "받을 수 없는 결정을 예외로 막으면 건이 굳는 것을 재현하고, 다시 묻는 방식으로 고친다."],
 "steps": [
  ("검토 앞에서 멈추기", '''# prepare 는 초안을 만드는 앞 단계, review 는 사람의 결정을 기다리는 단계입니다.
# interrupt 가 사람에게 보여 줄 packet 을 내보내고 실행을 끊습니다. 멈춘 상태는 checkpointer 에 남습니다.
# 관찰 포인트: invoke 가 끝났는데 report 는 돌지 않았습니다. 다음에 돌 노드가 review 로 남아 있습니다.
from typing import TypedDict
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

practice_ran = {"prepare": 0}

class PracticeCase(TypedDict, total=False):
    errors: list
    decision: str
    report: str

def practice_prepare(state):
    practice_ran["prepare"] += 1
    return {"errors": state.get("errors", [])}

def practice_allowed(state):
    return (["escalate", "reject"] if state["errors"] else ["approve", "escalate", "reject"])

def practice_report(state):
    return {"report": "보고서" if state["decision"] in ("approve", "escalate") else ""}

def practice_build(review):
    graph = StateGraph(PracticeCase)
    graph.add_node("prepare", practice_prepare)
    graph.add_node("review", review)
    graph.add_node("report", practice_report)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "review")
    graph.add_edge("review", "report")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=InMemorySaver())

def practice_review_once(state):
    answer = interrupt({"errors": state["errors"], "allowed": practice_allowed(state)})
    return {"decision": answer["decision"]}

practice_graph = practice_build(practice_review_once)
practice_config = {"configurable": {"thread_id": "EVT-2025-0034"}}
practice_paused = practice_graph.invoke({"errors": []}, practice_config)
practice_next = practice_graph.get_state(practice_config).next
print("사람에게 보여 줄 것:", practice_paused["__interrupt__"][0].value)
print("다음에 돌 노드:", practice_next)''',
   "invoke 가 돌아왔지만 report 는 돌지 않았고, 다음 노드가 review 로 남았습니다. 사람에게 보여 줄 packet(오류 없음, 가능한 결정 셋)은 interrupt 값으로 나옵니다. 멈춘 상태는 thread_id 로 찾을 수 있습니다."),
  ("결정을 넣어 이어 가기", '''# 같은 thread_id 로 Command(resume=결정) 을 넣으면 멈춘 자리부터 이어 갑니다.
# interrupt 를 부른 review 노드는 처음부터 다시 돌고, interrupt 가 이번에는 결정을 돌려줍니다.
# 관찰 포인트: 앞 단계(prepare)는 다시 돌지 않습니다. 실행 횟수가 1 그대로입니다.
practice_done = practice_graph.invoke(Command(resume={"decision": "approve"}), practice_config)
print("결정:", practice_done["decision"], "· 보고서:", practice_done["report"])
practice_prepare_runs = practice_ran["prepare"]
print("prepare 실행 횟수:", practice_prepare_runs)''',
   "approve 를 넣자 report 까지 가서 보고서가 나왔고, prepare 는 한 번만 돌았습니다. 대신 **review 노드 자체는 재개할 때 처음부터 다시 돕니다.** 그래서 interrupt 앞에는 다시 돌아도 되는 일(packet 만들기)만 둡니다. 알림 전송을 거기 두면 두 번 나갑니다."),
  ("예외로 막으면 굳는다, 다시 물으면 풀린다", '''# 오류가 있는 초안입니다. approve 는 받을 수 없고 escalate 는 받을 수 있습니다.
# 첫 번째 방식: 받을 수 없는 결정이면 예외를 던집니다. 그 뒤에 올바른 결정을 넣어 봅니다.
# 관찰 포인트: 재개 값은 기록에 남아 다시 재생됩니다. 예외를 던지면 올바른 결정도 같은 예외로 끝납니다.
def practice_review_strict(state):
    answer = interrupt({"allowed": practice_allowed(state)})
    if answer["decision"] not in practice_allowed(state):
        raise ValueError(f"{answer['decision']} 은 받을 수 없습니다")
    return {"decision": answer["decision"]}

practice_strict = practice_build(practice_review_strict)
practice_strict_config = {"configurable": {"thread_id": "strict"}}
practice_strict.invoke({"errors": ["근거 목록에 없는 절"]}, practice_strict_config)
practice_stuck = []
for practice_decision in ("approve", "escalate"):
    try:
        practice_strict.invoke(Command(resume={"decision": practice_decision}), practice_strict_config)
        practice_stuck.append((practice_decision, "통과"))
    except ValueError as error:
        practice_stuck.append((practice_decision, str(error)))
print("예외 방식:", practice_stuck)

# 두 번째 방식: 받을 수 없으면 이유를 붙여 다시 묻습니다(interrupt 를 한 번 더).
def practice_review_reask(state):
    answer = interrupt({"allowed": practice_allowed(state)})
    while answer["decision"] not in practice_allowed(state):
        answer = interrupt({"allowed": practice_allowed(state), "message": f"{answer['decision']} 은 받을 수 없습니다"})
    return {"decision": answer["decision"]}

practice_reask = practice_build(practice_review_reask)
practice_reask_config = {"configurable": {"thread_id": "reask"}}
practice_reask.invoke({"errors": ["근거 목록에 없는 절"]}, practice_reask_config)
practice_again = practice_reask.invoke(Command(resume={"decision": "approve"}), practice_reask_config)
practice_reasked = practice_reask.invoke(Command(resume={"decision": "escalate"}), practice_reask_config)
print("다시 묻기:", practice_again["__interrupt__"][0].value["message"], "→", practice_reasked["decision"], practice_reasked["report"])

assert practice_paused["__interrupt__"] and practice_next == ("review",), "검토 앞에서 멈추지 않았습니다"
assert practice_done["report"] == "보고서" and practice_prepare_runs == 1, "앞 단계가 다시 돌았습니다"
assert practice_stuck[1] == ("escalate", "approve 은 받을 수 없습니다"), "올바른 결정을 넣었는데 풀렸습니다(굳는 현상이 재현되지 않음)"
assert practice_reasked["decision"] == "escalate" and practice_reasked["report"] == "보고서"''',
   "예외 방식에서는 approve 가 거절된 뒤 escalate 를 넣어도 **\"approve 은 받을 수 없습니다\"** 로 끝납니다. 처음 넣은 재개 값이 기록에 남아 다시 재생되기 때문입니다. 이 건은 영원히 처리할 수 없게 굳습니다. 다시 묻는 방식에서는 approve 에 이유를 붙인 두 번째 interrupt 가 나오고, escalate 로 보고서까지 갑니다."),
 ],
 "exercise": {
  "intro": "다시 묻는 그래프에 \"approve\" 를 두 번 넣은 뒤 \"reject\" 를 넣어 보세요. 몇 번이고 다시 물을 수 있습니까? 실제 앱은 그래프에 닿기 전에 무엇으로 한 번 더 막는지 `app.py` 에서 찾아보세요.",
  "code": '''# 새 thread 로 시작해 결정을 차례로 넣습니다. 받을 수 없는 결정마다 다시 묻습니다.
# 마지막 결과의 report 가 비어 있으면 reject 로 끝난 것입니다.
practice_try_config = {"configurable": {"thread_id": "try"}}
practice_reask.invoke({"errors": ["근거 목록에 없는 절"]}, practice_try_config)
for practice_try_decision in ("approve", "approve", "reject"):
    practice_try = practice_reask.invoke(Command(resume={"decision": practice_try_decision}), practice_try_config)
    print(practice_try_decision, "→", practice_try.get("__interrupt__", [None])[0] and practice_try["__interrupt__"][0].value.get("message"), practice_try.get("report"))''',
 },
 "middle": "멈춘 시점의 packet 과 다음 노드, 재개 뒤 보고서와 앞 단계 실행 횟수, 그리고 예외 방식이 굳는 것과 다시 묻는 방식이 풀리는 것을 확인합니다.",
 "failure": "checkpointer 가 프로세스 메모리(InMemorySaver)면 재시작 한 번에 검토 대기 중이던 건이 사라집니다. **기다리라고 해 놓고 잊는 것**이라 운영에서는 DB 에 둡니다(과제 10 은 Postgres). 또 저장소에서 상태를 꺼낼 때 허용할 타입을 정하지 않으면 LangGraph 가 경고하고, 다음 버전부터는 꺼내기를 막습니다.",
 "app_link": "과제 10 App 의 `review.py::review` 가 같은 다시 묻기 방식으로 멈추고, `review.py::refusal` 이 받을 수 없는 결정의 이유를 만들며, `review.py::allowed_decisions` 가 검사 오류가 있으면 approve 를 뺍니다. `app.py::decide` 는 그래프에 닿기 전에 같은 목록으로 422 를 돌려줍니다. 저장소는 `shared/graph/checkpoint.py::thread_store` 가 매뉴얼·이력과 같은 Postgres 에 열어, 검토 대기 건이 재시작을 넘깁니다.",
 "next": "다음 `12_end_to_end_evaluation.ipynb` 에서는 지금까지의 조각을 한 그래프로 잇고, Agent 바깥의 숫자까지 평가합니다.",
})

# =============================================================================
# 12 전체 흐름과 종단 평가 (통합)
# =============================================================================
SPECS.append({
 "project": P, "file": "12_end_to_end_evaluation.ipynb",
 "title": "과제 10 · 12 · 전체 흐름을 잇고 ML 이 놓친 고장까지 세어 평가하기",
 "scenario": "부품은 다 만들었습니다. 이제 카드 한 장이 근거 수집 → 경로 → 검토 → 보고서까지 가는지 한 그래프로 확인하고, 평가해야 합니다. 그런데 Agent 만 평가하면 **ML 이 경보를 내지 않아 Agent 에게 오지 않은 고장**은 보이지 않습니다. 설비 관리자가 알고 싶은 것은 \"고장 중 몇 건을 잡았나\"입니다.",
 "objectives": ["병렬 수집 · 규칙 경로 · 검토 멈춤 · 보고서를 한 그래프로 잇는다.",
                "경보 카드 전체의 경로를 정답과 대조한다.",
                "경보가 없던 고장까지 넣어 시스템 재현율을 계산하고, Agent 만 본 숫자와 비교한다."],
 "steps": [
  ("한 그래프로 잇기", '''# 연습 카드 여섯 장입니다. met 은 판정 기준 성립 유형, failure 는 실제 고장 여부(평가 전용 정답)입니다.
# 그래프에는 failure 를 넘기지 않습니다. Agent 가 정답을 보면 평가가 성립하지 않습니다.
# 관찰 포인트: manual 과 history 가 함께 시작해 decide 로 모이고, review 에서 멈췄다가 report 로 갑니다.
import operator
from collections import Counter
from typing import Annotated, TypedDict
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

''' + PRACTICE_ROUTE + '''

evaluation_cases = [
    ({"id": "C1", "predicted": "HDF", "candidates": ["HDF"], "met": ["HDF"], "severity": "warning", "evidence": 9}, True),
    ({"id": "C2", "predicted": "OSF", "candidates": ["OSF"], "met": ["TWF"], "severity": "alarm", "evidence": 11}, True),
    ({"id": "C3", "predicted": "PWF", "candidates": ["PWF"], "met": ["PWF"], "severity": "alarm", "evidence": 8}, True),
    ({"id": "C4", "predicted": "HDF", "candidates": ["HDF"], "met": [], "severity": "warning", "evidence": 7}, False),
    ({"id": "C5", "predicted": "TWF", "candidates": ["TWF"], "met": ["TWF"], "severity": "warning", "evidence": 8}, False),
    ({"id": "C6", "predicted": "OSF", "candidates": ["OSF"], "met": ["OSF"], "severity": "alarm", "evidence": 10}, True),
]

class PracticeCase(TypedDict, total=False):
    card: dict
    evidence: Annotated[list, operator.add]
    route: str
    reasons: list
    decision: str
    report: str
    trace: Annotated[list, operator.add]

def manual(state):
    return {"evidence": [f"MC01-MM {t} 판정 기준" for t in state["card"]["met"]], "trace": ["manual"]}

def history(state):
    return {"evidence": [f"이력: 같은 예측({state['card']['predicted']})"], "trace": ["history"]}

def decide(state):
    route, reasons = practice_route(state["card"])
    return {"route": route, "reasons": reasons, "trace": [f"decide:{route}"]}

def review(state):
    answer = interrupt({"route": state["route"], "reasons": state["reasons"], "evidence": state["evidence"]})
    return {"decision": answer["decision"], "trace": [f"review:{answer['decision']}"]}

def report(state):
    text = "" if state["decision"] == "reject" else f"[{state['card']['id']}] {state['route']} {state['reasons']} · 근거 {len(state['evidence'])}건"
    return {"report": text, "trace": ["report"]}

practice_builder = StateGraph(PracticeCase)
for practice_name, practice_node in (("manual", manual), ("history", history), ("decide", decide),
                                     ("review", review), ("report", report)):
    practice_builder.add_node(practice_name, practice_node)
for practice_name in ("manual", "history"):
    practice_builder.add_edge(START, practice_name)
    practice_builder.add_edge(practice_name, "decide")
practice_builder.add_edge("decide", "review")
practice_builder.add_edge("review", "report")
practice_builder.add_edge("report", END)
practice_pipeline = practice_builder.compile(checkpointer=InMemorySaver())

practice_reports = {}
for practice_card, practice_decision in ((evaluation_cases[0][0], "approve"), (evaluation_cases[1][0], "escalate")):
    practice_config = {"configurable": {"thread_id": practice_card["id"]}}
    practice_pipeline.invoke({"card": practice_card, "trace": []}, practice_config)
    practice_out = practice_pipeline.invoke(Command(resume={"decision": practice_decision}), practice_config)
    practice_reports[practice_card["id"]] = practice_out
    print(f"{practice_card['id']}: {' → '.join(practice_out['trace'])}")
    print(f"    {practice_out['report']}")''',
   "C1 은 HDF 정탐이라 grounded_draft 로 가서 승인되었고, C2 는 예측(OSF)과 판정(TWF)이 달라 ESC-3 으로 넘겨 escalate 되었습니다. 두 건 모두 manual 과 history 가 decide 전에 돌았고, review 에서 멈췄다가 사람의 결정으로 report 까지 갔습니다."),
  ("경로를 정답과 대조", '''# 경보 카드 전체의 경로를 정답(실제 고장인가)과 나란히 셉니다. 경로는 그래프의 decide 와 같은 규칙입니다.
# 사람 검토와 보고서는 경로에 영향을 주지 않으므로 여기서는 돌리지 않습니다.
# 관찰 포인트: inspect_only(오탐 점검)로 보낸 실제 고장이 몇 건인지가 Agent 쪽의 놓침입니다.
practice_table = Counter((practice_route(card)[0], "고장" if failure else "오탐") for card, failure in evaluation_cases)
for practice_route_name in ("grounded_draft", "escalation", "inspect_only"):
    print(f"  {practice_route_name:15} 실제 고장 {practice_table[(practice_route_name, '고장')]} · 오탐 {practice_table[(practice_route_name, '오탐')]}")
practice_agent_missed = practice_table[("inspect_only", "고장")]
practice_alarmed_failures = sum(failure for _, failure in evaluation_cases)
print(f"경보로 온 실제 고장 {practice_alarmed_failures}건 중 Agent 가 점검만 권한 것 {practice_agent_missed}건")''',
   "grounded_draft 4건 중 1건(C5)은 오탐입니다. TWF 위험 구간에 들어 기준은 성립했지만 실제 고장은 아니었습니다. inspect_only 로 보낸 실제 고장은 0건이라, Agent 만 보면 \"고장을 하나도 놓치지 않았다\"고 말할 수 있습니다."),
  ("Agent 바깥까지 — 시스템 재현율", '''# 같은 기간에 ML 이 경보를 내지 않은 고장입니다. 이것은 Agent 에게 오지 않았습니다.
# 시스템 재현율 = 경보로 Agent 에게 온 실제 고장 / (그것 + 경보 없이 지나간 고장)
# 관찰 포인트: Agent 만 본 숫자(100%)와 시스템 재현율이 다릅니다. 차이는 Agent 가 볼 수 없었던 고장입니다.
practice_missed = [{"at": "2025-08-03T01:30:00+09:00", "actual": ["TWF"]},
                   {"at": "2025-08-19T13:00:00+09:00", "actual": ["HDF"]}]
practice_agent_recall = (practice_alarmed_failures - practice_agent_missed) / practice_alarmed_failures
practice_system_recall = (practice_alarmed_failures - practice_agent_missed) / (practice_alarmed_failures + len(practice_missed))
print(f"Agent 만 본 재현율  {practice_agent_recall:.1%}  (경보로 온 고장 기준)")
print(f"시스템 재현율       {practice_system_recall:.1%}  (경보가 없던 고장 {len(practice_missed)}건 포함)")
print("놓친 고장의 유형:", dict(Counter(t for m in practice_missed for t in m["actual"])))

assert practice_reports["C1"]["report"].startswith("[C1] grounded_draft")
assert practice_reports["C2"]["reasons"] == ["ESC-3"]
assert practice_table == Counter({("grounded_draft", "고장"): 3, ("grounded_draft", "오탐"): 1,
                                  ("escalation", "고장"): 1, ("inspect_only", "오탐"): 1})
assert practice_agent_recall == 1.0
assert round(practice_system_recall, 3) == 0.667, "경보가 없던 고장을 평가에 넣지 않았습니다"''',
   "Agent 만 보면 재현율 100% 이지만, 경보 없이 지나간 고장 2건을 넣으면 시스템 재현율은 66.7% 입니다. 나머지는 Agent 가 아무리 잘해도 볼 수 없었던 고장이고, 그 한계는 ML 의 경보 기준이 정합니다. **Agent 만 평가하면 이 차이가 보이지 않습니다.**"),
 ],
 "exercise": {
  "intro": "실제 앱의 평가를 돌려 보세요. DB 를 띄우고 적재한 뒤 앱을 띄우고(`uv run uvicorn task10_maintenance.app:app --port 8035 --env-file .env --loop task10_maintenance.loop:selector_loop_factory`) 브라우저로 `http://127.0.0.1:8035/evaluate` 를 열거나, 화면(Streamlit)의 '평가' 탭에서 \"평가 실행\"을 누릅니다. 아래 셀에 그 숫자를 적고, 연습 숫자와 비교해 보세요. 경로별 오탐은 어디에 몰려 있습니까? 놓친 고장은 어떤 유형이 많습니까?",
  "code": '''# 실제 앱 /evaluate 의 숫자를 적습니다(앱을 띄우지 않았으면 None 으로 둡니다).
# 연습 데이터의 숫자와 나란히 놓고 차이를 읽어 보세요.
practice_try_app_recall = None   # 예: 0.747
print("연습 시스템 재현율:", f"{practice_system_recall:.1%}", "· 실제 앱:", practice_try_app_recall)''',
 },
 "middle": "카드 두 장이 한 그래프에서 멈췄다가 보고서까지 가는 흐름, 경로별 실제 고장·오탐 수, 그리고 Agent 만 본 재현율과 시스템 재현율의 차이를 확인합니다.",
 "failure": "이 평가는 합성 데이터에서 잰 숫자입니다. HDF·PWF·OSF 가 규칙만으로 정답과 잘 맞는 것은 AI4I 2020 이 이 조건식으로 고장을 만든 데이터라서이고, 실제 설비에서는 그렇지 않습니다. 또 경로가 맞았다고 초안 문장이 맞는 것은 아닙니다. 문장의 품질은 사람 검토가 봅니다.",
 "app_link": "과제 10 App 의 `evaluation.py::evaluate` 가 같은 평가를 실제 데이터로 합니다. 대표 사례 S01~S10 은 10건 모두 기대 경로대로 가고, 경보 카드 111장은 grounded_draft 75장(실제 고장 63) · escalation 17장(11) · inspect_only 19장(0)입니다. 운영 기간 실제 고장 99건 중 74건이 경보로 와서 **시스템 재현율은 74.7%** 이고, 놓친 25건 중 10건이 TWF 입니다. 경로는 `evaluation.py::route_for` 가 그래프와 같은 규칙으로 정하고, `GET /evaluate`(`app.py::evaluate`)가 이 결과를 돌려줍니다.",
 "next": "이제 과제 10 App 전체를 읽을 준비가 되었습니다. `task10_maintenance/review.py` 의 그래프 그림부터 보고, 화면(Streamlit)에서 대표 사례 S01~S10 을 하나씩 처리해 보세요.",
})
