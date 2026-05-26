from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analyze.topic_modeling import run_topic_model
from src.io_utils import ensure_directories, load_dataframe_if_exists, save_dataframe, setup_logger


OUTPUT_FORMAT = "csv"

RUN_SPECS = [
    {
        "input_name": "topic_analysis_input",
        "video_output": "topic_video_assignments",
        "summary_output": "topic_summary",
        "channel_output": "channel_topic_distribution",
        "metadata_output": "topic_model_metadata.json",
        "label": "metadata",
    },
    {
        "input_name": "topic_analysis_input_transcript",
        "video_output": "topic_video_assignments_script",
        "summary_output": "topic_summary_script",
        "channel_output": "channel_topic_distribution_script",
        "metadata_output": "topic_model_metadata_script.json",
        "label": "transcript",
    },
]


def run_one_topic_analysis(spec: dict[str, str], logger) -> None:
    input_path = (PROJECT_ROOT / "data" / "processed" / spec["input_name"]).with_suffix(f".{OUTPUT_FORMAT}")
    topic_df = load_dataframe_if_exists(input_path)
    if topic_df.empty:
        logger.warning("No topic input found at %s. Skipping %s topic analysis.", input_path, spec["label"])
        return

    artifacts = run_topic_model(topic_df)

    video_path = save_dataframe(
        artifacts.video_topics_df,
        PROJECT_ROOT / "outputs" / "tables" / spec["video_output"],
        OUTPUT_FORMAT,
    )
    summary_path = save_dataframe(
        artifacts.topic_summary_df,
        PROJECT_ROOT / "outputs" / "tables" / spec["summary_output"],
        OUTPUT_FORMAT,
    )
    channel_path = save_dataframe(
        artifacts.channel_topic_share_df,
        PROJECT_ROOT / "outputs" / "tables" / spec["channel_output"],
        OUTPUT_FORMAT,
    )
    metadata_path = PROJECT_ROOT / "outputs" / "tables" / spec["metadata_output"]
    metadata = dict(artifacts.metadata)
    metadata["topic_input_label"] = spec["label"]
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(
        "Topic analysis (%s) completed with %s documents and %s topics.",
        spec["label"],
        artifacts.metadata["document_count"],
        artifacts.metadata["actual_topics"],
    )
    print(
        f"[{spec['label']}] video={video_path}, summary={summary_path}, "
        f"channel={channel_path}, metadata={metadata_path}"
    )


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger = setup_logger(PROJECT_ROOT / "logs", "32_run_topic_analysis", log_level)
    ensure_directories([PROJECT_ROOT / "outputs" / "tables"])

    for spec in RUN_SPECS:
        run_one_topic_analysis(spec, logger)


if __name__ == "__main__":
    main()
