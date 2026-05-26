from __future__ import annotations

import time
from typing import Any

import requests


class YouTubeClient:
    """Small wrapper around the YouTube Data API v3."""

    base_url = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str, timeout: int = 30, sleep_seconds: float = 0.1) -> None:
        if not api_key:
            raise ValueError("YouTube API key is required.")
        self.api_key = api_key
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds
        self.session = requests.Session()

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a GET request and return JSON data with basic error handling."""
        request_params = {"key": self.api_key, **params}
        response = self.session.get(
            f"{self.base_url}/{endpoint}",
            params=request_params,
            timeout=self.timeout,
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = ""
            try:
                detail = response.json().get("error", {}).get("message", "")
            except ValueError:
                detail = response.text
            raise requests.HTTPError(f"{exc}. API detail: {detail}") from exc

        time.sleep(self.sleep_seconds)
        return response.json()

    def search_videos(
        self,
        channel_id: str,
        query: str,
        published_after: str,
        published_before: str,
        max_results_per_page: int = 50,
    ) -> list[dict[str, Any]]:
        """Search videos within one channel and period."""
        items: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "part": "snippet",
                "type": "video",
                "order": "date",
                "channelId": channel_id,
                "q": query,
                "publishedAfter": published_after,
                "publishedBefore": published_before,
                "maxResults": max_results_per_page,
            }
            if page_token:
                params["pageToken"] = page_token

            data = self._request("search", params)
            items.extend(data.get("items", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return items

    def get_video_details(self, video_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch details for up to 50 video IDs per request."""
        details: list[dict[str, Any]] = []
        chunk_size = 50

        for start in range(0, len(video_ids), chunk_size):
            batch = video_ids[start : start + chunk_size]
            data = self._request(
                "videos",
                {
                    "part": "snippet,contentDetails,statistics",
                    "id": ",".join(batch),
                    "maxResults": len(batch),
                },
            )
            details.extend(data.get("items", []))

        return details

    def get_top_level_comments(
        self,
        video_id: str,
        max_results: int = 100,
        order: str = "relevance",
    ) -> list[dict[str, Any]]:
        """Fetch top-level comments for one video."""
        comments: list[dict[str, Any]] = []
        page_token: str | None = None
        remaining = max_results

        while remaining > 0:
            batch_size = min(100, remaining)
            params: dict[str, Any] = {
                "part": "snippet",
                "videoId": video_id,
                "textFormat": "plainText",
                "order": order,
                "maxResults": batch_size,
            }
            if page_token:
                params["pageToken"] = page_token

            data = self._request("commentThreads", params)
            comments.extend(data.get("items", []))
            remaining -= len(data.get("items", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return comments


def parse_iso8601_duration(duration: str) -> str:
    """Keep the original ISO 8601 duration string for downstream parsing."""
    return duration or ""
