from __future__ import annotations

import re

from .constants import COLUMN_MAP
from .utils import devanagari_to_ascii, normalize_header_text, normalize_inline_whitespace

DESIGNATION_RE = re.compile(
    r"(?<=[^\s]),?\s*(प्र\.अ\.|प्र\.स\.नि\.|ना\.सु\.|का\.मु\.|तत्कालीन|वरिष्ठ|नायब|उप|सहायक|प्रमुख|निर्देशक|अधिकृत|इन्जिनियर|लेखापाल|सुब्बा|अध्यक्ष|प्रहरी|शिक्षक|प्राध्यापक|सचिव|महानिर्देशक|स्रोतव्यक्ति|सञ्चालक)",
    re.UNICODE,
)


def parse_md_table(section_md: str) -> list[dict[str, object]]:
    rows = [_split_table_row(line) for line in section_md.splitlines() if line.strip().startswith("|")]
    rows = [row for row in rows if row]
    if len(rows) < 2:
        return []

    header = rows[0]
    body = [row for row in rows[1:] if not _is_separator_row(row)]
    normalized_headers = [normalize_header_text(cell) for cell in header]
    records: list[dict[str, object]] = []

    for row in body:
        padded = row + [""] * (len(normalized_headers) - len(row))
        raw_record = dict(zip(normalized_headers, padded, strict=False))
        mapped = _map_table_record(raw_record)
        if any(value not in (None, "", []) for value in mapped.values()):
            records.append(mapped)

    return records


def _split_table_row(line: str) -> list[str]:
    inner = line.strip().strip("|")
    return [cell.strip() for cell in inner.split("|")]


def _is_separator_row(row: list[str]) -> bool:
    return all(re.fullmatch(r"[:\-\s]+", cell or "") for cell in row)


def _map_table_record(raw_record: dict[str, str]) -> dict[str, object]:
    record: dict[str, object] = {}
    for header, value in raw_record.items():
        mapped_key = COLUMN_MAP.get(header, header.replace(" ", "_"))
        if mapped_key is None:
            continue
        clean_value = normalize_inline_whitespace(value)
        if mapped_key == "_name_office_raw":
            name, office = split_name_office(clean_value or "")
            record["प्रतिवादीको_नाम"] = name or None
            record["पद_र_कार्यालय"] = office or None
        elif mapped_key == "_other_accused_raw":
            if clean_value:
                existing = record.get("प्रतिवादीको_नाम")
                record["प्रतिवादीको_नाम"] = (
                    f"{existing} / {clean_value}" if existing else clean_value
                )
        elif mapped_key == "बिगो_रकम_raw":
            record["बिगो_रकम_raw"] = clean_value or None
        elif mapped_key == "क्र_सं":
            record["क्र_सं"] = devanagari_to_ascii(clean_value) or None
        elif mapped_key == "प्रतिवादी_सङ्ख्या":
            record["प्रतिवादी_सङ्ख्या"] = _safe_int(devanagari_to_ascii(clean_value))
        else:
            record[mapped_key] = clean_value or None

    names = [part.strip() for part in str(record.get("प्रतिवादीको_नाम", "")).split("/") if part.strip()]
    if names and not record.get("प्रतिवादी_सङ्ख्या"):
        record["प्रतिवादी_सङ्ख्या"] = len(names)
    return record


def split_name_office(raw: str) -> tuple[str, str]:
    match = DESIGNATION_RE.search(raw)
    if match:
        return raw[: match.start()].strip(" ,"), raw[match.start() :].strip()
    parts = raw.split(",", 1)
    return parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")


def _safe_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None
