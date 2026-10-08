"""Notebook을 계약대로 생성한다. 내용은 spec 모듈이 제공한다."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def markdown(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": text.rstrip().splitlines(keepends=True)}


def build(spec: dict) -> dict:
    cells = [markdown(
        f"# {spec['title']}\n\n"
        f"## 현업 시나리오\n{spec['scenario']}\n\n"
        f"## 학습 목표\n" + "\n".join(f"- {g}" for g in spec["objectives"])
    ), markdown(
        "## 직접 조립\n완성된 App을 가져오지 않습니다. 아래에서 작은 fixture와 핵심 함수를 직접 만듭니다."
    )]
    for index, (heading, body, *explain) in enumerate(spec["steps"], start=1):
        cells.append(markdown(f"### {index}단계 · {heading}"))
        cells.append(code(body))
        if explain:      # 단계마다 결과 해설을 붙인다
            cells.append(markdown(f"**결과 해설** — {explain[0]}"))
    if exercise := spec.get("exercise"):
        cells.append(markdown(f"## 직접 해 볼 과제\n{exercise['intro']}"))
        cells.append(code(exercise["code"]))
    cells.append(markdown(
        f"## 중간 결과\n{spec['middle']}\n\n"
        f"## 실패 경계\n{spec['failure']}\n\n"
        f"## 실제 app 연결\n{spec['app_link']}\n\n"
        f"## 다음 Notebook 연결\n{spec['next']}"
    ))
    return {"cells": cells, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.13"},
    }, "nbformat": 4, "nbformat_minor": 5}


def write_all(specs: list[dict]) -> list[Path]:
    written = []
    for spec in specs:
        path = ROOT / spec["project"] / "notebooks" / spec["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(build(spec), ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
        written.append(path)
    return written


# Notebook 내용은 여러 파일에 나눠 두었다. **전부 여기 적어야 한다.**
# 한때 w1 하나만 불러서 나머지 24개는 생성기가 건드리지 않았고, "생성기와
# Notebook 이 일치한다"는 확인이 그 24개에 대해 아무것도 검사하지 않았다.
SPEC_MODULES = [
    "notebook_specs_task10",
]


def all_specs() -> list[dict]:
    import importlib

    specs: list[dict] = []
    seen: dict[str, str] = {}
    for name in SPEC_MODULES:
        module = importlib.import_module(name)
        for spec in module.SPECS:
            key = f"{spec['project']}/{spec['file']}"
            if key in seen:
                raise SystemExit(f"{key} 가 {seen[key]} 와 {name} 양쪽에 있다")
            seen[key] = name
            specs.append(spec)
    return specs


if __name__ == "__main__":
    for path in write_all(all_specs()):
        print("wrote", path.relative_to(ROOT))
