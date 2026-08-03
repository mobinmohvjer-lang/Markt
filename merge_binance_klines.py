#!/usr/bin/env python3
"""
merge_binance_klines.py

Merge Binance monthly BTCUSDT 1h kline ZIP archives (as downloaded from
https://data.binance.vision) into a single, sorted, de-duplicated CSV,
and report any gaps in the hourly time series.

Usage
-----
    python merge_binance_klines.py /path/to/folder/with/zips
    python merge_binance_klines.py /path/to/folder/with/zips -o BTCUSDT_1h_full.csv

Notes
-----
- Binance kline ZIPs contain a single headerless CSV with 12 columns:
  open_time, open, high, low, close, volume, close_time, quote_volume,
  trades, taker_buy_base, taker_buy_quote, ignore
- The download folder from data.binance.vision also typically contains
  ".CHECKSUM" files (sometimes themselves zipped). Those are identified
  and skipped automatically because they don't contain a CSV member --
  the script never relies on filename patterns like "CHECKSUM" alone.
- Binance changed its exported timestamp precision from milliseconds to
  microseconds starting with data from January 2025 onward. This script
  detects the unit per-file (by magnitude) and normalizes everything to
  milliseconds so old and new months merge correctly.
- CSVs are read directly out of the ZIP archives in memory; nothing is
  extracted to disk.
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import zipfile
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

# Column layout for Binance spot kline data.
COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_base",
    "taker_buy_quote",
    "ignore",
]

# Some newer Binance exports include a header row ("open_time,open,...")
# while older ones don't. We detect this per-file rather than assuming.
HEADER_SENTINEL = "open_time"

ONE_HOUR_MS = 3_600_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Step 1: Discover ZIP files
# ----------------------------------------------------------------------

def find_zip_files(folder: Path) -> list[Path]:
    """Return every .zip file directly under `folder` (recursively)."""
    zip_files = sorted(folder.rglob("*.zip"))
    if not zip_files:
        log.warning("No .zip files found under %s", folder)
    return zip_files


# ----------------------------------------------------------------------
# Step 2: Read the CSV out of each ZIP without extracting to disk
# ----------------------------------------------------------------------

def read_klines_from_zip(zip_path: Path) -> pd.DataFrame | None:
    """
    Open a ZIP archive in memory and load its kline CSV into a DataFrame.

    Returns None (and logs a reason) if the archive doesn't contain a CSV
    kline file -- this is how CHECKSUM archives (which contain a .CHECKSUM
    text file, not a .csv) are filtered out, without relying on filename
    patterns.
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]

            if not csv_names:
                log.info("Skipping %s (no CSV inside -- likely a checksum file)", zip_path.name)
                return None

            if len(csv_names) > 1:
                log.warning(
                    "%s contains multiple CSVs (%s); using the first one",
                    zip_path.name, csv_names,
                )

            with zf.open(csv_names[0]) as f:
                raw = f.read()

        # Detect whether the CSV has a header row.
        first_line = raw.split(b"\n", 1)[0].decode("utf-8", errors="ignore")
        has_header = HEADER_SENTINEL in first_line

        df = pd.read_csv(
            io.BytesIO(raw),
            header=0 if has_header else None,
            names=None if has_header else COLUMNS,
        )
        if has_header:
            df.columns = [c.strip().lower() for c in df.columns]

        # Keep only the columns we need; some exports may have fewer/more.
        missing = set(["open_time", "open", "high", "low", "close", "volume",
                       "close_time"]) - set(df.columns)
        if missing:
            log.warning("%s is missing expected columns %s; skipping", zip_path.name, missing)
            return None

        _normalize_timestamp_unit(df, zip_path.name)

        return df

    except zipfile.BadZipFile:
        log.warning("Skipping %s (not a valid ZIP file)", zip_path.name)
        return None
    except Exception as exc:  # noqa: BLE001 - we want to log & continue, not crash the batch
        log.warning("Skipping %s (failed to read: %s)", zip_path.name, exc)
        return None


# Binance switched from millisecond to microsecond timestamps for exports
# starting in Jan 2025. A millisecond epoch value for any date in Binance's
# history (2017-today) has 13 digits; a microsecond value has 16. Anything
# clearly >= 1e15 is treated as microseconds and scaled down to ms.
MICROSECOND_THRESHOLD = 1_000_000_000_000_000  # 1e15


def _normalize_timestamp_unit(df: pd.DataFrame, source_name: str) -> None:
    """Detect per-file timestamp precision (ms vs µs) and convert to ms in-place."""
    sample = df["open_time"].iloc[0]
    if sample >= MICROSECOND_THRESHOLD:
        df["open_time"] = (df["open_time"] // 1000).astype("int64")
        if "close_time" in df.columns:
            df["close_time"] = (df["close_time"] // 1000).astype("int64")
        log.info("%s: detected microsecond timestamps, converted to milliseconds", source_name)


# ----------------------------------------------------------------------
# Step 3-5: Merge, sort, de-duplicate
# ----------------------------------------------------------------------

def build_merged_dataset(zip_files: list[Path]) -> pd.DataFrame:
    """Read every zip file and concatenate the results into one DataFrame."""
    frames = []
    for zp in zip_files:
        df = read_klines_from_zip(zp)
        if df is not None and not df.empty:
            frames.append(df)

    if not frames:
        raise RuntimeError("No valid kline data could be read from the given folder.")

    merged = pd.concat(frames, ignore_index=True)

    # Ensure numeric/int types for the timestamp columns (guards against
    # anything read in as string due to inconsistent headers).
    merged["open_time"] = pd.to_numeric(merged["open_time"], errors="coerce")
    merged = merged.dropna(subset=["open_time"])
    merged["open_time"] = merged["open_time"].astype("int64")

    before = len(merged)

    # Sort by Open Time ascending.
    merged = merged.sort_values("open_time", kind="mergesort").reset_index(drop=True)

    # Remove exact duplicate rows first, then duplicate open_time rows
    # (keeping the first occurrence) in case the same candle appears with
    # slightly different trailing stats across overlapping monthly files.
    merged = merged.drop_duplicates()
    merged = merged.drop_duplicates(subset="open_time", keep="first")
    merged = merged.reset_index(drop=True)

    removed = before - len(merged)
    if removed:
        log.info("Removed %d duplicate row(s)", removed)

    return merged


# ----------------------------------------------------------------------
# Step 6: Verify continuity of the 1h series
# ----------------------------------------------------------------------

def report_missing_candles(df: pd.DataFrame) -> None:
    """Log a report of any missing 1-hour candles based on open_time gaps."""
    diffs = df["open_time"].diff().iloc[1:]  # skip the first NaN
    gaps = diffs[diffs != ONE_HOUR_MS]

    if gaps.empty:
        log.info("Continuity check passed: no missing 1h candles found.")
        return

    log.warning("Continuity check found %d gap(s) in the data:", len(gaps))
    total_missing = 0
    for idx in gaps.index:
        prev_time = df.loc[idx - 1, "open_time"]
        curr_time = df.loc[idx, "open_time"]
        gap_ms = curr_time - prev_time
        missing_candles = int(gap_ms // ONE_HOUR_MS) - 1

        prev_ts = pd.to_datetime(prev_time, unit="ms", utc=True)
        curr_ts = pd.to_datetime(curr_time, unit="ms", utc=True)

        if gap_ms < ONE_HOUR_MS:
            log.warning(
                "  Irregular spacing (< 1h) between %s and %s (%.0f ms)",
                prev_ts, curr_ts, gap_ms,
            )
        else:
            total_missing += missing_candles
            log.warning(
                "  Missing %d candle(s) between %s and %s",
                missing_candles, prev_ts, curr_ts,
            )

    if total_missing:
        log.warning("Total missing candles across all gaps: %d", total_missing)


# ----------------------------------------------------------------------
# Step 7: Save output
# ----------------------------------------------------------------------

def save_dataset(df: pd.DataFrame, output_path: Path) -> None:
    df.to_csv(output_path, index=False)
    log.info("Saved %d rows to %s", len(df), output_path)


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge Binance monthly BTCUSDT 1h kline ZIP files into one CSV."
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing the downloaded Binance ZIP files.",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("BTCUSDT_1h_full.csv"),
        help="Output CSV path (default: BTCUSDT_1h_full.csv, written in the current directory).",
    )
    args = parser.parse_args()

    if not args.folder.is_dir():
        log.error("Folder not found: %s", args.folder)
        sys.exit(1)

    zip_files = find_zip_files(args.folder)
    if not zip_files:
        sys.exit(1)

    log.info("Found %d ZIP file(s) under %s", len(zip_files), args.folder)

    merged = build_merged_dataset(zip_files)
    log.info("Merged dataset spans %d rows after sorting/dedup", len(merged))

    report_missing_candles(merged)

    save_dataset(merged, args.output)


if __name__ == "__main__":
    main()
