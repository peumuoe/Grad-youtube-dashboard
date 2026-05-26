from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analyze.audience_reaction_classifier import classify_audience_reactions
from src.io_utils import ensure_directories, load_dataframe_if_exists, save_dataframe, setup_logger


INPUT_BASENAME = "audience_comment_input"
COMMENT_OUTPUT = "audience_comment_reaction_classification"
VIDEO_OUTPUT = "audience_video_reaction_summary"
CHANNEL_OUTPUT = "channel_audience_reaction_distribution"
VALIDATION_OUTPUT = "audience_reaction_validation_sample"


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logger = setup_logger(PROJECT_ROOT / "logs", "38_run_audience_reaction_analysis", log_level)
    ensure_directories([PROJECT_ROOT / "outputs" / "tables", PROJECT_ROOT / "data" / "processed"])

    input_path = (PROJECT_ROOT / "data" / "processed" / INPUT_BASENAME).with_suffix(f".{output_format}")
    comment_df = load_dataframe_if_exists(input_path)
    if comment_df.empty:
        raise ValueError(f"No audience comment input found at {input_path}. Run 09_split_analysis_inputs.py first.")

    comment_out_df, video_out_df, channel_out_df, validation_df = classify_audience_reactions(comment_df)

    comment_path = save_dataframe(comment_out_df, PROJECT_ROOT / "outputs" / "tables" / COMMENT_OUTPUT, "csv")
    video_path = save_dataframe(video_out_df, PROJECT_ROOT / "outputs" / "tables" / VIDEO_OUTPUT, "csv")
    channel_path = save_dataframe(channel_out_df, PROJECT_ROOT / "outputs" / "tables" / CHANNEL_OUTPUT, "csv")
    validation_path = save_dataframe(validation_df, PROJECT_ROOT / "data" / "processed" / VALIDATION_OUTPUT, "csv")

    logger.info(
        "Audience reaction analysis completed with %s classified comments, %s videos, and %s channels.",
        len(comment_out_df),
        video_out_df["video_id"].nunique(),
        channel_out_df["channel_name"].nunique(),
    )
    print(
        "Saved audience reaction outputs: "
        f"comments={comment_path}, videos={video_path}, channels={channel_path}, validation={validation_path}"
    )


if __name__ == "__main__":
    main()
