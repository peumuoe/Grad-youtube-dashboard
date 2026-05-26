from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi
from yt_dlp import YoutubeDL
from src.text_cleaner import normalize_transcript_text

@dataclass
class TranscriptFetchResult:
    """Normalized transcript payload for downstream storage."""

    transcript_source: str
    transcript_text_raw: str
    transcript_text_clean: str
    transcript_quality: str
    stt_applied: int
    transcript_language_code: str
    transcript_language: str
    transcript_is_generated: int
    transcript_segment_count: int
    transcript_error: str


class TranscriptClient:
    """Wrapper around youtube-transcript-api for public caption retrieval."""

    def __init__(
        self,
        project_root: Path | None = None,
        use_ytdlp_fallback: bool = False,
        cookies_from_browser: str = "",
        cookiefile: str = "",
        prefer_ytdlp_when_authenticated: bool = False,
    ) -> None:
        self.client = YouTubeTranscriptApi()
        self.project_root = project_root or Path.cwd()
        self.use_ytdlp_fallback = use_ytdlp_fallback
        self.cookies_from_browser = cookies_from_browser.strip()
        self.cookiefile = cookiefile.strip()
        self.prefer_ytdlp_when_authenticated = prefer_ytdlp_when_authenticated

    def _resolve_cookiefile(self) -> str:
        """Resolve a possibly relative cookie file path for yt-dlp."""
        if not self.cookiefile:
            return ""
        candidate = Path(self.cookiefile)
        if candidate.is_absolute():
            return str(candidate)
        return str((self.project_root / candidate).resolve())

    def _build_ytdlp_options(self) -> dict:
        """Build yt-dlp options for subtitle metadata extraction."""
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": False,
            "writeautomaticsub": False,
            "listsubtitles": False,
            "cachedir": False,
        }
        if self.cookies_from_browser:
            browser_name, _, browser_profile = self.cookies_from_browser.partition(":")
            if browser_profile.strip():
                options["cookiesfrombrowser"] = (browser_name.strip(), None, browser_profile.strip(), None)
            else:
                options["cookiesfrombrowser"] = (browser_name.strip(),)

        cookiefile = self._resolve_cookiefile()
        if cookiefile:
            options["cookiefile"] = cookiefile
        return options

    def _fetch_with_ytdlp(self, video_id: str, languages: list[str]) -> TranscriptFetchResult:
        """Try to extract subtitle text via yt-dlp metadata as a browser-aligned fallback."""
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        with YoutubeDL(self._build_ytdlp_options()) as ydl:
            info = ydl.extract_info(video_url, download=False)

        subtitle_blocks = []
        for key in ("subtitles", "automatic_captions"):
            subtitle_map = info.get(key) or {}
            for language in languages:
                language_items = subtitle_map.get(language) or []
                if language_items:
                    subtitle_blocks.append((key, language, language_items))
            if subtitle_blocks:
                break

        if not subtitle_blocks:
            raise ValueError(f"No yt-dlp subtitle metadata found for video_id={video_id}")

        subtitle_kind, language_code, subtitle_items = subtitle_blocks[0]
        text_parts: list[str] = []
        for item in subtitle_items:
            subtitle_url = item.get("url", "")
            if not subtitle_url:
                continue
            request_data = ydl.urlopen(subtitle_url).read().decode("utf-8", errors="ignore")
            if item.get("ext") == "json3":
                text_parts.extend(re.findall(r'"utf8":"(.*?)"', request_data))
            else:
                text_parts.extend(re.findall(r">([^<]+)<", request_data))

        raw_text = "\n".join(
            normalize_transcript_text(part.replace("\\n", " ").replace('\\"', '"'))
            for part in text_parts
            if normalize_transcript_text(part.replace("\\n", " ").replace('\\"', '"'))
        ).strip()

        if not raw_text:
            raise ValueError(f"yt-dlp subtitle text was empty for video_id={video_id}")

        clean_text = normalize_transcript_text(raw_text)
        is_generated = 1 if subtitle_kind == "automatic_captions" else 0
        quality = "auto_generated" if is_generated else "manual_caption"
        segment_count = len([line for line in raw_text.splitlines() if line.strip()])

        return TranscriptFetchResult(
            transcript_source="public_caption",
            transcript_text_raw=raw_text,
            transcript_text_clean=clean_text,
            transcript_quality=quality,
            stt_applied=0,
            transcript_language_code=language_code,
            transcript_language=language_code,
            transcript_is_generated=is_generated,
            transcript_segment_count=segment_count,
            transcript_error="",
        )

    def fetch_public_transcript(self, video_id: str, languages: list[str]) -> TranscriptFetchResult:
        """
        Fetch a public transcript if available.

        The library prefers manually created captions over generated ones when
        both exist for the requested language list.
        """
        should_try_ytdlp_first = (
            self.use_ytdlp_fallback
            and self.prefer_ytdlp_when_authenticated
            and bool(self.cookies_from_browser or self.cookiefile)
        )

        if should_try_ytdlp_first:
            try:
                return self._fetch_with_ytdlp(video_id=video_id, languages=languages)
            except Exception:
                pass

        try:
            transcript = self.client.fetch(video_id, languages=languages, preserve_formatting=False)
            raw_items = transcript.to_raw_data()

            raw_text = "\n".join(item.get("text", "").strip() for item in raw_items if item.get("text", "").strip())
            clean_text = normalize_transcript_text(raw_text)

            return TranscriptFetchResult(
                transcript_source="public_caption",
                transcript_text_raw=raw_text,
                transcript_text_clean=clean_text,
                transcript_quality="auto_generated" if transcript.is_generated else "manual_caption",
                stt_applied=0,
                transcript_language_code=transcript.language_code or "",
                transcript_language=transcript.language or "",
                transcript_is_generated=1 if transcript.is_generated else 0,
                transcript_segment_count=len(raw_items),
                transcript_error="",
            )
        except Exception as primary_exc:
            if not self.use_ytdlp_fallback:
                raise
            try:
                return self._fetch_with_ytdlp(video_id=video_id, languages=languages)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"youtube-transcript-api failed: {primary_exc}\n\nyt-dlp subtitle fallback failed: {fallback_exc}"
                ) from fallback_exc
