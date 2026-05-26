from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
import requests
import yaml
from dotenv import load_dotenv
from requests import Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_CONFIG_PATH = "config.yaml"


@dataclass(slots=True)
class RuntimePaths:
    project_root: Path
    raw_data_dir: Path


class YouTubeApiError(RuntimeError):
    """Raised when the YouTube Data API returns an error."""


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    path = Path(config_path)
    if not path.is_absolute():
        path = get_project_root() / path

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError("config.yaml must contain a YAML mapping.")

    return config


def load_api_key(env_path: str | Path | None = None) -> str:
    root = get_project_root()
    resolved_env_path = Path(env_path) if env_path else root / ".env"
    load_dotenv(resolved_env_path)

    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            f"YOUTUBE_API_KEY is missing. Expected it in {resolved_env_path}."
        )
    return api_key


def resolve_runtime_paths(config: dict[str, Any]) -> RuntimePaths:
    root = get_project_root()
    raw_dir = root / config["paths"]["raw_data_dir"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    return RuntimePaths(project_root=root, raw_data_dir=raw_dir)


def to_rfc3339_start(date_text: str) -> str:
    return f"{date_text}T00:00:00Z"


def to_rfc3339_end(date_text: str) -> str:
    end_dt = datetime.fromisoformat(date_text) + timedelta(days=1)
    return end_dt.strftime("%Y-%m-%dT00:00:00Z")


def chunked(items: list[str], size: int) -> Iterator[list[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_json(data: Any, output_path: str | Path) -> Path:
    path = Path(output_path)
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return path


def save_csv(records: list[dict[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    ensure_parent_dir(path)
    dataframe = pd.json_normalize(records)
    dataframe.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def load_json_records(input_path: str | Path) -> list[dict[str, Any]]:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of records in {path}")
    return data


class YouTubeClient:
    base_url = "https://www.googleapis.com/youtube/v3"

    def __init__(
        self,
        api_key: str,
        timeout: int = 30,
        logger: logging.Logger | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.logger = logger or setup_logger(self.__class__.__name__)
        self.session = requests.Session()

        retry = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        request_params = dict(params)
        request_params["key"] = self.api_key

        url = f"{self.base_url}/{endpoint}"
        self.logger.debug("Requesting %s with params=%s", url, request_params)

        try:
            response = self.session.get(url, params=request_params, timeout=self.timeout)
            self._raise_for_status(response)
            return response.json()
        except requests.RequestException as exc:
            raise YouTubeApiError(f"Failed request to {endpoint}: {exc}") from exc

    @staticmethod
    def _raise_for_status(response: Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            message = response.text
            raise YouTubeApiError(
                f"YouTube API returned {response.status_code}: {message}"
            ) from exc

    def search_videos(
        self,
        query: str,
        published_after: str,
        published_before: str,
        max_results: int,
        page_token: str | None = None,
        region_code: str | None = None,
        relevance_language: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "part": "snippet",
            "type": "video",
            "order": "date",
            "q": query,
            "publishedAfter": published_after,
            "publishedBefore": published_before,
            "maxResults": max_results,
        }
        if page_token:
            params["pageToken"] = page_token
        if region_code:
            params["regionCode"] = region_code
        if relevance_language:
            params["relevanceLanguage"] = relevance_language
        return self._request("search", params)

    def get_videos(self, video_ids: list[str]) -> dict[str, Any]:
        params = {
            "part": "snippet,contentDetails,statistics,status,topicDetails,liveStreamingDetails",
            "id": ",".join(video_ids),
            "maxResults": min(len(video_ids), 50),
        }
        return self._request("videos", params)

    def get_comment_threads(
        self,
        video_id: str,
        order: str,
        max_results: int,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "part": "snippet",
            "videoId": video_id,
            "order": order,
            "textFormat": "plainText",
            "maxResults": max_results,
        }
        if page_token:
            params["pageToken"] = page_token
        return self._request("commentThreads", params)
