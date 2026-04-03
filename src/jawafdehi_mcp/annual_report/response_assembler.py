from __future__ import annotations

import json
from pathlib import Path

from .constants import DATE_FIELDS, DATE_PATTERN, REQUIRED_RESPONSE_FIELDS
from .fs import read_json, write_json
from .utils import devanagari_to_ascii


def assemble_section_responses(
    slug: str, year: str, response_dir: Path, prompt_dir: Path
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    status = read_json(
        prompt_dir / "_status.json",
        default={"slug": slug, "year": year, "total_cases": 0, "cases": {}},
    )
    records_by_case: dict[str, dict[str, object]] = {}
    failures: list[dict[str, object]] = []

    batch_path = response_dir / "_batch.json"
    if batch_path.exists():
        for index, record in enumerate(_load_response(batch_path), start=1):
            case_id = _resolve_case_id(record, fallback=str(index))
            validated = _validate_record(record, str(batch_path))
            records_by_case[case_id] = validated
            if validated.get("_needs_review"):
                failures.append(validated)

    for case_path in sorted(response_dir.glob("case_*.json")):
        case_id = case_path.stem.removeprefix("case_")
        loaded = _load_response(case_path)
        if not loaded:
            continue
        validated = _validate_record(loaded[0], str(case_path))
        records_by_case[case_id] = validated
        if validated.get("_needs_review"):
            failures.append(validated)

    for case_id, case_status in status.get("cases", {}).items():
        case_status["done"] = case_id in records_by_case

    ordered_records = [records_by_case[key] for key in sorted(records_by_case, key=_sort_key)]
    return ordered_records, failures, status


def _load_response(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    raise ValueError(f"Unexpected JSON structure in {path}")


def _validate_record(record: dict[str, object], source_file: str) -> dict[str, object]:
    issues: list[str] = []
    validated = dict(record)

    for field in REQUIRED_RESPONSE_FIELDS:
        if field not in validated:
            issues.append(f"missing key: {field}")

    for field in DATE_FIELDS:
        value = validated.get(field)
        if value in (None, "", "null", "None"):
            continue
        normalized = devanagari_to_ascii(str(value)) or str(value)
        if not DATE_PATTERN.match(normalized):
            issues.append(f"bad date format in {field}: {value}")
        validated[field] = normalized

    if "क्र_सं" in validated and validated.get("क्र_सं") is not None:
        validated["क्र_सं"] = devanagari_to_ascii(str(validated["क्र_सं"]))

    validated["_source_file"] = source_file
    validated["_needs_review"] = bool(issues)
    if issues:
        validated["_review_issues"] = issues
    return validated


def _resolve_case_id(record: dict[str, object], fallback: str) -> str:
    serial = record.get("क्र_सं")
    if serial in (None, "", "null", "None"):
        return fallback
    return devanagari_to_ascii(str(serial)) or fallback


def _sort_key(value: str) -> tuple[int, str]:
    try:
        return (0, f"{int(value):08d}")
    except ValueError:
        return (1, value)


def persist_assembled_artifacts(
    records_path: Path,
    failures_path: Path,
    status_path: Path,
    records: list[dict[str, object]],
    failures: list[dict[str, object]],
    status: dict[str, object],
) -> None:
    write_json(records_path, records)
    write_json(failures_path, failures)
    write_json(status_path, status)
