from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.io_utils import (
    ensure_directories,
    get_timestamp_utc,
    load_dataframe_if_exists,
    merge_without_duplicates,
    save_dataframe,
    setup_logger,
)
from src.youtube_client import YouTubeClient


VIDEO_BASENAME = "videos_raw"
COMMENTS_BASENAME = "comments_raw"
COMMENTS_STATUS_BASENAME = "comments_collection_status"
MAX_COMMENTS_PER_VIDEO = 100
SAVE_EVERY_VIDEOS = 25
QUOTA_EXCEEDED_TEXT = "exceeded your <a href=\"/youtube/v3/getting-started#quota\">quota</a>"
COMMENTS_DISABLED_TEXT = "disabled comments"
TERMINAL_COMMENT_STATUSES = {"collected", "no_comments", "comments_disabled"}


def build_comment_rows(comment_items: list[dict], video_id: str, collected_at: str) -> list[dict]:
    """Flatten top-level comment API data into tabular rows."""
    rows: list[dict] = []

    for item in comment_items:
        top_comment = (
            item.get("snippet", {})
            .get("topLevelComment", {})
        )
        snippet = top_comment.get("snippet", {})

        row = {
            "comment_id": top_comment.get("id", ""),
            "video_id": video_id,
            "author_display_name": snippet.get("authorDisplayName", ""),
            "author_channel_id": snippet.get("authorChannelId", {}).get("value", ""),
            "comment_text_raw": snippet.get("textDisplay", ""),
            "like_count": snippet.get("likeCount", ""),
            "published_at": snippet.get("publishedAt", ""),
            "collected_at": collected_at,
        }
        rows.append(row)

    return rows


def is_quota_exceeded_error(exc: Exception) -> bool:
    """Detect YouTube API quota exhaustion from an exception message."""
    return QUOTA_EXCEEDED_TEXT in str(exc)


def is_comments_disabled_error(exc: Exception) -> bool:
    """Detect videos where comments are disabled."""
    return COMMENTS_DISABLED_TEXT in str(exc).lower()


def upsert_status_rows(existing_df: pd.DataFrame, new_rows: list[dict]) -> pd.DataFrame:
    """Upsert status rows by video_id, keeping the newest status first."""
    if not new_rows:
        return existing_df

    new_df = pd.DataFrame(new_rows)
    if existing_df.empty:
        return new_df.drop_duplicates(subset=["video_id"], keep="first").reset_index(drop=True)

    merged = pd.concat([new_df, existing_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["video_id"], keep="first").reset_index(drop=True)
    return merged


def save_partial_comments(
    existing_df: pd.DataFrame,
    collected_rows: list[dict],
    output_format: str,
) -> pd.DataFrame:
    """Persist partial comment progress and return the merged DataFrame."""
    if not collected_rows:
        return existing_df

    new_df = pd.DataFrame(collected_rows)
    if not new_df.empty:
        new_df = new_df.drop_duplicates(subset=["comment_id"], keep="first").reset_index(drop=True)

    merged_df = merge_without_duplicates(existing_df=existing_df, new_df=new_df, subset=["comment_id"])
    save_dataframe(merged_df, PROJECT_ROOT / "data" / "raw" / COMMENTS_BASENAME, output_format)
    collected_rows.clear()
    return merged_df


def save_partial_comment_status(
    existing_status_df: pd.DataFrame,
    status_rows: list[dict],
    output_format: str,
) -> pd.DataFrame:
    """Persist per-video comment collection status."""
    if not status_rows:
        return existing_status_df

    merged_status_df = upsert_status_rows(existing_status_df, status_rows)
    save_dataframe(
        merged_status_df,
        PROJECT_ROOT / "data" / "raw" / COMMENTS_STATUS_BASENAME,
        output_format,
    )
    status_rows.clear()
    return merged_status_df


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")
    save_every_videos = int(os.getenv("COMMENTS_SAVE_EVERY_VIDEOS", str(SAVE_EVERY_VIDEOS)))

    logger = setup_logger(PROJECT_ROOT / "logs", "02_collect_comments", log_level)
    ensure_directories([PROJECT_ROOT / "data" / "raw"])

    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is missing. Please set it in .env.")

    videos_path = (PROJECT_ROOT / "data" / "raw" / VIDEO_BASENAME).with_suffix(f".{output_format}")
    videos_df = load_dataframe_if_exists(videos_path)
    if videos_df.empty:
        raise ValueError(f"No video data found at {videos_path}. Run 01_collect_videos.py first.")

    output_path = (PROJECT_ROOT / "data" / "raw" / COMMENTS_BASENAME).with_suffix(f".{output_format}")
    existing_df = load_dataframe_if_exists(output_path)
    status_path = (PROJECT_ROOT / "data" / "raw" / COMMENTS_STATUS_BASENAME).with_suffix(
        f".{output_format}"
    )
    existing_status_df = load_dataframe_if_exists(status_path)

    client = YouTubeClient(api_key=api_key)
    collected_at = get_timestamp_utc()
    collected_rows: list[dict] = []
    status_rows: list[dict] = []

    existing_video_ids_with_comments: set[str] = set()
    if not existing_df.empty and "video_id" in existing_df.columns:
        existing_video_ids_with_comments = set(existing_df["video_id"].astype(str).dropna().unique().tolist())

    completed_video_ids_from_status: set[str] = set()
    if not existing_status_df.empty and {"video_id", "status"}.issubset(existing_status_df.columns):
        completed_video_ids_from_status = set(
            existing_status_df.loc[
                existing_status_df["status"].astype(str).isin(TERMINAL_COMMENT_STATUSES),
                "video_id",
            ]
            .astype(str)
            .dropna()
            .tolist()
        )

    video_ids = [
        video_id
        for video_id in videos_df["video_id"].astype(str).dropna().unique().tolist()
        if video_id not in existing_video_ids_with_comments
        and video_id not in completed_video_ids_from_status
    ]
    logger.info("Comment collection started for %s videos", len(video_ids))

    with tqdm(total=len(video_ids), desc="Collecting comments") as progress_bar:
        for idx, video_id in enumerate(video_ids, start=1):
            try:
                relevance_comments = client.get_top_level_comments(
                    video_id=video_id,
                    max_results=MAX_COMMENTS_PER_VIDEO,
                    order="relevance",
                )
                rows = build_comment_rows(relevance_comments, video_id, collected_at)
                collected_rows.extend(rows)
                status_rows.append(
                    {
                        "video_id": video_id,
                        "status": "collected" if rows else "no_comments",
                        "comment_rows": len(rows),
                        "error_type": "",
                        "collected_at": collected_at,
                    }
                )
                logger.info("Collected %s top-level comments for video=%s", len(rows), video_id)
                if idx % save_every_videos == 0:
                    existing_df = save_partial_comments(existing_df, collected_rows, output_format)
                    existing_status_df = save_partial_comment_status(
                        existing_status_df,
                        status_rows,
                        output_format,
                    )
                    logger.info("Saved partial comment progress at %s processed videos", idx)
            except Exception as exc:
                logger.exception("Failed collecting comments for video=%s: %s", video_id, exc)
                if is_quota_exceeded_error(exc):
                    existing_df = save_partial_comments(existing_df, collected_rows, output_format)
                    existing_status_df = save_partial_comment_status(
                        existing_status_df,
                        status_rows,
                        output_format,
                    )
                    logger.warning("Stopping comment collection early due to quota exhaustion.")
                    break
                if is_comments_disabled_error(exc):
                    status_rows.append(
                        {
                            "video_id": video_id,
                            "status": "comments_disabled",
                            "comment_rows": 0,
                            "error_type": "comments_disabled",
                            "collected_at": collected_at,
                        }
                    )
            finally:
                progress_bar.update(1)

    merged_df = save_partial_comments(existing_df, collected_rows, output_format)
    save_partial_comment_status(existing_status_df, status_rows, output_format)
    final_path = save_dataframe(merged_df, PROJECT_ROOT / "data" / "raw" / COMMENTS_BASENAME, output_format)

    logger.info("Comment collection finished. Saved %s unique rows to %s", len(merged_df), final_path)
    print(f"Saved {len(merged_df)} unique comments to {final_path}")


if __name__ == "__main__":
    main()
