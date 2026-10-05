from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

PageClassification = Literal["existing_searchable_text", "image_only", "inspection_failed", "unsupported_page_object"]
VerificationStatus = Literal["passed", "failed", "preserved_not_reverified", "not_run"]


@dataclass(frozen=True, slots=True)
class OcrProfile:
    profile_id: str
    label: str
    psm: int
    grayscale: bool = True
    autocontrast: bool = True
    threshold: int | None = None
    upscale: float = 1.0
    median_filter: int = 0
    sharpen: float = 1.0
    invert: bool = False
    transformation_count: int = 0
    remove_long_lines: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OcrOptions:
    languages: list[str] = field(default_factory=lambda: ["eng"])
    dpi: int = 300
    confidence_threshold: float = 85.0
    oem: int = 3
    preserve_interword_spaces: bool = True
    timeout_seconds: int = 300
    max_pages: int = 1000
    max_pixels_per_page: int = 120_000_000
    max_upscale: float = 3.0
    output_pdf: bool = True
    adaptive_planning: bool = True
    region_level_selection: bool = True
    domain_profile: str = "general"
    correction_memory_enabled: bool = False
    no_history: bool = False
    redact_logs: bool = False
    evidence_without_source_content: bool = False
    local_pii_warnings: bool = True

    @property
    def language_expression(self) -> str:
        ordered: list[str] = []
        for language in self.languages:
            clean = language.strip()
            if clean and clean not in ordered:
                ordered.append(clean)
        return "+".join(ordered or ["eng"])

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["language_expression"] = self.language_expression
        return data


@dataclass(slots=True)
class OcrWord:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int
    block_num: int
    par_num: int
    line_num: int
    word_num: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OcrPassResult:
    pass_number: int
    profile: OcrProfile
    text: str
    canonical_text: str
    mean_confidence: float | None
    token_count: int
    invalid_confidence_count: int
    words: list[OcrWord]
    tsv: str
    elapsed_seconds: float
    command: list[str]
    prepared_image_sha256: str
    prepared_width: int
    prepared_height: int
    stdout: str = ""
    stderr: str = ""
    calibrated_confidence: float | None = None

    def public_dict(self, include_words: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "pass_number": self.pass_number,
            "profile": self.profile.to_dict(),
            "text": self.text,
            "canonical_text": self.canonical_text,
            "mean_confidence": self.mean_confidence,
            "calibrated_confidence": self.calibrated_confidence,
            "token_count": self.token_count,
            "invalid_confidence_count": self.invalid_confidence_count,
            "elapsed_seconds": self.elapsed_seconds,
            "command": self.command,
            "prepared_image_sha256": self.prepared_image_sha256,
            "prepared_width": self.prepared_width,
            "prepared_height": self.prepared_height,
            "stderr": self.stderr,
        }
        if include_words:
            data["words"] = [word.to_dict() for word in self.words]
        return data


@dataclass(slots=True)
class OcrPageResult:
    page_number: int
    classification: PageClassification
    classification_reason: str
    source_page_width_points: float
    source_page_height_points: float
    source_image_width: int | None = None
    source_image_height: int | None = None
    source_image_sha256: str | None = None
    existing_text: str = ""
    passes: list[OcrPassResult] = field(default_factory=list)
    planned_profile_order: list[str] = field(default_factory=list)
    winning_pass_number: int | None = None
    winning_profile_id: str | None = None
    winner_mode: str = "not_run"
    mean_confidence: float | None = None
    calibrated_confidence: float | None = None
    accepted_threshold: bool | None = None
    manual_review_required: bool = False
    review_priority: str = "normal"
    tie_break_reason: str | None = None
    raw_ocr_text: str = ""
    canonical_ocr_text: str = ""
    extracted_pdf_text: str = ""
    verification_status: VerificationStatus = "not_run"
    verification_difference_count: int = 0
    embedding_status: str = "not_run"
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    agreement_metrics: dict[str, Any] = field(default_factory=dict)
    regions: list[dict[str, Any]] = field(default_factory=list)
    region_count: int = 0
    geometry_validation: dict[str, Any] = field(default_factory=dict)
    search_validation: dict[str, Any] = field(default_factory=dict)
    table_form_status: str = "not_detected"
    correction_status: str = "uncorrected"
    pii_warnings: list[dict[str, str]] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    @property
    def pass_count(self) -> int:
        return len(self.passes)

    def public_dict(self, include_passes: bool = True) -> dict[str, Any]:
        data = {
            "page_number": self.page_number,
            "classification": self.classification,
            "classification_reason": self.classification_reason,
            "source_page_width_points": self.source_page_width_points,
            "source_page_height_points": self.source_page_height_points,
            "source_image_width": self.source_image_width,
            "source_image_height": self.source_image_height,
            "source_image_sha256": self.source_image_sha256,
            "existing_text": self.existing_text,
            "pass_count": self.pass_count,
            "planned_profile_order": self.planned_profile_order,
            "winning_pass_number": self.winning_pass_number,
            "winning_profile_id": self.winning_profile_id,
            "winner_mode": self.winner_mode,
            "mean_confidence": self.mean_confidence,
            "calibrated_confidence": self.calibrated_confidence,
            "accepted_threshold": self.accepted_threshold,
            "manual_review_required": self.manual_review_required,
            "review_priority": self.review_priority,
            "tie_break_reason": self.tie_break_reason,
            "raw_ocr_text": self.raw_ocr_text,
            "canonical_ocr_text": self.canonical_ocr_text,
            "extracted_pdf_text": self.extracted_pdf_text,
            "verification_status": self.verification_status,
            "verification_difference_count": self.verification_difference_count,
            "embedding_status": self.embedding_status,
            "quality_metrics": self.quality_metrics,
            "agreement_metrics": self.agreement_metrics,
            "regions": self.regions,
            "region_count": self.region_count,
            "geometry_validation": self.geometry_validation,
            "search_validation": self.search_validation,
            "table_form_status": self.table_form_status,
            "correction_status": self.correction_status,
            "pii_warnings": self.pii_warnings,
            "artifacts": self.artifacts,
            "error": self.error,
        }
        if include_passes:
            data["passes"] = [item.public_dict() for item in self.passes]
        return data


@dataclass(slots=True)
class OcrDocumentResult:
    source: Path
    pages: list[OcrPageResult]
    engine_path: Path
    engine_version: str
    options: OcrOptions
    started_utc: str
    completed_utc: str
    status: str
    output_files: dict[str, Path] = field(default_factory=dict)
    evidence_path: Path | None = None
    dashboard_path: Path | None = None
    error: str | None = None

    @property
    def mean_confidence(self) -> float | None:
        values = [page.mean_confidence for page in self.pages if page.mean_confidence is not None]
        return round(sum(values) / len(values), 2) if values else None

    @property
    def mean_calibrated_confidence(self) -> float | None:
        values = [page.calibrated_confidence for page in self.pages if page.calibrated_confidence is not None]
        return round(sum(values) / len(values), 2) if values else None

    @property
    def review_page_count(self) -> int:
        return sum(1 for page in self.pages if page.manual_review_required)

    @property
    def verification_failure_count(self) -> int:
        return sum(1 for page in self.pages if page.verification_status == "failed")

    @property
    def text(self) -> str:
        sections: list[str] = []
        for page in self.pages:
            value = page.existing_text if page.classification == "existing_searchable_text" else page.raw_ocr_text
            sections.append(value.rstrip())
        return "\n\f\n".join(sections).rstrip() + "\n"

    def public_dict(self, include_passes: bool = True) -> dict[str, Any]:
        return {
            "product": "JA21 OCR Studio",
            "version": "0.3.2",
            "source": str(self.source),
            "engine_path": str(self.engine_path),
            "engine_version": self.engine_version,
            "options": self.options.to_dict(),
            "started_utc": self.started_utc,
            "completed_utc": self.completed_utc,
            "status": self.status,
            "error": self.error,
            "mean_confidence": self.mean_confidence,
            "mean_calibrated_confidence": self.mean_calibrated_confidence,
            "review_page_count": self.review_page_count,
            "verification_failure_count": self.verification_failure_count,
            "pages": [page.public_dict(include_passes=include_passes) for page in self.pages],
            "output_files": {name: str(path) for name, path in self.output_files.items()},
            "evidence_path": str(self.evidence_path) if self.evidence_path else None,
            "dashboard_path": str(self.dashboard_path) if self.dashboard_path else None,
        }
