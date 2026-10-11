"""文本清洗（开发文档 §8.2）。

一条硬约束贯穿全文：**只做删除与合并，不改写原句**。

原因是溯源：来源卡片给用户看的是**原文片段**，用户会拿去跟原文件核对。
如果清洗阶段顺手把「它」改成「自动思维」、把长句拆短，卡片上的文字就和
原文件对不上了，溯源这件事就失去意义。
"""

from __future__ import annotations

import re
from collections import Counter

from app.rag.loader import Block

# 页码行：纯数字、罗马数字，或 "第 12 页 / 12 / 共 30 页" 这类
PAGE_LINE = re.compile(
    r"^\s*(?:[-—–]\s*)?(?:第\s*)?\d{1,4}\s*(?:页)?\s*(?:/\s*共?\s*\d{1,4}\s*页?)?\s*(?:[-—–])?\s*$"
)
# 目录行：标题后面跟着一串点或中点
TOC_LINE = re.compile(r"^.{0,60}[.·。…]{4,}\s*\d{0,4}\s*$")
# 行尾多余的连字符断行（英文排版）；中文不用连字符，所以只处理拉丁字母
HYPHEN_BREAK = re.compile(r"([A-Za-z])-\n([a-z])")
URL = re.compile(r"https?://\S+")
BLANK_RUN = re.compile(r"\n{3,}")

# 页眉页脚判定：短行且在多页重复出现的才删。
# 只出现一两次的短行很可能是正文小标题，删了会丢内容。
HEADER_MAX_LEN = 30
HEADER_MIN_RATIO = 0.6


def clean(blocks: list[Block]) -> list[Block]:
    """清洗文本块。返回新的列表，不修改入参。"""
    if not blocks:
        return []

    repeated = _repeated_short_lines(blocks)
    cleaned: list[Block] = []
    for block in blocks:
        text = _clean_text(block.text, repeated)
        if text:
            cleaned.append(Block(text, block.section_path, block.page, dict(block.meta)))
    return cleaned


def _repeated_short_lines(blocks: list[Block]) -> set[str]:
    """找出跨页重复出现的短行——那就是页眉页脚。

    判定依据是**重复**而不是**长度**：随便删短行会误伤正文。
    只有既短、又出现在足够比例页面上的行，才敢删。
    """
    pages = {b.page for b in blocks if b.page}
    if len(pages) < 3:
        # 页数太少，统计不出"重复"，宁可不删
        return set()

    counter: Counter[str] = Counter()
    for block in blocks:
        for line in block.text.splitlines():
            stripped = line.strip()
            if 0 < len(stripped) <= HEADER_MAX_LEN:
                counter[stripped] += 1

    threshold = max(2, int(len(pages) * HEADER_MIN_RATIO))
    return {line for line, count in counter.items() if count >= threshold}


def _clean_text(text: str, repeated: set[str]) -> str:
    text = HYPHEN_BREAK.sub(r"\1\2", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = URL.sub("", text)

    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if stripped in repeated:
            continue
        if PAGE_LINE.match(stripped) and len(stripped) <= 20:
            continue
        if TOC_LINE.match(stripped):
            continue
        kept.append(line.rstrip())

    # 统一全角空格，压缩连续空行
    merged = "\n".join(kept).replace("\u3000", " ")
    return BLANK_RUN.sub("\n\n", merged).strip()

