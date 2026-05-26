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


FRAME_INPUT = "frame_video_classification.csv"
IDEOLOGY_INPUT = "ideology_video_estimates.csv"
FRAME_SAMPLE_OUTPUT = "frame_validation_sample"
IDEOLOGY_SAMPLE_OUTPUT = "ideology_validation_sample"
FRAME_SAMPLE_SIZE = 120
IDEOLOGY_SAMPLE_SIZE = 120


def build_frame_validation_sample(frame_df: pd.DataFrame) -> pd.DataFrame:
    """Sample uncertain or boundary frame classifications for manual review."""
    working_df = frame_df.copy()
    working_df["frame_text_cleaned"] = working_df["frame_text_cleaned"].fillna("").astype(str).str.strip()
    working_df["frame_uncertainty_score"] = 0
    working_df.loc[working_df["primary_frame"] == "기타/혼합", "frame_uncertainty_score"] += 3
    working_df.loc[working_df["frame_hit_count_total"].fillna(0).astype(float) <= 1, "frame_uncertainty_score"] += 2
    working_df.loc[working_df["frame_text_char_count"].fillna(0).astype(float) < 120, "frame_uncertainty_score"] += 1

    score_columns = [column for column in working_df.columns if column.startswith("frame_score_")]
    if score_columns:
        top_two_sum = (
            working_df[score_columns]
            .fillna(0)
            .apply(lambda row: sorted(row.tolist(), reverse=True)[:2], axis=1)
            .apply(lambda values: values[0] - values[1] if len(values) >= 2 else values[0] if values else 0)
        )
        working_df["frame_score_margin"] = top_two_sum
        working_df.loc[working_df["frame_score_margin"] <= 1, "frame_uncertainty_score"] += 1
    else:
        working_df["frame_score_margin"] = 0

    sampled_df = (
        working_df.sort_values(
            ["frame_uncertainty_score", "frame_hit_count_total", "frame_text_char_count"],
            ascending=[False, True, True],
            kind="stable",
        )
        .head(FRAME_SAMPLE_SIZE)
        .copy()
    )
    sampled_df["manual_frame_label"] = ""
    sampled_df["manual_frame_keep"] = 1
    sampled_df["manual_frame_notes"] = ""
    keep_columns = [
        "video_id",
        "channel_name",
        "channel_type",
        "search_keyword",
        "published_at",
        "title",
        "primary_frame",
        "frame_hit_count_total",
        "frame_score_margin",
        "frame_uncertainty_score",
        "frame_text_cleaned",
        "manual_frame_label",
        "manual_frame_keep",
        "manual_frame_notes",
    ]
    return sampled_df[keep_columns].reset_index(drop=True)


def build_ideology_validation_sample(ideo_df: pd.DataFrame, frame_df: pd.DataFrame) -> pd.DataFrame:
    """Sample uncertain issue-level ideology estimates for manual review."""
    merged_df = ideo_df.merge(
        frame_df[
            [
                "video_id",
                "channel_type",
                "search_keyword",
                "published_at",
                "title",
                "frame_text_cleaned",
                "primary_frame",
            ]
        ],
        on="video_id",
        how="left",
    )
    merged_df["ideology_abs_score"] = merged_df["ideology_relative_score"].abs()
    merged_df["ideology_total_hits"] = (
        merged_df["progressive_cue_hits"].fillna(0).astype(float)
        + merged_df["conservative_cue_hits"].fillna(0).astype(float)
    )
    merged_df["ideology_uncertainty_score"] = 0
    merged_df.loc[merged_df["ideology_abs_score"] <= 0.2, "ideology_uncertainty_score"] += 3
    merged_df.loc[merged_df["ideology_total_hits"] <= 2, "ideology_uncertainty_score"] += 2
    merged_df.loc[merged_df["primary_frame"] == "기타/혼합", "ideology_uncertainty_score"] += 1

    sampled_df = (
        merged_df.sort_values(
            ["ideology_uncertainty_score", "ideology_abs_score", "ideology_total_hits"],
            ascending=[False, True, True],
            kind="stable",
        )
        .head(IDEOLOGY_SAMPLE_SIZE)
        .copy()
    )
    sampled_df["manual_ideology_label"] = ""
    sampled_df["manual_ideology_keep"] = 1
    sampled_df["manual_ideology_notes"] = ""
    keep_columns = [
        "video_id",
        "channel_name",
        "channel_type",
        "search_keyword",
        "published_at",
        "title",
        "primary_frame",
        "ideology_relative_score",
        "ideology_relative_label",
        "progressive_cue_hits",
        "conservative_cue_hits",
        "ideology_total_hits",
        "ideology_uncertainty_score",
        "frame_text_cleaned",
        "manual_ideology_label",
        "manual_ideology_keep",
        "manual_ideology_notes",
    ]
    return sampled_df[keep_columns].reset_index(drop=True)


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger = setup_logger(PROJECT_ROOT / "logs", "37_prepare_analysis_validation_samples", log_level)
    ensure_directories([PROJECT_ROOT / "data" / "processed"])

    frame_df = load_dataframe_if_exists(PROJECT_ROOT / "outputs" / "tables" / FRAME_INPUT)
    ideo_df = load_dataframe_if_exists(PROJECT_ROOT / "outputs" / "tables" / IDEOLOGY_INPUT)
    if frame_df.empty or ideo_df.empty:
        raise ValueError("Missing analysis outputs. Run 33 and 34 first.")

    frame_sample_df = build_frame_validation_sample(frame_df)
    ideology_sample_df = build_ideology_validation_sample(ideo_df, frame_df)

    frame_path = save_dataframe(
        frame_sample_df,
        PROJECT_ROOT / "data" / "processed" / FRAME_SAMPLE_OUTPUT,
        "csv",
    )
    ideology_path = save_dataframe(
        ideology_sample_df,
        PROJECT_ROOT / "data" / "processed" / IDEOLOGY_SAMPLE_OUTPUT,
        "csv",
    )

    logger.info(
        "Prepared validation samples: frame=%s, ideology=%s",
        len(frame_sample_df),
        len(ideology_sample_df),
    )
    print(f"Saved validation samples: frame={frame_path}, ideology={ideology_path}")


if __name__ == "__main__":
    main()
