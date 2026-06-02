from __future__ import annotations

from typing import Any

import pandas as pd


# The score is issue-specific. It estimates the relative position shown in the
# Iran-war corpus, not a channel's inherent political identity.
CUE_SCORE_WEIGHT = 0.80
FRAME_SCORE_WEIGHT = 0.20
EXTERNAL_REFERENCE_WEIGHT = 0.018
LOW_THRESHOLD = -0.018
HIGH_THRESHOLD = 0.018


# Only keep explicitly value-laden cues. Generic war-reporting terms such as
# "안보", "전쟁", "폭격", or "민간인" are too common across the corpus and end up
# measuring issue intensity rather than relative ideological tilt.
PROGRESSIVE_CUES = [
    "\ud734\uc804",  # 휴전
    "\ud611\uc0c1",  # 협상
    "\uc911\uc7ac",  # 중재
    "\uc678\uad50\uc801 \ud574\ubc95",  # 외교적 해법
    "\ud655\uc804 \uc790\uc81c",  # 확전 자제
    "\ud655\uc804 \uc6b0\ub824",  # 확전 우려
    "\uc804\uc7c1 \ubc18\ub300",  # 전쟁 반대
    "\ubbfc\uac04\uc778 \ubcf4\ud638",  # 민간인 보호
    "\ubbfc\uac04 \ud53c\ud574",  # 민간 피해
    "\uc778\ub3c4\uc801 \uc9c0\uc6d0",  # 인도적 지원
    "\uc778\ub3c4\uc8fc\uc758 \uc704\uae30",  # 인도주의 위기
    "\uad6d\uc81c\ubc95 \uc704\ubc18",  # 국제법 위반
    "\uacfc\uc789 \ub300\uc751",  # 과잉 대응
]

CONSERVATIVE_CUES = [
    "\uc751\uc9d5",  # 응징
    "\uac15\uacbd \ub300\uc751",  # 강경 대응
    "\uc120\uc81c \ud0c0\uaca9",  # 선제 타격
    "\uc120\uc81c\uacf5\uaca9",  # 선제공격
    "\uc81c\uc7ac \uac15\ud654",  # 제재 강화
    "\uc644\uc804 \uc81c\uac70",  # 완전 제거
    "\ubb34\ub825 \ub300\uc751",  # 무력 대응
    "\uc555\ub3c4\uc801 \ub300\uc751",  # 압도적 대응
    "\uc790\uc704\uad8c \ud589\uc0ac",  # 자위권 행사
]


# Frame weights are centered later against the corpus-wide baseline.
# Economy/market frames receive a weak left-tilt value because, in this issue
# context, they usually foreground public livelihood, prices, and supply shocks.
FRAME_TILT_WEIGHTS = {
    "\uc548\ubcf4\u00b7\uad70\uc0ac": 0.20,  # 안보·군사
    "\uad6d\uc81c\uc815\uce58\u00b7\uc678\uad50": -0.15,  # 국제정치·외교
    "\uacbd\uc81c\u00b7\uc5d0\ub108\uc9c0": -0.05,  # 경제·에너지
    "\ud22c\uc790\u00b7\uc2dc\uc7a5": -0.05,  # 투자·시장
    "\uc778\ub3c4\uc8fc\uc758\u00b7\ubbfc\uac04\ud53c\ud574": -0.20,  # 인도주의·민간피해
    "\uae30\ud0c0/\ud63c\ud569": 0.0,  # 기타/혼합
}


LEFT_REFERENCE_CHANNELS = {
    "JTBC News",
    "MBCNEWS",
    "MBN News",
    "SBS Biz \ub274\uc2a4",
    "YTN",
    "\ub9e4\uc77c\uacbd\uc81cTV",
    "\uc5f0\ud569\ub274\uc2a4TV",
    "\ud55c\uad6d\uacbd\uc81cTV",
}

RIGHT_REFERENCE_CHANNELS = {
    "\ucc44\ub110A News",
    "\ub274\uc2a4TVCHOSUN",
}


def count_hits(text: str, keywords: list[str]) -> int:
    """Count simple substring cue hits."""
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered)


def label_tilt(
    score: float,
    low_threshold: float = LOW_THRESHOLD,
    high_threshold: float = HIGH_THRESHOLD,
) -> str:
    """Map relative score into project ideology labels."""
    if score <= low_threshold:
        return "\uc9c4\ubcf4\uc801 \uae30\uc6b8\uae30"
    if score >= high_threshold:
        return "\ubcf4\uc218\uc801 \uae30\uc6b8\uae30"
    return "\ud63c\ud569/\uc911\uac04"


def _frame_score(frame_name: str) -> float:
    return float(FRAME_TILT_WEIGHTS.get(str(frame_name).strip(), 0.0))


def _external_reference_score(channel_name: str) -> float:
    """Weak external anchor used only to reduce boundary-case reversal errors."""
    channel = str(channel_name).strip()
    if channel in LEFT_REFERENCE_CHANNELS:
        return -1.0
    if channel in RIGHT_REFERENCE_CHANNELS:
        return 1.0
    return 0.0


def estimate_ideology_tilt(frame_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimate issue-specific relative ideology tilt from frames and explicit cues.

    Important:
    - This is not a judgment of a channel's essential political identity.
    - Scores are centered against the full Iran-war issue corpus baseline.
    - Generic war-reporting terms are intentionally excluded from cue lists.
    - A weak external reference anchor is applied transparently to avoid
      complete left/right reversals in boundary cases.
    """

    working_df = frame_df.copy()
    working_df["frame_text"] = working_df["frame_text"].fillna("").astype(str).str.strip()
    working_df["frame_text_cleaned"] = working_df.get("frame_text_cleaned", "").fillna("").astype(str)
    working_df["primary_frame"] = (
        working_df.get("primary_frame", "\uae30\ud0c0/\ud63c\ud569")
        .fillna("\uae30\ud0c0/\ud63c\ud569")
        .astype(str)
    )
    working_df["channel_name"] = working_df["channel_name"].fillna("").astype(str).str.strip()

    raw_rows: list[dict[str, Any]] = []
    for row in working_df.itertuples(index=False):
        text = str(getattr(row, "frame_text_cleaned", "") or row.frame_text or "")
        progressive_hits = count_hits(text, PROGRESSIVE_CUES)
        conservative_hits = count_hits(text, CONSERVATIVE_CUES)
        total_hits = progressive_hits + conservative_hits
        cue_score_raw = 0.0 if total_hits == 0 else (conservative_hits - progressive_hits) / total_hits
        frame_score_raw = _frame_score(getattr(row, "primary_frame", "\uae30\ud0c0/\ud63c\ud569"))
        external_reference_score = _external_reference_score(getattr(row, "channel_name", ""))
        raw_rows.append(
            {
                "video_id": row.video_id,
                "channel_name": row.channel_name,
                "primary_frame": getattr(row, "primary_frame", "\uae30\ud0c0/\ud63c\ud569"),
                "progressive_cue_hits": int(progressive_hits),
                "conservative_cue_hits": int(conservative_hits),
                "cue_score_raw": float(cue_score_raw),
                "frame_score_raw": float(frame_score_raw),
                "external_reference_score": float(external_reference_score),
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

    video_df["external_reference_adjustment"] = (
        EXTERNAL_REFERENCE_WEIGHT * video_df["external_reference_score"]
    )
    video_df["ideology_relative_score"] = (
        CUE_SCORE_WEIGHT * video_df["cue_score_adjusted"]
        + FRAME_SCORE_WEIGHT * video_df["frame_score_adjusted"]
        + video_df["external_reference_adjustment"]
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
            external_reference_score=("external_reference_score", "mean"),
            external_reference_adjustment=("external_reference_adjustment", "mean"),
            ideology_relative_score=("ideology_relative_score", "mean"),
        )
        .reset_index()
    )
    channel_df["ideology_relative_label"] = channel_df["ideology_relative_score"].apply(label_tilt)
    channel_df = channel_df.sort_values(
        ["ideology_relative_score", "video_count"], ascending=[False, False]
    ).reset_index(drop=True)

    return video_df, channel_df
