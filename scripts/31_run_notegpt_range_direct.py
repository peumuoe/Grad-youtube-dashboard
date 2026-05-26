from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BATCH_DIR = ROOT / "data" / "processed" / "notebooklm_batches"
DEFAULT_OUTPUT_ROOT = ROOT / "data" / "raw"
DEFAULT_PROGRESS_PATH = DEFAULT_OUTPUT_ROOT / "notegpt_range_progress.json"
DEFAULT_LOCK_PATH = DEFAULT_OUTPUT_ROOT / "notegpt_range_runner.lock"
BATCH_SCRIPT = ROOT / "scripts" / "25_notegpt_selenium_batch.py"
BATCH_RE = re.compile(r"batch_(\d+)_urls\.txt$", re.IGNORECASE)
REPORT_RE = re.compile(r"notegpt_batch_report_.*\.json$", re.IGNORECASE)
DEBUG_CHROME_SCRIPT = ROOT / "scripts" / "23_launch_chrome_debug.ps1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run NoteGPT batch collection sequentially using the single-batch runner directly."
    )
    parser.add_argument("--start-batch", type=int, required=True)
    parser.add_argument("--end-batch", type=int)
    parser.add_argument("--auto-end", action="store_true")
    parser.add_argument("--batch-dir", default=str(DEFAULT_BATCH_DIR))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--progress-path", default=str(DEFAULT_PROGRESS_PATH))
    parser.add_argument("--lock-path", default=str(DEFAULT_LOCK_PATH))
    parser.add_argument(
        "--max-attempts-per-batch",
        type=int,
        default=3,
        help="How many times to retry a batch when it ends with fatal_error or without producing a fresh report.",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock(lock_path: Path) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            pid = int(payload.get("pid", 0))
        except Exception:
            pid = 0
        if pid and process_is_alive(pid):
            raise RuntimeError(f"Another range runner is already active. pid={pid}")
        lock_path.unlink(missing_ok=True)
    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "started_at": now_iso()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def release_lock(lock_path: Path) -> None:
    try:
        if lock_path.exists():
            lock_path.unlink()
    except Exception:
        pass


def list_batch_files(batch_dir: Path) -> list[tuple[int, Path]]:
    items: list[tuple[int, Path]] = []
    for path in batch_dir.glob("batch_*_urls.txt"):
        match = BATCH_RE.search(path.name)
        if not match:
            continue
        items.append((int(match.group(1)), path))
    return sorted(items, key=lambda item: item[0])


def build_output_dir(output_root: Path, batch_number: int) -> Path:
    return output_root / f"notegpt_exports_batch_{batch_number:03d}"


def latest_report(output_dir: Path) -> Path | None:
    reports = sorted(
        [path for path in output_dir.glob("notegpt_batch_report_*.json") if REPORT_RE.match(path.name)],
        key=lambda path: path.name,
    )
    return reports[-1] if reports else None


def read_report(report_path: Path | None) -> dict[str, Any]:
    if report_path is None or not report_path.exists():
        return {}
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_batch_urls(batch_file: Path) -> list[str]:
    if not batch_file.exists():
        return []
    return [
        line.strip()
        for line in batch_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def report_matches_batch_file(report: dict[str, Any], batch_file: Path) -> bool:
    report_urls = [str(url).strip() for url in report.get("requested_urls", []) if str(url).strip()]
    batch_urls = read_batch_urls(batch_file)
    if not report_urls or not batch_urls:
        return False
    return report_urls == batch_urls


def batch_completed(output_dir: Path, batch_file: Path) -> bool:
    report = read_report(latest_report(output_dir))
    return bool(report) and not report.get("fatal_error") and report_matches_batch_file(report, batch_file)


def write_range_progress(
    progress_path: Path,
    *,
    status: str,
    start_batch: int,
    end_batch: int,
    current_batch: int,
    current_batch_file: Path | None,
    last_result: dict[str, Any],
) -> None:
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": now_iso(),
        "status": status,
        "start_batch": start_batch,
        "end_batch": end_batch,
        "current_batch": current_batch,
        "current_batch_id": f"batch_{current_batch:03d}" if current_batch else "",
        "current_batch_file": str(current_batch_file) if current_batch_file else "",
        "last_result": last_result,
    }
    progress_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_single_batch(batch_file: Path, output_dir: Path) -> subprocess.CompletedProcess[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        str(BATCH_SCRIPT),
        "--url-file",
        str(batch_file),
        "--output-dir",
        str(output_dir),
    ]
    return subprocess.run(cmd, cwd=str(ROOT), check=False)


def report_signature(report_path: Path | None) -> tuple[str, int]:
    if report_path is None or not report_path.exists():
        return ("", -1)
    try:
        stat = report_path.stat()
        return (str(report_path), stat.st_mtime_ns)
    except Exception:
        return (str(report_path), -1)


def is_browser_session_fatal_error(message: str) -> bool:
    lowered = str(message or "").lower()
    snippets = (
        "httpconnectionpool(",
        "read timed out",
        "timed out receiving message from renderer",
        "max retries exceeded",
        "connection refused",
        "failed to establish a new connection",
        "invalid session id",
        "not connected to devtools",
        "web view not found",
        "no such window",
    )
    return any(snippet in lowered for snippet in snippets)


def debug_port_open(host: str = "127.0.0.1", port: int = 9222, timeout_seconds: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def relaunch_debug_chrome_if_needed(force_restart: bool = False) -> None:
    if debug_port_open() and not force_restart:
        return
    if force_restart:
        print("[direct-runner] forcing a fresh debug Chrome session before retry...", flush=True)
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force",
            ],
            cwd=str(ROOT),
            check=False,
        )
        time.sleep(2)
    else:
        print("[direct-runner] debug Chrome port 9222 is unavailable. Relaunching debug Chrome...", flush=True)
    subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(DEBUG_CHROME_SCRIPT),
        ],
        cwd=str(ROOT),
        check=False,
    )
    time.sleep(3)


def main() -> int:
    args = parse_args()
    batch_dir = Path(args.batch_dir)
    output_root = Path(args.output_root)
    progress_path = Path(args.progress_path)
    lock_path = Path(args.lock_path)

    batch_files = list_batch_files(batch_dir)
    if not batch_files:
        raise RuntimeError(f"No batch files found in {batch_dir}")

    batch_numbers = [number for number, _ in batch_files]
    if args.start_batch not in batch_numbers:
        raise RuntimeError(f"Start batch {args.start_batch} not found in {batch_dir}")

    max_batch = batch_numbers[-1]
    end_batch = max_batch if args.auto_end or args.end_batch is None else args.end_batch

    selected = [(number, path) for number, path in batch_files if args.start_batch <= number <= end_batch]
    if not selected:
        raise RuntimeError("No batches selected to run.")

    acquire_lock(lock_path)
    last_result: dict[str, Any] = {}
    try:
        for number, batch_file in selected:
            output_dir = build_output_dir(output_root, number)
            if batch_completed(output_dir, batch_file):
                report_path = latest_report(output_dir)
                report = read_report(report_path)
                last_result = {
                    "batch_file": str(batch_file),
                    "output_dir": str(output_dir),
                    "return_code": 0,
                    "started_at": "",
                    "ended_at": "",
                    "report_path": str(report_path) if report_path else "",
                    "skipped": True,
                    "skip_reason": "already_completed",
                    "succeeded": len(report.get("succeeded", [])),
                    "failed": len(report.get("failed", [])),
                }
                write_range_progress(
                    progress_path,
                    status="running",
                    start_batch=args.start_batch,
                    end_batch=end_batch,
                    current_batch=number + 1 if number < end_batch else number,
                    current_batch_file=batch_file,
                    last_result=last_result,
                )
                continue

            previous_report_signature = report_signature(latest_report(output_dir))
            batch_succeeded = False
            for attempt in range(1, max(1, int(args.max_attempts_per_batch)) + 1):
                started_at = now_iso()
                write_range_progress(
                    progress_path,
                    status="running",
                    start_batch=args.start_batch,
                    end_batch=end_batch,
                    current_batch=number,
                    current_batch_file=batch_file,
                    last_result=last_result,
                )
                print(
                    f"[direct-runner] starting batch_{number:03d} attempt={attempt} -> {output_dir}",
                    flush=True,
                )
                result = run_single_batch(batch_file, output_dir)
                ended_at = now_iso()
                report_path = latest_report(output_dir)
                report = read_report(report_path)
                current_report_signature = report_signature(report_path)
                has_fresh_report = current_report_signature != previous_report_signature and bool(report_path)
                fatal_error = str(report.get("fatal_error", ""))
                last_result = {
                    "batch_file": str(batch_file),
                    "output_dir": str(output_dir),
                    "return_code": int(result.returncode),
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "report_path": str(report_path) if report_path else "",
                    "succeeded": len(report.get("succeeded", [])),
                    "failed": len(report.get("failed", [])),
                    "fatal_error": fatal_error,
                    "attempt": attempt,
                    "has_fresh_report": has_fresh_report,
                }
                if has_fresh_report and not fatal_error:
                    batch_succeeded = True
                    break

                retry_reason = fatal_error or "batch did not produce a fresh report"
                print(
                    f"[direct-runner] batch_{number:03d} attempt={attempt} needs retry: {retry_reason}",
                    flush=True,
                )
                if attempt < max(1, int(args.max_attempts_per_batch)):
                    if is_browser_session_fatal_error(retry_reason):
                        relaunch_debug_chrome_if_needed(force_restart=True)
                    elif not debug_port_open():
                        relaunch_debug_chrome_if_needed()
                    time.sleep(3)
                    previous_report_signature = current_report_signature
                    continue

                write_range_progress(
                    progress_path,
                    status="aborted",
                    start_batch=args.start_batch,
                    end_batch=end_batch,
                    current_batch=number,
                    current_batch_file=batch_file,
                    last_result=last_result,
                )
                return 1

            if not batch_succeeded:
                write_range_progress(
                    progress_path,
                    status="aborted",
                    start_batch=args.start_batch,
                    end_batch=end_batch,
                    current_batch=number,
                    current_batch_file=batch_file,
                    last_result=last_result,
                )
                return 1

            write_range_progress(
                progress_path,
                status="running",
                start_batch=args.start_batch,
                end_batch=end_batch,
                current_batch=number + 1 if number < end_batch else number,
                current_batch_file=batch_file,
                last_result=last_result,
            )

        write_range_progress(
            progress_path,
            status="completed",
            start_batch=args.start_batch,
            end_batch=end_batch,
            current_batch=end_batch,
            current_batch_file=None,
            last_result=last_result,
        )
        return 0
    finally:
        release_lock(lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
