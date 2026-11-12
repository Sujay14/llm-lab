"""Split page text into overlapping chunks. A chunk never spans two pages, so page numbers stay exact."""
from __future__ import annotations

from dataclasses import dataclass

import config
from services.pdf_processor import PageText


@dataclass
class Chunk:
    text: str
    pdf_page: int
    printed_label: str | None
    index: int  # position in the whole document, 0-based


def _split_long_line(line: str, size: int, overlap: int) -> list[str]:
    step = max(1, size - overlap)
    return [line[i : i + size] for i in range(0, len(line), step)]


def chunk_page(page: PageText, size: int, overlap: int) -> list[str]:
    """Pack whole lines into chunks of <= `size` characters, repeating ~`overlap` characters
    of trailing lines at the start of the next chunk. Splitting on line boundaries keeps
    table rows and 'name: value unit' lines intact."""
    lines: list[str] = []
    for line in page.text.splitlines():
        lines.extend(_split_long_line(line, size, overlap) if len(line) > size else [line])

    chunks: list[str] = []
    current: list[str] = []
    length = 0
    new_lines = 0  # lines in `current` that are not just carried-over overlap
    for line in lines:
        added = len(line) + 1
        if current and length + added > size and new_lines:
            chunks.append("\n".join(current))
            carry: list[str] = []
            carried = 0
            for prev in reversed(current):
                if carried + len(prev) + 1 > overlap:
                    break
                carry.insert(0, prev)
                carried += len(prev) + 1
            current, length, new_lines = carry, carried, 0
        current.append(line)
        length += added
        new_lines += 1
    if current and new_lines:
        chunks.append("\n".join(current))
    return chunks


def chunk_pages(
    pages: list[PageText], size: int = config.CHUNK_SIZE, overlap: int = config.CHUNK_OVERLAP
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        for text in chunk_page(page, size, overlap):
            if text.strip():
                chunks.append(Chunk(text.strip(), page.pdf_page, page.printed_label, len(chunks)))
    return chunks
