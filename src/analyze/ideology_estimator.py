from __future__ import annotations

from typing import Any

import pandas as pd


# Only keep explicitly value-laden cues. Generic war-reporting terms such as
# "안보", "동맹", "봉쇄" or "민간인" are too common across the corpus and end up
# measuring issue intensity rather than relative ideological tilt.
PROGRESSIVE_CUES = [
    "휴전",
    "협상",
    "중재",
    "외교적 해법",
    "확전 자제",
    "확전 우려",
    "전쟁 반대",
    "민간인 보호",
    "민간 피해",
    "인도적 지원",
    "인도주의 위기",
    "국제법 위반",
    "과잉 대응",
]

CONSERVATIVE_CUES = [
    "응징",
    "보복",
    "강경 대응",
    "정밀 타격",
    "선제 타격",
    "선제공격",
    "제재 강화",
    "정권 교체",
    "완전 제거",
    "무력 대응",
    "압도적 대응",
    "자위권 행사",
]


# Frame weights are centered later against the corpus-wide baseline.
# The goal is not to label a channel's inherent politics, but to estimate
# whether this issue corpus is framed relatively more hawkish or more
# diplomatic/humanitarian than the overall corpus average.
FRAME_TILT_WEIGHTS = {
    "안보·군사": 0.4,
    "국제정치·외교": -0.3,
    "경제·에너지": 0.0,
    "투자·시장": 0.0,
    "인도주의·민간피해": -0.4,
    "기타/혼합": 0.0,
}


def count_hits(text: str, keywords: list[str]) -> int:
    """Count simple substring cue hits."""
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered)


def label_tilt(score: float, low_threshold: float = -0.12, high_threshold: float = 0.12) -> str:
    """Map relative score into project ideology labels."""
    if score <= low_threshold:
        return "진보적 기울기"
    if score >= high_threshold:
        return "보수적 기울기"
    return "혼합/중간"


def _frame_score(frame_name: str) -> float:
    return float(FRAME_TILT_WEIGHTS.get(str(frame_name).strip(), 0.0))


def estimate_ideology_tilt(frame_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimate issue-specific relative ideology tilt from frames and explicit cues.

    Important:
    - This is not a judgment of a channel's essential political identity.
    - Scores are centered against the full Iran-war issue corpus baseline.
    - Generic war-reporting terms are intentionally excluded from cue lists.
    """

    working_df = frame_df.copy()
    working_df["frame_text"] = working_df["frame_text"].fillna("").astype(str).str.strip()
    working_df["frame_text_cleaned"] = working_df.get("frame_text_cleaned", "").fillna("").astype(str)
    working_df["primary_frame"] = working_df.get("primary_frame", "기타/혼합").fillna("기타/혼합").astype(str)

    raw_rows: list[dict[str, Any]] = []
    for row in working_df.itertuples(index=False):
        text = str(getattr(row, "frame_text_cleaned", "") or row.frame_text or "")
        progressive_hits = count_hits(text, PROGRESSIVE_CUES)
        conservative_hits = count_hits(text, CONSERVATIVE_CUES)
        total_hits = progressive_hits + conservative_hits
        cue_score_raw = 0.0 if total_hits == 0 else (conservative_hits - progressive_hits) / total_hits
        frame_score_raw = _frame_score(getattr(row, "primary_frame", "기타/혼합"))
        raw_rows.append(
            {
                "video_id": row.video_id,
                "channel_name": row.channel_name,
                "primary_frame": getattr(row, "primary_frame", "기타/혼합"),
                "progressive_cue_hits": int(progressive_hits),
                "conservative_cue_hits": int(conservative_hits),
                "cue_score_raw": float(cue_score_raw),
                "frame_score_raw": float(frame_score_raw),
            }
        )

    video_df = pd.DataFrame(raw_rows)

    frame_baseline = float(video_df["frame_score_raw"].mean()) if not video_df.empty else 0.0
    cue_hit_mask = (video_df["progressive_cue_hits"] + video_df["conservative_cue_hits"]) > 0
    cue_baseline = float(video_df.loc[cue_hit_mask, "cue_score_raw"].mean()) if cue_hit_mask.any() else 0.0

    video_df["frame_score_adjusted"] = video_df["frame_score_raw"] - frame_baseline
    video_df["cue_score_adjusted"] = 0.0
    if cue_hit_mask.any():
        video_df.loc[cue_hit_mask, "cue_score_adjusted"] = (
            video_df.loc[cue_hit_mask, "cue_score_raw"] - cue_baseline
        )

    # Keep frame information as a weaker contextual signal and let explicit
    # value-laden cues carry more weight. This reduces researcher-imposed
    # interpretation from mapping whole frames directly onto a left/right axis.
    video_df["ideology_relative_score"] = (
        0.30 * video_df["frame_score_adjusted"] + 0.70 * video_df["cue_score_adjusted"]
    )
    video_df["ideology_relative_label"] = video_df["ideology_relative_score"].apply(label_tilt)

    channel_df = (
        video_df.groupby("channel_name", dropna=False)
        .agg(
            video_count=("video_id", "count"),
            progressive_cue_hits=("progressive_cue_hits", "sum"),
            conservative_cue_hits=("conservative_cue_hits", "sum"),
            frame_score_raw=("frame_score_raw", "mean"),
            frame_score_adjusted=("frame_score_adjusted", "mean"),
            cue_score_adjusted=("cue_score_adjusted", "mean"),
            ideology_relative_score=("ideology_relative_score", "mean"),
        )
        .reset_index()
    )
    channel_df["ideology_relative_label"] = channel_df["ideology_relative_score"].apply(label_tilt)
    channel_df = channel_df.sort_values(
        ["ideology_relative_score", "video_count"], ascending=[False, False]
    ).reset_index(drop=True)

    return video_df, channel_df
