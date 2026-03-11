from __future__ import annotations

import re


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def chunk_text(text: str, limit: int = 3500) -> list[str]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    if len(normalized) <= limit:
        return [normalized]

    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    def split_hard(segment: str) -> None:
        for index in range(0, len(segment), limit):
            piece = segment[index : index + limit].strip()
            if piece:
                chunks.append(piece)

    paragraphs = normalized.split("\n\n")
    for paragraph in paragraphs:
        candidate = paragraph.strip()
        if not candidate:
            continue
        if len(candidate) > limit:
            flush()
            lines = candidate.splitlines()
            line_buffer = ""
            for line in lines:
                if len(line) > limit:
                    if line_buffer:
                        chunks.append(line_buffer.strip())
                        line_buffer = ""
                    split_hard(line)
                    continue
                joined = f"{line_buffer}\n{line}".strip() if line_buffer else line
                if len(joined) <= limit:
                    line_buffer = joined
                else:
                    if line_buffer:
                        chunks.append(line_buffer.strip())
                    line_buffer = line
            if line_buffer:
                chunks.append(line_buffer.strip())
            continue

        joined = f"{current}\n\n{candidate}".strip() if current else candidate
        if len(joined) <= limit:
            current = joined
        else:
            flush()
            current = candidate

    flush()
    return chunks


def normalize_display_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = ANSI_ESCAPE_RE.sub("", normalized)
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def chunk_display_text(text: str, limit: int = 3500) -> list[str]:
    cleaned = normalize_display_text(text)
    if not cleaned:
        return []

    chunks = chunk_text(cleaned, limit=limit)
    if len(chunks) <= 1:
        return chunks

    # Keep space for the chunk label.
    body_limit = max(50, limit - 20)
    relabeled_chunks = chunk_text(cleaned, limit=body_limit)
    total = len(relabeled_chunks)
    return [f"[Part {index}/{total}]\n\n{chunk}" for index, chunk in enumerate(relabeled_chunks, start=1)]
