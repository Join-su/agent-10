"""정비 매뉴얼 md 정본에서 PDF 변환본을 만든다.

    uv run python scripts/task10/build_manual_pdfs.py

md → HTML 은 pandoc, HTML → PDF 는 Chrome headless 가 한다. 둘 다 Python 패키지가
아니라 설치된 프로그램이다. 경로가 다르면 `--pandoc`, `--chrome` 으로 준다.

**정본은 md 다.** PDF 는 현업에서 받는 문서 형태를 재현하려는 변환본이다. PDF 에서
텍스트를 다시 뽑으면 표가 줄글로 풀리고 머리말 구분이 사라진다. 그 손실이 Notebook
에서 보여 줄 내용이다.
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "task10_maintenance"
MD_DIR = ROOT / "data" / "manuals" / "md"
PDF_DIR = ROOT / "data" / "manuals" / "pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

STYLE = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", sans-serif;
       font-size: 10.5pt; line-height: 1.55; color: #111; }
h1 { font-size: 18pt; border-bottom: 2px solid #333; padding-bottom: 4px; }
h2 { font-size: 14pt; margin-top: 1.4em; border-bottom: 1px solid #999; }
h3 { font-size: 12pt; margin-top: 1.1em; }
h4 { font-size: 11pt; }
table { border-collapse: collapse; width: 100%; margin: 0.6em 0; font-size: 9.5pt; }
th, td { border: 1px solid #888; padding: 3px 6px; vertical-align: top; }
th { background: #eee; }
blockquote { border-left: 4px solid #c33; margin: 0.6em 0; padding: 2px 10px; background: #fbeeee; }
header#title-block-header { display: none; }
"""


def render(md: Path, pandoc: str, chrome: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / f"{md.stem}.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        css = Path(tmp) / "style.css"
        css.write_text(STYLE, encoding="utf-8")
        html = Path(tmp) / f"{md.stem}.html"
        # 앞머리(YAML)는 문서 속성으로만 쓰고 본문에 찍지 않는다.
        subprocess.run([pandoc, str(md), "--from", "markdown+yaml_metadata_block",
                        "--to", "html5", "--standalone", "--embed-resources",
                        "--css", str(css), "--metadata", "lang=ko",
                        "--output", str(html)], check=True)
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", html.as_uri()],
                       check=True, capture_output=True)
    return pdf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pandoc", default="pandoc")
    parser.add_argument("--chrome", default=CHROME)
    args = parser.parse_args()
    for md in sorted(MD_DIR.glob("*.md")):
        pdf = render(md, args.pandoc, args.chrome, PDF_DIR)
        print(f"{md.name} → {pdf.relative_to(ROOT)} ({pdf.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
