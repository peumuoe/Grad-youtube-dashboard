from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass


URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
EMAIL_PATTERN = re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b")
WHITESPACE_PATTERN = re.compile(r"\s+")
KOREAN_PATTERN = re.compile(r"[가-힣]")
LATIN_PATTERN = re.compile(r"[A-Za-z]")
DIGIT_PATTERN = re.compile(r"\d")
REPEATED_PUNCT_PATTERN = re.compile(r"([!?.,~])\1{2,}")
ZERO_WIDTH_PATTERN = re.compile(r"[\u200b-\u200d\ufeff]")
PIPE_DELIMITER_PATTERN = re.compile(r"\s*\|\|\|\s*")


@dataclass
class PreprocessResult:
    """Container for conservative text preprocessing outputs."""

    text_normalized: str
    text_light_clean: str
    text_char_count: int
    text_token_count: int
    flag_has_url: int
    flag_has_email: int
    flag_has_korean: int
    flag_has_latin: int
    flag_has_digits: int
    flag_repeated_punct: int
    flag_has_pipe_delimiter: int
    flag_empty_after_clean: int
    preprocess_notes: str


def normalize_text(text: str) -> str:
    """Apply conservative Unicode and whitespace normalization."""
    normalized = html.unescape(str(text or ""))
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = ZERO_WIDTH_PATTERN.sub("", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\t", " ")
    normalized = re.sub(r"\n+", "\n", normalized)
    normalized = re.sub(r"[ ]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ ]+", "\n", normalized)
    normalized = normalized.strip()
    return normalized


def light_clean_text(text: str) -> str:
    """Apply low-risk cleaning that should not change sentence meaning."""
    cleaned = normalize_text(text)
    cleaned = PIPE_DELIMITER_PATTERN.sub(" [COMMENT_SEP] ", cleaned)
    cleaned = WHITESPACE_PATTERN.sub(" ", cleaned)
    cleaned = cleaned.strip()
    return cleaned


def preprocess_text(text: str) -> PreprocessResult:
    """Preprocess one text field while preserving meaning as much as possible."""
    normalized = normalize_text(text)
    light_clean = light_clean_text(text)

    has_url = 1 if URL_PATTERN.search(normalized) else 0
    has_email = 1 if EMAIL_PATTERN.search(normalized) else 0
    has_korean = 1 if KOREAN_PATTERN.search(normalized) else 0
    has_latin = 1 if LATIN_PATTERN.search(normalized) else 0
    has_digits = 1 if DIGIT_PATTERN.search(normalized) else 0
    has_repeated_punct = 1 if REPEATED_PUNCT_PATTERN.search(normalized) else 0
    has_pipe_delimiter = 1 if "|||" in normalized or "[COMMENT_SEP]" in light_clean else 0
    empty_after_clean = 1 if light_clean == "" else 0

    notes: list[str] = []
    if has_url:
        notes.append("contains_url")
    if has_email:
        notes.append("contains_email")
    if has_latin and has_korean:
        notes.append("mixed_korean_latin")
    if has_repeated_punct:
        notes.append("repeated_punctuation")
    if has_pipe_delimiter:
        notes.append("comment_aggregation_delimiter")
    if empty_after_clean:
        notes.append("empty_after_clean")

    return PreprocessResult(
        text_normalized=normalized,
        text_light_clean=light_clean,
        text_char_count=len(light_clean),
        text_token_count=len([token for token in light_clean.split(" ") if token]),
        flag_has_url=has_url,
        flag_has_email=has_email,
        flag_has_korean=has_korean,
        flag_has_latin=has_latin,
        flag_has_digits=has_digits,
        flag_repeated_punct=has_repeated_punct,
        flag_has_pipe_delimiter=has_pipe_delimiter,
        flag_empty_after_clean=empty_after_clean,
        preprocess_notes="; ".join(notes),
    )
