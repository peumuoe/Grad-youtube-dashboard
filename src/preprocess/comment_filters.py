from __future__ import annotations

import re

import pandas as pd

from src.preprocess.text_preprocessor import URL_PATTERN, light_clean_text


MIN_COMMENT_TEXT_CHARS = 15
MAX_COMMENTS_PER_AUTHOR = 2
REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{5,}")
LAUGHTER_ONLY_PATTERN = re.compile(r"^[ㅋㅎ]{2,}$")
URL_ONLY_PATTERN = re.compile(r"^(https?://\S+|www\.\S+)$")


def normalize_author_id(value: object) -> str:
    """Return a stable author identifier for per-video de-duplication."""
    normalized = str(value or "").strip()
    return normalized if normalized else "UNKNOWN_AUTHOR"


def is_url_only_comment(text: str) -> bool:
    """Return True when the comment is only a URL after trimming."""
    return bool(URL_ONLY_PATTERN.fullmatch(text.strip()))


def is_repetitive_comment(text: str) -> bool:
    """Flag extremely repetitive or non-informative comments conservatively."""
    compact = re.sub(r"\s+", "", text)
    if len(compact) == 0:
        return True
    if LAUGHTER_ONLY_PATTERN.fullmatch(compact):
        return True
    if REPEATED_CHAR_PATTERN.search(compact):
        return True
    unique_ratio = len(set(compact)) / max(len(compact), 1)
    if len(compact) >= 15 and unique_ratio < 0.2:
        return True
    return False


def prepare_filtered_comment_rows(comments_df: pd.DataFrame) -> pd.DataFrame:
    """Return comment rows with conservative filtering flags and selection result."""
    if comments_df.empty:
        return pd.DataFrame(
            columns=[
                "comment_id",
                "video_id",
                "author_display_name",
                "author_channel_id",
                "comment_text_raw",
                "comment_text_clean",
                "comment_like_count",
                "published_at",
                "author_key",
                "exclude_short",
                "exclude_url_only",
                "exclude_repetitive",
                "exclude_author_cap",
                "comment_selected_flag",
                "comment_filter_reason",
            ]
        )

    working_df = comments_df.copy()
    working_df["comment_text_raw"] = working_df["comment_text_raw"].fillna("").astype(str).str.strip()
    working_df["comment_text_clean"] = working_df["comment_text_raw"].apply(light_clean_text)
    working_df["author_key"] = working_df["author_channel_id"].apply(normalize_author_id)
    working_df["comment_like_count"] = pd.to_numeric(working_df.get("like_count", 0), errors="coerce").fillna(0)
    working_df["published_at"] = working_df.get("published_at", "").fillna("").astype(str)
    working_df = working_df.sort_values(
        ["video_id", "comment_like_count", "published_at"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)

    selected_flags: list[int] = []
    exclude_short_flags: list[int] = []
    exclude_url_flags: list[int] = []
    exclude_repetitive_flags: list[int] = []
    exclude_author_cap_flags: list[int] = []
    reasons: list[str] = []

    current_video_id = None
    author_counts: dict[str, int] = {}

    for row in working_df.itertuples(index=False):
        video_id = str(row.video_id)
        if video_id != current_video_id:
            current_video_id = video_id
            author_counts = {}

        cleaned_text = str(row.comment_text_clean or "").strip()
        raw_text = str(row.comment_text_raw or "").strip()
        author_key = normalize_author_id(getattr(row, "author_key", ""))

        exclude_short = int(len(cleaned_text) < MIN_COMMENT_TEXT_CHARS)
        exclude_url_only = int(
            is_url_only_comment(cleaned_text)
            or (bool(URL_PATTERN.search(cleaned_text)) and cleaned_text == raw_text)
        )
        exclude_repetitive = int(is_repetitive_comment(cleaned_text))
        exclude_author_cap = 0

        if not exclude_short and not exclude_url_only and not exclude_repetitive:
            if author_counts.get(author_key, 0) >= MAX_COMMENTS_PER_AUTHOR:
                exclude_author_cap = 1
            else:
                author_counts[author_key] = author_counts.get(author_key, 0) + 1

        selected_flag = int(not any([exclude_short, exclude_url_only, exclude_repetitive, exclude_author_cap]))

        reason_parts: list[str] = []
        if exclude_short:
            reason_parts.append("short")
        if exclude_url_only:
            reason_parts.append("url_only")
        if exclude_repetitive:
            reason_parts.append("repetitive")
        if exclude_author_cap:
            reason_parts.append("author_cap")
        if selected_flag:
            reason_parts.append("selected")

        selected_flags.append(selected_flag)
        exclude_short_flags.append(exclude_short)
        exclude_url_flags.append(exclude_url_only)
        exclude_repetitive_flags.append(exclude_repetitive)
        exclude_author_cap_flags.append(exclude_author_cap)
        reasons.append("; ".join(reason_parts))

    working_df["exclude_short"] = exclude_short_flags
    working_df["exclude_url_only"] = exclude_url_flags
    working_df["exclude_repetitive"] = exclude_repetitive_flags
    working_df["exclude_author_cap"] = exclude_author_cap_flags
    working_df["comment_selected_flag"] = selected_flags
    working_df["comment_filter_reason"] = reasons
    return working_df


def build_filtered_comment_aggregation(filtered_comments_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate already-filtered comment rows to video-level analysis fields."""
    if filtered_comments_df.empty:
        return pd.DataFrame(
            columns=[
                "video_id",
                "comment_count_candidate",
                "comment_count_selected",
                "comment_excluded_short",
                "comment_excluded_url_only",
                "comment_excluded_repetitive",
                "comment_excluded_author_cap",
                "comments_text_filtered",
                "comments_filter_note",
            ]
        )

    aggregated_rows: list[dict] = []
    for video_id, group_df in filtered_comments_df.groupby("video_id", dropna=False, sort=False):
        selected_texts = (
            group_df.loc[group_df["comment_selected_flag"] == 1, "comment_text_clean"].fillna("").astype(str).tolist()
        )

        excluded_short = int(group_df["exclude_short"].fillna(0).sum())
        excluded_url_only = int(group_df["exclude_url_only"].fillna(0).sum())
        excluded_repetitive = int(group_df["exclude_repetitive"].fillna(0).sum())
        excluded_author_cap = int(group_df["exclude_author_cap"].fillna(0).sum())

        notes: list[str] = []
        if excluded_short:
            notes.append(f"short_excluded={excluded_short}")
        if excluded_url_only:
            notes.append(f"url_only_excluded={excluded_url_only}")
        if excluded_repetitive:
            notes.append(f"repetitive_excluded={excluded_repetitive}")
        if excluded_author_cap:
            notes.append(f"author_cap_excluded={excluded_author_cap}")
        if not selected_texts:
            notes.append("no_comment_passed_filters")

        aggregated_rows.append(
            {
                "video_id": video_id,
                "comment_count_candidate": int(len(group_df)),
                "comment_count_selected": int(group_df["comment_selected_flag"].fillna(0).sum()),
                "comment_excluded_short": excluded_short,
                "comment_excluded_url_only": excluded_url_only,
                "comment_excluded_repetitive": excluded_repetitive,
                "comment_excluded_author_cap": excluded_author_cap,
                "comments_text_filtered": " [COMMENT_SEP] ".join([text for text in selected_texts if text]),
                "comments_filter_note": "; ".join(notes),
            }
        )

    return pd.DataFrame(aggregated_rows)
