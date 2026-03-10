from __future__ import annotations


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
