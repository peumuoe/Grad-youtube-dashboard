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

from src.config_loader import load_channels, load_keywords
from src.io_utils import (
    ensure_directories,
    get_timestamp_utc,
    load_dataframe_if_exists,
    merge_without_duplicates,
    save_dataframe,
    setup_logger,
)
from src.youtube_client import YouTubeClient, parse_iso8601_duration


START_DATE = "2026-03-01T00:00:00Z"
END_DATE = "2026-03-22T00:00:00Z"
OUTPUT_BASENAME = "videos_raw"
STATUS_BASENAME = "video_collection_status"


def build_video_rows(
    search_items: list[dict],
    video_details_map: dict[str, dict],
    channel_name: str,
    channel_type: str,
    keyword: str,
    collected_at: str,
) -> list[dict]:
    """Convert API responses into flat rows for storage."""
    rows: list[dict] = []

    for item in search_items:
        video_id = item.get("id", {}).get("videoId", "")
        if not video_id:
            continue

        detail = video_details_map.get(video_id, {})
        snippet = detail.get("snippet", {})
        statistics = detail.get("statistics", {})
        content_details = detail.get("contentDetails", {})

        row = {
            "video_id": video_id,
            "channel_id": snippet.get("channelId") or item.get("snippet", {}).get("channelId", ""),
            "channel_name": snippet.get("channelTitle") or channel_name,
            "channel_type": channel_type,
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "published_at": snippet.get("publishedAt", ""),
            "view_count": statistics.get("viewCount", ""),
            "like_count": statistics.get("likeCount", ""),
            "comment_count": statistics.get("commentCount", ""),
            "duration": parse_iso8601_duration(content_details.get("duration", "")),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "search_keyword": keyword,
            "collected_at": collected_at,
        }
        rows.append(row)

    return rows


def build_task_key(channel_name: str, keyword: str) -> str:
    """Build a stable key for one channel-keyword collection task."""
    return f"{channel_name}|||{keyword}"


def load_status_dataframe(status_path: Path) -> pd.DataFrame:
    """Load status data and return a normalized schema."""
    status_df = load_dataframe_if_exists(status_path)
    if status_df.empty:
        return pd.DataFrame(
            columns=[
                "channel_name",
                "channel_type",
                "channel_id",
                "search_keyword",
                "status",
                "collected_rows",
                "last_collected_at",
                "note",
            ]
        )

    for column in [
        "channel_name",
        "channel_type",
        "channel_id",
        "search_keyword",
        "status",
        "collected_rows",
        "last_collected_at",
        "note",
    ]:
        if column not in status_df.columns:
            status_df[column] = ""

    return status_df


def get_success_task_keys(status_df: pd.DataFrame) -> set[str]:
    """Return task keys that were already collected successfully."""
    if status_df.empty:
        return set()

    success_df = status_df[status_df["status"].astype(str).str.lower() == "success"].copy()
    return {
        build_task_key(str(row.channel_name), str(row.search_keyword))
        for row in success_df.itertuples(index=False)
    }


def upsert_status_row(
    status_df: pd.DataFrame,
    row_data: dict,
) -> pd.DataFrame:
    """Insert or update one collection task status row."""
    mask = (
        status_df["channel_name"].astype(str).eq(str(row_data["channel_name"]))
        & status_df["search_keyword"].astype(str).eq(str(row_data["search_keyword"]))
    )

    if mask.any():
        for key, value in row_data.items():
            status_df.loc[mask, key] = value
        return status_df.reset_index(drop=True)

    return pd.concat([status_df, pd.DataFrame([row_data])], ignore_index=True)


def bootstrap_status_from_existing_videos(
    status_df: pd.DataFrame,
    existing_df: pd.DataFrame,
    collected_at: str,
) -> pd.DataFrame:
    """Seed successful task status from an existing videos file when no status file exists yet."""
    if not status_df.empty or existing_df.empty:
        return status_df

    required_columns = {"channel_name", "channel_type", "channel_id", "search_keyword"}
    if not required_columns.issubset(existing_df.columns):
        return status_df

    grouped_df = (
        existing_df.groupby(
            ["channel_name", "channel_type", "channel_id", "search_keyword"],
            dropna=False,
        )
        .size()
        .reset_index(name="collected_rows")
    )
    grouped_df["status"] = "success"
    grouped_df["last_collected_at"] = collected_at
    grouped_df["note"] = "bootstrapped_from_existing_videos"
    return grouped_df[
        [
            "channel_name",
            "channel_type",
            "channel_id",
            "search_keyword",
            "status",
            "collected_rows",
            "last_collected_at",
            "note",
        ]
    ].copy()


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logger = setup_logger(PROJECT_ROOT / "logs", "01_collect_videos", log_level)
    ensure_directories([PROJECT_ROOT / "data" / "raw"])

    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is missing. Please set it in .env.")

    channels_df = load_channels(PROJECT_ROOT / "config")
    keywords_df = load_keywords(PROJECT_ROOT / "config")

    blank_channel_ids = channels_df["channel_id"].astype(str).str.strip() == ""
    if blank_channel_ids.any():
        missing_names = channels_df.loc[blank_channel_ids, "channel_name"].tolist()
        raise ValueError(
            "Some channel_id values are empty in config/channels_master.csv: "
            + ", ".join(missing_names)
        )

    output_path = (PROJECT_ROOT / "data" / "raw" / OUTPUT_BASENAME).with_suffix(f".{output_format}")
    status_path = (PROJECT_ROOT / "data" / "raw" / STATUS_BASENAME).with_suffix(f".{output_format}")
    existing_df = load_dataframe_if_exists(output_path)
    collected_at = get_timestamp_utc()
    status_df = load_status_dataframe(status_path)
    status_df = bootstrap_status_from_existing_videos(status_df, existing_df, collected_at)
    success_task_keys = get_success_task_keys(status_df)

    client = YouTubeClient(api_key=api_key)
    collected_rows: list[dict] = []

    total_tasks = len(channels_df) * len(keywords_df)
    logger.info("Video collection started: %s channels x %s keywords", len(channels_df), len(keywords_df))
    logger.info("Skipping %s previously successful channel-keyword tasks", len(success_task_keys))

    with tqdm(total=total_tasks, desc="Collecting videos") as progress_bar:
        for channel_row in channels_df.itertuples(index=False):
            for keyword_row in keywords_df.itertuples(index=False):
                task_key = build_task_key(channel_row.channel_name, keyword_row.keyword)
                if task_key in success_task_keys:
                    logger.info(
                        "Skipped already collected task for channel=%s keyword=%s",
                        channel_row.channel_name,
                        keyword_row.keyword,
                    )
                    progress_bar.update(1)
                    continue

                try:
                    search_items = client.search_videos(
                        channel_id=channel_row.channel_id,
                        query=keyword_row.keyword,
                        published_after=START_DATE,
                        published_before=END_DATE,
                    )

                    video_ids = list(
                        {
                            item.get("id", {}).get("videoId", "")
                            for item in search_items
                            if item.get("id", {}).get("videoId", "")
                        }
                    )
                    video_details = client.get_video_details(video_ids) if video_ids else []
                    details_map = {item["id"]: item for item in video_details if item.get("id")}

                    rows = build_video_rows(
                        search_items=search_items,
                        video_details_map=details_map,
                        channel_name=channel_row.channel_name,
                        channel_type=channel_row.channel_type,
                        keyword=keyword_row.keyword,
                        collected_at=collected_at,
                    )
                    collected_rows.extend(rows)

                    logger.info(
                        "Collected %s rows for channel=%s keyword=%s",
                        len(rows),
                        channel_row.channel_name,
                        keyword_row.keyword,
                    )

                    status_df = upsert_status_row(
                        status_df=status_df,
                        row_data={
                            "channel_name": channel_row.channel_name,
                            "channel_type": channel_row.channel_type,
                            "channel_id": channel_row.channel_id,
                            "search_keyword": keyword_row.keyword,
                            "status": "success",
                            "collected_rows": len(rows),
                            "last_collected_at": collected_at,
                            "note": "",
                        },
                    )
                    success_task_keys.add(task_key)
                    save_dataframe(status_df, PROJECT_ROOT / "data" / "raw" / STATUS_BASENAME, output_format)
                except Exception as exc:
                    logger.exception(
                        "Failed collecting videos for channel=%s keyword=%s: %s",
                        channel_row.channel_name,
                        keyword_row.keyword,
                        exc,
                    )
                    status_df = upsert_status_row(
                        status_df=status_df,
                        row_data={
                            "channel_name": channel_row.channel_name,
                            "channel_type": channel_row.channel_type,
                            "channel_id": channel_row.channel_id,
                            "search_keyword": keyword_row.keyword,
                            "status": "failed",
                            "collected_rows": "",
                            "last_collected_at": collected_at,
                            "note": str(exc),
                        },
                    )
                    save_dataframe(status_df, PROJECT_ROOT / "data" / "raw" / STATUS_BASENAME, output_format)
                finally:
                    progress_bar.update(1)

    new_df = pd.DataFrame(collected_rows)
    if not new_df.empty:
        new_df = new_df.drop_duplicates(subset=["video_id"], keep="first").reset_index(drop=True)

    merged_df = merge_without_duplicates(existing_df=existing_df, new_df=new_df, subset=["video_id"])
    final_path = save_dataframe(merged_df, PROJECT_ROOT / "data" / "raw" / OUTPUT_BASENAME, output_format)
    status_final_path = save_dataframe(status_df, PROJECT_ROOT / "data" / "raw" / STATUS_BASENAME, output_format)

    logger.info("Video collection finished. Saved %s unique rows to %s", len(merged_df), final_path)
    logger.info("Saved collection status rows to %s", status_final_path)
    print(f"Saved {len(merged_df)} unique videos to {final_path}")


if __name__ == "__main__":
    main()
