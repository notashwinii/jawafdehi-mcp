from __future__ import annotations

from pathlib import Path

from .constants import CASE_START
from .fs import write_json, write_text
from .utils import devanagari_to_ascii


def split_case_blocks(section_md: str) -> list[tuple[str, str]]:
    matches = list(CASE_START.finditer(section_md))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section_md)
        blocks.append((match.group(1), section_md[start:end].strip()))
    return blocks


def export_case_prompts(
    slug: str,
    year: str,
    section_md: str,
    prompt_template: str,
    batch_template: str,
    out_dir: Path,
) -> dict[str, object]:
    blocks = split_case_blocks(section_md)
    if not blocks:
        return {"slug": slug, "year": year, "total_cases": 0, "cases": {}}

    for devanagari_num, block in blocks:
        ascii_num = devanagari_to_ascii(devanagari_num) or devanagari_num
        prompt = prompt_template.replace("{CASE_BLOCK}", block)
        write_text(out_dir / f"case_{ascii_num}.txt", prompt)

    separator = "\n\n" + ("-" * 60) + "\n\n"
    all_cases = separator.join(
        f"मुद्दा नं. {devanagari_to_ascii(num) or num}:\n{block}" for num, block in blocks
    )
    batch_prompt = batch_template.replace("{ALL_CASES}", all_cases)
    write_text(out_dir / "_batch.txt", batch_prompt)

    status = {
        "slug": slug,
        "year": year,
        "total_cases": len(blocks),
        "cases": {
            (devanagari_to_ascii(num) or num): {
                "devanagari_num": num,
                "prompt_file": f"case_{devanagari_to_ascii(num) or num}.txt",
                "response_file": f"case_{devanagari_to_ascii(num) or num}.json",
                "done": False,
            }
            for num, _ in blocks
        },
    }
    write_json(out_dir / "_status.json", status)
    return status
