from __future__ import annotations

import difflib
import json
import unicodedata
from pathlib import Path
from typing import Iterable

from .models import OcrWord

COMPARISON_CONTRACT = {
    "contract_id": "JA21-EXACT-TOKEN-STREAM-1",
    "encoding": "UTF-8",
    "unicode_normalization": "NFC",
    "token_separator": "U+0020 SPACE",
    "line_and_layout_whitespace": "represented by one token separator",
    "leading_trailing_whitespace": "removed",
    "null_characters": "removed",
    "control_characters": "removed except token separator",
    "page_scope": "one page at a time",
    "acceptance": "exact code-point equality after contract transformation",
}


def normalize_token(token: str) -> str:
    value = unicodedata.normalize("NFC", token.replace("\x00", ""))
    return "".join(character for character in value if character == " " or not unicodedata.category(character).startswith("C"))


def canonical_from_tokens(tokens: Iterable[str]) -> str:
    return " ".join(value for token in tokens if (value := normalize_token(token).strip()))


def canonical_from_words(words: Iterable[OcrWord]) -> str:
    ordered = sorted(words, key=lambda item: (item.block_num, item.par_num, item.line_num, item.word_num, item.top, item.left))
    return canonical_from_tokens(item.text for item in ordered)


def exact_compare(expected: str, actual: str) -> dict[str, object]:
    passed = expected == actual
    first_mismatch: int | None = None
    if not passed:
        limit = min(len(expected), len(actual))
        for index in range(limit):
            if expected[index] != actual[index]:
                first_mismatch = index
                break
        if first_mismatch is None:
            first_mismatch = limit
    opcodes = []
    differences = 0
    matcher = difflib.SequenceMatcher(a=expected, b=actual, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            differences += max(i2 - i1, j2 - j1)
            opcodes.append({
                "operation": tag,
                "expected_range": [i1, i2],
                "actual_range": [j1, j2],
                "expected": expected[i1:i2],
                "actual": actual[j1:j2],
            })
    return {
        "contract": COMPARISON_CONTRACT,
        "passed": passed,
        "expected_length": len(expected),
        "actual_length": len(actual),
        "difference_count": differences,
        "first_mismatch_offset": first_mismatch,
        "differences": opcodes,
    }


def write_difference_report(destination_json: Path, destination_md: Path, comparison: dict[str, object]) -> None:
    destination_json.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# JA21 OCR Exact Verification Difference Report",
        "",
        f"- Contract: `{COMPARISON_CONTRACT['contract_id']}`",
        f"- Passed: **{comparison['passed']}**",
        f"- Expected characters: {comparison['expected_length']}",
        f"- Extracted characters: {comparison['actual_length']}",
        f"- Difference count: {comparison['difference_count']}",
        f"- First mismatch offset: {comparison['first_mismatch_offset']}",
        "",
        "## Differences",
        "",
    ]
    differences = comparison.get("differences") or []
    if not differences:
        lines.append("No character differences were detected.")
    else:
        for index, item in enumerate(differences, start=1):
            lines.extend([
                f"### Difference {index}",
                "",
                f"- Operation: `{item['operation']}`",
                f"- Expected range: `{item['expected_range']}`",
                f"- Extracted range: `{item['actual_range']}`",
                f"- Expected: `{str(item['expected']).replace('`', 'ˋ')}`",
                f"- Extracted: `{str(item['actual']).replace('`', 'ˋ')}`",
                "",
            ])
    destination_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
