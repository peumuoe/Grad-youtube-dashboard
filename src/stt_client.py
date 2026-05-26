from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel
from yt_dlp import YoutubeDL


DEFAULT_AUDIO_CACHE_DIR = Path("data/raw/audio_cache")


def _to_absolute_path(project_root: Path, raw_path: str) -> Path:
    """Resolve a possibly relative path against the project root."""
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return project_root / candidate


@dataclass
class STTFetchResult:
    """Normalized result for local speech-to-text transcription."""

    transcript_text_raw: str
    transcript_quality: str
    transcript_language_code: str
    transcript_language: str
    transcript_segment_count: int
    transcript_error: str


class STTClient:
    """Download YouTube audio and transcribe it locally with faster-whisper."""

    def __init__(
        self,
        enabled: bool = False,
        project_root: Path | None = None,
        model_size: str = "tiny",
        device: str = "cpu",
        compute_type: str = "int8",
        beam_size: int = 1,
        audio_cache_dir: str = str(DEFAULT_AUDIO_CACHE_DIR),
        keep_downloaded_audio: bool = False,
        cookies_from_browser: str = "",
        cookiefile: str = "",
        audio_format: str = "bestaudio[abr<=96]/bestaudio/best",
    ) -> None:
        self.enabled = enabled
        self.project_root = project_root or Path.cwd()
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.audio_cache_dir = _to_absolute_path(self.project_root, audio_cache_dir)
        self.keep_downloaded_audio = keep_downloaded_audio
        self.cookies_from_browser = cookies_from_browser.strip()
        self.cookiefile = cookiefile.strip()
        self.audio_format = audio_format.strip() or "bestaudio[abr<=96]/bestaudio/best"
        self._model: WhisperModel | None = None

    def _resolve_cookiefile(self) -> str:
        """Resolve a possibly relative cookie file path for yt-dlp."""
        if not self.cookiefile:
            return ""
        candidate = Path(self.cookiefile)
        if candidate.is_absolute():
            return str(candidate)
        return str((self.project_root / candidate).resolve())

    def _get_model(self) -> WhisperModel:
        """Load the Whisper model lazily so the script starts quickly."""
        if self._model is None:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def _download_audio(self, video_id: str, video_url: str) -> Path:
        """Download the best available audio stream for one video."""
        self.audio_cache_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(self.audio_cache_dir / f"{video_id}.%(ext)s")

        ydl_options = {
            "format": self.audio_format,
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "retries": 3,
            "cachedir": False,
            "overwrites": False,
        }

        if self.cookies_from_browser:
            browser_name, _, browser_profile = self.cookies_from_browser.partition(":")
            if browser_profile.strip():
                ydl_options["cookiesfrombrowser"] = (browser_name.strip(), None, browser_profile.strip(), None)
            else:
                ydl_options["cookiesfrombrowser"] = (browser_name.strip(),)

        cookiefile = self._resolve_cookiefile()
        if cookiefile:
            ydl_options["cookiefile"] = cookiefile

        with YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(video_url, download=True)
            downloaded_path = ydl.prepare_filename(info)

        candidate_path = Path(downloaded_path)
        if candidate_path.exists():
            return candidate_path

        fallback_matches = sorted(self.audio_cache_dir.glob(f"{video_id}.*"))
        if fallback_matches:
            return fallback_matches[0]

        raise FileNotFoundError(f"Downloaded audio file was not found for video_id={video_id}")

    def _transcribe_audio(self, audio_path: Path) -> STTFetchResult:
        """Run local Whisper transcription against the downloaded audio."""
        model = self._get_model()
        segments, info = model.transcribe(
            str(audio_path),
            beam_size=self.beam_size,
            vad_filter=True,
        )

        segment_list = list(segments)
        text_parts = [segment.text.strip() for segment in segment_list if segment.text.strip()]
        raw_text = "\n".join(text_parts).strip()
        language_code = getattr(info, "language", "") or ""
        language_name = language_code.upper() if language_code else ""

        return STTFetchResult(
            transcript_text_raw=raw_text,
            transcript_quality=f"stt_{self.model_size}",
            transcript_language_code=language_code,
            transcript_language=language_name,
            transcript_segment_count=len(segment_list),
            transcript_error="",
        )

    def fetch_transcript(self, video_id: str, video_url: str) -> STTFetchResult:
        """Download audio and transcribe it when captions/scripts are unavailable."""
        if not self.enabled:
            raise NotImplementedError(
                "STT is not enabled yet. Set ENABLE_STT=1 to turn on local transcription."
            )

        if not video_url.strip():
            raise ValueError(f"Missing video_url for STT transcription: video_id={video_id}")

        audio_path: Path | None = None
        try:
            audio_path = self._download_audio(video_id=video_id, video_url=video_url)
            return self._transcribe_audio(audio_path)
        finally:
            if audio_path is not None and audio_path.exists() and not self.keep_downloaded_audio:
                with contextlib.suppress(OSError):
                    audio_path.unlink()
