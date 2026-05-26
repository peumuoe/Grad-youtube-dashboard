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
COMMENTS_BASENAME = "comments_raw"
TRANSCRIPTS_BASENAME = "transcripts_raw"
TRANSCRIPT_ANALYSIS_BASENAME = "transcripts_analysis_ready"
OUTPUT_BASENAME = "text_analysis_corpus"


def normalize_text_value(value: object) -> str:
    """Return a clean string while treating NaN-like values as empty."""
    if pd.isna(value):
        return ""
    return str(value or "").strip()


def pick_best_transcript_text(row: pd.Series) -> str:
    """Choose the best available transcript text for the corpus."""
    analysis_text = normalize_text_value(row.get("analysis_text", ""))
    corrected_text = normalize_text_value(row.get("transcript_text_corrected", ""))
    clean_text = normalize_text_value(row.get("transcript_text_clean", ""))

    if analysis_text:
        return analysis_text
    if corrected_text:
        return corrected_text
    return clean_text


def build_comment_aggregation(comments_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate comments to a video-level field for later NLP."""
    if comments_df.empty:
        return pd.DataFrame(columns=["video_id", "comment_count_collected", "comments_text_joined"])

    working_df = comments_df.copy()
    working_df["comment_text_raw"] = working_df["comment_text_raw"].fillna("").astype(str).str.strip()
    grouped_df = (
        working_df.groupby("video_id", dropna=False)
        .agg(
            comment_count_collected=("comment_id", "count"),
            comments_text_joined=("comment_text_raw", lambda values: " ||| ".join([value for value in values if value])),
        )
        .reset_index()
    )
    return grouped_df


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logger = setup_logger(PROJECT_ROOT / "logs", "06_build_text_analysis_corpus", log_level)
    ensure_directories([PROJECT_ROOT / "data" / "processed"])

    videos_path = (PROJECT_ROOT / "data" / "raw" / VIDEOS_BASENAME).with_suffix(f".{output_format}")
    videos_df = load_dataframe_if_exists(videos_path)
    if videos_df.empty:
        raise ValueError(f"No video data found at {videos_path}. Run 01_collect_videos.py first.")

    comments_path = (PROJECT_ROOT / "data" / "raw" / COMMENTS_BASENAME).with_suffix(f".{output_format}")
    comments_df = load_dataframe_if_exists(comments_path)

    transcripts_path = (PROJECT_ROOT / "data" / "processed" / TRANSCRIPT_ANALYSIS_BASENAME).with_suffix(f".{output_format}")
    if not transcripts_path.exists():
        transcripts_path = (PROJECT_ROOT / "data" / "raw" / TRANSCRIPTS_BASENAME).with_suffix(f".{output_format}")
    transcripts_df = load_dataframe_if_exists(transcripts_path)

    comment_agg_df = build_comment_aggregation(comments_df)
    corpus_df = videos_df.copy()
    corpus_df = corpus_df.merge(comment_agg_df, on="video_id", how="left")

    if not transcripts_df.empty:
        transcript_columns = [
            "video_id",
            "transcript_source",
            "analysis_text",
            "analysis_use_flag",
            "analysis_quality_label",
            "transcript_text_corrected",
            "transcript_text_clean",
        ]
        available_columns = [column for column in transcript_columns if column in transcripts_df.columns]
        transcript_subset_df = transcripts_df[available_columns].drop_duplicates(subset=["video_id"], keep="last")
        corpus_df = corpus_df.merge(transcript_subset_df, on="video_id", how="left")
    else:
        corpus_df["transcript_source"] = ""
        corpus_df["analysis_text"] = ""
        corpus_df["analysis_use_flag"] = 0
        corpus_df["analysis_quality_label"] = ""
        corpus_df["transcript_text_corrected"] = ""
        corpus_df["transcript_text_clean"] = ""

    corpus_df["best_transcript_text"] = corpus_df.apply(pick_best_transcript_text, axis=1)
    corpus_df["title_description_text"] = (
        corpus_df["title"].fillna("").astype(str).str.strip()
        + " "
        + corpus_df["description"].fillna("").astype(str).str.strip()
    ).str.strip()
    corpus_df["analysis_priority_text"] = corpus_df["title_description_text"]
    has_usable_transcript = corpus_df["analysis_use_flag"].fillna(0).astype(float) == 1
    corpus_df.loc[has_usable_transcript, "analysis_priority_text"] = (
        corpus_df.loc[has_usable_transcript, "title_description_text"].fillna("").astype(str).str.strip()
        + " "
        + corpus_df.loc[has_usable_transcript, "best_transcript_text"].fillna("").astype(str).str.strip()
    ).str.strip()
    corpus_df["text_strategy_note"] = "title_description_only"
    corpus_df.loc[has_usable_transcript, "text_strategy_note"] = "title_description_plus_transcript"

    final_path = save_dataframe(
        corpus_df.reset_index(drop=True),
        PROJECT_ROOT / "data" / "processed" / OUTPUT_BASENAME,
        output_format,
    )

    transcript_usable_count = int(has_usable_transcript.sum())
    logger.info(
        "Built text analysis corpus with %s rows and %s transcript-usable rows at %s",
        len(corpus_df),
        transcript_usable_count,
        final_path,
    )
    print(f"Saved {len(corpus_df)} corpus rows to {final_path} ({transcript_usable_count} transcript-usable)")


if __name__ == "__main__":
    main()
