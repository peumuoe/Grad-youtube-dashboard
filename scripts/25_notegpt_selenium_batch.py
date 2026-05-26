from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("notegpt_selenium_batch")

DEFAULT_URLS = [
    "https://www.youtube.com/watch?v=JQB92KeQ5oo",
    "https://www.youtube.com/watch?v=OBz5o8EkjPk",
    "https://www.youtube.com/watch?v=5EtxutAb2tA",
    "https://www.youtube.com/watch?v=b4ySI0ZE7tk",
    "https://www.youtube.com/watch?v=PfTvcz8WGlg",
]


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Selenium + NoteGPT transcript extraction for a small batch of YouTube videos."
    )
    parser.add_argument(
        "--debugger-address",
        default="127.0.0.1:9222",
        help="Chrome remote debugging address. Default: 127.0.0.1:9222",
    )
    parser.add_argument(
        "--output-dir",
        default="data/raw/notegpt_exports",
        help="Directory to write *_transcript.json outputs.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Maximum wait time for transcript generation per video. Default: 30",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=1.0,
        help="Pause between videos. Default: 1.0",
    )
    parser.add_argument(
        "--attempts-per-url",
        type=int,
        default=1,
        help="How many times to retry the same target video before marking it failed. Default: 1",
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        default=[],
        help="YouTube watch URL to include. Repeat this argument to override the defaults.",
    )
    parser.add_argument(
        "--url-file",
        default="",
        help="Optional text file with one YouTube watch URL per line.",
    )
    parser.add_argument(
        "--report-file",
        default="",
        help="Optional prior batch report JSON. Can be used to select only failed or succeeded URLs.",
    )
    parser.add_argument(
        "--failed-only",
        action="store_true",
        help="When used with --report-file, rerun only URLs listed under failed.",
    )
    parser.add_argument(
        "--succeeded-only",
        action="store_true",
        help="When used with --report-file, select only URLs listed under succeeded.",
    )
    parser.add_argument(
        "--video-id",
        action="append",
        dest="video_ids",
        default=[],
        help="Restrict execution to specific YouTube video IDs. Repeat this argument as needed.",
    )
    parser.add_argument(
        "--exclude-video-id",
        action="append",
        dest="exclude_video_ids",
        default=[],
        help="Skip specific YouTube video IDs. Repeat this argument as needed.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of selected URLs to run after filtering.",
    )
    parser.add_argument(
        "--write-selected-url-file",
        default="",
        help="Optional path to write the final selected URL list before execution.",
    )
    parser.add_argument(
        "--no-skip-existing-output",
        action="store_true",
        help="By default, skip URLs whose *_transcript.json already exists in the output directory. Use this flag to disable that behavior.",
    )
    parser.add_argument(
        "--max-consecutive-mismatches",
        type=int,
        default=3,
        help="Abort the batch when this many mismatch failures happen in a row. Default: 3",
    )
    parser.add_argument(
        "--max-same-wrong-video-streak",
        type=int,
        default=2,
        help="Abort the batch when the same wrong video ID appears in mismatch failures this many times in a row. Default: 2",
    )
    return parser.parse_args()


def load_one_video_module() -> Any:
    module_path = Path(__file__).with_name("24_notegpt_selenium_one_video.py")
    spec = importlib.util.spec_from_file_location("notegpt_selenium_one_video", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Selenium helper module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_report_path(output_dir: Path) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return output_dir / f"notegpt_batch_report_{stamp}.json"


def build_progress_path(output_dir: Path) -> Path:
    return output_dir / "notegpt_batch_progress.json"


def resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def normalize_video_id(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    if "youtube.com" in cleaned or "youtu.be" in cleaned:
        match = re.search(r"[?&]v=([^&]+)", cleaned)
        if match:
            return match.group(1).strip()
        short_match = re.search(r"youtu\.be/([^?&/]+)", cleaned)
        if short_match:
            return short_match.group(1).strip()
    return cleaned


def load_report_urls(report_path: Path, bucket: str) -> list[str]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    rows = payload.get(bucket, [])
    urls: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if url:
            urls.append(url)
    return urls


def deduplicate_urls(urls: list[str], helper: Any) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        video_id = helper.get_video_id_from_url(url) or url
        if video_id in seen:
            continue
        seen.add(video_id)
        deduped.append(url)
    return deduped


def load_urls(args: argparse.Namespace, helper: Any) -> list[str]:
    if args.failed_only and args.succeeded_only:
        raise ValueError("--failed-only and --succeeded-only cannot be used together.")

    if args.report_file:
        report_path = resolve_path(args.report_file)
        if not report_path.exists():
            raise FileNotFoundError(f"Report file not found: {report_path}")
        if args.failed_only:
            urls = load_report_urls(report_path, "failed")
        elif args.succeeded_only:
            urls = load_report_urls(report_path, "succeeded")
        else:
            urls = load_report_urls(report_path, "failed") + load_report_urls(report_path, "succeeded")
    elif args.urls:
        urls = args.urls
    elif args.url_file:
        url_file = resolve_path(args.url_file)
        if not url_file.exists():
            raise FileNotFoundError(f"URL file not found: {url_file}")
        urls = [
            line.strip()
            for line in url_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        urls = DEFAULT_URLS

    urls = deduplicate_urls(urls, helper)

    include_ids = {normalize_video_id(value) for value in args.video_ids if normalize_video_id(value)}
    exclude_ids = {normalize_video_id(value) for value in args.exclude_video_ids if normalize_video_id(value)}

    if include_ids:
        urls = [url for url in urls if helper.get_video_id_from_url(url) in include_ids]
    if exclude_ids:
        urls = [url for url in urls if helper.get_video_id_from_url(url) not in exclude_ids]
    if args.limit and args.limit > 0:
        urls = urls[: args.limit]

    if args.write_selected_url_file:
        output_path = resolve_path(args.write_selected_url_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
        LOGGER.info("Wrote selected URL list to %s", output_path)

    return urls


def existing_output_video_ids(output_dir: Path) -> set[str]:
    video_ids: set[str] = set()
    if not output_dir.exists():
        return video_ids
    for path in output_dir.glob("*_transcript.json"):
        name = path.name
        if name.endswith("_transcript.json"):
            video_ids.add(name[: -len("_transcript.json")])
    return video_ids


def filter_existing_output_urls(urls: list[str], output_dir: Path, helper: Any) -> list[str]:
    existing_ids = existing_output_video_ids(output_dir)
    if not existing_ids:
        return urls
    filtered = [url for url in urls if helper.get_video_id_from_url(url) not in existing_ids]
    skipped = len(urls) - len(filtered)
    if skipped:
        LOGGER.info(
            "Skipping %s URLs because transcript JSONs already exist in %s",
            skipped,
            output_dir,
        )
    return filtered


def is_mismatch_error_message(message: str) -> bool:
    lowered = message.lower()
    return "mismatch" in lowered and "video" in lowered


def extract_wrong_video_id_from_message(message: str) -> str:
    patterns = [
        r"current_video_id=([A-Za-z0-9_-]{11})",
        r"payload_video_id=([A-Za-z0-9_-]{11})",
        r"v=([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1)
    return ""


def is_window_lost_error_message(message: str) -> bool:
    lowered = message.lower()
    snippets = (
        "target window already closed",
        "no such window",
        "browsing context has been discarded",
        "web view not found",
        "httpconnectionpool(",
        "read timed out",
        "timed out receiving message from renderer",
        "timeout: timed out receiving message from renderer",
        "max retries exceeded",
        "connection refused",
        "failed to establish a new connection",
    )
    return any(snippet in lowered for snippet in snippets)


def reconnect_driver(helper: Any, debugger_address: str) -> Any:
    LOGGER.warning("Reconnecting to Chrome at %s after collection tab/session loss...", debugger_address)
    return helper.connect_driver(debugger_address)


def abort_batch_due_to_session_failure(
    progress_path: Path,
    *,
    total_urls: int,
    succeeded: list[dict[str, Any]],
    failed: list[dict[str, Any]],
    index: int,
    url: str,
    expected_video_id: str,
    attempt: int,
    error_message: str,
) -> RuntimeError:
    fatal_error = (
        "Browser session recovery failed. "
        f"video_index={index} url={url} expected_video_id={expected_video_id} "
        f"attempt={attempt} error={error_message}"
    )
    write_progress(
        progress_path,
        status="aborted",
        total_urls=total_urls,
        completed=len(succeeded) + len(failed),
        succeeded=len(succeeded),
        failed=len(failed),
        current_index=index,
        current_url=url,
        current_video_id=expected_video_id,
        current_attempt=attempt,
        stage="aborted",
        last_error=error_message,
        fatal_error=fatal_error,
    )
    LOGGER.error("%s", fatal_error)
    return RuntimeError(fatal_error)


def safe_current_url(driver: Any) -> str:
    if driver is None:
        return ""
    try:
        return str(driver.current_url or "")
    except Exception:
        return ""


def write_progress(
    progress_path: Path,
    *,
    status: str,
    total_urls: int,
    completed: int,
    succeeded: int,
    failed: int,
    current_index: int = 0,
    current_url: str = "",
    current_video_id: str = "",
    current_attempt: int = 0,
    stage: str = "",
    last_error: str = "",
    fatal_error: str = "",
) -> None:
    payload = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": status,
        "total_urls": total_urls,
        "completed": completed,
        "remaining": max(total_urls - completed, 0),
        "succeeded": succeeded,
        "failed": failed,
        "current_index": current_index,
        "current_url": current_url,
        "current_video_id": current_video_id,
        "current_attempt": current_attempt,
        "stage": stage,
        "last_error": last_error,
        "fatal_error": fatal_error,
    }
    progress_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_batch(args: argparse.Namespace) -> int:
    helper = load_one_video_module()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = build_progress_path(output_dir)
    urls = load_urls(args, helper)
    if not args.no_skip_existing_output:
        urls = filter_existing_output_urls(urls, output_dir, helper)

    write_progress(
        progress_path,
        status="starting",
        total_urls=len(urls),
        completed=0,
        succeeded=0,
        failed=0,
    )

    if not urls:
        LOGGER.info("No URLs left to process after filtering and existing-output checks.")
    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    fatal_error = ""
    driver = None
    consecutive_mismatches = 0
    previous_wrong_video_id = ""
    same_wrong_video_streak = 0

    try:
        if not urls:
            raise StopIteration

        LOGGER.info("Attaching to Chrome at %s", args.debugger_address)
        driver = helper.connect_driver(args.debugger_address)
        for index, url in enumerate(urls, start=1):
            LOGGER.info("Starting video %s/%s: %s", index, len(urls), url)
            expected_video_id = helper.get_video_id_from_url(url)
            last_error: Exception | None = None
            for attempt in range(1, max(args.attempts_per_url, 1) + 1):
                write_progress(
                    progress_path,
                    status="running",
                    total_urls=len(urls),
                    completed=len(succeeded) + len(failed),
                    succeeded=len(succeeded),
                    failed=len(failed),
                    current_index=index,
                    current_url=url,
                    current_video_id=expected_video_id,
                    current_attempt=attempt,
                    stage="navigating",
                )
                try:
                    helper.open_video_page(driver, url, args.timeout_seconds, expected_video_id)
                    write_progress(
                        progress_path,
                        status="running",
                        total_urls=len(urls),
                        completed=len(succeeded) + len(failed),
                        succeeded=len(succeeded),
                        failed=len(failed),
                        current_index=index,
                        current_url=url,
                        current_video_id=expected_video_id,
                        current_attempt=attempt,
                        stage="mounting_notegpt",
                    )
                    helper.show_collection_overlay(
                        driver,
                        f"Collecting {index}/{len(urls)}",
                        f"{expected_video_id} | attempt {attempt}/{max(args.attempts_per_url, 1)}",
                    )
                    LOGGER.info("Giving NoteGPT a moment to finish mounting...")
                    helper.wait_for_transcript_button(driver, 8)
                    write_progress(
                        progress_path,
                        status="running",
                        total_urls=len(urls),
                        completed=len(succeeded) + len(failed),
                        succeeded=len(succeeded),
                        failed=len(failed),
                        current_index=index,
                        current_url=url,
                        current_video_id=expected_video_id,
                        current_attempt=attempt,
                        stage="clicking_transcript",
                    )
                    helper.click_transcript_button(driver, args.timeout_seconds, expected_video_id)
                    write_progress(
                        progress_path,
                        status="running",
                        total_urls=len(urls),
                        completed=len(succeeded) + len(failed),
                        succeeded=len(succeeded),
                        failed=len(failed),
                        current_index=index,
                        current_url=url,
                        current_video_id=expected_video_id,
                        current_attempt=attempt,
                        stage="waiting_for_panel",
                    )
                    helper.wait_for_loading_or_transcript(driver, 20, expected_video_id)
                    payload = helper.wait_for_transcript_payload(driver, args.timeout_seconds, expected_video_id)
                    payload_video_id = str(payload.get("video_id") or "").strip()
                    if expected_video_id and payload_video_id != expected_video_id:
                        raise RuntimeError(
                            f"Payload video mismatch detected. expected_video_id={expected_video_id} "
                            f"payload_video_id={payload_video_id} current_url={driver.current_url}"
                        )
                    output_path = helper.save_payload(payload, output_dir)
                    succeeded.append(
                        {
                            "url": url,
                            "expected_video_id": expected_video_id,
                            "video_id": payload.get("video_id"),
                            "title": payload.get("title"),
                            "output_path": str(output_path),
                            "text_length": payload.get("text_length"),
                            "attempt": attempt,
                        }
                    )
                    LOGGER.info(
                        "Saved transcript for video=%s title=%s to %s",
                        payload.get("video_id"),
                        payload.get("title"),
                        output_path,
                    )
                    write_progress(
                        progress_path,
                        status="running",
                        total_urls=len(urls),
                        completed=len(succeeded) + len(failed),
                        succeeded=len(succeeded),
                        failed=len(failed),
                        current_index=index,
                        current_url=url,
                        current_video_id=expected_video_id,
                        current_attempt=attempt,
                        stage="saved",
                    )
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    error_message = str(exc)
                    if is_window_lost_error_message(error_message):
                        try:
                            if driver is not None:
                                try:
                                    driver.quit()
                                except Exception:
                                    pass
                            driver = reconnect_driver(helper, args.debugger_address)
                            LOGGER.warning(
                                "Recovered from collection tab/window loss while processing %s. Retrying the same URL.",
                                url,
                            )
                            time.sleep(1.0)
                            continue
                        except Exception as reconnect_exc:
                            error_message = (
                                f"{error_message} | reconnect_failed={reconnect_exc}"
                            )
                            session_failure = abort_batch_due_to_session_failure(
                                progress_path,
                                total_urls=len(urls),
                                succeeded=succeeded,
                                failed=failed,
                                index=index,
                                url=url,
                                expected_video_id=expected_video_id,
                                attempt=attempt,
                                error_message=error_message,
                            )
                            raise session_failure from reconnect_exc
                    if attempt < max(args.attempts_per_url, 1) and helper.is_retryable_error(exc):
                        LOGGER.warning(
                            "Retrying video %s/%s after attempt %s failed: %s",
                            index,
                            len(urls),
                            attempt,
                            exc,
                        )
                        time.sleep(args.pause_seconds)
                        continue
                    LOGGER.exception("Failed video %s/%s: %s", index, len(urls), url)
                    error_message = str(exc)
                    is_mismatch = is_mismatch_error_message(error_message)
                    wrong_video_id = extract_wrong_video_id_from_message(error_message) if is_mismatch else ""
                    if is_mismatch:
                        consecutive_mismatches += 1
                        if wrong_video_id and wrong_video_id == previous_wrong_video_id:
                            same_wrong_video_streak += 1
                        else:
                            same_wrong_video_streak = 1 if wrong_video_id else 0
                        previous_wrong_video_id = wrong_video_id
                    else:
                        consecutive_mismatches = 0
                        previous_wrong_video_id = ""
                        same_wrong_video_streak = 0
                    failed.append(
                        {
                            "url": url,
                            "expected_video_id": expected_video_id,
                            "current_url": safe_current_url(driver),
                            "error": error_message,
                            "attempts_used": attempt,
                        }
                    )
                    write_progress(
                        progress_path,
                        status="running",
                        total_urls=len(urls),
                        completed=len(succeeded) + len(failed),
                        succeeded=len(succeeded),
                        failed=len(failed),
                        current_index=index,
                        current_url=url,
                        current_video_id=expected_video_id,
                        current_attempt=attempt,
                        stage="failed",
                        last_error=error_message,
                    )
                    if is_mismatch and (
                        consecutive_mismatches >= max(args.max_consecutive_mismatches, 1)
                        or (
                            wrong_video_id
                            and same_wrong_video_streak >= max(args.max_same_wrong_video_streak, 1)
                        )
                    ):
                        fatal_error = (
                            "Mismatch circuit breaker triggered. "
                            f"consecutive_mismatches={consecutive_mismatches} "
                            f"same_wrong_video_streak={same_wrong_video_streak} "
                            f"wrong_video_id={wrong_video_id or 'unknown'}"
                        )
                        write_progress(
                            progress_path,
                            status="aborted",
                            total_urls=len(urls),
                            completed=len(succeeded) + len(failed),
                            succeeded=len(succeeded),
                            failed=len(failed),
                            current_index=index,
                            current_url=url,
                            current_video_id=expected_video_id,
                            current_attempt=attempt,
                            stage="aborted",
                            last_error=error_message,
                            fatal_error=fatal_error,
                        )
                        LOGGER.error("%s", fatal_error)
                        raise RuntimeError(fatal_error) from exc
                    break
            if index < len(urls):
                time.sleep(args.pause_seconds)
    except StopIteration:
        pass
    except Exception as exc:
        fatal_error = str(exc)
        LOGGER.exception("Batch aborted before completion.")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    report = {
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "debugger_address": args.debugger_address,
        "requested_urls": urls,
        "succeeded": succeeded,
        "failed": failed,
    }
    if fatal_error:
        report["fatal_error"] = fatal_error
    report_path = build_report_path(output_dir)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_progress(
        progress_path,
        status="completed" if not fatal_error else "aborted",
        total_urls=len(urls),
        completed=len(succeeded) + len(failed),
        succeeded=len(succeeded),
        failed=len(failed),
        fatal_error=fatal_error,
    )

    LOGGER.info(
        "Batch finished. succeeded=%s failed=%s report=%s",
        len(succeeded),
        len(failed),
        report_path,
    )
    # Normal per-video failures such as "no subtitles" should not make the whole
    # batch look like a process-level crash. Reserve non-zero exit codes for
    # actual batch-aborting failures only.
    return 0 if not fatal_error else 1


def main() -> int:
    configure_logging()
    args = parse_args()
    return run_batch(args)


if __name__ == "__main__":
    raise SystemExit(main())
