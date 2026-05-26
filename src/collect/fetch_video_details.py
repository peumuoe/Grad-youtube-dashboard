from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from src.collect.youtube_client import (
    YouTubeApiError,
    YouTubeClient,
    chunked,
    load_api_key,
    load_config,
    load_json_records,
    resolve_runtime_paths,
    save_csv,
    save_json,
    setup_logger,
)


LOGGER = setup_logger("collect.fetch_video_details")


def normalize_video_item(
    item: dict[str, Any],
    search_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    content_details = item.get("contentDetails", {})
    status = item.get("status", {})
    topic_details = item.get("topicDetails", {})
    live_details = item.get("liveStreamingDetails", {})
    search_record = search_lookup.get(item.get("id", ""), {})

    return {
        "video_id": item.get("id", ""),
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "published_at": snippet.get("publishedAt", ""),
        "channel_id": snippet.get("channelId", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "default_language": snippet.get("defaultLanguage", ""),
        "default_audio_language": snippet.get("defaultAudioLanguage", ""),
        "tags": snippet.get("tags", []),
        "category_id": snippet.get("categoryId", ""),
        "duration": content_details.get("duration", ""),
        "definition": content_details.get("definition", ""),
        "caption": content_details.get("caption", ""),
        "licensed_content": content_details.get("licensedContent"),
        "view_count": statistics.get("viewCount"),
        "like_count": statistics.get("likeCount"),
        "favorite_count": statistics.get("favoriteCount"),
        "comment_count": statistics.get("commentCount"),
        "privacy_status": status.get("privacyStatus", ""),
        "upload_status": status.get("uploadStatus", ""),
        "embeddable": status.get("embeddable"),
        "topic_categories": topic_details.get("topicCategories", []),
        "actual_start_time": live_details.get("actualStartTime", ""),
        "actual_end_time": live_details.get("actualEndTime", ""),
        "matched_keywords": search_record.get("matched_keywords", []),
        "keyword_count": search_record.get("keyword_count", 0),
        "search_query": search_record.get("search_query", ""),
    }


def fetch_video_details(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runtime_paths = resolve_runtime_paths(config)
    api_key = load_api_key()
    client = YouTubeClient(api_key=api_key, logger=LOGGER)

    search_path = runtime_paths.raw_data_dir / "youtube_search_results.json"
    search_records = load_json_records(search_path)
    if not search_records:
        raise ValueError(
            "youtube_search_results.json is empty. Run search_videos.py first."
        )

    unique_video_ids = sorted(
        {record["video_id"] for record in search_records if record.get("video_id")}
    )
    search_lookup = {record["video_id"]: record for record in search_records}

    LOGGER.info("Fetching details for %s videos", len(unique_video_ids))

    detail_records: list[dict[str, Any]] = []
    failed_batches: list[dict[str, Any]] = []

    for batch_index, video_id_batch in enumerate(chunked(unique_video_ids, 50), start=1):
        try:
            response = client.get_videos(video_id_batch)
        except YouTubeApiError as exc:
            LOGGER.exception("videos.list failed for batch %s: %s", batch_index, exc)
            failed_batches.append(
                {
                    "batch_index": batch_index,
                    "video_ids": video_id_batch,
                    "error": str(exc),
                }
            )
            continue

        for item in response.get("items", []):
            detail_records.append(normalize_video_item(item, search_lookup))

    detail_records.sort(key=lambda item: item.get("published_at", ""), reverse=True)

    summary = {
        "requested_video_count": len(unique_video_ids),
        "fetched_video_count": len(detail_records),
        "failed_batch_count": len(failed_batches),
        "failed_batches": failed_batches,
    }

    output_json = runtime_paths.raw_data_dir / "youtube_video_details.json"
    output_csv = runtime_paths.raw_data_dir / "youtube_video_details.csv"
    summary_json = runtime_paths.raw_data_dir / "youtube_video_details_summary.json"

    save_json(detail_records, output_json)
    save_csv(detail_records, output_csv)
    save_json(summary, summary_json)

    LOGGER.info("Saved %s video detail rows to %s", len(detail_records), output_json)
    return detail_records, summary


def main() -> None:
    try:
        config = load_config()
        fetch_video_details(config)
    except Exception as exc:
        LOGGER.exception("fetch_video_details.py failed: %s", exc)
        raise


if __name__ == "__main__":
    main()
