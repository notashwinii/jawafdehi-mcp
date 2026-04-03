from __future__ import annotations

import re


def detect_structure(section_md: str) -> str:
    table_lines = [line for line in section_md.splitlines() if line.strip().startswith("|")]
    para_markers = re.findall(r"^\s*\([०-९0-9]+\)", section_md, re.MULTILINE)
    if len(table_lines) >= 3:
        return "table"
    if para_markers:
        return "paragraph"
    return "paragraph"
