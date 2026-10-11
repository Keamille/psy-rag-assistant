"""文档解析（开发文档 §8.2）：PDF / DOCX / Markdown / 纯文本 → 结构化文本块。

输出统一成 `list[Block]`，每块带 `text` / `section_path` / `page` 三个字段，
后面的清洗与切分只依赖这个结构，不再关心原始格式。

`section_path` 是**溯源的骨架**：来源卡片上那句「《认知行为疗法基础》> 第2章 > 2.3 自动思维」
就是它。所以解析阶段要把标题层级保留下来，丢掉了就再也补不回来。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# 判定"疑似扫描件"的阈值：平均每页可抽取的字符数低于这个值，
# 基本可以确定是图片型 PDF 而不是文本型。
SCANNED_CHARS_PER_PAGE = 50


class ParseError(Exception):
    """文档无法解析（扫描件、加密、格式损坏等）。

    这个异常会被 document_service 捕获并把文档标记为 failed，
    带上 error_message 显示在后台，而不是让整个入库任务崩掉。
    """


@dataclass
class Block:
    text: str
    section_path: str = ""
    page: int | None = None
    meta: dict = field(default_factory=dict)


def load(path: str, source_type: str) -> list[Block]:
    """按类型分派解析器。source_type 取 pdf / docx / md / txt。"""
    if not os.path.exists(path):
        raise ParseError(f"文件不存在：{path}")

    kind = (source_type or "").lower().lstrip(".")
    if kind == "pdf":
        return _load_pdf(path)
    if kind == "docx":
        return _load_docx(path)
    if kind in ("md", "markdown"):
        return _load_markdown(path)
    if kind == "txt":
        return _load_text(path)
    raise ParseError(f"不支持的文档类型：{source_type}")


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _load_pdf(path: str) -> list[Block]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ParseError("缺少依赖 pypdf，无法解析 PDF") from exc

    try:
        reader = PdfReader(path)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"PDF 打开失败：{exc}") from exc

    if getattr(reader, "is_encrypted", False):
        raise ParseError("PDF 已加密，无法解析")

    blocks: list[Block] = []
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            # 单页失败不该让整篇文档作废
            text = ""
            blocks.append(Block("", page=page_no, meta={"error": str(exc)[:100]}))
        text = text.strip()
        if text:
            blocks.append(Block(text, page=page_no))

    total_chars = sum(len(b.text) for b in blocks)
    page_count = len(reader.pages) or 1
    if total_chars / page_count < SCANNED_CHARS_PER_PAGE:
        raise ParseError(
            f"疑似扫描件：平均每页仅可抽取 {total_chars / page_count:.0f} 个字符"
            f"（阈值 {SCANNED_CHARS_PER_PAGE}），请改用文本版或先做 OCR"
        )
    return blocks


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def _load_docx(path: str) -> list[Block]:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise ParseError("缺少依赖 python-docx，无法解析 Word") from exc

    try:
        document = docx.Document(path)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Word 打开失败：{exc}") from exc

    blocks: list[Block] = []
    headings: list[str] = []

    for para in document.paragraphs:
        text = (para.text or "").strip()
        if not text:
            continue
        style = (para.style.name or "") if para.style else ""
        level = _heading_level(style)
        if level:
            # 标题：截断到该层级，维护 section_path 栈
            headings = headings[: level - 1]
            headings.append(text)
            continue
        blocks.append(Block(text, section_path=" > ".join(headings)))

    if not blocks:
        raise ParseError("Word 里没有可提取的正文段落")
    return blocks


def _heading_level(style_name: str) -> int:
    """从 Word 样式名判断标题级别。中英文样式名都要认。"""
    if not style_name:
        return 0
    lowered = style_name.lower().replace(" ", "")
    if lowered in ("title", "标题"):
        return 1
    for token in ("heading", "标题"):
        if lowered.startswith(token):
            suffix = lowered[len(token):]
            if suffix.isdigit():
                return min(int(suffix), 4)
    return 0


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _load_markdown(path: str) -> list[Block]:
    with open(path, encoding="utf-8", errors="replace") as fp:
        raw = fp.read()

    blocks: list[Block] = []
    headings: list[str] = []
    buffer: list[str] = []
    in_code = False

    def flush() -> None:
        text = "\n".join(buffer).strip()
        buffer.clear()
        if text:
            blocks.append(Block(text, section_path=" > ".join(headings)))

    for line in raw.splitlines():
        stripped = line.strip()
        # 代码块里的 # 是注释不是标题
        if stripped.startswith("```"):
            in_code = not in_code
            buffer.append(line)
            continue
        if not in_code and stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            title = stripped[hashes:].strip()
            if title and 1 <= hashes <= 6:
                flush()
                headings = headings[: hashes - 1]
                headings.append(title)
                continue
        buffer.append(line)
    flush()

    if not blocks:
        raise ParseError("Markdown 里没有可提取的正文")
    return blocks


# ---------------------------------------------------------------------------
# 纯文本
# ---------------------------------------------------------------------------


def _load_text(path: str) -> list[Block]:
    with open(path, encoding="utf-8", errors="replace") as fp:
        raw = fp.read()
    title = os.path.splitext(os.path.basename(path))[0]
    blocks = [
        Block(para.strip(), section_path=title)
        for para in raw.split("\n\n")
        if para.strip()
    ]
    if not blocks:
        raise ParseError("文本文件为空")
    return blocks

