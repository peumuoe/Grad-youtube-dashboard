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
from src.review_labeler import label_transcript_quality


TRANSCRIPTS_BASENAME = "transcripts_raw"
REVIEW_BASENAME = "transcripts_review_queue"
MANUAL_REVIEW_DEFAULTS = {
    "manual_quality_label": "",
    "manual_review_status": "pending",
    "manual_corrected_text": "",
    "manual_title_summary": "",
    "manual_key_terms": "",
    "manual_review_notes": "",
    "final_use_flag": 0,
}


def merge_existing_manual_columns(new_df: pd.DataFrame, existing_df: pd.DataFrame) -> pd.DataFrame:
    """Preserve manual review inputs when the queue is regenerated."""
    if existing_df.empty or "video_id" not in existing_df.columns:
        merged_df = new_df.copy()
    else:
        manual_columns = ["video_id", *MANUAL_REVIEW_DEFAULTS.keys()]
        available_columns = [column for column in manual_columns if column in existing_df.columns]
        existing_manual_df = existing_df[available_columns].drop_duplicates(subset=["video_id"], keep="last")
        merged_df = new_df.merge(existing_manual_df, on="video_id", how="left")

    for column_name, default_value in MANUAL_REVIEW_DEFAULTS.items():
        if column_name not in merged_df.columns:
            merged_df[column_name] = default_value
        merged_df[column_name] = merged_df[column_name].fillna(default_value)

    return merged_df


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logger = setup_logger(PROJECT_ROOT / "logs", "04_prepare_transcript_review", log_level)
    ensure_directories([PROJECT_ROOT / "data" / "processed"])

    transcripts_path = (PROJECT_ROOT / "data" / "raw" / TRANSCRIPTS_BASENAME).with_suffix(f".{output_format}")
    transcripts_df = load_dataframe_if_exists(transcripts_path)
    if transcripts_df.empty:
        raise ValueError(f"No transcript data found at {transcripts_path}. Run 03_collect_transcripts_stub.py first.")

    existing_review_path = (PROJECT_ROOT / "data" / "processed" / REVIEW_BASENAME).with_suffix(f".{output_format}")
    existing_review_df = load_dataframe_if_exists(existing_review_path)

    review_df = transcripts_df.copy()
    if "text_needs_review" in review_df.columns:
        review_df = review_df[review_df["text_needs_review"].fillna(0).astype(int) == 1].copy()

    if "correction_status" in review_df.columns:
        review_df = review_df[review_df["correction_status"].astype(str).isin(["cleaned", "corrected"])].copy()

    label_results = review_df.apply(
        lambda row: label_transcript_quality(
            transcript_source=row.get("transcript_source", ""),
            transcript_language_code=row.get("transcript_language_code", ""),
            transcript_text=row.get("transcript_text_corrected", ""),
            transcript_segment_count=int(float(row.get("transcript_segment_count", 0) or 0)),
        ),
        axis=1,
    )
    review_df["quality_label"] = [result.quality_label for result in label_results]
    review_df["quality_score"] = [result.quality_score for result in label_results]
    review_df["recommended_use"] = [result.recommended_use for result in label_results]
    review_df["auto_label_reason"] = [result.auto_label_reason for result in label_results]
    review_df["language_match_flag"] = [result.language_match_flag for result in label_results]
    review_df["repetition_flag"] = [result.repetition_flag for result in label_results]
    review_df["foreign_script_flag"] = [result.foreign_script_flag for result in label_results]
    review_df["review_status"] = "pending"
    review_df["review_notes"] = ""
    review_df = merge_existing_manual_columns(review_df, existing_review_df)

    sort_columns = [column for column in ["quality_score", "transcript_segment_count", "video_id"] if column in review_df.columns]
    ascending_flags = [True, False, True][: len(sort_columns)]
    if sort_columns:
        review_df = review_df.sort_values(sort_columns, ascending=ascending_flags).reset_index(drop=True)

    final_path = save_dataframe(
        review_df.reset_index(drop=True),
        PROJECT_ROOT / "data" / "processed" / REVIEW_BASENAME,
        output_format,
    )

    logger.info("Prepared transcript review queue with %s rows at %s", len(review_df), final_path)
    print(f"Saved {len(review_df)} transcript review rows to {final_path}")


if __name__ == "__main__":
    main()
