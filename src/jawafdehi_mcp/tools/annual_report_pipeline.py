"""Annual report extraction tools migrated from the standalone regrex package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from mcp.types import TextContent

from jawafdehi_mcp.annual_report.pipeline import (
    assemble_year,
    extract_year_pdf,
    prepare_year,
    status_year,
)

from .base import BaseTool


def _coerce_root(arguments: dict[str, Any]) -> Path:
    workspace_root = arguments.get("workspace_root")
    if not isinstance(workspace_root, str) or not workspace_root.strip():
        raise ValueError("'workspace_root' must be a non-empty absolute path.")
    root = Path(workspace_root).expanduser()
    if not root.is_absolute():
        raise ValueError("'workspace_root' must be an absolute path.")
    return root


def _coerce_optional_path(arguments: dict[str, Any], key: str) -> Path | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' must be a non-empty path when provided.")
    path = Path(value).expanduser()
    return path if path.is_absolute() else _coerce_root(arguments) / path


def _coerce_required_path(arguments: dict[str, Any], key: str) -> Path:
    path = _coerce_optional_path(arguments, key)
    if path is None:
        raise ValueError(f"'{key}' is required.")
    return path


def _coerce_year(arguments: dict[str, Any]) -> str:
    value = arguments.get("year")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("'year' must be a non-empty string.")
    return value


def _coerce_timeout(arguments: dict[str, Any]) -> float:
    value = arguments.get("timeout_seconds", 300.0)
    if not isinstance(value, int | float):
        raise ValueError("'timeout_seconds' must be numeric.")
    return float(value)


def _run_with_logs(operation: Callable[[Callable[[str], None]], dict[str, Any]]) -> dict[str, Any]:
    logs: list[str] = []

    def progress(message: str) -> None:
        logs.append(message)

    result = dict(operation(progress))
    if logs:
        result["logs"] = logs
    return result


def _text_response(data: dict[str, Any]) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))]


class ExtractAnnualReportPdfTool(BaseTool):
    @property
    def name(self) -> str:
        return "extract_annual_report_pdf"

    @property
    def description(self) -> str:
        return (
            "Extract a Nepali annual report PDF to Markdown using MarkItDown with the "
            "configured likhit plugin, and write the report/debug extraction artifacts "
            "inside a workspace."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "workspace_root": {
                    "type": "string",
                    "description": "Absolute path to the annual-report workspace root.",
                },
                "year": {
                    "type": "string",
                    "description": "Year label like 2071-72.",
                },
                "pdf_path": {
                    "type": "string",
                    "description": "Absolute or workspace-relative path to the source PDF.",
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": "Optional extraction timeout in seconds. Defaults to 300.",
                    "default": 300,
                },
            },
            "required": ["workspace_root", "year", "pdf_path"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            root = _coerce_root(arguments)
            year = _coerce_year(arguments)
            pdf_path = _coerce_required_path(arguments, "pdf_path")
            timeout_seconds = _coerce_timeout(arguments)
            result = _run_with_logs(
                lambda progress: extract_year_pdf(
                    root,
                    year,
                    pdf_path=pdf_path,
                    progress=progress,
                    timeout_seconds=timeout_seconds,
                )
            )
            return _text_response(result)
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]


class PrepareAnnualReportYearTool(BaseTool):
    @property
    def name(self) -> str:
        return "prepare_annual_report_year"

    @property
    def description(self) -> str:
        return (
            "Prepare section manifests, split markdown, parse table sections, and export "
            "manual prompt files for paragraph sections in the annual-report pipeline."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "workspace_root": {
                    "type": "string",
                    "description": "Absolute path to the annual-report workspace root.",
                },
                "year": {"type": "string", "description": "Year label like 2071-72."},
                "md_path": {
                    "type": "string",
                    "description": "Absolute or workspace-relative path to an existing markdown file.",
                },
                "pdf_path": {
                    "type": "string",
                    "description": "Absolute or workspace-relative path to a source PDF.",
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": "Optional extraction timeout in seconds when using pdf_path.",
                    "default": 300,
                },
            },
            "required": ["workspace_root", "year"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            root = _coerce_root(arguments)
            year = _coerce_year(arguments)
            md_path = _coerce_optional_path(arguments, "md_path")
            pdf_path = _coerce_optional_path(arguments, "pdf_path")
            if bool(md_path) == bool(pdf_path):
                raise ValueError("Provide exactly one of 'md_path' or 'pdf_path'.")
            timeout_seconds = _coerce_timeout(arguments)
            result = _run_with_logs(
                lambda progress: prepare_year(
                    root,
                    year,
                    md_path=md_path,
                    pdf_path=pdf_path,
                    progress=progress,
                    timeout_seconds=timeout_seconds,
                )
            )
            return _text_response(result)
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]


class AssembleAnnualReportYearTool(BaseTool):
    @property
    def name(self) -> str:
        return "assemble_annual_report_year"

    @property
    def description(self) -> str:
        return (
            "Assemble manually saved JSON responses, normalize the resulting records, and "
            "write section-wise XLSX files for an annual report year."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "workspace_root": {
                    "type": "string",
                    "description": "Absolute path to the annual-report workspace root.",
                },
                "year": {"type": "string", "description": "Year label like 2071-72."},
            },
            "required": ["workspace_root", "year"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            root = _coerce_root(arguments)
            year = _coerce_year(arguments)
            result = _run_with_logs(
                lambda progress: assemble_year(root, year, progress=progress)
            )
            return _text_response(result)
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]


class AnnualReportStatusTool(BaseTool):
    @property
    def name(self) -> str:
        return "annual_report_status"

    @property
    def description(self) -> str:
        return (
            "Show paragraph extraction progress for an annual report year, including how "
            "many case-response JSON files have been dropped so far."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "workspace_root": {
                    "type": "string",
                    "description": "Absolute path to the annual-report workspace root.",
                },
                "year": {"type": "string", "description": "Year label like 2071-72."},
            },
            "required": ["workspace_root", "year"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            root = _coerce_root(arguments)
            year = _coerce_year(arguments)
            result = {"year": year, "rows": status_year(root, year)}
            return _text_response(result)
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]


class AnnualReportPathsTool(BaseTool):
    @property
    def name(self) -> str:
        return "annual_report_year_paths"

    @property
    def description(self) -> str:
        return (
            "Return the main working directories and files used by the annual-report "
            "pipeline for a given year."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "workspace_root": {
                    "type": "string",
                    "description": "Absolute path to the annual-report workspace root.",
                },
                "year": {"type": "string", "description": "Year label like 2071-72."},
            },
            "required": ["workspace_root", "year"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            root = _coerce_root(arguments)
            year = _coerce_year(arguments)
            result = {
                "year": year,
                "paths": {
                    "report_markdown": str(root / "reports" / f"{year}.md"),
                    "debug_dir": str(root / "debug" / year),
                    "prompt_dir": str(root / "prompts" / year),
                    "response_dir": str(root / "llm_responses" / year),
                    "output_dir": str(root / "output" / year),
                },
            }
            return _text_response(result)
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]
