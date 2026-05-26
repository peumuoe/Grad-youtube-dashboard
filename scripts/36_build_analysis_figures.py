from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analyze.report_builder import build_simple_svg_bar_chart
from src.io_utils import ensure_directories, load_dataframe_if_exists, setup_logger


def write_svg(path: Path, svg_text: str) -> None:
    path.write_text(svg_text, encoding="utf-8")


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger = setup_logger(PROJECT_ROOT / "logs", "36_build_analysis_figures", log_level)
    ensure_directories([PROJECT_ROOT / "outputs" / "figures"])

    ideology_df = load_dataframe_if_exists(PROJECT_ROOT / "outputs" / "tables" / "channel_ideology_estimates.csv")
    frame_df = load_dataframe_if_exists(PROJECT_ROOT / "outputs" / "tables" / "channel_frame_distribution.csv")
    if ideology_df.empty or frame_df.empty:
        raise ValueError("Missing ideology or frame outputs. Run 33~35 scripts first.")

    ideology_rows = ideology_df.sort_values("ideology_relative_score", ascending=False).to_dict("records")
    ideology_svg = build_simple_svg_bar_chart(
        ideology_rows,
        title="채널별 이념적 기울기 추정 점수",
        label_key="channel_name",
        value_key="ideology_relative_score",
        value_format=".3f",
        bar_color="#b04747",
    )
    write_svg(PROJECT_ROOT / "outputs" / "figures" / "channel_ideology_estimates.svg", ideology_svg)

    security_df = frame_df[frame_df["primary_frame"] == "안보·군사"].copy()
    security_rows = security_df.sort_values("frame_share_within_channel", ascending=False).to_dict("records")
    security_svg = build_simple_svg_bar_chart(
        security_rows,
        title="채널별 안보·군사 프레임 비중",
        label_key="channel_name",
        value_key="frame_share_within_channel",
        value_format=".3f",
        bar_color="#1f5aa6",
    )
    write_svg(PROJECT_ROOT / "outputs" / "figures" / "channel_security_frame_share.svg", security_svg)

    logger.info("Built SVG analysis figures for %s channels.", len(ideology_df))
    print("Saved figures: channel_ideology_estimates.svg, channel_security_frame_share.svg")


if __name__ == "__main__":
    main()
