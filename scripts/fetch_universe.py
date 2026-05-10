"""Fetch the Darvas Box Scanner universe and write data/universe.json.

Pure server-side fetch via yfinance — no CORS, no rate-limit cliffs, no
proxy chain. The static JSON output is what the dashboard reads at load
time, replacing the previous in-browser query1.finance.yahoo.com chain.

Run:
    pip install -r requirements.txt
    python scripts/fetch_universe.py

A GitHub Actions workflow runs this daily at 22:00 UTC after US market
close. The output JSON is committed to the repo and served via Pages.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


# ── Universe (must match the array in index.html) ────────────────────
UNIVERSE: list[str] = [
    "SPY",
    # Tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
    "AVGO", "AMD", "CRM", "ORCL", "ADBE",
    # Health
    "LLY", "UNH", "JNJ", "MRK", "ABBV", "PFE",
    # Financials
    "JPM", "V", "MA", "BAC", "GS", "BLK",
    # Energy
    "XOM", "CVX", "COP",
    # Consumer
    "HD", "MCD", "COST", "PG", "KO", "WMT",
    # Industrials
    "CAT", "HON", "GE",
    # Utilities
    "NEE", "SO", "DUK",
    # Comm
    "NFLX", "DIS", "CMCSA",
]

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "universe.json"
PERIOD = "5y"
INTERVAL = "1d"
MIN_ROWS = 100  # match the existing JS guard: data.length > 100 → keep


def fetch_one(ticker: str) -> list[dict]:
    """Fetch OHLCV for a single ticker, normalise to the dashboard's shape."""
    df = yf.Ticker(ticker).history(
        period=PERIOD, interval=INTERVAL, auto_adjust=False
    )
    if df.empty:
        return []
    df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
    rows: list[dict] = []
    for ts, row in df.iterrows():
        # Skip incomplete rows — the dashboard's guard does the same.
        if pd.isna(row.get("Close")) or pd.isna(row.get("High")) or \
                pd.isna(row.get("Low")) or pd.isna(row.get("Volume")):
            continue
        rows.append({
            "date": ts.strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 4) if pd.notna(row.get("Open")) else None,
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]),
        })
    return rows


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    tickers: dict[str, list[dict]] = {}
    failures: list[str] = []

    for i, t in enumerate(UNIVERSE, start=1):
        try:
            rows = fetch_one(t)
            if len(rows) < MIN_ROWS:
                print(f"[{i:>2}/{len(UNIVERSE)}] {t}: insufficient rows ({len(rows)}), skipping")
                failures.append(t)
                continue
            tickers[t] = rows
            print(f"[{i:>2}/{len(UNIVERSE)}] {t}: {len(rows)} rows  "
                  f"({rows[0]['date']} → {rows[-1]['date']})")
        except Exception as exc:
            print(f"[{i:>2}/{len(UNIVERSE)}] {t}: FAILED — {exc}")
            failures.append(t)

    if "SPY" not in tickers:
        raise SystemExit("SPY missing — refusing to write a universe without the regime anchor.")
    if len(tickers) < 30:
        raise SystemExit(
            f"Only {len(tickers)}/{len(UNIVERSE)} tickers fetched — refusing to overwrite "
            "with a sparse universe. Failures: " + ", ".join(failures)
        )

    payload = {
        "schema_version": 1,
        "as_of_utc": now_utc,
        "period": PERIOD,
        "interval": INTERVAL,
        "ticker_count": len(tickers),
        "failures": failures,
        "tickers": tickers,
    }

    OUT_PATH.write_text(json.dumps(payload), encoding="utf-8")
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"\n[emit] {OUT_PATH}: {len(tickers)} tickers, {size_kb:,.1f} KB")
    if failures:
        print(f"[warn] {len(failures)} ticker(s) failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
