from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH_DIR = PROJECT_ROOT / "data" / "processed" / "notebooklm_batches"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "raw"
DEFAULT_BATCH_SCRIPT = PROJECT_ROOT / "scripts" / "25_notegpt_selenium_batch.py"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "data" / "raw" / "notegpt_overnight_run_report.json"
DEFAULT_PROGRESS_PATH = PROJECT_ROOT / "data" / "raw" / "notegpt_range_progress.json"
DEFAULT_LOCK_PATH = PROJECT_ROOT / "data" / "raw" / "notegpt_range_runner.lock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run multiple NoteGPT Selenium batch files in sequence."
    )
    parser.add_argument("--start-batch", type=int, required=True, help="First batch number, e.g. 3")
    parser.add_argument(
        "--end-batch",
        type=int,
        default=0,
        help="Last batch number, e.g. 20. Use 0 with --auto-end to continue through the last available batch file.",
    )
    parser.add_argument(
        "--auto-end",
        action="store_true",
        help="Automatically detect the highest available batch_XXX_urls.txt file and use that as --end-batch.",
    )
    parser.add_argument(
        "--batch-dir",
        default=str(DEFAULT_BATCH_DIR),
        help="Directory containing batch_XXX_urls.txt files.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Root directory for per-batch transcript output folders.",
    )
    parser.add_argument(
        "--attempts-per-url",
        type=int,
        default=1,
        help="How many attempts to allow per video URL. Default: 1",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="Transcript timeout per video. Default: 60",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=2.0,
        help="Pause between videos inside each batch. Default: 2.0",
    )
    parser.add_argument(
        "--sleep-between-batches",
        type=float,
        default=5.0,
        help="Pause between whole batch files. Default: 5.0",
    )
    parser.add_argument(
        "--debugger-address",
        default="127.0.0.1:9222",
        help="Chrome remote debugging address. Default: 127.0.0.1:9222",
    )
    parser.add_argument(
        "--report-path",
        default=str(DEFAULT_REPORT_PATH),
        help="JSON summary report path for the full overnight run.",
    )
    parser.add_argument(
        "--progress-path",
        default=str(DEFAULT_PROGRESS_PATH),
        help="JSON progress path updated during the range run.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop the overnight run if any batch exits non-zero.",
    )
    parser.add_argument(
        "--rerun-completed",
        action="store_true",
        help="Rerun batches even if a per-batch report JSON already exists. Default: skip completed batches.",
    )
    parser.add_argument(
        "--max-batch-retries",
        type=int,
        default=3,
        help="How many times to retry the same batch if the child batch process exits abnormally without a fatal_error. Default: 3",
    )
    parser.add_argument(
        "--lock-path",
        default=str(DEFAULT_LOCK_PATH),
        help="Lock file path used to prevent overlapping range runners.",
    )
    return parser.parse_args()


def batch_id_from_number(number: int) -> str:
    return f"batch_{number:03d}"


def resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_lock(lock_path: Path) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        existing_pid = int(payload.get("pid", 0) or 0)
        if existing_pid and process_is_alive(existing_pid):
            raise RuntimeError(
                f"Another range runner is already active (pid={existing_pid}). "
                f"Remove {lock_path} only if you are sure that process is gone."
            )
    payload = {
        "pid": os.getpid(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    lock_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def release_lock(lock_path: Path) -> None:
    try:
        if lock_path.exists():
            lock_path.unlink()
    except Exception:
        pass


def find_last_available_batch_number(batch_dir: Path) -> int:
    numbers: list[int] = []
    for path in batch_dir.glob("batch_*_urls.txt"):
        parts = path.stem.split("_")
        if len(parts) < 2:
            continue
        try:
            numbers.append(int(parts[1]))
        except ValueError:
            continue
    return max(numbers) if numbers else 0


def write_range_progress(
    progress_path: Path,
    *,
    status: str,
    start_batch: int,
    end_batch: int,
    current_batch: int = 0,
    current_batch_id: str = "",
    current_batch_file: str = "",
    last_result: dict[str, object] | None = None,
) -> None:
    payload = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": status,
        "start_batch": start_batch,
        "end_batch": end_batch,
        "current_batch": current_batch,
        "current_batch_id": current_batch_id,
        "current_batch_file": current_batch_file,
        "last_result": last_result or {},
    }
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def find_latest_report(output_dir: Path) -> Path | None:
    reports = sorted(output_dir.glob("notegpt_batch_report_*.json"))
    return reports[-1] if reports else None


def load_report_payload(report_path: Path | None) -> dict[str, object]:
    if report_path is None or not report_path.exists():
        return {}
    return json.loads(report_path.read_text(encoding="utf-8"))


def batch_is_completed(output_dir: Path) -> bool:
    report_path = find_latest_report(output_dir)
    payload = load_report_payload(report_path)
    if not payload:
        return False
    fatal_error = str(payload.get("fatal_error") or "").strip()
    return not fatal_error


def run_one_batch(
    batch_script: Path,
    batch_file: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> dict[str, object]:
    command = [
        str(Path(sys.executable)),
        "-u",
        str(batch_script),
        "--url-file",
        str(batch_file),
        "--output-dir",
        str(output_dir),
        "--attempts-per-url",
        str(args.attempts_per_url),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--pause-seconds",
        str(args.pause_seconds),
        "--debugger-address",
        str(args.debugger_address),
    ]

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    ended_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    report_path = find_latest_report(output_dir)

    batch_result: dict[str, object] = {
        "batch_file": str(batch_file),
        "output_dir": str(output_dir),
        "return_code": completed.returncode,
        "started_at": started_at,
        "ended_at": ended_at,
        "report_path": str(report_path) if report_path else "",
    }

    if report_path and report_path.exists():
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        batch_result["succeeded"] = len(payload.get("succeeded", []))
        batch_result["failed"] = len(payload.get("failed", []))
        batch_result["fatal_error"] = str(payload.get("fatal_error") or "")
    else:
        batch_result["succeeded"] = 0
        batch_result["failed"] = 0
        batch_result["fatal_error"] = "missing_report"

    return batch_result


def should_retry_batch(result: dict[str, object]) -> bool:
    fatal_error = str(result.get("fatal_error") or "").strip()
    if fatal_error:
        return False
    report_path = str(result.get("report_path") or "").strip()
    if not report_path:
        return True
    return int(result.get("return_code", 0)) != 0


def main() -> int:
    args = parse_args()
    batch_dir = resolve_path(args.batch_dir)
    output_root = resolve_path(args.output_root)
    batch_script = resolve_path(str(DEFAULT_BATCH_SCRIPT))
    report_path = resolve_path(args.report_path)
    progress_path = resolve_path(args.progress_path)
    lock_path = resolve_path(args.lock_path)

    acquire_lock(lock_path)

    try:
        end_batch = args.end_batch
        if args.auto_end:
            end_batch = find_last_available_batch_number(batch_dir)
            if end_batch <= 0:
                raise ValueError(f"No batch_XXX_urls.txt files were found in {batch_dir}.")
        if end_batch <= 0:
            raise ValueError("--end-batch must be greater than 0 unless --auto-end is used.")
        if end_batch < args.start_batch:
            raise ValueError("--end-batch must be greater than or equal to --start-batch.")

        results: list[dict[str, object]] = []
        write_range_progress(
            progress_path,
            status="starting",
            start_batch=args.start_batch,
            end_batch=end_batch,
        )

        for batch_number in range(args.start_batch, end_batch + 1):
            batch_id = batch_id_from_number(batch_number)
            batch_file = batch_dir / f"{batch_id}_urls.txt"
            write_range_progress(
                progress_path,
                status="running",
                start_batch=args.start_batch,
                end_batch=end_batch,
                current_batch=batch_number,
                current_batch_id=batch_id,
                current_batch_file=str(batch_file),
                last_result=results[-1] if results else None,
            )
            if not batch_file.exists():
                results.append(
                    {
                        "batch_file": str(batch_file),
                        "output_dir": "",
                        "return_code": -1,
                        "started_at": "",
                        "ended_at": "",
                        "report_path": "",
                        "succeeded": 0,
                        "failed": 0,
                        "error": "batch_file_missing",
                    }
                )
                if args.stop_on_error:
                    break
                continue

            output_dir = output_root / f"notegpt_exports_{batch_id}"
            if not args.rerun_completed and batch_is_completed(output_dir):
                existing_report = find_latest_report(output_dir)
                payload = load_report_payload(existing_report)
                result: dict[str, object] = {
                    "batch_file": str(batch_file),
                    "output_dir": str(output_dir),
                    "return_code": 0,
                    "started_at": "",
                    "ended_at": "",
                    "report_path": str(existing_report) if existing_report else "",
                    "skipped": True,
                    "skip_reason": "already_completed",
                }
                if payload:
                    result["succeeded"] = len(payload.get("succeeded", []))
                    result["failed"] = len(payload.get("failed", []))
                else:
                    result["succeeded"] = 0
                    result["failed"] = 0
                print(
                    f"[overnight] skipping {batch_id} because an existing report was found: "
                    f"{result['report_path']}"
                )
                results.append(result)
                write_range_progress(
                    progress_path,
                    status="running",
                    start_batch=args.start_batch,
                    end_batch=end_batch,
                    current_batch=batch_number,
                    current_batch_id=batch_id,
                    current_batch_file=str(batch_file),
                    last_result=result,
                )
                continue

            last_attempt = 0
            result: dict[str, object] = {}
            for attempt in range(1, max(args.max_batch_retries, 1) + 1):
                last_attempt = attempt
                print(f"[overnight] starting {batch_id} attempt={attempt} -> {output_dir}")
                result = run_one_batch(batch_script, batch_file, output_dir, args)
                result["attempt"] = attempt
                if not should_retry_batch(result):
                    break
                print(
                    f"[overnight] retrying {batch_id} because the child batch exited abnormally "
                    f"(rc={result['return_code']} report={result.get('report_path','') or 'missing'})."
                )
                time.sleep(3.0)
            results.append(result)
            write_range_progress(
                progress_path,
                status="running",
                start_batch=args.start_batch,
                end_batch=end_batch,
                current_batch=batch_number,
                current_batch_id=batch_id,
                current_batch_file=str(batch_file),
                last_result=result,
            )
            print(
                f"[overnight] finished {batch_id} rc={result['return_code']} "
                f"succeeded={result['succeeded']} failed={result['failed']} "
                f"attempts={last_attempt}"
            )

            if not result.get("report_path"):
                print(f"[overnight] stopping after {batch_id} because no batch report was written.")
                break

            if result.get("fatal_error"):
                print(f"[overnight] stopping after {batch_id} because a fatal error was recorded: {result['fatal_error']}")
                break

            if result["return_code"] != 0 and args.stop_on_error:
                break

            if batch_number < end_batch:
                time.sleep(args.sleep_between_batches)

        report_payload = {
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "start_batch": args.start_batch,
            "end_batch": end_batch,
            "results": results,
            "total_succeeded": sum(int(row.get("succeeded", 0)) for row in results),
            "total_failed": sum(int(row.get("failed", 0)) for row in results),
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        write_range_progress(
            progress_path,
            status="completed",
            start_batch=args.start_batch,
            end_batch=end_batch,
            current_batch=end_batch,
            current_batch_id=batch_id_from_number(end_batch),
            current_batch_file=str(batch_dir / f"{batch_id_from_number(end_batch)}_urls.txt"),
            last_result=results[-1] if results else None,
        )

        print(
            f"[overnight] report saved to {report_path} "
            f"(total_succeeded={report_payload['total_succeeded']} total_failed={report_payload['total_failed']})"
        )
        return 0
    finally:
        release_lock(lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
