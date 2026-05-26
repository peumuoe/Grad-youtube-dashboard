from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analyze.input_builder import (
    build_audience_comment_input,
    build_audience_video_input,
    build_frame_input,
    build_topic_input,
    build_topic_input_from_transcript,
)
from src.io_utils import ensure_directories, load_dataframe_if_exists, save_dataframe, setup_logger
from src.preprocess.comment_filters import prepare_filtered_comment_rows


STAGE2_BASENAME = "text_analysis_inputs_stage2"
COMMENTS_BASENAME = "comments_raw"
TOPIC_OUTPUT = "topic_analysis_input"
TOPIC_TRANSCRIPT_OUTPUT = "topic_analysis_input_transcript"
FRAME_OUTPUT = "frame_analysis_input"
AUDIENCE_VIDEO_OUTPUT = "audience_video_input"
AUDIENCE_COMMENT_OUTPUT = "audience_comment_input"


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logger = setup_logger(PROJECT_ROOT / "logs", "09_split_analysis_inputs", log_level)
    ensure_directories([PROJECT_ROOT / "data" / "processed"])

    stage2_path = (PROJECT_ROOT / "data" / "processed" / STAGE2_BASENAME).with_suffix(f".{output_format}")
    stage2_df = load_dataframe_if_exists(stage2_path)
    if stage2_df.empty:
        raise ValueError(f"No stage2 analysis input found at {stage2_path}. Run 08_prepare_analysis_inputs.py first.")

    comments_path = (PROJECT_ROOT / "data" / "raw" / COMMENTS_BASENAME).with_suffix(f".{output_format}")
    comments_df = load_dataframe_if_exists(comments_path)
    filtered_comments_df = prepare_filtered_comment_rows(comments_df)

    topic_df = build_topic_input(stage2_df)
    topic_transcript_df = build_topic_input_from_transcript(stage2_df)
    frame_df = build_frame_input(stage2_df)
    audience_video_df = build_audience_video_input(stage2_df)
    audience_comment_df = build_audience_comment_input(filtered_comments_df, stage2_df)

    topic_path = save_dataframe(topic_df, PROJECT_ROOT / "data" / "processed" / TOPIC_OUTPUT, output_format)
    topic_transcript_path = save_dataframe(
        topic_transcript_df,
        PROJECT_ROOT / "data" / "processed" / TOPIC_TRANSCRIPT_OUTPUT,
        output_format,
    )
    frame_path = save_dataframe(frame_df, PROJECT_ROOT / "data" / "processed" / FRAME_OUTPUT, output_format)
    audience_video_path = save_dataframe(
        audience_video_df, PROJECT_ROOT / "data" / "processed" / AUDIENCE_VIDEO_OUTPUT, output_format
    )
    audience_comment_path = save_dataframe(
        audience_comment_df, PROJECT_ROOT / "data" / "processed" / AUDIENCE_COMMENT_OUTPUT, output_format
    )

    logger.info(
        "Split stage2 inputs into topic=%s, topic_transcript=%s, frame=%s, audience_video=%s, audience_comment=%s",
        len(topic_df),
        len(topic_transcript_df),
        len(frame_df),
        len(audience_video_df),
        len(audience_comment_df),
    )
    print(
        "Saved analysis inputs: "
        f"topic={topic_path}, topic_transcript={topic_transcript_path}, frame={frame_path}, audience_video={audience_video_path}, "
        f"audience_comment={audience_comment_path}"
    )


if __name__ == "__main__":
    main()
