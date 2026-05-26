from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analyze.frame_classifier import classify_frames
from src.io_utils import ensure_directories, load_dataframe_if_exists, save_dataframe, setup_logger


INPUT_BASENAME = "frame_analysis_input"
VIDEO_OUTPUT = "frame_video_classification"
CHANNEL_OUTPUT = "channel_frame_distribution"


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logger = setup_logger(PROJECT_ROOT / "logs", "33_run_frame_analysis", log_level)
    ensure_directories([PROJECT_ROOT / "outputs" / "tables"])

    input_path = (PROJECT_ROOT / "data" / "processed" / INPUT_BASENAME).with_suffix(f".{output_format}")
    frame_df = load_dataframe_if_exists(input_path)
    if frame_df.empty:
        raise ValueError(f"No frame input found at {input_path}. Run 09_split_analysis_inputs.py first.")

    video_df, channel_df = classify_frames(frame_df)

    video_path = save_dataframe(video_df, PROJECT_ROOT / "outputs" / "tables" / VIDEO_OUTPUT, "csv")
    channel_path = save_dataframe(channel_df, PROJECT_ROOT / "outputs" / "tables" / CHANNEL_OUTPUT, "csv")

    logger.info(
        "Frame analysis completed with %s videos and %s channels.",
        len(video_df),
        channel_df["channel_name"].nunique(),
    )
    print(f"Saved frame outputs: video={video_path}, channel={channel_path}")


if __name__ == "__main__":
    main()
