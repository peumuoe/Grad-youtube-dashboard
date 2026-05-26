from __future__ import annotations

import re
import sys
from collections import Counter
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
    load_json_records,
    resolve_runtime_paths,
    save_csv,
    save_json,
    setup_logger,
)


LOGGER = setup_logger("collect.fetch_comments")
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
NON_WORD_PATTERN = re.compile(r"[\W_]+", re.UNICODE)
AD_PATTERN = re.compile(
    r"(카톡|오픈채팅|open chat|수익|리딩|텔레그램|구독하면|홍보|문의|010-|무료방|상담)",
    re.IGNORECASE,
)


def is_url_only(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return bool(URL_PATTERN.fullmatch(stripped))


def is_emoji_or_symbol_only(text: str) -> bool:
    cleaned = NON_WORD_PATTERN.sub("", text)
    return cleaned == ""


def normalize_comment_item(
    item: dict[str, Any],
    video_lookup: dict[str, dict[str, Any]],
    source_order: str,
) -> dict[str, Any]:
    snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
    video_id = item.get("snippet", {}).get("videoId", "")
    video_meta = video_lookup.get(video_id, {})
    return {
        "video_id": video_id,
        "comment_id": item.get("snippet", {}).get("topLevelComment", {}).get("id", ""),
        "comment_text": snippet.get("textDisplay", "").strip(),
        "author_name": snippet.get("authorDisplayName", "").strip(),
        "author_channel_id": (
            snippet.get("authorChannelId", {}) or {}
        ).get("value", ""),
        "published_at": snippet.get("publishedAt", ""),
        "updated_at": snippet.get("updatedAt", ""),
        "like_count": snippet.get("likeCount"),
        "viewer_rating": snippet.get("viewerRating", ""),
        "reply_count": item.get("snippet", {}).get("totalReplyCount", 0),
        "source_order": source_order,
        "video_title": video_meta.get("title", ""),
        "channel_id": video_meta.get("channel_id", ""),
        "channel_title": video_meta.get("channel_title", ""),
        "matched_keywords": video_meta.get("matched_keywords", []),
    }


def passes_comment_filters(record: dict[str, Any], config: dict[str, Any]) -> bool:
    rules = config.get("comment_selection", {})
    text = record.get("comment_text", "").strip()

    if len(text) < rules.get("min_comment_length", 0):
        return False
    if rules.get("remove_url_only", False) and is_url_only(text):
        return False
    if rules.get("remove_emoji_only", False) and is_emoji_or_symbol_only(text):
        return False
    if rules.get("remove_ad_comments", False) and AD_PATTERN.search(text):
        return False
    return True


def fetch_ordered_comments(
    client: YouTubeClient,
    video_id: str,
    order: str,
    target_count: int,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    page_token: str | None = None
    max_page_requests = 5

    for _ in range(max_page_requests):
        response = client.get_comment_threads(
            video_id=video_id,
            order=order,
            max_results=min(100, max(target_count, 20)),
            page_token=page_token,
        )
        items = response.get("items", [])
        if not items:
            break
        collected.extend(items)
        if len(collected) >= target_count * 2:
            break
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return collected


def merge_and_filter_comments(
    relevance_items: list[dict[str, Any]],
    time_items: list[dict[str, Any]],
    video_lookup: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    author_counter: Counter[str] = Counter()
    seen_comment_ids: set[str] = set()
    merged_records: list[dict[str, Any]] = []

    ordered_inputs = [
        ("relevance", relevance_items),
        ("time", time_items),
    ]

    for source_order, items in ordered_inputs:
        for item in items:
            record = normalize_comment_item(item, video_lookup, source_order)
            comment_id = record.get("comment_id", "")
            author_key = record.get("author_channel_id") or record.get("author_name")

            if not comment_id or comment_id in seen_comment_ids:
                continue
            if not passes_comment_filters(record, config):
                continue
            if author_counter[author_key] >= config["comment_selection"]["max_comments_per_author"]:
                continue

            seen_comment_ids.add(comment_id)
            author_counter[author_key] += 1
            merged_records.append(record)

    return merged_records


def fetch_comments(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runtime_paths = resolve_runtime_paths(config)
    api_key = load_api_key()
    client = YouTubeClient(api_key=api_key, logger=LOGGER)

    details_path = runtime_paths.raw_data_dir / "youtube_video_details.json"
    if details_path.exists():
        video_records = load_json_records(details_path)
    else:
        fallback_path = runtime_paths.raw_data_dir / "youtube_search_results.json"
        video_records = load_json_records(fallback_path)

    if not video_records:
        raise ValueError(
            "No video records found. Run search_videos.py or fetch_video_details.py first."
        )

    video_lookup = {record["video_id"]: record for record in video_records if record.get("video_id")}
    rules = config["comment_selection"]

    comment_records: list[dict[str, Any]] = []
    video_summaries: list[dict[str, Any]] = []
    failed_videos: list[dict[str, Any]] = []

    for index, video_id in enumerate(video_lookup, start=1):
        LOGGER.info("Fetching comments for %s (%s/%s)", video_id, index, len(video_lookup))
        try:
            relevance_items = fetch_ordered_comments(
                client=client,
                video_id=video_id,
                order="relevance",
                target_count=rules["max_comments_relevance"],
            )
            time_items = fetch_ordered_comments(
                client=client,
                video_id=video_id,
                order="time",
                target_count=rules["max_comments_time"],
            )
        except YouTubeApiError as exc:
            LOGGER.warning("Comments unavailable for video_id=%s: %s", video_id, exc)
            failed_videos.append({"video_id": video_id, "error": str(exc)})
            continue

        merged = merge_and_filter_comments(
            relevance_items=relevance_items[: rules["max_comments_relevance"]],
            time_items=time_items[: rules["max_comments_time"]],
            video_lookup=video_lookup,
            config=config,
        )
        comment_records.extend(merged)
        video_summaries.append(
            {
                "video_id": video_id,
                "relevance_fetched": len(relevance_items),
                "time_fetched": len(time_items),
                "merged_comment_count": len(merged),
            }
        )

    summary = {
        "video_count": len(video_lookup),
        "comment_count": len(comment_records),
        "failed_video_count": len(failed_videos),
        "failed_videos": failed_videos,
        "video_summaries": video_summaries,
    }

    output_json = runtime_paths.raw_data_dir / "youtube_comments.json"
    output_csv = runtime_paths.raw_data_dir / "youtube_comments.csv"
    summary_json = runtime_paths.raw_data_dir / "youtube_comments_summary.json"

    save_json(comment_records, output_json)
    save_csv(comment_records, output_csv)
    save_json(summary, summary_json)

    LOGGER.info("Saved %s comments to %s", len(comment_records), output_json)
    return comment_records, summary


def main() -> None:
    try:
        config = load_config()
        fetch_comments(config)
    except Exception as exc:
        LOGGER.exception("fetch_comments.py failed: %s", exc)
        raise


if __name__ == "__main__":
    main()
