from __future__ import annotations

from .constants import TOC_ENTRY
from .utils import heading_anchor_from_title, slugify_title


def discover_sections(markdown: str) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    existing_slugs: set[str] = set()
    lines = markdown.splitlines()

    for match in TOC_ENTRY.finditer(markdown):
        raw_title = match.group(1).strip()
        page_hint = int(match.group(2))
        line_index = markdown[: match.start()].count("\n")
        sections.append(
            {
                "raw_title": raw_title,
                "page_hint": page_hint,
                "slug": slugify_title(raw_title, existing_slugs),
                "heading_anchor": heading_anchor_from_title(raw_title),
                "structure": None,
                "_toc_line_index": line_index,
                "_source_line_count": len(lines),
            }
        )

    if not sections:
        raise ValueError(
            "No case sections ending with 'मुद्दाहरू' were found in the Markdown table of contents."
        )

    return sections
