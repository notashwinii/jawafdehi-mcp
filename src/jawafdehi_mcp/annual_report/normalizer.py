from __future__ import annotations

import re

from .constants import DEVANAGARI_DIGITS
from .utils import normalize_inline_whitespace


def normalize_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for record in records:
        item = dict(record)
        item["बिगो_रकम"] = normalize_bigo(item.get("बिगो_रकम_raw"))
        item["आयोगको_निर्णय_मिति"] = normalize_miti(item.get("आयोगको_निर्णय_मिति"))
        item["आरोपपत्र_दायर_मिति"] = normalize_miti(item.get("आरोपपत्र_दायर_मिति"))
        item["प्रतिवादीको_नाम"] = _normalize_names(item.get("प्रतिवादीको_नाम"))
        if item.get("पद_र_कार्यालय") is not None:
            item["पद_र_कार्यालय"] = normalize_inline_whitespace(str(item["पद_र_कार्यालय"]))
        for text_field in ("उजुरीको_व्यहोरा", "अनुसन्धानबाट_पुष्टि", "कसुर_दफा"):
            if item.get(text_field) is not None:
                item[text_field] = normalize_inline_whitespace(str(item[text_field]))

        if item.get("प्रतिवादी_सङ्ख्या") in (None, "", "null", "None"):
            names = [part.strip() for part in str(item.get("प्रतिवादीको_नाम", "")).split("/") if part.strip()]
            item["प्रतिवादी_सङ्ख्या"] = len(names) if names else None
        else:
            try:
                item["प्रतिवादी_सङ्ख्या"] = int(str(item["प्रतिवादी_सङ्ख्या"]).translate(DEVANAGARI_DIGITS))
            except ValueError:
                item["_needs_review"] = True
        normalized.append(item)
    return normalized


def normalize_bigo(raw: object) -> str | None:
    if raw in (None, "", "-", "–", "—"):
        return None
    value = str(raw).strip()
    value = value.replace(",", "")
    value = value.translate(DEVANAGARI_DIGITS)
    value = value.replace("।", ".")
    value = re.sub(r"\.([–\-—])$", ".0", value)
    value = re.sub(r"[^\d\.]", "", value)
    if not value or value == ".":
        return None
    return value


def normalize_miti(raw: object) -> str | None:
    if raw in (None, "", "null", "None"):
        return None
    return str(raw).strip().translate(DEVANAGARI_DIGITS).replace("।", ".")


def _normalize_names(raw: object) -> str | None:
    if raw in (None, "", "null", "None"):
        return None
    parts = [normalize_inline_whitespace(part) for part in str(raw).split("/")]
    parts = [part for part in parts if part]
    if not parts:
        return None
    return " / ".join(parts)
