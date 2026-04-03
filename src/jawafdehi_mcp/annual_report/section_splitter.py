from __future__ import annotations

import re

from .constants import FOOTER
from .utils import compact_blank_lines, normalize_inline_whitespace

_WORD_RE = re.compile(r"[\w\u0900-\u097F]+", re.UNICODE)


def split_sections(
    markdown: str, manifest: list[dict[str, object]]
) -> dict[str, str]:
    lines = markdown.splitlines()
    body_search_start = max(int(item.get("_toc_line_index", 0)) for item in manifest) + 1
    starts: list[tuple[int, dict[str, object]]] = []

    for item in manifest:
        anchor = str(item["heading_anchor"])
        index = _find_heading_line(lines, anchor, body_search_start)
        starts.append((index, item))

    starts.sort(key=lambda pair: pair[0])
    sections: dict[str, str] = {}
    for idx, (start_line, item) in enumerate(starts):
        next_line = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        chunk = "\n".join(lines[start_line:next_line]).strip()
        cleaned = FOOTER.sub("", chunk)
        sections[str(item["slug"])] = compact_blank_lines(cleaned)
    return sections


def _find_heading_line(lines: list[str], anchor: str, start_at: int) -> int:
    anchor_words = _tokenize(anchor)
    best_index = -1
    best_score = 0.0

    for idx, line in enumerate(lines[start_at:], start=start_at):
        line_words = _tokenize(line)
        if not line_words:
            continue
        overlap = len(anchor_words & line_words)
        if not overlap:
            continue
        score = overlap / max(len(anchor_words), 1)
        if anchor in normalize_inline_whitespace(line):
            score += 0.75
        if score > best_score:
            best_score = score
            best_index = idx

    if best_index == -1:
        for idx, line in enumerate(lines):
            if anchor in normalize_inline_whitespace(line):
                return idx
        raise ValueError(f"Could not find body heading for section anchor: {anchor}")
    return best_index


def _tokenize(value: str) -> set[str]:
    normalized = normalize_inline_whitespace(value) or ""
    return {token.lower() for token in _WORD_RE.findall(normalized)}
