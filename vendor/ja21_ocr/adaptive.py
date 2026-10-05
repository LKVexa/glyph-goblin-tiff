from __future__ import annotations

from .models import OcrProfile
from .profiles import PROFILES
from .quality import PageQuality


def plan_profiles(quality: PageQuality) -> tuple[OcrProfile, ...]:
    """Deterministically order the six frozen profiles without changing membership."""
    score: dict[str, float] = {profile.profile_id: 0.0 for profile in PROFILES}
    score["P1_GENERAL_DOCUMENT"] += 30
    score["P2_DENSE_TEXT"] += quality.text_density * 0.55 + quality.table_likelihood * 0.15
    score["P3_MIXED_LAYOUT"] += quality.multi_column_likelihood * 0.8 + quality.photo_likelihood * 0.2
    score["P4_RECOVERY_HIGH_CONTRAST"] += quality.blur_score * 0.25 + (100 - quality.contrast_score) * 0.6 + quality.bleed_through_score * 0.2
    score["P5_RECOVERY_ENLARGED_SOURCE"] += quality.blur_score * 0.55 + max(0, 300 - quality.effective_dpi) * 0.18
    score["P6_RECOVERY_CONSERVATIVE_LAYOUT"] += quality.noise_score * 0.45 + quality.compression_artifact_score * 0.35 + quality.handwriting_likelihood * 0.15
    ranked = sorted(PROFILES, key=lambda profile: (-score[profile.profile_id], profile.profile_id))
    # Keep exactly 3 initial and 3 recovery phases: reorder only within the approved groups.
    initial_ids = {p.profile_id for p in PROFILES[:3]}
    recovery_ids = {p.profile_id for p in PROFILES[3:]}
    initial = sorted((p for p in ranked if p.profile_id in initial_ids), key=lambda p: (-score[p.profile_id], p.profile_id))
    recovery = sorted((p for p in ranked if p.profile_id in recovery_ids), key=lambda p: (-score[p.profile_id], p.profile_id))
    return tuple(initial + recovery)
