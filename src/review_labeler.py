from __future__ import annotations

import re
from dataclasses import dataclass


EXPECTED_LANGUAGE_CODES = {"ko", "en"}


@dataclass
class ReviewLabelResult:
    """Auto-label output for transcript review prioritization."""

    quality_label: str
    quality_score: int
    recommended_use: str
    auto_label_reason: str
    language_match_flag: int
    repetition_flag: int
    foreign_script_flag: int


def detect_repetition(text: str) -> bool:
    """Flag obvious repeated chunks that often appear in bad STT output."""
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return False

    chunk_size = max(30, min(120, len(normalized) // 4 or 30))
    seen_chunks: set[str] = set()
    for start in range(0, max(1, len(normalized) - chunk_size + 1), max(10, chunk_size // 2)):
        chunk = normalized[start : start + chunk_size]
        if len(chunk) < 30:
            continue
        if chunk in seen_chunks:
            return True
        seen_chunks.add(chunk)
    return False


def detect_foreign_script(text: str) -> bool:
    """Flag transcripts dominated by non-Korean scripts."""
    if not text.strip():
        return False

    foreign_matches = re.findall(r"[\u0590-\u05FF\u0600-\u06FF\u0400-\u04FF]", text)
    return len(foreign_matches) >= 10


def label_transcript_quality(
    transcript_source: str,
    transcript_language_code: str,
    transcript_text: str,
    transcript_segment_count: int,
) -> ReviewLabelResult:
    """Assign a pragmatic first-pass quality label for transcript review."""
    source = str(transcript_source).strip().lower()
    language_code = str(transcript_language_code).strip().lower()
    text = str(transcript_text or "").strip()

    if source != "stt":
        return ReviewLabelResult(
            quality_label="usable",
            quality_score=3,
            recommended_use="full_analysis",
            auto_label_reason="non_stt_source",
            language_match_flag=1,
            repetition_flag=0,
            foreign_script_flag=0,
        )

    if not text:
        return ReviewLabelResult(
            quality_label="not_usable",
            quality_score=1,
            recommended_use="exclude_or_manual_fix",
            auto_label_reason="empty_text",
            language_match_flag=0,
            repetition_flag=0,
            foreign_script_flag=0,
        )

    language_match_flag = 1 if language_code in EXPECTED_LANGUAGE_CODES else 0
    repetition_flag = 1 if detect_repetition(text) else 0
    foreign_script_flag = 1 if detect_foreign_script(text) else 0

    if language_match_flag == 0 or foreign_script_flag == 1:
        return ReviewLabelResult(
            quality_label="not_usable",
            quality_score=1,
            recommended_use="exclude_or_manual_fix",
            auto_label_reason="language_mismatch_or_foreign_script",
            language_match_flag=language_match_flag,
            repetition_flag=repetition_flag,
            foreign_script_flag=foreign_script_flag,
        )

    if repetition_flag == 1 or transcript_segment_count <= 10:
        return ReviewLabelResult(
            quality_label="partially_usable",
            quality_score=2,
            recommended_use="limited_analysis",
            auto_label_reason="short_or_repetitive_stt",
            language_match_flag=language_match_flag,
            repetition_flag=repetition_flag,
            foreign_script_flag=foreign_script_flag,
        )

    return ReviewLabelResult(
        quality_label="usable",
        quality_score=3,
        recommended_use="full_analysis",
        auto_label_reason="stt_passed_basic_checks",
        language_match_flag=language_match_flag,
        repetition_flag=repetition_flag,
        foreign_script_flag=foreign_script_flag,
    )
