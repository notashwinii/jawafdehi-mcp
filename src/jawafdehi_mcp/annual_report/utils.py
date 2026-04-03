from __future__ import annotations

import re

from .constants import DEVANAGARI_DIGITS, SLUG_KEYWORDS


def devanagari_to_ascii(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value).translate(DEVANAGARI_DIGITS)


def normalize_inline_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"[ \t]+", " ", str(value)).strip()


def compact_blank_lines(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", value.strip())


def normalize_header_text(value: str) -> str:
    value = normalize_inline_whitespace(value) or ""
    return value.replace("_", " ").replace("।", ".")


def heading_anchor_from_title(raw_title: str) -> str:
    title = re.sub(r"^\s*[०-९0-9]+(?:\.[०-९0-9]+)*\s*", "", raw_title)
    title = re.sub(r"\s*-{2,}\s*\d+\s*$", "", title)
    return normalize_inline_whitespace(title) or raw_title.strip()


def slugify_title(raw_title: str, existing: set[str]) -> str:
    normalized = normalize_inline_whitespace(raw_title) or raw_title
    for keywords, slug in SLUG_KEYWORDS:
        if all(keyword in normalized for keyword in keywords):
            return uniquify_slug(slug, existing)

    anchor = heading_anchor_from_title(raw_title)
    asciiish = re.sub(r"[^a-z0-9]+", "_", anchor.lower()).strip("_")
    fallback = asciiish if asciiish else "unknown_section"
    return uniquify_slug(fallback, existing)


def uniquify_slug(base: str, existing: set[str]) -> str:
    if base not in existing:
        existing.add(base)
        return base
    index = 2
    while f"{base}_{index}" in existing:
        index += 1
    slug = f"{base}_{index}"
    existing.add(slug)
    return slug
