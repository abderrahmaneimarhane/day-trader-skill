"""Deterministic indicator baseline for research; not a validated strategy."""
import math


def _ema(values, period):
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1.0)
    out = [sum(values[:period]) / period]
    for value in values[period:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def _rsi(values, period=14):
    if len(values) <= period:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _atr(rates, period=14):
    if len(rates) <= period:
        return None
    trs = []
    for i in range(1, len(rates)):
        high, low = float(rates[i]["high"]), float(rates[i]["low"])
        prev_close = float(rates[i - 1]["close"])
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs[-period:]) / period


def evaluate(rates, config):
    """Return a candidate only on a fresh EMA cross; never submits an order."""
    closes = [float(row["close"]) for row in rates]
    fast_n = int(config.get("ema_fast", 20))
    slow_n = int(config.get("ema_slow", 50))
    rsi_n = int(config.get("rsi_period", 14))
    atr_n = int(config.get("atr_period", 14))
    fast, slow = _ema(closes, fast_n), _ema(closes, slow_n)
    atr, rsi = _atr(rates, atr_n), _rsi(closes, rsi_n)
    if len(fast) < 2 or len(slow) < 2 or atr is None or rsi is None:
        return {"signal": "none", "reason": "Insufficient indicator history"}
    # EMA arrays start at different offsets; align their final two observations.
    f_prev, f_now = fast[-2], fast[-1]
    s_prev, s_now = slow[-2], slow[-1]
    side = "buy" if f_prev <= s_prev and f_now > s_now else (
        "sell" if f_prev >= s_prev and f_now < s_now else "none")
    if side == "none":
        return {"signal": "none", "reason": "No confirmed EMA crossover",
                "rsi": rsi, "atr": atr}
    if (side == "buy" and rsi >= 70) or (side == "sell" and rsi <= 30):
        return {"signal": "none", "reason": "RSI extreme filter", "rsi": rsi, "atr": atr}
    close = closes[-1]
    multiple = float(config.get("stop_atr_multiple", 1.5))
    rr = float(config.get("reward_risk", 2.0))
    distance = atr * multiple
    stop = close - distance if side == "buy" else close + distance
    target = close + distance * rr if side == "buy" else close - distance * rr
    if not all(math.isfinite(x) and x > 0 for x in (close, stop, target)):
        return {"signal": "none", "reason": "Invalid calculated prices"}
    return {"signal": side, "entry_reference": close, "stop_loss": stop,
            "take_profit": target, "rsi": rsi, "atr": atr,
            "strategy": "EMA crossover + RSI filter + ATR stop"}
