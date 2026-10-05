from __future__ import annotations

import re

from .agreement import AgreementMetrics
from .models import OcrPassResult
from .quality import PageQuality


def _character_plausibility(text: str) -> float:
    if not text:
        return 0.0
    printable = sum(1 for char in text if char.isprintable() and char != "\ufffd")
    alnum = sum(1 for char in text if char.isalnum())
    weird_runs = len(re.findall(r"[^\w\s.,:;!?()'\"/\\-]{3,}", text, re.UNICODE))
    score = printable / len(text) * 70 + min(30, alnum / len(text) * 55) - weird_runs * 4
    return max(0.0, min(100.0, score))


def calibrate_confidence(winner: OcrPassResult, agreement: AgreementMetrics, quality: PageQuality) -> float:
    raw = winner.mean_confidence or 0.0
    plausibility = _character_plausibility(winner.canonical_text)
    token_support = min(100.0, winner.token_count * 2.5)
    quality_penalty = quality.blur_score * 0.06 + quality.noise_score * 0.04 + quality.edge_clipping_score * 0.03
    score = raw * 0.62 + plausibility * 0.14 + agreement.mean_pairwise_similarity * 0.14 + token_support * 0.10 - quality_penalty
    return round(max(0.0, min(100.0, score)), 2)
