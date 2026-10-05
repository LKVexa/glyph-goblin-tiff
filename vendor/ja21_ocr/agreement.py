from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher

from .models import OcrPassResult


@dataclass(slots=True)
class AgreementMetrics:
    mean_pairwise_similarity: float
    minimum_pairwise_similarity: float
    maximum_pairwise_similarity: float
    unanimous_token_ratio: float
    disagreement_count: int
    pairwise: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def compare_passes(passes: list[OcrPassResult]) -> AgreementMetrics:
    pairwise: list[dict[str, object]] = []
    similarities: list[float] = []
    token_sets = []
    for item in passes:
        token_sets.append(item.canonical_text.split())
    for i, left in enumerate(passes):
        for right in passes[i + 1:]:
            ratio = SequenceMatcher(None, left.canonical_text, right.canonical_text, autojunk=False).ratio() * 100
            ratio = round(ratio, 3)
            similarities.append(ratio)
            pairwise.append({"left_pass": left.pass_number, "right_pass": right.pass_number, "similarity": ratio})
    if not token_sets:
        unanimous = 0.0
    else:
        common = set(token_sets[0])
        union = set(token_sets[0])
        for tokens in token_sets[1:]:
            common.intersection_update(tokens)
            union.update(tokens)
        unanimous = round((len(common) / max(1, len(union))) * 100, 3)
    return AgreementMetrics(
        mean_pairwise_similarity=round(sum(similarities) / len(similarities), 3) if similarities else 100.0,
        minimum_pairwise_similarity=min(similarities) if similarities else 100.0,
        maximum_pairwise_similarity=max(similarities) if similarities else 100.0,
        unanimous_token_ratio=unanimous,
        disagreement_count=sum(1 for value in similarities if value < 99.999),
        pairwise=pairwise,
    )
