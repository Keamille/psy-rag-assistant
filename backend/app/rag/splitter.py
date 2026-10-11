"""结构化切分（开发文档 §8.2）。

策略：先按标题层级分段，再在段内按语义边界切分。

三个参数各自解决一个具体问题，不要随手改：

  size=420     切太碎会丢掉上下文（"它"指代什么就查不到了），
               切太大又会稀释向量语义（一块里混了三四个话题，
               检索时相似度被平均掉）。中文技术文档 300–500 字是常见区间。

  overlap=60   防止答案正好被切在边界上：一句话的前半在上一块、
               后半在下一块，两块单独看都不完整。重叠让边界附近的内容
               在两块里都出现，检索到任一块都能拿到完整句子。

  不切在句子中间  这是硬约束。中文里一个句子被拦腰截断，
               语义损失比多切一块大得多。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 句末标点。中文顿号、逗号不算句末——按它们切会切出大量碎块。
SENTENCE_END = re.compile(r"(?<=[。！？；!?;])")
# 兜底：一段里完全没有句末标点时（例如表格行、代码、列表），
# 只能按逗号或空格切，避免造出一个超长块。
SOFT_BREAK = re.compile(r"(?<=[，,、])")


@dataclass
class Chunk:
    content: str
    section_path: str = ""
    page: int | None = None
    seq: int = 0
    title: str = ""
    sensitivity: str = "internal"
    tags: list[str] = field(default_factory=list)
    db_id: int | None = None


def split_section(
    text: str,
    section_path: str = "",
    page: int | None = None,
    size: int = 420,
    overlap: int = 60,
    min_len: int = 80,
    max_len: int = 700,
) -> list[Chunk]:
    """把一段正文切成若干块。返回的 seq 从 0 开始，仅在本段内有序。"""
    if size <= 0:
        raise ValueError("size 必须为正数")
    if overlap >= size:
        # 重叠大于等于块长会导致切分不收敛（块越切越多）
        raise ValueError("overlap 必须小于 size")

    units = _to_units(text, size=size, max_len=max_len)
    if not units:
        return []

    chunks: list[Chunk] = []
    buffer = ""

    for unit in units:
        candidate = f"{buffer}\n{unit}" if buffer else unit
        if len(candidate) > max_len and buffer:
            # 攒不下了，先把当前 buffer 落成一块，再带上重叠尾巴开始新块
            chunks.append(Chunk(buffer.strip(), section_path, page, len(chunks)))
            buffer = _tail(buffer, overlap) + unit
        else:
            buffer = candidate

    if buffer.strip():
        tail = buffer.strip()
        # 结尾的小尾巴并进上一块，而不是单独成块——
        # 太短的块在检索里几乎不可能被命中，留着只是噪音
        if chunks and len(tail) < min_len:
            chunks[-1].content = f"{chunks[-1].content}\n{tail}"
        else:
            chunks.append(Chunk(tail, section_path, page, len(chunks)))

    return chunks


def split_document(
    blocks: list,
    size: int = 420,
    overlap: int = 60,
    min_len: int = 80,
    max_len: int = 700,
    title: str = "",
    sensitivity: str = "internal",
    tags: list[str] | None = None,
) -> list[Chunk]:
    """把 loader 输出的 Block 序列切成块，并全局编号。

    相邻且 `section_path` 与 `page` 相同的 Block 会先合并再切分。
    这样做是因为 PDF 解析出来的一个段落经常被拆成多个 Block，
    逐个切会切出大量半截句子。
    """
    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_key: tuple[str, int | None] | None = None

    def flush() -> None:
        nonlocal buffer, buffer_key
        if not buffer or buffer_key is None:
            return
        section_path, page = buffer_key
        produced = split_section(
            "\n".join(buffer),
            section_path=section_path,
            page=page,
            size=size,
            overlap=overlap,
            min_len=min_len,
            max_len=max_len,
        )
        for chunk in produced:
            chunk.seq = len(chunks)
            chunk.title = title
            chunk.sensitivity = sensitivity
            chunk.tags = list(tags or [])
            chunks.append(chunk)
        buffer = []
        buffer_key = None

    for block in blocks:
        text = (getattr(block, "text", "") or "").strip()
        if not text:
            continue
        key = (getattr(block, "section_path", "") or "", getattr(block, "page", None))
        if buffer_key is not None and key != buffer_key:
            flush()
        buffer_key = key
        buffer.append(text)
    flush()

    return _merge_small(chunks, size=size, min_len=min_len, max_len=max_len)


def _merge_small(chunks: list[Chunk], size: int, min_len: int, max_len: int) -> list[Chunk]:
    """把过小的块并进前一块。

    为什么必须有这一步：标题层级是**检索的边界**，但不该是**切分的强边界**。
    一份提纲式文档每节只有一两句话，如果每个 `##` 都独立成块，
    就会产生一堆 60~120 字的碎片——这种块在向量检索里几乎不可能被稳定命中，
    而且在 Prompt 里占了一个完整的名额却只提供一句话的信息量。

    合并阈值取 `max(min_len, size // 2)`，而不是只盯着 min_len：
    目标块长是 420，那么 200 字的块同样偏小——它占了 Prompt 里一个完整名额，
    却只提供半块的信息量。按一半目标长度来合并，实际块长会收敛到 300~420。

    合并时保留前一块的 section_path：合并后的内容大部分仍属那一节，
    而且越靠前的章节路径对用户定位越有帮助。
    """
    if not chunks:
        return []

    merge_below = max(min_len, size // 2)
    merged: list[Chunk] = []
    for chunk in chunks:
        if merged and len(chunk.content) < merge_below:
            previous = merged[-1]
            combined = len(previous.content) + len(chunk.content) + 1
            if combined <= max_len:
                previous.content = f"{previous.content}\n{chunk.content}"
                continue
        merged.append(chunk)

    # 合并后重新编号，保证 seq 连续——它要写进向量 id，不能有洞
    for index, chunk in enumerate(merged):
        chunk.seq = index
    return merged


def _to_units(text: str, size: int, max_len: int) -> list[str]:
    """把一段文本拆成"最小可切单元"：短段落直接成单元，长段落按句子打包。"""
    units: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_len:
            units.append(paragraph)
            continue
        units.extend(_pack_sentences(paragraph, size=size))
    return units


def _pack_sentences(paragraph: str, size: int) -> list[str]:
    """按句子边界把长段落打包成不超过 size 的片段。"""
    sentences = [s for s in SENTENCE_END.split(paragraph) if s.strip()]
    if len(sentences) <= 1:
        # 整段没有句末标点：退一步按逗号切；再不行就原样返回，
        # 交给外层按 max_len 处理（宁可超长也不切碎句子）
        soft = [s for s in SOFT_BREAK.split(paragraph) if s.strip()]
        sentences = soft if len(soft) > 1 else [paragraph]

    units: list[str] = []
    buffer = ""
    for sentence in sentences:
        if len(buffer) + len(sentence) > size and buffer:
            units.append(buffer)
            buffer = sentence
        else:
            buffer += sentence
    if buffer:
        units.append(buffer)
    return units


def _tail(text: str, overlap: int) -> str:
    """取尾部重叠内容。

    从句子边界开始取，而不是死板地取最后 N 个字符——
    否则新块的开头会是半个句子，读起来像错乱。
    """
    if overlap <= 0 or len(text) <= overlap:
        return text
    tail = text[-overlap:]
    parts = SENTENCE_END.split(tail)
    if len(parts) > 1:
        # 丢掉第一段（它多半是被截断的半句）
        tail = "".join(parts[1:])
    return tail or text[-overlap:]

