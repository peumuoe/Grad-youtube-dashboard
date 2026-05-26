from __future__ import annotations

from typing import Any

import pandas as pd


def build_channel_analysis_summary(
    frame_distribution_df: pd.DataFrame,
    ideology_df: pd.DataFrame,
    topic_distribution_df: pd.DataFrame,
    audience_distribution_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build one channel-level summary table for reporting."""
    dominant_frame_df = (
        frame_distribution_df.sort_values(
            ["channel_name", "video_count", "primary_frame"],
            ascending=[True, False, True],
        )
        .groupby("channel_name", as_index=False)
        .first()[["channel_name", "primary_frame", "frame_share_within_channel", "channel_total"]]
        .rename(
            columns={
                "primary_frame": "dominant_frame",
                "frame_share_within_channel": "dominant_frame_share",
                "channel_total": "frame_video_count",
            }
        )
    )

    dominant_topic_df = (
        topic_distribution_df.sort_values(
            ["channel_name", "video_count", "topic_label"],
            ascending=[True, False, True],
        )
        .groupby("channel_name", as_index=False)
        .first()[["channel_name", "topic_label", "topic_share_within_channel", "channel_total"]]
        .rename(
            columns={
                "topic_label": "dominant_topic",
                "topic_share_within_channel": "dominant_topic_share",
                "channel_total": "topic_video_count",
            }
        )
    )

    summary_df = ideology_df.merge(dominant_frame_df, on="channel_name", how="left")
    summary_df = summary_df.merge(dominant_topic_df, on="channel_name", how="left")
    if audience_distribution_df is not None and not audience_distribution_df.empty:
        dominant_audience_df = (
            audience_distribution_df.sort_values(
                ["channel_name", "comment_count", "comment_like_sum", "primary_reaction"],
                ascending=[True, False, False, True],
            )
            .groupby("channel_name", as_index=False)
            .first()[
                [
                    "channel_name",
                    "primary_reaction",
                    "reaction_share_within_channel",
                    "channel_total_comments",
                ]
            ]
            .rename(
                columns={
                    "primary_reaction": "dominant_audience_reaction",
                    "reaction_share_within_channel": "dominant_audience_reaction_share",
                    "channel_total_comments": "audience_comment_count",
                }
            )
        )
        summary_df = summary_df.merge(dominant_audience_df, on="channel_name", how="left")
    summary_df = summary_df[
        [column for column in [
            "channel_name",
            "video_count",
            "ideology_relative_score",
            "ideology_relative_label",
            "dominant_frame",
            "dominant_frame_share",
            "dominant_topic",
            "dominant_topic_share",
            "dominant_audience_reaction",
            "dominant_audience_reaction_share",
            "audience_comment_count",
            "progressive_cue_hits",
            "conservative_cue_hits",
        ] if column in summary_df.columns]
    ].sort_values(["video_count", "channel_name"], ascending=[False, True]).reset_index(drop=True)
    return summary_df


def build_frame_wide_table(frame_distribution_df: pd.DataFrame) -> pd.DataFrame:
    """Build a wide table of frame shares by channel."""
    pivot_df = frame_distribution_df.pivot_table(
        index="channel_name",
        columns="primary_frame",
        values="frame_share_within_channel",
        aggfunc="first",
        fill_value=0.0,
    ).reset_index()
    pivot_df.columns.name = None
    return pivot_df


def build_topic_wide_table(topic_distribution_df: pd.DataFrame) -> pd.DataFrame:
    """Build a wide table of top topic shares by channel."""
    pivot_df = topic_distribution_df.pivot_table(
        index="channel_name",
        columns="topic_label",
        values="topic_share_within_channel",
        aggfunc="first",
        fill_value=0.0,
    ).reset_index()
    pivot_df.columns.name = None
    return pivot_df


def build_audience_wide_table(audience_distribution_df: pd.DataFrame) -> pd.DataFrame:
    """Build a wide table of audience reaction shares by channel."""
    pivot_df = audience_distribution_df.pivot_table(
        index="channel_name",
        columns="primary_reaction",
        values="reaction_share_within_channel",
        aggfunc="first",
        fill_value=0.0,
    ).reset_index()
    pivot_df.columns.name = None
    return pivot_df


def build_simple_svg_bar_chart(
    rows: list[dict[str, Any]],
    title: str,
    label_key: str,
    value_key: str,
    value_format: str = ".2f",
    width: int = 960,
    bar_color: str = "#1f5aa6",
) -> str:
    """Build a simple static SVG horizontal bar chart."""
    left_margin = 220
    right_margin = 80
    top_margin = 60
    row_height = 32
    bar_area = width - left_margin - right_margin
    max_value = max([float(row[value_key]) for row in rows], default=1.0) or 1.0
    height = top_margin + row_height * len(rows) + 40

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<style>text{font-family:Segoe UI,Arial,sans-serif;fill:#111;} .title{font-size:22px;font-weight:700;} '
        '.label{font-size:13px;} .value{font-size:12px;fill:#333;} .axis{stroke:#bbb;stroke-width:1;}</style>',
        f'<text x="{left_margin}" y="30" class="title">{title}</text>',
        f'<line x1="{left_margin}" y1="{top_margin - 8}" x2="{width - right_margin}" y2="{top_margin - 8}" class="axis"/>',
    ]

    for idx, row in enumerate(rows):
        y = top_margin + idx * row_height
        label = str(row[label_key])
        value = float(row[value_key])
        bar_width = 0 if max_value == 0 else (value / max_value) * bar_area
        parts.append(f'<text x="{left_margin - 12}" y="{y + 16}" text-anchor="end" class="label">{label}</text>')
        parts.append(f'<rect x="{left_margin}" y="{y + 4}" width="{bar_width:.1f}" height="18" fill="{bar_color}" rx="3"/>')
        parts.append(
            f'<text x="{left_margin + bar_width + 8:.1f}" y="{y + 18}" class="value">{format(value, value_format)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)
