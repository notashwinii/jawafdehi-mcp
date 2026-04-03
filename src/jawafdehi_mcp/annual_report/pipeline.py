from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .case_exporter import export_case_prompts
from .extractor import PdfExtractionResult, extract_pdf_to_markdown
from .fs import ensure_dir, read_json, write_json, write_text
from .normalizer import normalize_records
from .response_assembler import assemble_section_responses, persist_assembled_artifacts
from .section_splitter import split_sections
from .structure_router import detect_structure
from .table_parser import parse_md_table
from .templates import DEFAULT_BATCH_TEMPLATE, DEFAULT_CASE_TEMPLATE
from .toc_discovery import discover_sections


def _noop_progress(_: str) -> None:
    return None


@dataclass(slots=True)
class PipelinePaths:
    root: Path
    reports: Path
    prompts: Path
    responses: Path
    debug: Path
    output: Path

    @classmethod
    def from_root(cls, root: Path) -> "PipelinePaths":
        return cls(
            root=root,
            reports=root / "reports",
            prompts=root / "prompts",
            responses=root / "llm_responses",
            debug=root / "debug",
            output=root / "output",
        )


def prepare_year(
    root: Path,
    year: str,
    *,
    md_path: Path | None = None,
    pdf_path: Path | None = None,
    progress: Callable[[str], None] | None = None,
    timeout_seconds: float = 300.0,
) -> dict[str, object]:
    log = progress or _noop_progress
    paths = PipelinePaths.from_root(root)
    log(f"[{year}] Ensuring project directories")
    ensure_project_dirs(paths, year)
    if pdf_path:
        log(f"[{year}] Starting PDF to Markdown extraction from {pdf_path}")
    else:
        log(f"[{year}] Loading Markdown from {md_path}")
    source_markdown, extraction = _resolve_source_markdown(
        paths,
        year,
        md_path=md_path,
        pdf_path=pdf_path,
        progress=log,
        timeout_seconds=timeout_seconds,
    )
    if pdf_path:
        log(f"[{year}] PDF extraction complete")
    log(f"[{year}] Discovering sections from table of contents")
    manifest = discover_sections(source_markdown)
    write_json(paths.debug / year / "section_manifest.json", _clean_manifest(manifest))

    log(f"[{year}] Splitting {len(manifest)} sections")
    prompt_template, batch_template = _load_prompt_templates(paths)
    sections = split_sections(source_markdown, manifest)

    for item in manifest:
        slug = str(item["slug"])
        section_text = sections[slug]
        write_text(paths.debug / year / "sections" / f"{slug}.md", section_text)
        structure = detect_structure(section_text)
        item["structure"] = structure
        log(f"[{year}] Processing section '{slug}' as {structure}")
        if structure == "table":
            records = parse_md_table(section_text)
            write_json(paths.debug / year / "records" / f"{slug}_records.json", records)
            log(f"[{year}] Parsed {len(records)} table records for '{slug}'")
        else:
            export_case_prompts(
                slug=slug,
                year=year,
                section_md=section_text,
                prompt_template=prompt_template,
                batch_template=batch_template,
                out_dir=paths.prompts / year / slug,
            )
            log(f"[{year}] Exported prompts for paragraph section '{slug}'")

    write_json(paths.debug / year / "section_manifest.json", _clean_manifest(manifest))
    log(f"[{year}] Prepare complete")
    return {
        "year": year,
        "sections": len(manifest),
        "extraction_used": extraction is not None,
        "markdown_path": str(paths.reports / f"{year}.md") if extraction else str(md_path),
    }


def extract_year_pdf(
    root: Path,
    year: str,
    pdf_path: Path,
    *,
    progress: Callable[[str], None] | None = None,
    timeout_seconds: float = 300.0,
) -> dict[str, object]:
    log = progress or _noop_progress
    paths = PipelinePaths.from_root(root)
    log(f"[{year}] Ensuring project directories")
    ensure_project_dirs(paths, year)
    log(f"[{year}] Starting PDF to Markdown extraction from {pdf_path}")
    extraction = extract_pdf_to_markdown(
        pdf_path, progress=log, timeout_seconds=timeout_seconds
    )
    report_md_path = paths.reports / f"{year}.md"
    write_text(report_md_path, extraction.markdown)
    write_text(paths.debug / year / "extraction" / "extracted.md", extraction.markdown)
    if extraction.text:
        write_text(paths.debug / year / "extraction" / "extracted.txt", extraction.text)
    write_json(paths.debug / year / "extraction" / "metadata.json", extraction.metadata)
    log(f"[{year}] Wrote extracted markdown to {report_md_path}")
    return {
        "year": year,
        "markdown_path": str(report_md_path),
        "text_length": extraction.metadata.get("text_length"),
    }


def assemble_year(
    root: Path,
    year: str,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    from .xlsx_writer import write_section_xlsx

    log = progress or _noop_progress
    paths = PipelinePaths.from_root(root)
    log(f"[{year}] Loading section manifest")
    manifest = read_json(paths.debug / year / "section_manifest.json", default=[])
    if not manifest:
        raise FileNotFoundError(f"No section manifest found for {year}. Run prepare first.")

    written = 0
    for item in manifest:
        slug = item["slug"]
        structure = item["structure"]
        log(f"[{year}] Assembling section '{slug}' ({structure})")
        records_path = paths.debug / year / "records" / f"{slug}_records.json"
        failures_path = paths.debug / year / "records" / f"{slug}_failures.json"
        status_path = paths.prompts / year / slug / "_status.json"

        if structure == "table":
            records = read_json(records_path, default=[])
            failures = []
        else:
            records, failures, status = assemble_section_responses(
                slug=slug,
                year=year,
                response_dir=paths.responses / year / slug,
                prompt_dir=paths.prompts / year / slug,
            )
            persist_assembled_artifacts(
                records_path, failures_path, status_path, records, failures, status
            )

        normalized = normalize_records(records)
        write_json(paths.debug / year / "records" / f"{slug}_normalized.json", normalized)
        if structure == "table" and not failures_path.exists():
            write_json(failures_path, [])
        write_section_xlsx(normalized, paths.output / year / f"{slug}.xlsx")
        log(f"[{year}] Wrote XLSX for '{slug}' with {len(normalized)} records")
        written += 1

    log(f"[{year}] Assemble complete")
    return {"year": year, "sections_written": written}


def status_year(root: Path, year: str) -> list[dict[str, object]]:
    paths = PipelinePaths.from_root(root)
    manifest = read_json(paths.debug / year / "section_manifest.json", default=[])
    rows: list[dict[str, object]] = []
    for item in manifest:
        slug = item["slug"]
        structure = item["structure"]
        if structure == "table":
            rows.append(
                {
                    "section": slug,
                    "structure": "TABLE",
                    "done": "auto",
                    "remaining": 0,
                    "total": "auto",
                }
            )
            continue

        status = read_json(
            paths.prompts / year / slug / "_status.json",
            default={"total_cases": 0, "cases": {}},
        )
        done = sum(1 for case in status["cases"].values() if case.get("done"))
        total = int(status.get("total_cases", 0))
        rows.append(
            {
                "section": slug,
                "structure": "PARA",
                "done": done,
                "remaining": max(total - done, 0),
                "total": total,
            }
        )
    return rows


def ensure_project_dirs(paths: PipelinePaths, year: str) -> None:
    ensure_dir(paths.reports)
    ensure_dir(paths.prompts)
    ensure_dir(paths.responses / year)
    ensure_dir(paths.debug / year / "sections")
    ensure_dir(paths.debug / year / "records")
    ensure_dir(paths.debug / year / "extraction")
    ensure_dir(paths.output / year)
    _ensure_prompt_templates(paths)


def _resolve_source_markdown(
    paths: PipelinePaths,
    year: str,
    *,
    md_path: Path | None,
    pdf_path: Path | None,
    progress: Callable[[str], None] | None = None,
    timeout_seconds: float = 300.0,
) -> tuple[str, PdfExtractionResult | None]:
    if pdf_path:
        extraction = extract_pdf_to_markdown(
            pdf_path, progress=progress, timeout_seconds=timeout_seconds
        )
        write_text(paths.reports / f"{year}.md", extraction.markdown)
        write_text(paths.debug / year / "extraction" / "extracted.md", extraction.markdown)
        if extraction.text:
            write_text(paths.debug / year / "extraction" / "extracted.txt", extraction.text)
        write_json(paths.debug / year / "extraction" / "metadata.json", extraction.metadata)
        return extraction.markdown, extraction

    if not md_path:
        raise ValueError("One of md_path or pdf_path must be provided.")
    markdown = md_path.read_text(encoding="utf-8")
    write_text(paths.debug / year / "extraction" / "source.md", markdown)
    return markdown, None


def _clean_manifest(manifest: list[dict[str, object]]) -> list[dict[str, object]]:
    cleaned = []
    for item in manifest:
        cleaned.append({key: value for key, value in item.items() if not key.startswith("_")})
    return cleaned


def _ensure_prompt_templates(paths: PipelinePaths) -> None:
    template_path = paths.prompts / "template.txt"
    batch_template_path = paths.prompts / "batch_template.txt"
    if not template_path.exists():
        write_text(template_path, DEFAULT_CASE_TEMPLATE)
    if not batch_template_path.exists():
        write_text(batch_template_path, DEFAULT_BATCH_TEMPLATE)


def _load_prompt_templates(paths: PipelinePaths) -> tuple[str, str]:
    return (
        (paths.prompts / "template.txt").read_text(encoding="utf-8"),
        (paths.prompts / "batch_template.txt").read_text(encoding="utf-8"),
    )
