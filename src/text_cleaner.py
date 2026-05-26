from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd


@dataclass
class CleanedTranscriptText:
    """Container for normalized and corrected transcript text."""

    transcript_text_clean: str
    transcript_text_corrected: str
    correction_status: str
    correction_notes: str
    text_needs_review: int


def normalize_whitespace(text: str) -> str:
    """Collapse repeated whitespace and trim."""
    normalized = text.replace("\xa0", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def normalize_transcript_text(text: str) -> str:
    """Apply lightweight cleanup before later NLP steps."""
    normalized = normalize_whitespace(text)
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    normalized = re.sub(r"([,.;:!?]){2,}", r"\1", normalized)
    return normalized.strip()


def apply_replacement_rules(text: str, replacements_df: pd.DataFrame) -> tuple[str, list[str]]:
    """Apply simple string replacement rules from config."""
    corrected = text
    notes: list[str] = []

    if replacements_df.empty:
        return corrected, notes

    active_df = replacements_df.copy()
    if "active_flag" in active_df.columns:
        active_df = active_df[active_df["active_flag"].astype(str) == "1"]
    if "priority" in active_df.columns:
        active_df["priority"] = pd.to_numeric(active_df["priority"], errors="coerce").fillna(999)
        active_df = active_df.sort_values(["priority", "wrong_text"])

    for row in active_df.itertuples(index=False):
        wrong_text = str(getattr(row, "wrong_text", "")).strip()
        corrected_text = str(getattr(row, "corrected_text", "")).strip()
        if not wrong_text or not corrected_text:
            continue
        if wrong_text in corrected:
            corrected = corrected.replace(wrong_text, corrected_text)
            notes.append(f"{wrong_text}->{corrected_text}")

    return corrected, notes


def build_cleaned_transcript_text(
    raw_text: str,
    replacements_df: pd.DataFrame,
    source: str,
) -> CleanedTranscriptText:
    """Create clean and corrected text variants while preserving the raw text."""
    clean_text = normalize_transcript_text(raw_text)
    corrected_text, replacement_notes = apply_replacement_rules(clean_text, replacements_df)

    if not raw_text.strip():
        return CleanedTranscriptText(
            transcript_text_clean="",
            transcript_text_corrected="",
            correction_status="raw",
            correction_notes="",
            text_needs_review=0,
        )

    needs_review = 1 if source in {"public_caption", "stt"} else 0
    status = "cleaned"
    if replacement_notes:
        status = "corrected"

    return CleanedTranscriptText(
        transcript_text_clean=clean_text,
        transcript_text_corrected=corrected_text,
        correction_status=status,
        correction_notes="; ".join(replacement_notes),
        text_needs_review=needs_review,
    )
