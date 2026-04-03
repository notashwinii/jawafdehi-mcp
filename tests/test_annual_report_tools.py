"""Tests for the annual-report MCP tools migrated from regrex."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jawafdehi_mcp.annual_report.extractor import (
    ExtractionError,
    MissingExtractorDependencyError,
    extract_pdf_to_markdown,
)
from jawafdehi_mcp.annual_report.normalizer import normalize_bigo, normalize_miti
from jawafdehi_mcp.annual_report.pipeline import assemble_year, prepare_year
from jawafdehi_mcp.annual_report.response_assembler import assemble_section_responses
from jawafdehi_mcp.annual_report.structure_router import detect_structure
from jawafdehi_mcp.annual_report.toc_discovery import discover_sections
from jawafdehi_mcp.tools.annual_report_pipeline import (
    AnnualReportPathsTool,
    AnnualReportStatusTool,
    AssembleAnnualReportYearTool,
    PrepareAnnualReportYearTool,
)

SAMPLE_MD = """विषयसूची
६.३.१ झुठा शैक्षिक योग्यताको प्रमाणपत्रसम्बन्धी मुद्दाहरू -------- 36
६.३.२ बिबिध मुद्दाहरू -------- 40

६.३.१ झुठा शैक्षिक योग्यताको प्रमाणपत्रसम्बन्धी मुद्दाहरू
| क्र.सं. | प्रतिवादीको नाम, पद र कार्यालय | निर्णय मिति | बिगो रकम |
| --- | --- | --- | --- |
| १ | राम बहादुर, अधिकृत, शिक्षा कार्यालय | २०७१।४।११ | १,५०,००० |

६.३.२ बिबिध मुद्दाहरू
(१) प्रतिवादी सीता अधिकारी। मिति २०७२।१।२ मा विशेष अदालतमा आरोपपत्र दायर। मिति २०७१।१२।३० को निर्णयानुसार बिगो रु.५००० कायम गरी।
(२) प्रतिवादी गीता शर्मा। मिति २०७२।२।१ मा विशेष अदालतमा आरोपपत्र दायर।
"""


@pytest.fixture
def annual_report_workspace(tmp_path: Path) -> Path:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "sample.md").write_text(SAMPLE_MD, encoding="utf-8")
    return tmp_path


def test_discover_sections():
    sections = discover_sections(SAMPLE_MD)
    assert len(sections) == 2
    assert sections[0]["slug"] == "jhuta_praman"


def test_detect_structure():
    assert detect_structure("| a |\n| - |\n| 1 |\n| 2 |\n| 3 |\n| 4 |\n") == "table"
    assert detect_structure("(१) test") == "paragraph"


def test_prepare_md_creates_debug_and_prompts(annual_report_workspace: Path):
    result = prepare_year(
        annual_report_workspace,
        "2071-72",
        md_path=annual_report_workspace / "reports" / "sample.md",
    )
    assert result["sections"] == 2
    manifest = json.loads(
        (
            annual_report_workspace
            / "debug"
            / "2071-72"
            / "section_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest[0]["structure"] == "table"
    assert manifest[1]["structure"] == "paragraph"
    assert (
        annual_report_workspace / "prompts" / "2071-72" / "bibidh" / "_batch.txt"
    ).exists()


def test_assemble_paragraph_and_write_xlsx(annual_report_workspace: Path):
    prepare_year(
        annual_report_workspace,
        "2071-72",
        md_path=annual_report_workspace / "reports" / "sample.md",
    )
    response_dir = annual_report_workspace / "llm_responses" / "2071-72" / "bibidh"
    response_dir.mkdir(parents=True, exist_ok=True)
    (response_dir / "_batch.json").write_text(
        json.dumps(
            [
                {
                    "क्र_सं": "1",
                    "प्रतिवादीको_नाम": "सीता अधिकारी",
                    "पद_र_कार्यालय": "अधिकृत",
                    "उजुरीको_व्यहोरा": "गल्ती",
                    "अनुसन्धानबाट_पुष्टि": "पुष्टि",
                    "आयोगको_निर्णय_मिति": "2071.12.30",
                    "आरोपपत्र_दायर_मिति": "2072.1.2",
                    "बिगो_रकम_raw": "5000",
                    "कसुर_दफा": None,
                    "प्रतिवादी_सङ्ख्या": 1,
                },
                {
                    "क्र_सं": "2",
                    "प्रतिवादीको_नाम": "गीता शर्मा",
                    "पद_र_कार्यालय": "कर्मचारी",
                    "उजुरीको_व्यहोरा": "गल्ती",
                    "अनुसन्धानबाट_पुष्टि": "पुष्टि",
                    "आयोगको_निर्णय_मिति": None,
                    "आरोपपत्र_दायर_मिति": "2072.2.1",
                    "बिगो_रकम_raw": None,
                    "कसुर_दफा": None,
                    "प्रतिवादी_सङ्ख्या": 1,
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = assemble_year(annual_report_workspace, "2071-72")
    assert result["sections_written"] == 2
    assert (
        annual_report_workspace / "output" / "2071-72" / "bibidh.xlsx"
    ).exists()
    normalized = json.loads(
        (
            annual_report_workspace
            / "debug"
            / "2071-72"
            / "records"
            / "bibidh_normalized.json"
        ).read_text(encoding="utf-8")
    )
    assert normalized[0]["बिगो_रकम"] == "5000"


def test_assemble_section_responses_marks_invalid_dates_for_review(
    annual_report_workspace: Path,
):
    prompt_dir = annual_report_workspace / "prompts" / "2071-72" / "bibidh"
    response_dir = annual_report_workspace / "llm_responses" / "2071-72" / "bibidh"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    response_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "_status.json").write_text(
        json.dumps(
            {
                "slug": "bibidh",
                "year": "2071-72",
                "total_cases": 1,
                "cases": {"1": {"done": False}},
            }
        ),
        encoding="utf-8",
    )
    (response_dir / "case_1.json").write_text(
        json.dumps(
            {
                "क्र_सं": "1",
                "प्रतिवादीको_नाम": "नाम",
                "पद_र_कार्यालय": "पद",
                "उजुरीको_व्यहोरा": "व्यहोरा",
                "अनुसन्धानबाट_पुष्टि": "पुष्टि",
                "आयोगको_निर्णय_मिति": "2071/1/1",
                "आरोपपत्र_दायर_मिति": None,
                "बिगो_रकम_raw": None,
                "कसुर_दफा": None,
                "प्रतिवादी_सङ्ख्या": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    records, failures, status = assemble_section_responses(
        "bibidh", "2071-72", response_dir, prompt_dir
    )
    assert records[0]["_needs_review"] is True
    assert len(failures) == 1
    assert status["cases"]["1"]["done"] is True


def test_normalizers():
    assert normalize_bigo("१,५०,०००") == "150000"
    assert normalize_miti("२०७१।४।११") == "2071.4.11"


def test_extract_pdf_missing_dependency(monkeypatch, annual_report_workspace: Path):
    monkeypatch.setitem(__import__("sys").modules, "markitdown", None)
    with pytest.raises(MissingExtractorDependencyError):
        extract_pdf_to_markdown(annual_report_workspace / "reports" / "missing.pdf")


def test_extract_pdf_success_and_empty(monkeypatch, annual_report_workspace: Path):
    class FakeResult:
        def __init__(self, text_content: str) -> None:
            self.text_content = text_content
            self.title = "report"

    class FakeMarkItDown:
        def __init__(self, *, enable_plugins: bool) -> None:
            self.enable_plugins = enable_plugins

        def convert(self, path: str) -> FakeResult:
            if path.endswith("empty.pdf"):
                return FakeResult("")
            return FakeResult("# extracted")

    fake_module = type("FakeModule", (), {"MarkItDown": FakeMarkItDown})
    monkeypatch.setitem(__import__("sys").modules, "markitdown", fake_module)
    result = extract_pdf_to_markdown(annual_report_workspace / "reports" / "ok.pdf")
    assert result.markdown == "# extracted"
    with pytest.raises(ExtractionError):
        extract_pdf_to_markdown(annual_report_workspace / "reports" / "empty.pdf")


@pytest.mark.asyncio
async def test_prepare_tool_returns_json(annual_report_workspace: Path):
    tool = PrepareAnnualReportYearTool()
    response = await tool.execute(
        {
            "workspace_root": str(annual_report_workspace),
            "year": "2071-72",
            "md_path": "reports/sample.md",
        }
    )
    payload = json.loads(response[0].text)
    assert payload["sections"] == 2


@pytest.mark.asyncio
async def test_status_and_paths_tools(annual_report_workspace: Path):
    prepare_year(
        annual_report_workspace,
        "2071-72",
        md_path=annual_report_workspace / "reports" / "sample.md",
    )
    status_tool = AnnualReportStatusTool()
    status_response = await status_tool.execute(
        {"workspace_root": str(annual_report_workspace), "year": "2071-72"}
    )
    status_payload = json.loads(status_response[0].text)
    assert status_payload["year"] == "2071-72"
    assert len(status_payload["rows"]) == 2

    paths_tool = AnnualReportPathsTool()
    paths_response = await paths_tool.execute(
        {"workspace_root": str(annual_report_workspace), "year": "2071-72"}
    )
    paths_payload = json.loads(paths_response[0].text)
    assert paths_payload["paths"]["report_markdown"].endswith("reports/2071-72.md")


@pytest.mark.asyncio
async def test_assemble_tool_errors_before_prepare(tmp_path: Path):
    tool = AssembleAnnualReportYearTool()
    response = await tool.execute(
        {"workspace_root": str(tmp_path), "year": "2071-72"}
    )
    assert "Error:" in response[0].text
