from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from src.collect.youtube_client import (
    YouTubeApiError,
    YouTubeClient,
    load_api_key,
    load_config,
    resolve_runtime_paths,
    save_csv,
    save_json,
    setup_logger,
    to_rfc3339_end,
    to_rfc3339_start,
)


LOGGER = setup_logger("collect.search_videos")


def build_query(keyword: str, exclusions: list[str]) -> str:
    exclusion_expr = " ".join(f'-"{term}"' for term in exclusions)
    return f"{keyword} {exclusion_expr}".strip()


def contains_any(text: str, keywords: list[str]) -> bool:
    normalized = text.casefold()
    return any(keyword.casefold() in normalized for keyword in keywords)


def passes_channel_filter(channel_title: str, config: dict[str, Any]) -> bool:
    channel_filter = config.get("channel_filter", {})
    include_keywords = channel_filter.get("include_keywords", [])
    exclude_keywords = channel_filter.get("exclude_keywords", [])

    if exclude_keywords and contains_any(channel_title, exclude_keywords):
        return False
    if include_keywords and not contains_any(channel_title, include_keywords):
        return False
    return True


def passes_video_filter(title: str, description: str, config: dict[str, Any]) -> bool:
    combined = " ".join([title, description])
    keyword_config = config.get("keywords", {})
    video_filter = config.get("video_filter", {})

    if contains_any(combined, keyword_config.get("exclusion", [])):
        return False
    if contains_any(combined, video_filter.get("exclude_keywords", [])):
        return False
    return True


def normalize_search_item(item: dict[str, Any], keyword: str, query: str) -> dict[str, Any]:
    snippet = item.get("snippet", {})
    video_id = item.get("id", {}).get("videoId")
    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "published_at": snippet.get("publishedAt", ""),
        "channel_id": snippet.get("channelId", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "search_keyword": keyword,
        "search_query": query,
        "thumbnails": snippet.get("thumbnails", {}),
    }


def collect_search_results(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_key = load_api_key()
    client = YouTubeClient(api_key=api_key, logger=LOGGER)
    youtube_config = config["youtube"]
    runtime_paths = resolve_runtime_paths(config)

    primary = config.get("keywords", {}).get("primary", [])
    secondary = config.get("keywords", {}).get("secondary", [])
    exclusions = config.get("keywords", {}).get("exclusion", [])
    search_keywords = primary + secondary

    published_after = to_rfc3339_start(config["date_range"]["start_date"])
    published_before = to_rfc3339_end(config["date_range"]["end_date"])

    deduped_records: dict[str, dict[str, Any]] = {}
    matched_keywords: dict[str, set[str]] = defaultdict(set)
    raw_items: list[dict[str, Any]] = []
    skipped_channel = 0
    skipped_video = 0
    total_api_items = 0

    for keyword in search_keywords:
        page_token: str | None = None
        query = build_query(keyword, exclusions)
        LOGGER.info("Searching keyword='%s'", keyword)

        for page_index in range(youtube_config["max_search_pages_per_keyword"]):
            try:
                response = client.search_videos(
                    query=query,
                    published_after=published_after,
                    published_before=published_before,
                    max_results=youtube_config["max_results_per_page"],
                    page_token=page_token,
                    region_code=config.get("region_code"),
                    relevance_language=config.get("language"),
                )
            except YouTubeApiError as exc:
                LOGGER.exception("Search failed for keyword '%s': %s", keyword, exc)
                break

            items = response.get("items", [])
            total_api_items += len(items)
            if not items:
                LOGGER.info("No results for keyword='%s' page=%s", keyword, page_index + 1)
                break

            for item in items:
                record = normalize_search_item(item, keyword, query)
                if not record["video_id"]:
                    continue
                if not passes_channel_filter(record["channel_title"], config):
                    skipped_channel += 1
                    continue
                if not passes_video_filter(record["title"], record["description"], config):
                    skipped_video += 1
                    continue

                raw_items.append(record)
                matched_keywords[record["video_id"]].add(keyword)

                if record["video_id"] not in deduped_records:
                    deduped_records[record["video_id"]] = record

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    final_records: list[dict[str, Any]] = []
    for video_id, record in deduped_records.items():
        merged_record = dict(record)
        merged_record["matched_keywords"] = sorted(matched_keywords[video_id])
        merged_record["keyword_count"] = len(merged_record["matched_keywords"])
        final_records.append(merged_record)

    final_records.sort(key=lambda item: item.get("published_at", ""), reverse=True)

    summary = {
        "search_keywords": search_keywords,
        "published_after": published_after,
        "published_before": published_before,
        "raw_item_count": len(raw_items),
        "unique_video_count": len(final_records),
        "api_item_count": total_api_items,
        "skipped_channel_count": skipped_channel,
        "skipped_video_count": skipped_video,
    }

    output_json = runtime_paths.raw_data_dir / "youtube_search_results.json"
    output_csv = runtime_paths.raw_data_dir / "youtube_search_results.csv"
    summary_json = runtime_paths.raw_data_dir / "youtube_search_summary.json"

    save_json(final_records, output_json)
    save_csv(final_records, output_csv)
    save_json(summary, summary_json)

    LOGGER.info("Saved %s unique videos to %s", len(final_records), output_json)
    return final_records, summary


def main() -> None:
    try:
        config = load_config()
        collect_search_results(config)
    except Exception as exc:
        LOGGER.exception("search_videos.py failed: %s", exc)
        raise


if __name__ == "__main__":
    main()
