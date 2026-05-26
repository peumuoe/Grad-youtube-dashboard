from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.io_utils import load_dataframe_if_exists, save_dataframe, setup_logger


VIDEO_BASENAME = "videos_raw"
TRANSCRIPTS_BASENAME = "transcripts_raw"
OUTPUT_BASENAME = "article_script_queue"
SUCCESS_SOURCES = {"public_caption", "provided_script", "stt"}


def build_current_transcript_lookup(transcripts_df: pd.DataFrame) -> pd.DataFrame:
    """Return one transcript status row per video."""
    if transcripts_df.empty:
        return pd.DataFrame(columns=["video_id", "transcript_source"])

    working_df = transcripts_df.copy()
    working_df["video_id"] = working_df["video_id"].astype(str)
    if "collected_at" not in working_df.columns:
        working_df["collected_at"] = ""

    working_df = working_df.sort_values(["video_id", "collected_at"], ascending=[True, True])
    working_df = working_df.drop_duplicates(subset=["video_id"], keep="last")
    return working_df[["video_id", "transcript_source"]].reset_index(drop=True)


def main() -> None:
    logger = setup_logger(PROJECT_ROOT / "logs", "12_prepare_article_script_queue", "INFO")

    videos_df = load_dataframe_if_exists(PROJECT_ROOT / "data" / "raw" / f"{VIDEO_BASENAME}.csv")
    if videos_df.empty:
        raise ValueError("videos_raw.csv is required before preparing article queues.")

    transcripts_df = load_dataframe_if_exists(
        PROJECT_ROOT / "data" / "raw" / f"{TRANSCRIPTS_BASENAME}.csv"
    )
    transcript_status_df = build_current_transcript_lookup(transcripts_df)

    videos_df = videos_df.copy()
    videos_df["video_id"] = videos_df["video_id"].astype(str)
    merged_df = videos_df.merge(transcript_status_df, on="video_id", how="left")
    merged_df["transcript_source"] = merged_df["transcript_source"].fillna("unattempted")

    target_df = merged_df.loc[~merged_df["transcript_source"].isin(SUCCESS_SOURCES)].copy()
    target_df["article_search_query"] = (
        target_df["channel_name"].fillna("").astype(str).str.strip()
        + " "
        + target_df["title"].fillna("").astype(str).str.strip()
    ).str.strip()
    target_df["article_candidate_url"] = ""
    target_df["article_title"] = ""
    target_df["article_body_raw"] = ""
    target_df["use_flag"] = 0
    target_df["source_note"] = "Broadcast article body candidate"

    keep_columns = [
        "video_id",
        "channel_name",
        "channel_type",
        "published_at",
        "search_keyword",
        "title",
        "url",
        "transcript_source",
        "article_search_query",
        "article_candidate_url",
        "article_title",
        "article_body_raw",
        "use_flag",
        "source_note",
    ]
    target_df = target_df[keep_columns].reset_index(drop=True)

    output_path = save_dataframe(
        target_df,
        PROJECT_ROOT / "data" / "processed" / OUTPUT_BASENAME,
        "csv",
    )
    logger.info("Prepared article script queue with %s rows", len(target_df))
    print(f"Saved article queue to {output_path} with {len(target_df)} rows.")


if __name__ == "__main__":
    main()
