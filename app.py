"""
Original Base Candle Strategy - Python Version
Converted from Pine Script v5 for use with Bitcoin (BTC/USDT)
Designed to run on Render via HTTP requests as part of a larger workflow.

Requirements:
    pip install ccxt pandas numpy flask

Usage:
    Run as Flask API -> POST /signal with OHLCV data
    Or call get_signal() directly with a DataFrame
"""

import pandas as pd
import numpy as np
from flask import Flask, request, jsonify

app = Flask(__name__)

# ─── Configuration ──────────────────────────────────────────────────────────
PIP_SIZE         = 0.01        # For BTC you may want to adjust (e.g. 1.0 USD)
BREAK_EVEN_PIPS  = 20 * PIP_SIZE
TRAIL_STEP_PIPS  = 50 * PIP_SIZE
TRAIL_PROFIT_PIPS= 45 * PIP_SIZE

# ─── Heikin-Ashi Calculation ─────────────────────────────────────────────────
def compute_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Heikin-Ashi candles from standard OHLCV DataFrame.
    Input columns: open, high, low, close
    """
    ha = pd.DataFrame(index=df.index)
    ha["close"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ha["open"]  = 0.0

    # First HA open = midpoint of first real candle
    ha.iloc[0, ha.columns.get_loc("open")] = (df["open"].iloc[0] + df["close"].iloc[0]) / 2

    for i in range(1, len(ha)):
        ha.iloc[i, ha.columns.get_loc("open")] = (
            ha.iloc[i - 1]["open"] + ha.iloc[i - 1]["close"]
        ) / 2

    ha["high"]  = pd.concat([df["high"], ha["open"], ha["close"]], axis=1).max(axis=1)
    ha["low"]   = pd.concat([df["low"],  ha["open"], ha["close"]], axis=1).min(axis=1)

    return ha

# ─── Signal Detection ────────────────────────────────────────────────────────
def get_signal(df: pd.DataFrame) -> dict:
    """
    Analyze the last N candles and return a trading signal.

    Args:
        df: DataFrame with columns [open, high, low, close, volume]
            Must have at least 4 rows (base + c1 + c2 + current)

    Returns:
        dict with keys:
            signal       : "BUY" | "SELL" | "NONE"
            base_high    : float
            base_low     : float
            stop_loss    : float
            entry_price  : float (close of current candle)
            inside_box   : bool
    """
    if len(df) < 4:
        return {"error": "Need at least 4 candles"}

    ha = compute_heikin_ashi(df)

    # Pine Script indices (bar_index):
    #   [3] = base candle  (4 bars ago from current)
    #   [2] = c1           (3 bars ago)
    #   [1] = c2           (2 bars ago)
    #   [0] = current candle
    base_high = ha["high"].iloc[-4]
    base_low  = ha["low"].iloc[-4]

    c1_high   = ha["high"].iloc[-3]
    c1_low    = ha["low"].iloc[-3]

    c2_high   = ha["high"].iloc[-2]
    c2_low    = ha["low"].iloc[-2]

    current_close = ha["close"].iloc[-1]

    # Inside condition: both c1 and c2 are inside the base candle range
    inside = (
        c1_high <= base_high and c1_low >= base_low and
        c2_high <= base_high and c2_low >= base_low
    )

    signal     = "NONE"
    stop_loss  = None

    if inside:
        if current_close > base_high:
            signal    = "BUY"
            stop_loss = base_low
        elif current_close < base_low:
            signal    = "SELL"
            stop_loss = base_high

    return {
        "signal":      signal,
        "base_high":   round(base_high, 2),
        "base_low":    round(base_low,  2),
        "stop_loss":   round(stop_loss, 2) if stop_loss is not None else None,
        "entry_price": round(current_close, 2),
        "inside_box":  inside,
    }

# ─── Stop Loss Manager ───────────────────────────────────────────────────────
def update_stop_loss(
    position_side: str,   # "BUY" or "SELL"
    avg_entry:     float,
    current_price: float,
    current_sl:    float,
) -> float:
    """
    Apply Break-Even and Trailing Stop logic.

    Returns updated stop_loss value.
    """
    sl = current_sl

    if position_side == "BUY":
        pnl = current_price - avg_entry

        # Break-Even: move SL to entry after 20 pips profit
        if pnl >= BREAK_EVEN_PIPS:
            sl = max(sl, avg_entry)

        # Trailing Stop: after 50 pips profit, trail 45 pips behind price
        if pnl >= TRAIL_STEP_PIPS:
            trail_sl = current_price - TRAIL_PROFIT_PIPS
            sl = max(sl, trail_sl)

    elif position_side == "SELL":
        pnl = avg_entry - current_price

        # Break-Even
        if pnl >= BREAK_EVEN_PIPS:
            sl = min(sl, avg_entry)

        # Trailing Stop
        if pnl >= TRAIL_STEP_PIPS:
            trail_sl = current_price + TRAIL_PROFIT_PIPS
            sl = min(sl, trail_sl)

    return round(sl, 2)

# ─── Flask HTTP API ──────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/signal", methods=["POST"])
def signal_endpoint():
    """
    POST /signal
    Body (JSON):
    {
        "candles": [
            {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            ...  // at least 4 candles, newest last
        ]
    }

    Returns:
    {
        "signal": "BUY" | "SELL" | "NONE",
        "base_high": float,
        "base_low": float,
        "stop_loss": float | null,
        "entry_price": float,
        "inside_box": bool
    }
    """
    data = request.get_json(force=True)
    if not data or "candles" not in data:
        return jsonify({"error": "Missing 'candles' in request body"}), 400

    try:
        df = pd.DataFrame(data["candles"])
        required_cols = {"open", "high", "low", "close"}
        if not required_cols.issubset(df.columns):
            return jsonify({"error": f"Candles must include columns: {required_cols}"}), 400

        result = get_signal(df)
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/update_sl", methods=["POST"])
def update_sl_endpoint():
    """
    POST /update_sl
    Body (JSON):
    {
        "position_side": "BUY" | "SELL",
        "avg_entry": float,
        "current_price": float,
        "current_sl": float
    }

    Returns:
    {
        "updated_sl": float
    }
    """
    data = request.get_json(force=True)
    required = {"position_side", "avg_entry", "current_price", "current_sl"}
    if not required.issubset(data or {}):
        return jsonify({"error": f"Missing fields: {required}"}), 400

    try:
        new_sl = update_stop_loss(
            position_side = data["position_side"],
            avg_entry     = float(data["avg_entry"]),
            current_price = float(data["current_price"]),
            current_sl    = float(data["current_sl"]),
        )
        return jsonify({"updated_sl": new_sl})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Entry Point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Local dev — Render uses gunicorn automatically
    app.run(host="0.0.0.0", port=5000, debug=True)
