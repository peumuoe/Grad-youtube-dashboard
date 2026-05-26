from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analyze.report_builder import (
    build_audience_wide_table,
    build_channel_analysis_summary,
    build_frame_wide_table,
    build_topic_wide_table,
)
from src.io_utils import ensure_directories, load_dataframe_if_exists, save_dataframe, setup_logger


FRAME_INPUT = "channel_frame_distribution.csv"
TOPIC_INPUT = "channel_topic_distribution.csv"
IDEOLOGY_INPUT = "channel_ideology_estimates.csv"
AUDIENCE_INPUT = "channel_audience_reaction_distribution.csv"


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger = setup_logger(PROJECT_ROOT / "logs", "35_build_analysis_summary_tables", log_level)
    ensure_directories([PROJECT_ROOT / "outputs" / "tables"])

    frame_df = load_dataframe_if_exists(PROJECT_ROOT / "outputs" / "tables" / FRAME_INPUT)
    topic_df = load_dataframe_if_exists(PROJECT_ROOT / "outputs" / "tables" / TOPIC_INPUT)
    ideology_df = load_dataframe_if_exists(PROJECT_ROOT / "outputs" / "tables" / IDEOLOGY_INPUT)
    audience_df = load_dataframe_if_exists(PROJECT_ROOT / "outputs" / "tables" / AUDIENCE_INPUT)
    if frame_df.empty or topic_df.empty or ideology_df.empty:
        raise ValueError("Missing analysis outputs. Run 32~34 scripts first.")

    summary_df = build_channel_analysis_summary(frame_df, ideology_df, topic_df, audience_df)
    frame_wide_df = build_frame_wide_table(frame_df)
    topic_wide_df = build_topic_wide_table(topic_df)
    audience_wide_df = build_audience_wide_table(audience_df) if not audience_df.empty else None

    summary_path = save_dataframe(summary_df, PROJECT_ROOT / "outputs" / "tables" / "channel_analysis_summary", "csv")
    frame_path = save_dataframe(frame_wide_df, PROJECT_ROOT / "outputs" / "tables" / "channel_frame_share_wide", "csv")
    topic_path = save_dataframe(topic_wide_df, PROJECT_ROOT / "outputs" / "tables" / "channel_topic_share_wide", "csv")
    if audience_wide_df is not None:
        audience_path = save_dataframe(
            audience_wide_df,
            PROJECT_ROOT / "outputs" / "tables" / "channel_audience_reaction_share_wide",
            "csv",
        )
    else:
        audience_path = "not-generated"

    logger.info("Built summary tables for %s channels.", len(summary_df))
    print(f"Saved summary tables: {summary_path}, {frame_path}, {topic_path}, {audience_path}")


if __name__ == "__main__":
    main()
