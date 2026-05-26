from __future__ import annotations

from typing import Any

import pandas as pd


REACTION_RULES: dict[str, list[str]] = {
    "비판/분노": [
        "최악",
        "문제",
        "미친",
        "망하",
        "짜증",
        "분노",
        "화난",
        "역겹",
        "양아치",
        "악마",
        "전범",
        "탄핵",
        "규탄",
        "책임",
        "큰 잘못",
        "싫다",
        "나쁘",
    ],
    "불안/공포": [
        "걱정",
        "불안",
        "무섭",
        "큰일",
        "위기",
        "재앙",
        "위험",
        "불안하다",
        "걱정된다",
        "어쩌나",
        "패닉",
        "망할까",
        "공포",
        "불안정",
        "두렵",
    ],
    "지지/응원": [
        "응원",
        "힘내",
        "화이팅",
        "파이팅",
        "지지",
        "찬성",
        "잘한다",
        "잘했",
        "믿는다",
        "가즈아",
        "옳다",
        "든든",
        "훌륭",
        "멋지",
    ],
    "조롱/냉소": [
        "ㅋㅋ",
        "ㅎㅎ",
        "어이없",
        "코미디",
        "개그",
        "웃기",
        "헛소리",
        "실화냐",
        "꿀잼",
        "비웃",
        "레전드",
        "웃프",
        "황당",
        "허언",
    ],
    "정보보완/해설": [
        "왜냐",
        "때문",
        "즉",
        "결국",
        "사실상",
        "한마디로",
        "정리하면",
        "배경",
        "맥락",
        "분석",
        "설명",
        "가능성",
        "전략",
        "협상",
        "파병",
        "원유",
        "가스",
        "관세",
        "해협",
    ],
}

REACTION_ORDER = [
    "비판/분노",
    "불안/공포",
    "지지/응원",
    "조롱/냉소",
    "정보보완/해설",
    "기타/혼합",
]


def count_rule_hits(text: str, keywords: list[str]) -> int:
    """Count simple substring hits for one audience-reaction rule."""
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered)


def build_reaction_scores(text: str, char_count: int) -> dict[str, int]:
    """Build a score map with a few lightweight heuristics for long explanatory comments."""
    score_map = {reaction: count_rule_hits(text, keywords) for reaction, keywords in REACTION_RULES.items()}

    if char_count >= 120:
        score_map["정보보완/해설"] += 1
    if text.count(".") >= 3 or text.count("..") >= 2:
        score_map["정보보완/해설"] += 1
    if "?" in text or "왜" in text:
        score_map["정보보완/해설"] += 1
    if text.count("!") >= 2:
        score_map["비판/분노"] += 1
    return score_map


def assign_primary_reaction(score_map: dict[str, int]) -> str:
    """Assign a conservative audience-reaction label with tie fallback."""
    positive = {reaction: score for reaction, score in score_map.items() if score > 0}
    if not positive:
        return "기타/혼합"

    top_score = max(positive.values())
    top_reactions = [reaction for reaction, score in positive.items() if score == top_score]
    if len(top_reactions) >= 2:
        return "기타/혼합"
    return top_reactions[0]


def classify_audience_reactions(
    comment_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Classify audience comments and aggregate them to video/channel summaries."""
    working_df = comment_df.copy()
    working_df["comment_text_clean"] = working_df["comment_text_clean"].fillna("").astype(str).str.strip()
    working_df["comment_text_char_count"] = working_df["comment_text_char_count"].fillna(0).astype(int)
    working_df = working_df[working_df["comment_selected_flag"].fillna(0).astype(int) == 1].copy()

    score_rows: list[dict[str, Any]] = []
    for row in working_df.itertuples(index=False):
        text = str(row.comment_text_clean or "")
        score_map = build_reaction_scores(text, int(getattr(row, "comment_text_char_count", 0) or 0))
        primary = assign_primary_reaction(score_map)
        score_values = sorted(score_map.values(), reverse=True)
        top_margin = score_values[0] - score_values[1] if len(score_values) >= 2 else score_values[0]

        score_rows.append(
            {
                "comment_id": row.comment_id,
                "primary_reaction": primary,
                "reaction_hit_count_total": int(sum(score_map.values())),
                "reaction_score_margin": int(top_margin),
                "reaction_uncertainty_score": int((1 if primary == "기타/혼합" else 0) + (1 if top_margin <= 1 else 0)),
                **{f"reaction_score_{reaction}": int(score) for reaction, score in score_map.items()},
            }
        )

    score_df = pd.DataFrame(score_rows)
    classified_df = working_df.merge(score_df, on="comment_id", how="left")

    video_reaction_counts = (
        classified_df.groupby(
            ["video_id", "channel_name", "channel_type", "published_at", "title", "primary_reaction"],
            dropna=False,
        )
        .agg(
            comment_count=("comment_id", "count"),
            comment_like_sum=("comment_like_count", "sum"),
        )
        .reset_index()
    )
    video_reaction_counts["video_total_comments"] = video_reaction_counts.groupby("video_id")["comment_count"].transform("sum")
    video_reaction_counts["reaction_share_within_video"] = (
        video_reaction_counts["comment_count"] / video_reaction_counts["video_total_comments"]
    )

    dominant_video_reaction_df = (
        video_reaction_counts.sort_values(
            ["video_id", "comment_count", "comment_like_sum", "primary_reaction"],
            ascending=[True, False, False, True],
        )
        .groupby("video_id", as_index=False)
        .first()
        .rename(
            columns={
                "primary_reaction": "dominant_reaction",
                "comment_count": "dominant_reaction_comment_count",
                "comment_like_sum": "dominant_reaction_like_sum",
                "reaction_share_within_video": "dominant_reaction_share",
                "video_total_comments": "selected_comment_count",
            }
        )
    )

    channel_distribution_df = (
        classified_df.groupby(["channel_name", "primary_reaction"], dropna=False)
        .agg(
            comment_count=("comment_id", "count"),
            comment_like_sum=("comment_like_count", "sum"),
        )
        .reset_index()
    )
    channel_distribution_df["channel_total_comments"] = channel_distribution_df.groupby("channel_name")["comment_count"].transform("sum")
    channel_distribution_df["reaction_share_within_channel"] = (
        channel_distribution_df["comment_count"] / channel_distribution_df["channel_total_comments"]
    )
    channel_distribution_df = channel_distribution_df.sort_values(
        ["channel_name", "comment_count", "primary_reaction"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    validation_df = build_audience_validation_sample(classified_df)
    return classified_df, dominant_video_reaction_df, channel_distribution_df, validation_df


def build_audience_validation_sample(classified_df: pd.DataFrame, sample_size: int = 120) -> pd.DataFrame:
    """Sample uncertain audience reactions for manual review."""
    working_df = classified_df.copy()
    working_df["reaction_review_priority"] = 0
    working_df.loc[working_df["primary_reaction"] == "기타/혼합", "reaction_review_priority"] += 3
    working_df.loc[working_df["reaction_hit_count_total"].fillna(0).astype(float) <= 1, "reaction_review_priority"] += 2
    working_df.loc[working_df["reaction_score_margin"].fillna(0).astype(float) <= 1, "reaction_review_priority"] += 1
    working_df.loc[working_df["comment_text_char_count"].fillna(0).astype(float) >= 180, "reaction_review_priority"] += 1

    sampled_df = (
        working_df.sort_values(
            ["reaction_review_priority", "reaction_hit_count_total", "comment_text_char_count"],
            ascending=[False, True, False],
            kind="stable",
        )
        .head(sample_size)
        .copy()
    )
    sampled_df["manual_reaction_label"] = ""
    sampled_df["manual_reaction_keep"] = 1
    sampled_df["manual_reaction_notes"] = ""

    keep_columns = [
        "comment_id",
        "video_id",
        "channel_name",
        "channel_type",
        "published_at",
        "title",
        "comment_like_count",
        "comment_text_clean",
        "primary_reaction",
        "reaction_hit_count_total",
        "reaction_score_margin",
        "reaction_uncertainty_score",
        "reaction_review_priority",
        "manual_reaction_label",
        "manual_reaction_keep",
        "manual_reaction_notes",
    ]
    return sampled_df[keep_columns].reset_index(drop=True)
