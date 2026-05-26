from __future__ import annotations

import pandas as pd


def build_topic_input(df: pd.DataFrame) -> pd.DataFrame:
    """Build a topic-analysis input table from stage2 rows."""
    topic_df = df.loc[df["title_desc_use_flag"] == 1].copy()
    topic_df["topic_text"] = topic_df["topic_input_text"].fillna("").astype(str).str.strip()
    topic_df["topic_text_char_count"] = topic_df["topic_text"].str.len()
    topic_df["topic_source_type"] = "title_description"
    keep_columns = [
        "video_id",
        "channel_id",
        "channel_name",
        "channel_type",
        "search_keyword",
        "published_at",
        "title",
        "description",
        "topic_text",
        "topic_text_char_count",
        "topic_source_type",
        "analysis_stage2_note",
    ]
    return topic_df[keep_columns].reset_index(drop=True)


def build_topic_input_from_transcript(df: pd.DataFrame) -> pd.DataFrame:
    """Build a transcript-first topic-analysis input table from stage2 rows."""
    topic_df = df.loc[df["transcript_use_flag"] == 1].copy()
    topic_df["topic_text"] = topic_df["transcript_input_text"].fillna("").astype(str).str.strip()
    topic_df["topic_text_char_count"] = topic_df["topic_text"].str.len()
    topic_df = topic_df.loc[topic_df["topic_text_char_count"] >= 30].copy()
    topic_df["topic_source_type"] = "transcript"
    keep_columns = [
        "video_id",
        "channel_id",
        "channel_name",
        "channel_type",
        "search_keyword",
        "published_at",
        "title",
        "description",
        "topic_text",
        "topic_text_char_count",
        "topic_source_type",
        "analysis_stage2_note",
    ]
    return topic_df[keep_columns].reset_index(drop=True)


def build_frame_input(df: pd.DataFrame) -> pd.DataFrame:
    """Build a frame-analysis input table from stage2 rows."""
    frame_df = df.loc[df["title_desc_use_flag"] == 1].copy()
    frame_df["frame_text"] = frame_df["frame_input_text"].fillna("").astype(str).str.strip()
    frame_df["frame_text_char_count"] = frame_df["frame_text"].str.len()
    frame_df["frame_source_type"] = "title_description"
    frame_df.loc[frame_df["transcript_use_flag"] == 1, "frame_source_type"] = "title_description_plus_transcript"
    keep_columns = [
        "video_id",
        "channel_id",
        "channel_name",
        "channel_type",
        "search_keyword",
        "published_at",
        "title",
        "frame_text",
        "frame_text_char_count",
        "frame_source_type",
        "transcript_use_flag",
        "analysis_stage2_note",
    ]
    return frame_df[keep_columns].reset_index(drop=True)


def build_audience_video_input(df: pd.DataFrame) -> pd.DataFrame:
    """Build a video-level audience input table from stage2 rows."""
    audience_df = df.loc[df["comments_use_flag"] == 1].copy()
    audience_df["audience_text"] = audience_df["audience_input_text"].fillna("").astype(str).str.strip()
    audience_df["audience_text_char_count"] = audience_df["audience_text"].str.len()
    keep_columns = [
        "video_id",
        "channel_id",
        "channel_name",
        "channel_type",
        "search_keyword",
        "published_at",
        "title",
        "comment_count_candidate",
        "comment_count_selected",
        "comment_excluded_short",
        "comment_excluded_url_only",
        "comment_excluded_repetitive",
        "comment_excluded_author_cap",
        "comments_filter_note",
        "audience_text",
        "audience_text_char_count",
    ]
    return audience_df[keep_columns].reset_index(drop=True)


def build_audience_comment_input(
    filtered_comments_df: pd.DataFrame,
    stage2_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build a comment-level audience input table using filtered comment rows."""
    if filtered_comments_df.empty:
        return pd.DataFrame(
            columns=[
                "comment_id",
                "video_id",
                "channel_id",
                "channel_name",
                "channel_type",
                "search_keyword",
                "published_at",
                "author_display_name",
                "author_channel_id",
                "comment_like_count",
                "comment_text_clean",
                "comment_text_char_count",
                "comment_selected_flag",
                "comment_filter_reason",
            ]
        )

    video_meta_df = stage2_df[
        [
            "video_id",
            "channel_id",
            "channel_name",
            "channel_type",
            "search_keyword",
            "title",
        ]
    ].drop_duplicates(subset=["video_id"], keep="first")

    comment_df = filtered_comments_df.copy()
    comment_df = comment_df.loc[comment_df["comment_selected_flag"] == 1].copy()
    comment_df["comment_text_char_count"] = (
        comment_df["comment_text_clean"].fillna("").astype(str).str.len()
    )
    comment_df = comment_df.merge(video_meta_df, on="video_id", how="left")

    keep_columns = [
        "comment_id",
        "video_id",
        "channel_id",
        "channel_name",
        "channel_type",
        "search_keyword",
        "title",
        "published_at",
        "author_display_name",
        "author_channel_id",
        "comment_like_count",
        "comment_text_clean",
        "comment_text_char_count",
        "comment_selected_flag",
        "comment_filter_reason",
    ]
    return comment_df[keep_columns].reset_index(drop=True)
