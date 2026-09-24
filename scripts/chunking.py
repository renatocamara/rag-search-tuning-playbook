"""
Two chunking strategies, so module 03 can show the difference on the same file.

naive
    Fixed-size character windows with overlap. This is what most first
    versions of a RAG pipeline do (and what generic "split by tokens" helpers
    give you). It cuts tables in half and separates a table from the heading
    and part number that give it meaning.

structured
    Split on Markdown headings, never split inside a table, and prepend a
    short contextual header (document title + part numbers) to every chunk so
    each chunk can stand on its own when the retriever returns it alone.
    Large sections are further split by paragraph up to max_chars.

Both return a list of dicts: {"text": ..., "section": ..., "index": n}.
"""

import re


def naive_chunks(body, max_chars=400, overlap=60):
    chunks, start, n = [], 0, 0
    while start < len(body):
        end = min(len(body), start + max_chars)
        chunks.append({"text": body[start:end].strip(), "section": "", "index": n})
        n += 1
        if end == len(body):
            break
        start = end - overlap
    return [c for c in chunks if c["text"]]


_HEADING = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)


def _split_sections(body):
    """Yield (heading, text) pairs. Text before the first heading gets heading ''."""
    positions = [(m.start(), m.group(2).strip()) for m in _HEADING.finditer(body)]
    if not positions:
        yield "", body
        return
    if positions[0][0] > 0:
        yield "", body[:positions[0][0]]
    for i, (pos, heading) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(body)
        text = body[pos:end]
        text = text.split("\n", 1)[1] if "\n" in text else ""
        yield heading, text


def _split_paragraphs_keep_tables(text, max_chars):
    """Split a section into blocks no longer than max_chars, but treat a whole
    Markdown table as one indivisible block."""
    blocks, current = [], []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|"):
            table = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                table.append(lines[i])
                i += 1
            blocks.append("\n".join(table))
            continue
        current.append(line)
        if line.strip() == "":
            blocks.append("\n".join(current))
            current = []
        i += 1
    if current:
        blocks.append("\n".join(current))

    out, buf = [], ""
    for b in blocks:
        b = b.strip("\n")
        if not b.strip():
            continue
        if b.lstrip().startswith("|"):
            if buf.strip():
                out.append(buf)
            out.append(b)  # a table is always its own block
            buf = ""
        elif len(buf) + len(b) + 2 <= max_chars:
            buf = (buf + "\n\n" + b) if buf else b
        else:
            if buf.strip():
                out.append(buf)
            buf = b
    if buf.strip():
        out.append(buf)
    return out


def structured_chunks(body, title, part_numbers, max_chars=1200):
    header = f"Document: {title}"
    if part_numbers:
        header += f"\nPart numbers: {', '.join(part_numbers)}"
    chunks, n = [], 0
    for heading, text in _split_sections(body):
        for block in _split_paragraphs_keep_tables(text, max_chars):
            prefix = header + (f"\nSection: {heading}" if heading else "") + "\n\n"
            chunks.append({"text": prefix + block.strip(), "section": heading, "index": n})
            n += 1
    return chunks


def chunk(body, strategy, title="", part_numbers=None, **kw):
    if strategy == "naive":
        return naive_chunks(body, **{k: v for k, v in kw.items() if k in ("max_chars", "overlap")})
    if strategy == "structured":
        return structured_chunks(body, title, part_numbers or [], **{k: v for k, v in kw.items() if k in ("max_chars",)})
    raise ValueError(f"unknown chunking strategy {strategy}")
