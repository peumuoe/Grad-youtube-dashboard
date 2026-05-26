from __future__ import annotations

from typing import Any

import pandas as pd


PROGRESSIVE_CUES = [
    "휴전",
    "민간인",
    "민간 피해",
    "인도주의",
    "난민",
    "외교적 해법",
    "협상",
    "중재",
    "확전 우려",
    "전쟁 반대",
    "국제법",
    "민생 부담",
]

CONSERVATIVE_CUES = [
    "응징",
    "보복",
    "안보",
    "억제",
    "동맹",
    "군사력",
    "정밀 타격",
    "강경 대응",
    "제재 강화",
    "방어권",
    "선제",
    "봉쇄",
]


def count_hits(text: str, keywords: list[str]) -> int:
    """Count simple substring cue hits."""
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered)


def label_tilt(score: float, low_threshold: float = -0.15, high_threshold: float = 0.15) -> str:
    """Map relative score into project ideology labels."""
    if score <= low_threshold:
        return "진보적 기울기"
    if score >= high_threshold:
        return "보수적 기울기"
    return "혼합/중간"


def estimate_ideology_tilt(frame_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimate issue-specific relative ideology tilt from text cues."""
    working_df = frame_df.copy()
    working_df["frame_text"] = working_df["frame_text"].fillna("").astype(str).str.strip()

    video_rows: list[dict[str, Any]] = []
    for row in working_df.itertuples(index=False):
        text = str(getattr(row, "frame_text_cleaned", "") or row.frame_text or "")
        progressive_hits = count_hits(text, PROGRESSIVE_CUES)
        conservative_hits = count_hits(text, CONSERVATIVE_CUES)
        total_hits = progressive_hits + conservative_hits
        relative_score = 0.0 if total_hits == 0 else (conservative_hits - progressive_hits) / total_hits
        video_rows.append(
            {
                "video_id": row.video_id,
                "channel_name": row.channel_name,
                "progressive_cue_hits": int(progressive_hits),
                "conservative_cue_hits": int(conservative_hits),
                "ideology_relative_score": float(relative_score),
                "ideology_relative_label": label_tilt(relative_score),
            }
        )

    video_df = pd.DataFrame(video_rows)
    channel_df = (
        video_df.groupby("channel_name", dropna=False)
        .agg(
            video_count=("video_id", "count"),
            progressive_cue_hits=("progressive_cue_hits", "sum"),
            conservative_cue_hits=("conservative_cue_hits", "sum"),
            ideology_relative_score=("ideology_relative_score", "mean"),
        )
        .reset_index()
    )
    channel_df["ideology_relative_label"] = channel_df["ideology_relative_score"].apply(label_tilt)
    channel_df = channel_df.sort_values(
        ["ideology_relative_score", "video_count"], ascending=[False, False]
    ).reset_index(drop=True)

    return video_df, channel_df
