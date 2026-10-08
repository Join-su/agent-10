import streamlit as st

from app_pages._common import WorkflowApiError, call, read

PROJECT = "task10_maintenance"

st.title("과제 10 · 설비 이상 대응 지원", icon=":material/build:")
st.write(
    "ML 이 만든 **이상 이벤트 카드**를 받아 매뉴얼과 정비 이력에서 근거를 모으고, "
    "SOP 규칙으로 **처리 경로**를 정한 뒤 초안을 검사합니다. 보고서는 **정비 기술자가 "
    "결정해야** 만들어집니다. 이 화면은 설비를 제어하지 않습니다."
)

try:
    diagnostics = read(PROJECT, "/diagnostics")
except WorkflowApiError as error:
    st.warning(str(error), icon=":material/link_off:")
    diagnostics = None

if diagnostics:
    columns = st.columns(4)
    columns[0].metric("실행 모드", diagnostics["mode"].upper(), border=True)
    columns[1].metric("매뉴얼 임베딩",
                      "녹화본" if diagnostics["embedding_source"] == "recorded" else "실시간",
                      border=True)
    columns[2].metric("이력 Tool", "MCP" if diagnostics["tool_source"] == "mcp" else "내부",
                      border=True)
    columns[3].metric("멈춘 건",
                      "파일에 남음" if diagnostics["thread_durability"] == "file"
                      else "재시작 시 소실", border=True)
    if warning := diagnostics.get("warning"):
        st.warning(warning, icon=":material/warning:")
    if note := diagnostics.get("note"):
        st.info(note, icon=":material/info:")

ROUTE_LABELS = {"grounded_draft": "근거 기반 초안", "escalation": "상위 보고(escalation)",
                "inspect_only": "점검만(오탐 의심)"}
DECISION_LABELS = {"approve": "승인", "revise": "수정 요청", "escalate": "상위 보고", "reject": "반려"}

handle, scoreboard = st.tabs(["이벤트 처리", "평가"])

with handle:
    try:
        cards = read(PROJECT, "/cards")
    except WorkflowApiError as error:
        st.error(str(error))
        cards = []

    only_scenarios = st.toggle("대표 사례(S01~S10)만 보기", value=True, key="t10_only_scenarios")
    shown = [c for c in cards if c["scenario_id"] or not only_scenarios]
    shown.sort(key=lambda c: (c["scenario_id"] or "S99", c["event_id"]))

    def label(card: dict) -> str:
        head = f"{card['scenario_id']} · " if card["scenario_id"] else ""
        tail = f" — {card['teaching_point']}" if card["teaching_point"] else ""
        return (f"{head}{card['event_id']} · 예측 {card['predicted_failure_type']} "
                f"{card['probability']:.2f} ({card['confidence_level']}){tail}")

    with st.form("t10_case_form"):
        chosen = st.selectbox("이상 이벤트 카드", shown, format_func=label, key="t10_card")
        repairs = chosen["completed_repairs"] if chosen else []
        send_repairs = st.checkbox(
            f"앞서 끝낸 조치 기록 {len(repairs)}건을 함께 보내기 (조치 후 재발 판단)",
            value=bool(repairs), disabled=not repairs, key="t10_send_repairs")
        submitted = st.form_submit_button("처리 시작", type="primary",
                                          icon=":material/play_arrow:", width="stretch",
                                          key="t10_submit")

    if submitted and chosen:
        with st.status("근거 수집(매뉴얼 ∥ 이력) → 경로 → 초안·검사 → 사람 검토", expanded=True) as status:
            try:
                st.session_state.t10_result = call(PROJECT, "/cases", {
                    "event_id": chosen["event_id"],
                    "completed_repairs": repairs if send_repairs else [],
                })
            except WorkflowApiError as error:
                status.update(label="실패", state="error")
                st.error(str(error))
            else:
                status.update(label="검토 대기", state="complete", expanded=False)

    if result := st.session_state.get("t10_result"):
        packet = result.get("packet")
        if result["status"] == "awaiting_review":
            st.warning("정비 기술자 검토 대기 — 보고서는 사람이 결정해야 만들어집니다.",
                       icon=":material/person_alert:")
        elif result["status"] == "reported":
            st.success("보고서가 만들어졌습니다.", icon=":material/check_circle:")
        else:
            st.info("반려되어 이 이벤트의 처리를 끝냈습니다.", icon=":material/do_not_disturb_on:")
        st.caption("지나간 노드 · " + " → ".join(result["trace"]))

        if packet:
            route = packet["route"]
            reasons = ", ".join(packet["escalation_reasons"])
            st.subheader(f"처리 경로: {ROUTE_LABELS[route]}" + (f" ({reasons})" if reasons else ""))

            st.markdown("**판정 기준 확인** — 모델의 예측과 별개로 코드가 계산합니다")
            st.code("\n".join(packet["criteria"]), language=None)

            if packet["cause_candidates"]:
                st.markdown("**추정 원인 후보**")
                st.dataframe(
                    [{"순위": c["rank"], "유형": c["failure_type"], "근거 설명": c["rationale"],
                      "인용": ", ".join(c["evidence_ids"])} for c in packet["cause_candidates"]],
                    hide_index=True, key="t10_candidates")
            if packet["inspection_steps"]:
                st.markdown("**점검·조치 단계**")
                st.dataframe(
                    [{"순서": s["order"], "내용": s["instruction"], "인용": ", ".join(s["evidence_ids"])}
                     for s in packet["inspection_steps"]],
                    hide_index=True, key="t10_steps")
            st.caption(f"준비 부품 · {', '.join(packet['parts_to_prepare']) or '없음'} · "
                       f"작성 {packet['drafted_by']} · 수정 요청 {packet['revisions']}회")
            if packet["validation_errors"]:
                st.error("초안 검사 오류 — 승인할 수 없습니다\n\n"
                         + "\n".join(f"- {e}" for e in packet["validation_errors"]),
                         icon=":material/rule:")
            if refused := packet.get("message"):
                st.error(refused, icon=":material/block:")

            with st.expander(f"근거 {len(packet['evidence'])}건"):
                st.dataframe(
                    [{"ID": e["evidence_id"], "종류": e["kind"], "찾은 이유": e["reason"],
                      "내용": e["excerpt"]} for e in packet["evidence"]],
                    hide_index=True, key="t10_evidence")

        with st.expander("매뉴얼 검색 질의와 이력 Tool 호출"):
            st.dataframe([{"질의": q["label"], "문장": q["text"], "찾은 절": ", ".join(q["citations"])}
                          for q in result["queries"]], hide_index=True, key="t10_queries")
            st.dataframe([{"Tool": c["tool"], "인자": str(c["arguments"]), "성공": c["ok"],
                           "결과": c["summary"]} for c in result["tool_calls"]],
                         hide_index=True, key="t10_tool_calls")
            if result["filled_history_types"]:
                st.caption(f"Agent 가 빠뜨려 코드가 채운 이력 유형 · {result['filled_history_types']}")

        if result["status"] == "awaiting_review" and packet:
            st.divider()
            st.subheader("정비 기술자 결정")
            with st.form("t10_decision_form"):
                left, right = st.columns(2)
                decision = left.selectbox("결정", packet["allowed_decisions"],
                                          format_func=DECISION_LABELS.get, key="t10_decision")
                reviewer = right.text_input("검토자 역할", value="정비 기술자", max_chars=40,
                                            key="t10_reviewer")
                note = st.text_input("의견", value="", max_chars=400, key="t10_note")
                decided = st.form_submit_button("결정 제출", type="primary",
                                                icon=":material/gavel:", width="stretch",
                                                key="t10_decide")
            if decided:
                try:
                    st.session_state.t10_result = call(
                        PROJECT, f"/cases/{result['case_id']}/decision",
                        {"decision": decision, "reviewer_role": reviewer, "note": note})
                except WorkflowApiError as error:
                    st.error(str(error))
                else:
                    st.rerun()

        if result.get("report_markdown"):
            st.divider()
            st.markdown(result["report_markdown"])

with scoreboard:
    st.write("대표 사례의 경로가 SOP 대로인지, 그리고 **ML 이 경보를 내지 않아 Agent 가 보지 못한 "
             "고장**까지 넣은 시스템 재현율을 봅니다.")
    if st.button("평가 실행", icon=":material/analytics:", key="t10_evaluate"):
        try:
            st.session_state.t10_evaluation = read(PROJECT, "/evaluate")
        except WorkflowApiError as error:
            st.error(str(error))

    if evaluation := st.session_state.get("t10_evaluation"):
        system = evaluation["system"]
        columns = st.columns(4)
        columns[0].metric("대표 사례 통과", f"{evaluation['scenarios_passed']}/{len(evaluation['scenarios'])}",
                          border=True)
        columns[1].metric("시스템 재현율", f"{system['system_recall']:.1%}", border=True)
        columns[2].metric("실제 고장", system["actual_failures"], border=True)
        columns[3].metric("ML 이 놓친 고장", system["missed_by_ml"], border=True)
        st.caption(evaluation["note"])
        st.dataframe([{"경로": ROUTE_LABELS[r["route"]], "실제 고장": r["failures"], "오탐": r["false_alarms"]}
                      for r in evaluation["routes"]], hide_index=True, key="t10_routes")
        st.dataframe([{"사례": s["scenario_id"], "카드": s["event_id"], "가르치는 것": s["teaching_point"],
                       "기대": f"{s['expected_route']} {s['expected_reasons'] or ''}",
                       "실제": f"{s['route']} {s['reasons'] or ''}", "통과": s["passed"]}
                      for s in evaluation["scenarios"]], hide_index=True, key="t10_scenarios")
