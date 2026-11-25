# -*- coding: utf-8 -*-
"""
md2pdf.py —— Markdown 转 PDF（中文友好，排版可控）
=====================================================
原理：Markdown -> 带样式的 HTML -> 用 Edge 无头模式打印成 PDF。
优点：不依赖 pandoc / LaTeX，Windows 自带 Edge 即可，中文字体、表格、代码块都正常。

用法：
    python scripts/md2pdf.py <input.md>              # 输出同名 .pdf
    python scripts/md2pdf.py <input.md> <out.pdf>    # 指定输出路径

示例：
    python scripts/md2pdf.py 面试问答准备.md

依赖：
    pip install markdown          # 必需
    pip install pymupdf           # 可选，用来打印 PDF 页数（没装也能正常出 PDF）
    Edge 浏览器                    # Windows 一般自带
"""
import os
import sys
import uuid
import shutil
import argparse
import subprocess

import markdown

# ---------------------------- 中文排版样式 ----------------------------
# 说明：@page 控制 A4 页边距；表格/代码块避免跨页断裂；标题用蓝色系。
CSS = """
@page { size: A4; margin: 15mm 14mm; }
* { box-sizing: border-box; }
body {
  font-family: "Microsoft YaHei", "微软雅黑", "PingFang SC", sans-serif;
  font-size: 10.5pt; line-height: 1.7; color: #222; margin: 0;
}
h1 { font-size: 19pt; text-align: center; border-bottom: 2.5px solid #2c6fbb;
     padding-bottom: 8px; margin: 0 0 6px 0; color: #1a3d66; }
h2 { font-size: 14pt; color: #1a3d66; border-left: 5px solid #2c6fbb;
     padding-left: 9px; margin: 20px 0 8px 0; page-break-after: avoid; }
h3 { font-size: 12pt; color: #2c6fbb; margin: 14px 0 6px 0; page-break-after: avoid; }
p { margin: 5px 0; }
ul, ol { margin: 5px 0; padding-left: 22px; }
li { margin: 3px 0; }
strong { color: #b3261e; }
blockquote {
  margin: 8px 0; padding: 8px 14px; background: #f4f7fb;
  border-left: 3px solid #9db8d6; color: #333; font-size: 10pt;
}
blockquote p { margin: 3px 0; }
table {
  border-collapse: collapse; width: 100%; margin: 10px 0;
  font-size: 9.5pt; page-break-inside: avoid;
}
th, td { border: 1px solid #c9d3dd; padding: 5px 8px; vertical-align: top; text-align: left; }
th { background: #e8f0f8; color: #1a3d66; font-weight: 700; }
tr:nth-child(even) td { background: #fafcfe; }
code {
  font-family: Consolas, "Courier New", monospace; font-size: 9.5pt;
  background: #eef1f4; padding: 1px 4px; border-radius: 3px; color: #c7254e;
}
pre { background: #f5f7f9; padding: 10px; border-radius: 4px; overflow-x: auto;
      page-break-inside: avoid; }
pre code { background: none; color: #333; padding: 0; }
hr { border: none; border-top: 1px dashed #ccc; margin: 16px 0; }
h2, h3, table, blockquote { page-break-inside: avoid; }
"""

# Edge 常见安装路径（按顺序尝试）
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_edge() -> str:
    """定位 Edge 可执行文件；也可用环境变量 EDGE_PATH 指定。"""
    env = os.getenv("EDGE_PATH")
    if env and os.path.exists(env):
        return env
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("未找到 Edge，请设置环境变量 EDGE_PATH 指向 msedge.exe")


def md_to_html(md_text: str, title: str) -> str:
    """Markdown -> 完整 HTML（内联样式）。"""
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>{title}</title><style>{CSS}</style></head>"
        f"<body>{body}</body></html>"
    )


def html_to_pdf(html_path: str, pdf_path: str) -> None:
    """用 Edge 无头模式把 HTML 打印成 PDF。"""
    edge = find_edge()
    url = "file:///" + html_path.replace("\\", "/")

    def _run(flag):
        # --no-pdf-header-footer：去掉页眉页脚（网址、日期）
        cmd = [edge, flag, "--disable-gpu", "--no-pdf-header-footer",
               f"--print-to-pdf={pdf_path}", url]
        return subprocess.run(cmd, capture_output=True, timeout=180)

    if os.path.exists(pdf_path):
        os.remove(pdf_path)

    _run("--headless")
    if not os.path.exists(pdf_path) and os.name == "nt":
        _run("--headless=new")  # 老版本 Edge 的回退写法

    if not os.path.exists(pdf_path):
        raise RuntimeError("Edge 未能生成 PDF，请确认 Edge 可正常启动")


def main():
    parser = argparse.ArgumentParser(description="Markdown 转中文友好 PDF")
    parser.add_argument("input", help="输入的 .md 文件路径")
    parser.add_argument("output", nargs="?", help="输出的 .pdf 路径（默认同名）")
    args = parser.parse_args()

    md_path = os.path.abspath(args.input)
    if not os.path.exists(md_path):
        print(f"[错误] 找不到输入文件：{md_path}")
        sys.exit(1)

    # 默认输出：与输入同目录、同名 .pdf
    if args.output:
        pdf_path = os.path.abspath(args.output)
    else:
        pdf_path = os.path.splitext(md_path)[0] + ".pdf"
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    title = os.path.splitext(os.path.basename(md_path))[0]
    html = md_to_html(md_text, title)

    # HTML 放临时目录，用 ASCII 文件名，避免中文路径在命令行里出问题
    tmp_html = os.path.join(
        os.environ.get("TEMP", "."), f"md2pdf_{uuid.uuid4().hex}.html"
    )
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(html)

    # 先输出到临时 PDF，再复制到目标（目标被占用时可降级另存）
    tmp_pdf = os.path.join(
        os.environ.get("TEMP", "."), f"md2pdf_{uuid.uuid4().hex}.pdf"
    )

    try:
        html_to_pdf(tmp_html, tmp_pdf)

        try:
            shutil.copyfile(tmp_pdf, pdf_path)
            final_pdf = pdf_path
        except PermissionError:
            # 目标 PDF 正被阅读器占用，另存为 -new.pdf
            final_pdf = os.path.splitext(pdf_path)[0] + "-new.pdf"
            shutil.copyfile(tmp_pdf, final_pdf)
            print(f"[提示] 目标被占用，已另存为：{final_pdf}")

        size_kb = os.path.getsize(final_pdf) / 1024
        print(f"[完成] {final_pdf}  ({size_kb:.0f} KB)")

        # 可选：打印页数
        try:
            import fitz
            with fitz.open(final_pdf) as d:
                print(f"[信息] 共 {len(d)} 页")
        except ImportError:
            pass

    finally:
        for p in (tmp_html, tmp_pdf):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


if __name__ == "__main__":
    main()
