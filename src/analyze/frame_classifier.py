from __future__ import annotations

from typing import Any

import pandas as pd

from src.analyze.boilerplate_filters import strip_boilerplate


FRAME_RULES: dict[str, list[str]] = {
    "안보·군사": [
        "공습",
        "폭격",
        "미사일",
        "드론",
        "군사",
        "공격",
        "방공",
        "요격",
        "해협 봉쇄",
        "핵시설",
        "군함",
        "병력",
        "타격",
    ],
    "국제정치·외교": [
        "정상회담",
        "외교",
        "협상",
        "중재",
        "유엔",
        "제재",
        "동맹",
        "성명",
        "규탄",
        "지지 요청",
        "휴전",
        "백악관",
        "대사관",
    ],
    "경제·에너지": [
        "유가",
        "가스전",
        "호르무즈",
        "원유",
        "원자재",
        "에너지",
        "수출",
        "공급망",
        "물류",
        "관세",
        "무역",
        "천연가스",
    ],
    "투자·시장": [
        "증시",
        "주가",
        "코스피",
        "코스닥",
        "환율",
        "투자",
        "시장",
        "채권",
        "금리",
        "비트코인",
        "나스닥",
        "테슬라",
        "엔비디아",
    ],
    "인도주의·민간피해": [
        "민간인",
        "피란",
        "난민",
        "인도주의",
        "사상자",
        "어린이",
        "병원",
        "구호",
        "희생",
        "인명피해",
        "구조",
        "민간 피해",
    ],
}


def count_rule_hits(text: str, keywords: list[str]) -> int:
    """Count simple substring hits for one frame rule."""
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered)


def assign_primary_frame(score_map: dict[str, int]) -> str:
    """Assign the primary frame with a conservative tie rule."""
    positive = {frame: score for frame, score in score_map.items() if score > 0}
    if not positive:
        return "기타/혼합"

    top_score = max(positive.values())
    top_frames = [frame for frame, score in positive.items() if score == top_score]
    if len(top_frames) >= 2:
        return "기타/혼합"
    return top_frames[0]


def classify_frames(frame_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Classify frame text into project frame categories."""
    working_df = frame_df.copy()
    working_df["frame_text"] = working_df["frame_text"].fillna("").astype(str).str.strip()
    working_df["frame_text_cleaned"] = working_df["frame_text"].apply(strip_boilerplate)

    score_rows: list[dict[str, Any]] = []
    for row in working_df.itertuples(index=False):
        text = str(row.frame_text_cleaned or "")
        score_map = {frame: count_rule_hits(text, keywords) for frame, keywords in FRAME_RULES.items()}
        primary = assign_primary_frame(score_map)
        score_rows.append(
            {
                "video_id": row.video_id,
                "primary_frame": primary,
                "frame_hit_count_total": int(sum(score_map.values())),
                **{f"frame_score_{frame}": int(score) for frame, score in score_map.items()},
            }
        )

    score_df = pd.DataFrame(score_rows)
    merged_df = working_df.merge(score_df, on="video_id", how="left")

    distribution_df = (
        merged_df.groupby(["channel_name", "primary_frame"], dropna=False)
        .size()
        .rename("video_count")
        .reset_index()
    )
    distribution_df["channel_total"] = distribution_df.groupby("channel_name")["video_count"].transform("sum")
    distribution_df["frame_share_within_channel"] = distribution_df["video_count"] / distribution_df["channel_total"]
    distribution_df = distribution_df.sort_values(
        ["channel_name", "video_count", "primary_frame"], ascending=[True, False, True]
    ).reset_index(drop=True)

    return merged_df, distribution_df
