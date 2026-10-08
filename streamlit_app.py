import streamlit as st

st.set_page_config(page_title="과제 10 · 설비 이상 대응 지원", page_icon=":material/build:", layout="wide")

page = st.navigation(
    [
        st.Page("app_pages/task10_maintenance.py", title="과제 10 · 설비 이상 대응",
                icon=":material/build:", default=True),
    ],
    position="top",
)

with st.sidebar:
    st.subheader("캡스톤 과제 10")
    st.caption("제조 설비 이상 대응 지원 Agent — 근거 수집 · 처리 경로 · 사람 검토 · 보고서")
    st.info("FastAPI 를 8035 포트로 실행하세요.", icon=":material/info:")
    st.caption("이 앱은 읽기 전용입니다. 설비를 제어하거나 작업 지시를 내리지 않습니다.")

page.run()
