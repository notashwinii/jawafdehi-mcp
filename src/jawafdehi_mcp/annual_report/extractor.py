from __future__ import annotations

import multiprocessing
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from time import monotonic, strftime
from typing import Callable


class ExtractionError(RuntimeError):
    """Raised when PDF extraction fails or yields unusable markdown."""


class MissingExtractorDependencyError(ExtractionError):
    """Raised when MarkItDown/likhit is unavailable."""


class ExtractionTimeoutError(ExtractionError):
    """Raised when PDF extraction exceeds the configured timeout."""


@dataclass(slots=True)
class PdfExtractionResult:
    markdown: str
    text: str | None
    metadata: dict[str, object]


def extract_pdf_to_markdown(
    pdf_path: Path,
    *,
    progress: Callable[[str], None] | None = None,
    heartbeat_seconds: float = 10.0,
    timeout_seconds: float = 300.0,
    fallback_to_default: bool = True,
) -> PdfExtractionResult:
    log = progress or _noop_progress
    try:
        result, elapsed = _run_with_timeout(
            pdf_path,
            progress=log,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=timeout_seconds,
            enable_plugins=True,
        )
        metadata = {
            "backend": "markitdown-likhit",
            "input_path": str(pdf_path),
            "plugins_enabled": True,
            "title": result.get("title"),
            "elapsed_seconds": round(elapsed, 3),
            "fallback_used": False,
        }
        return _build_result(pdf_path, result, metadata)
    except ExtractionTimeoutError:
        if not fallback_to_default:
            raise
        log(
            _stamp(
                "Plugin-based extraction timed out; falling back to default MarkItDown PDF conversion"
            )
        )
        result, elapsed = _run_with_timeout(
            pdf_path,
            progress=log,
            heartbeat_seconds=heartbeat_seconds,
            timeout_seconds=min(timeout_seconds, 120.0) if timeout_seconds else 120.0,
            enable_plugins=False,
        )
        metadata = {
            "backend": "markitdown-default",
            "input_path": str(pdf_path),
            "plugins_enabled": False,
            "title": result.get("title"),
            "elapsed_seconds": round(elapsed, 3),
            "fallback_used": True,
            "fallback_reason": "likhit_timeout",
        }
        return _build_result(pdf_path, result, metadata)


def _run_with_timeout(
    pdf_path: Path,
    *,
    progress: Callable[[str], None],
    heartbeat_seconds: float,
    timeout_seconds: float,
    enable_plugins: bool,
) -> tuple[dict[str, object], float]:
    mode = "MarkItDown.convert()" if enable_plugins else "default MarkItDown PDF conversion"
    progress(_stamp(f"Creating MarkItDown client for {pdf_path}"))
    ctx = multiprocessing.get_context("fork")
    queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(target=_run_markitdown_convert, args=(str(pdf_path), queue, enable_plugins))
    started_at = monotonic()
    process.start()
    progress(_stamp(f"Calling {mode} for {pdf_path}"))

    stop_event = Event()
    heartbeat = Thread(
        target=_heartbeat,
        args=(stop_event, progress, pdf_path, heartbeat_seconds, started_at),
        daemon=True,
    )
    heartbeat.start()
    try:
        status = "error"
        payload: object = "MarkItDown.convert() exited without returning output."
        while True:
            if not queue.empty():
                status, payload = queue.get()
                break
            if not process.is_alive():
                break
            elapsed = monotonic() - started_at
            if timeout_seconds and elapsed >= timeout_seconds:
                process.terminate()
                process.join(timeout=1)
                raise ExtractionTimeoutError(
                    f"PDF extraction timed out after {elapsed:.1f}s for {pdf_path}. "
                    f"The {'plugin-based' if enable_plugins else 'default'} converter appears to be hanging on this file."
                )
            stop_event.wait(min(heartbeat_seconds, 0.5))
    finally:
        stop_event.set()
        heartbeat.join(timeout=0.1)
        if process.is_alive():
            process.join(timeout=0.1)

    elapsed = monotonic() - started_at
    progress(_stamp(f"{mode} returned after {elapsed:.1f}s"))
    if status == "import_error":
        raise MissingExtractorDependencyError(
            "markitdown-likhit is not installed. Install project dependencies to enable PDF extraction."
        ) from ImportError(str(payload))
    if status == "error":
        raise ExtractionError(str(payload))
    result = payload if isinstance(payload, dict) else {}
    return result, elapsed


def _build_result(
    pdf_path: Path, result: dict[str, object], metadata: dict[str, object]
) -> PdfExtractionResult:
    markdown = str(result.get("text_content", "") or "")
    if not markdown.strip():
        raise ExtractionError(
            f"PDF extraction produced empty Markdown for {pdf_path}. Aborting before section parsing."
        )
    metadata["text_length"] = len(markdown)
    return PdfExtractionResult(markdown=markdown, text=markdown, metadata=metadata)


def _noop_progress(_: str) -> None:
    return None


def _stamp(message: str) -> str:
    return f"[{strftime('%H:%M:%S')}] {message}"


def _heartbeat(
    stop_event: Event,
    progress: Callable[[str], None],
    pdf_path: Path,
    heartbeat_seconds: float,
    started_at: float,
) -> None:
    while not stop_event.wait(heartbeat_seconds):
        elapsed = monotonic() - started_at
        progress(_stamp(f"Still extracting {pdf_path}... elapsed {elapsed:.1f}s"))


def _run_markitdown_convert(
    pdf_path: str, queue: multiprocessing.Queue, enable_plugins: bool
) -> None:
    try:
        from markitdown import MarkItDown
    except ImportError as exc:  # pragma: no cover
        queue.put(("import_error", str(exc)))
        return

    try:
        result = MarkItDown(enable_plugins=enable_plugins).convert(pdf_path)
    except Exception as exc:  # pragma: no cover
        queue.put(("error", f"{type(exc).__name__}: {exc}"))
        return

    queue.put(
        (
            "ok",
            {
                "text_content": getattr(result, "text_content", ""),
                "title": getattr(result, "title", None),
            },
        )
    )
