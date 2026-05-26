from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.io_utils import ensure_directories, load_dataframe_if_exists, save_dataframe, setup_logger


VIDEOS_BASENAME = "videos_raw"
TRANSCRIPTS_BASENAME = "transcripts_raw"
AUDIENCE_COMMENT_BASENAME = "audience_comment_input"
PUBLIC_CAPTION_REVIEW_BASENAME = "public_caption_review_sample"
COMMENT_REVIEW_BASENAME = "audience_comment_review_sample"
PUBLIC_CAPTION_SAMPLE_SIZE = 68
COMMENT_SAMPLE_SIZE = 50


def build_public_caption_review_sample(videos_df: pd.DataFrame, transcripts_df: pd.DataFrame) -> pd.DataFrame:
    """Build a review queue for public-caption transcripts with video metadata."""
    public_df = transcripts_df[transcripts_df["transcript_source"] == "public_caption"].copy()
    if public_df.empty:
        return pd.DataFrame()

    video_meta_columns = [
        "video_id",
        "channel_id",
        "channel_name",
        "channel_type",
        "title",
        "description",
        "search_keyword",
        "published_at",
        "url",
    ]
    video_meta_df = videos_df[video_meta_columns].drop_duplicates(subset=["video_id"], keep="first")
    merged_df = public_df.merge(video_meta_df, on="video_id", how="left")

    keep_columns = [
        "video_id",
        "channel_id",
        "channel_name",
        "channel_type",
        "search_keyword",
        "published_at",
        "title",
        "url",
        "transcript_source",
        "transcript_language_code",
        "transcript_language",
        "transcript_is_generated",
        "transcript_segment_count",
        "transcript_text_clean",
    ]
    merged_df = merged_df[keep_columns].drop_duplicates(subset=["video_id"], keep="last")
    merged_df["manual_quality_label"] = ""
    merged_df["manual_review_status"] = "pending"
    merged_df["manual_keep_for_analysis"] = 0
    merged_df["manual_issue_type"] = ""
    merged_df["manual_review_notes"] = ""
    merged_df["manual_corrected_excerpt"] = ""
    merged_df = merged_df.sort_values(["channel_name", "published_at", "video_id"]).reset_index(drop=True)
    return merged_df.head(PUBLIC_CAPTION_SAMPLE_SIZE)


def build_comment_review_sample(comment_df: pd.DataFrame) -> pd.DataFrame:
    """Build a balanced manual-review sample for audience comments."""
    if comment_df.empty:
        return pd.DataFrame()

    working_df = comment_df.copy()
    working_df = working_df.sort_values(
        ["channel_name", "comment_like_count", "comment_text_char_count"],
        ascending=[True, False, False],
        kind="stable",
    ).reset_index(drop=True)

    sample_parts: list[pd.DataFrame] = []
    channels = working_df["channel_name"].value_counts().index.tolist()
    if channels:
        per_channel = max(1, COMMENT_SAMPLE_SIZE // len(channels))
        for channel_name in channels:
            sample_parts.append(working_df[working_df["channel_name"] == channel_name].head(per_channel))

    sampled_df = pd.concat(sample_parts, ignore_index=True).drop_duplicates(subset=["comment_id"], keep="first")
    if len(sampled_df) < COMMENT_SAMPLE_SIZE:
        remaining_df = working_df[~working_df["comment_id"].isin(sampled_df["comment_id"])]
        needed = COMMENT_SAMPLE_SIZE - len(sampled_df)
        sampled_df = pd.concat([sampled_df, remaining_df.head(needed)], ignore_index=True)

    sampled_df = sampled_df.head(COMMENT_SAMPLE_SIZE).copy()
    sampled_df["manual_relevance_label"] = ""
    sampled_df["manual_noise_flag"] = 0
    sampled_df["manual_noise_type"] = ""
    sampled_df["manual_keep_for_audience_analysis"] = 1
    sampled_df["manual_review_notes"] = ""
    keep_columns = [
        "comment_id",
        "video_id",
        "channel_id",
        "channel_name",
        "channel_type",
        "search_keyword",
        "title",
        "published_at",
        "author_display_name",
        "comment_like_count",
        "comment_text_clean",
        "comment_text_char_count",
        "comment_filter_reason",
        "manual_relevance_label",
        "manual_noise_flag",
        "manual_noise_type",
        "manual_keep_for_audience_analysis",
        "manual_review_notes",
    ]
    return sampled_df[keep_columns].reset_index(drop=True)


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logger = setup_logger(PROJECT_ROOT / "logs", "10_prepare_review_samples", log_level)
    ensure_directories([PROJECT_ROOT / "data" / "processed"])

    videos_path = (PROJECT_ROOT / "data" / "raw" / VIDEOS_BASENAME).with_suffix(f".{output_format}")
    transcripts_path = (PROJECT_ROOT / "data" / "raw" / TRANSCRIPTS_BASENAME).with_suffix(f".{output_format}")
    audience_comment_path = (PROJECT_ROOT / "data" / "processed" / AUDIENCE_COMMENT_BASENAME).with_suffix(
        f".{output_format}"
    )

    videos_df = load_dataframe_if_exists(videos_path)
    transcripts_df = load_dataframe_if_exists(transcripts_path)
    audience_comment_df = load_dataframe_if_exists(audience_comment_path)

    if videos_df.empty:
        raise ValueError(f"No video data found at {videos_path}.")
    if transcripts_df.empty:
        raise ValueError(f"No transcript data found at {transcripts_path}.")
    if audience_comment_df.empty:
        raise ValueError(f"No audience comment data found at {audience_comment_path}.")

    public_caption_review_df = build_public_caption_review_sample(videos_df, transcripts_df)
    comment_review_df = build_comment_review_sample(audience_comment_df)

    public_path = save_dataframe(
        public_caption_review_df,
        PROJECT_ROOT / "data" / "processed" / PUBLIC_CAPTION_REVIEW_BASENAME,
        output_format,
    )
    comment_path = save_dataframe(
        comment_review_df,
        PROJECT_ROOT / "data" / "processed" / COMMENT_REVIEW_BASENAME,
        output_format,
    )

    logger.info(
        "Prepared review samples: public_caption=%s rows, audience_comment=%s rows",
        len(public_caption_review_df),
        len(comment_review_df),
    )
    print(
        f"Saved review samples: public_caption={public_path} ({len(public_caption_review_df)} rows), "
        f"audience_comment={comment_path} ({len(comment_review_df)} rows)"
    )


if __name__ == "__main__":
    main()
