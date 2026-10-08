# 과제 10 API 와 화면을 담는 단일 이미지. CMD 로 무엇을 띄울지 고른다(compose 참고).
FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# 의존성 먼저 복사해 레이어 캐시를 살린다.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 앱이 실제로 쓰는 것을 전부 담는다. 하나라도 빠지면 컨테이너에서 import 가 깨진다.
# `tests/test_container_image_matches_the_repository.py` 가 빠진 것을 잡는다.
# scripts 는 compose 의 init 서비스가 Postgres 에 적재할 때 쓴다.
COPY shared ./shared
COPY task10_maintenance ./task10_maintenance
COPY scripts ./scripts
COPY app_pages ./app_pages
COPY streamlit_app.py curriculum_manifest.yaml notebook_contracts.yaml ./

ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8035 8501

CMD ["uvicorn", "task10_maintenance.app:app", "--host", "0.0.0.0", "--port", "8035", "--loop", "task10_maintenance.loop:selector_loop_factory"]
