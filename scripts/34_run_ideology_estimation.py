from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analyze.ideology_estimator import estimate_ideology_tilt
from src.io_utils import ensure_directories, load_dataframe_if_exists, save_dataframe, setup_logger


INPUT_BASENAME = "frame_video_classification"
VIDEO_OUTPUT = "ideology_video_estimates"
CHANNEL_OUTPUT = "channel_ideology_estimates"


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logger = setup_logger(PROJECT_ROOT / "logs", "34_run_ideology_estimation", log_level)
    ensure_directories([PROJECT_ROOT / "outputs" / "tables"])

    input_path = (PROJECT_ROOT / "outputs" / "tables" / INPUT_BASENAME).with_suffix(".csv")
    frame_df = load_dataframe_if_exists(input_path)
    if frame_df.empty:
        raise ValueError(f"No frame classification found at {input_path}. Run 33_run_frame_analysis.py first.")

    video_df, channel_df = estimate_ideology_tilt(frame_df)

    video_path = save_dataframe(video_df, PROJECT_ROOT / "outputs" / "tables" / VIDEO_OUTPUT, "csv")
    channel_path = save_dataframe(channel_df, PROJECT_ROOT / "outputs" / "tables" / CHANNEL_OUTPUT, "csv")

    logger.info(
        "Ideology estimation completed with %s channels.",
        channel_df["channel_name"].nunique(),
    )
    print(f"Saved ideology outputs: video={video_path}, channel={channel_path}")


if __name__ == "__main__":
    main()
