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
from src.preprocess.comment_filters import (
    MIN_COMMENT_TEXT_CHARS,
    build_filtered_comment_aggregation,
    prepare_filtered_comment_rows,
)


INPUT_BASENAME = "text_analysis_corpus_preprocessed"
COMMENTS_BASENAME = "comments_raw"
OUTPUT_BASENAME = "text_analysis_inputs_stage2"
MIN_TITLE_DESC_CHARS = 15
MIN_COMMENTS_FOR_AUDIENCE_INPUT = 2


def build_concat_text(parts: list[str]) -> str:
    """Join non-empty text parts with a visible separator."""
    cleaned_parts = [str(part).strip() for part in parts if str(part).strip() and str(part).strip().lower() != "nan"]
    return " [SEP] ".join(cleaned_parts)


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logger = setup_logger(PROJECT_ROOT / "logs", "08_prepare_analysis_inputs", log_level)
    ensure_directories([PROJECT_ROOT / "data" / "processed"])

    input_path = (PROJECT_ROOT / "data" / "processed" / INPUT_BASENAME).with_suffix(f".{output_format}")
    df = load_dataframe_if_exists(input_path)
    if df.empty:
        raise ValueError(f"No preprocessed corpus found at {input_path}. Run 07_preprocess_text_corpus.py first.")

    comments_path = (PROJECT_ROOT / "data" / "raw" / COMMENTS_BASENAME).with_suffix(f".{output_format}")
    comments_df = load_dataframe_if_exists(comments_path)

    stage2_df = df.copy()
    filtered_comment_rows_df = prepare_filtered_comment_rows(comments_df)
    filtered_comment_df = build_filtered_comment_aggregation(filtered_comment_rows_df)
    stage2_df = stage2_df.merge(filtered_comment_df, on="video_id", how="left")

    stage2_df["comment_input_text"] = stage2_df["comments_text_filtered"].fillna("").astype(str).str.strip()
    stage2_df["title_desc_use_flag"] = (
        stage2_df["title_description_text_light_clean"].fillna("").astype(str).str.len() >= MIN_TITLE_DESC_CHARS
    ).astype(int)
    stage2_df["comments_use_flag"] = (
        (stage2_df["comment_input_text"].fillna("").astype(str).str.len() >= MIN_COMMENT_TEXT_CHARS)
        & (stage2_df["comment_count_selected"].fillna(0).astype(float) >= MIN_COMMENTS_FOR_AUDIENCE_INPUT)
    ).astype(int)
    stage2_df["transcript_use_flag"] = stage2_df["analysis_use_flag"].fillna(0).astype(float).astype(int)

    stage2_df["topic_input_text"] = stage2_df["title_description_text_light_clean"].fillna("").astype(str).str.strip()
    stage2_df["transcript_input_text"] = stage2_df["best_transcript_text_light_clean"].fillna("").astype(str).str.strip()

    stage2_df["frame_input_text"] = stage2_df.apply(
        lambda row: build_concat_text(
            [
                row.get("title_description_text_light_clean", ""),
                row.get("best_transcript_text_light_clean", "") if int(row.get("transcript_use_flag", 0)) == 1 else "",
            ]
        ),
        axis=1,
    )
    stage2_df["audience_input_text"] = stage2_df["comment_input_text"]
    stage2_df["analysis_bundle_text"] = stage2_df.apply(
        lambda row: build_concat_text(
            [
                row.get("title_description_text_light_clean", "") if int(row.get("title_desc_use_flag", 0)) == 1 else "",
                row.get("best_transcript_text_light_clean", "") if int(row.get("transcript_use_flag", 0)) == 1 else "",
                row.get("comment_input_text", "") if int(row.get("comments_use_flag", 0)) == 1 else "",
            ]
        ),
        axis=1,
    )

    stage2_df["analysis_stage2_note"] = "title_description_priority"
    stage2_df.loc[stage2_df["comments_use_flag"] == 1, "analysis_stage2_note"] = "title_description_plus_comments"
    stage2_df.loc[stage2_df["transcript_use_flag"] == 1, "analysis_stage2_note"] = (
        stage2_df.loc[stage2_df["transcript_use_flag"] == 1, "analysis_stage2_note"] + "_plus_transcript"
    )

    final_path = save_dataframe(
        stage2_df.reset_index(drop=True),
        PROJECT_ROOT / "data" / "processed" / OUTPUT_BASENAME,
        output_format,
    )

    logger.info(
        "Prepared stage2 analysis inputs with %s rows, %s comment-usable rows, and %s transcript-usable rows at %s",
        len(stage2_df),
        int(stage2_df["comments_use_flag"].sum()),
        int(stage2_df["transcript_use_flag"].sum()),
        final_path,
    )
    print(f"Saved {len(stage2_df)} stage2 analysis rows to {final_path}")


if __name__ == "__main__":
    main()
