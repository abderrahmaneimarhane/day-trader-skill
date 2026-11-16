"""Public Yahoo Finance chart adapter for Android research mode.

This adapter is for market research only. Quotes are not Exness executable
prices, broker symbol names, or contract specifications.
"""
from datetime import datetime, timezone
from urllib.parse import quote
import requests

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

def fetch_closed_bars(symbol, interval="15m", range_="30d", timeout=15):
    """Fetch OHLCV bars and conservatively discard the newest possibly open bar."""
    url = f"{BASE_URL}/{quote(symbol, safe='')}"
    response = requests.get(
        url, params={"interval": interval, "range": range_, "includePrePost": "false"},
        headers={"User-Agent": "Mozilla/5.0 (compatible; AndroidResearchAgent/1.0)"},
        timeout=timeout,
    )
    response.raise_for_status()
    chart = response.json().get("chart", {})
    if chart.get("error"):
        raise RuntimeError("Market-data provider returned an error")
    results = chart.get("result") or []
    if not results:
        raise RuntimeError(f"No market data returned for {symbol}")
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
    bars = []
    for i, timestamp in enumerate(timestamps):
        try:
            values = {
                "open": quote_data["open"][i], "high": quote_data["high"][i],
                "low": quote_data["low"][i], "close": quote_data["close"][i],
                "tick_volume": (quote_data.get("volume") or [None] * len(timestamps))[i],
                "time": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
            }
            if any(value is None for key, value in values.items()
                   if key not in ("tick_volume", "time")):
                continue
            for key in ("open", "high", "low", "close"):
                values[key] = float(values[key])
            bars.append(values)
        except (IndexError, TypeError, ValueError, OverflowError):
            continue
    if len(bars) > 1:
        bars = bars[:-1]
    if len(bars) < 60:
        raise RuntimeError(f"Insufficient closed history for {symbol}: {len(bars)} bars")
    return bars
