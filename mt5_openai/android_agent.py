"""Android-compatible research scanner: proposes trades, never places orders."""
import argparse
import datetime as dt
import json
import os
import uuid

from .android_market_data import fetch_closed_bars
from .strategy import evaluate
from .android_ai_analyst import analyse_market


def _trend_context(symbol, interval, range_):
    bars = fetch_closed_bars(symbol, interval=interval, range_=range_)
    closes = [float(row["close"]) for row in bars]
    sma20, sma50 = sum(closes[-20:]) / 20, sum(closes[-50:]) / 50
    trend = "bullish" if sma20 > sma50 else "bearish" if sma20 < sma50 else "neutral"
    return {"last_closed_close": closes[-1], "sma20": sma20,
            "sma50": sma50, "trend": trend}


def _load_state(path):
    if not os.path.exists(path):
        return {"proposals": []}
    with open(path, encoding="utf-8") as handle:
        state = json.load(handle)
    if not isinstance(state, dict) or not isinstance(state.get("proposals"), list):
        raise RuntimeError("Invalid Android agent state file")
    return state


def _save_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    os.replace(temporary, path)


def set_decision(proposal, decision):
    """Approval means manual review in MT5, never execution."""
    if decision not in ("approved_for_manual_review", "rejected"):
        raise ValueError("Unsupported proposal decision")
    if proposal.get("status") != "pending":
        raise ValueError("Proposal has already been decided")
    proposal["status"] = decision
    proposal["decision_time"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return proposal


def scan(config):
    state_path = config.get("state_path", "mt5_openai/android_state.json")
    state = _load_state(state_path)
    existing_keys = {(p.get("provider_symbol"), p.get("signal_bar_time"), p.get("side"))
                     for p in state["proposals"]}
    results = []
    for label, spec in config.get("markets", {}).items():
        try:
            symbol = spec["symbol"]
            bars = fetch_closed_bars(symbol, config.get("interval", "15m"),
                                     config.get("history_range", "30d"))
            candidate = evaluate(bars, config.get("strategy", {}))
            if candidate["signal"] == "none":
                results.append({"market": label, "status": "NO_SIGNAL",
                                "reason": candidate["reason"]})
                continue
            higher = {}
            for item in config.get("context", [
                {"name": "H1", "interval": "1h", "range": "3mo"},
                {"name": "D1", "interval": "1d", "range": "1y"},
            ]):
                higher[item["name"]] = _trend_context(symbol, item["interval"], item["range"])
            side = candidate["signal"]
            snapshot = {
                "market": label, "provider_symbol": symbol,
                "timeframe": config.get("interval", "15m"),
                "last_closed_bar": bars[-1]["time"],
                "last_closed_close": bars[-1]["close"],
                "candidate": candidate, "higher_timeframe_context": higher,
                "data_source": "Yahoo Finance chart API; indicative, not broker quotes",
            }
            ai = analyse_market(snapshot, config.get("model", "gpt-4.1-mini"))
            expected_bias = "bullish" if side == "buy" else "bearish"
            if (ai.get("bias") != expected_bias or ai.get("regime") == "unclear" or
                    ai.get("risk_flags") or float(ai.get("confidence", 0)) <
                    float(config.get("ai_min_confidence", 0.65))):
                results.append({"market": label, "status": "AI_FILTER",
                                "reason": "AI context did not confirm candidate", "ai": ai})
                continue
            key = (symbol, bars[-1]["time"], side)
            if key in existing_keys:
                results.append({"market": label, "status": "DUPLICATE",
                                "reason": "This closed-bar setup was already recorded"})
                continue
            risk_fraction = min(float(config.get("risk_per_trade", 0.02)), 0.02)
            reference_equity = float(config.get("reference_equity", 10.0))
            proposal = {
                "id": str(uuid.uuid4()),
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "market": label, "provider_symbol": symbol, "side": side,
                "timeframe": config.get("interval", "15m"),
                "signal_bar_time": bars[-1]["time"],
                "entry_reference": candidate["entry_reference"],
                "stop_loss": candidate["stop_loss"],
                "take_profit": candidate["take_profit"],
                "reward_risk": config.get("strategy", {}).get("reward_risk", 2.0),
                "risk_fraction": risk_fraction, "reference_equity": reference_equity,
                "max_planned_loss": reference_equity * risk_fraction,
                "lot_size": None,
                "lot_size_note": "Not calculated: broker contract specifications and live executable quote are unavailable in Android research mode.",
                "strategy": candidate, "ai": ai, "higher_timeframe_context": higher,
                "data_warning": "Indicative Yahoo Finance prices only. Verify exact Exness symbol, live quote, spread, contract size, margin and minimum volume in MT5 before placing any order.",
                "status": "pending", "execution": "MANUAL_ONLY",
            }
            state["proposals"].insert(0, proposal)
            existing_keys.add(key)
            results.append({"market": label, "status": "PROPOSAL_CREATED",
                            "proposal_id": proposal["id"]})
        except Exception as exc:
            results.append({"market": label, "status": "ERROR",
                            "reason": type(exc).__name__ + ": " + str(exc)})
    state["proposals"] = state["proposals"][:100]
    _save_state(state_path, state)
    return {"mode": "ANDROID_SEMI_AUTOMATIC_MANUAL_EXECUTION",
            "live_orders_enabled": False, "results": results,
            "pending_proposals": sum(1 for p in state["proposals"]
                                     if p.get("status") == "pending")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="mt5_openai/android_config.json")
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as handle:
        config = json.load(handle)
    print(json.dumps(scan(config), indent=2))


if __name__ == "__main__":
    main()
