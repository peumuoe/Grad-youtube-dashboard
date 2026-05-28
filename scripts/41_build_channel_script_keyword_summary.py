from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.app.streamlit_app import _extract_script_keyword_rows, normalize_channel_column


INPUT_PATH = PROJECT_ROOT / "outputs" / "tables" / "topic_video_assignments_script.csv"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "tables" / "channel_script_keyword_summary.csv"


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    df = normalize_channel_column(pd.read_csv(INPUT_PATH, low_memory=False))
    if df.empty or "channel_name" not in df.columns:
        raise ValueError("Input data must include a non-empty channel_name column.")

    rows: list[dict[str, object]] = []
    for channel_name in sorted(df["channel_name"].dropna().astype(str).str.strip().unique()):
        channel_df = df[df["channel_name"] == channel_name].copy()
        keyword_rows = _extract_script_keyword_rows(channel_df, limit=15)
        total = sum(int(item["count"]) for item in keyword_rows) or 1
        for rank, item in enumerate(keyword_rows, start=1):
            count = int(item["count"])
            rows.append(
                {
                    "channel_name": channel_name,
                    "keyword": str(item["keyword"]),
                    "count": count,
                    "share_pct": round(count / total * 100.0, 1),
                    "rank": rank,
                }
            )

    summary_df = pd.DataFrame(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"Saved {len(summary_df)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
