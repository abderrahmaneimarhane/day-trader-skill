"""One-pass MT5 market scanner. It never lets AI bypass deterministic controls."""
import argparse
import datetime as dt
import json
import os
from .mt5_adapter import MT5Adapter
from .strategy import evaluate
from .ai_analyst import analyse_market
from .risk import size_position
from .execution import submit_market_order, ExecutionBlocked


def _daily_loss_guard(mt5, account, state_path):
    now = dt.datetime.now(dt.timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(start, now)
    if deals is None:
        raise RuntimeError("Cannot read today's deal history; fail closed")
    net = sum(float(d.profit) + float(d.commission) + float(d.swap) +
              float(getattr(d, "fee", 0.0)) for d in deals)
    day_start_balance = float(account.balance) - net
    drawdown = max(0.0, day_start_balance - float(account.equity))
    day_key = now.date().isoformat()
    state = {}
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
    if state.get("date") != day_key or state.get("server") != str(account.server) or state.get("login") != int(account.login):
        state = {"date": day_key, "server": str(account.server),
                 "login": int(account.login), "max_daily_loss_seen": 0.0}
    max_seen = max(float(state.get("max_daily_loss_seen", 0.0)), drawdown)
    state["max_daily_loss_seen"] = max_seen
    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    temp_path = state_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(temp_path, state_path)
    return max_seen


def run(config):
    adapter = MT5Adapter(config.get("terminal_path"))
    mt5 = adapter.mt5
    results = []
    try:
        account = adapter.connect()
        if not account.trade_allowed and config.get("execution_mode") == "automatic_live":
            raise RuntimeError("Account trading is disabled")
        positions = mt5.positions_get()
        if positions is None:
            raise RuntimeError("Cannot read open positions; fail closed")
        daily_loss = _daily_loss_guard(mt5, account, config.get("state_path", "mt5_openai/state.json"))
        active_count = len(positions)
        for symbol in config.get("symbols", []):
            try:
                if active_count >= int(config.get("max_open_positions", 1)):
                    results.append({"symbol": symbol, "status": "SKIP",
                                    "reason": "Maximum open positions reached"})
                    continue
                if any(p.symbol == symbol for p in positions):
                    results.append({"symbol": symbol, "status": "SKIP",
                                    "reason": "Position already open for this symbol"})
                    continue
                rates = adapter.closed_bars(symbol, config.get("timeframe", "M15"), 250)
                strategy_cfg = config.get("strategy", {})
                candidate = evaluate(rates, strategy_cfg)
                if candidate["signal"] == "none":
                    results.append({"symbol": symbol, "status": "NO_SIGNAL",
                                    "reason": candidate["reason"]})
                    continue
                tick, info = mt5.symbol_info_tick(symbol), mt5.symbol_info(symbol)
                if tick is None or info is None or info.point <= 0:
                    raise RuntimeError("Quote or symbol metadata unavailable")
                spread = (float(tick.ask) - float(tick.bid)) / float(info.point)
                if spread > float(config.get("max_spread_points", 35)):
                    results.append({"symbol": symbol, "status": "BLOCK",
                                    "reason": "Spread exceeds configured maximum",
                                    "spread_points": spread})
                    continue
                side = candidate["signal"]
                entry = float(tick.ask if side == "buy" else tick.bid)
                snapshot = {"symbol": symbol, "timeframe": config.get("timeframe", "M15"),
                            "closed_bar_count": len(rates), "last_closed_close": float(rates[-1]["close"]),
                            "spread_points": spread, "candidate": candidate}
                context = analyse_market(snapshot, config.get("model", "gpt-4.1-mini"))
                if context["confidence"] < float(config.get("ai_min_confidence", 0.65)):
                    results.append({"symbol": symbol, "status": "AI_FILTER",
                                    "reason": "AI confidence below threshold", "ai": context})
                    continue
                if context["bias"] != side or context["regime"] == "unclear" or context["risk_flags"]:
                    results.append({"symbol": symbol, "status": "AI_FILTER",
                                    "reason": "AI context does not confirm candidate", "ai": context})
                    continue
                order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
                sizing = size_position(mt5, symbol, order_type, entry,
                                       candidate["stop_loss"], float(account.equity),
                                       float(config.get("risk_per_trade", 0.02)),
                                       daily_loss, float(config.get("max_daily_loss_pct", 0.04)))
                if not sizing.approved:
                    results.append({"symbol": symbol, "status": "RISK_BLOCK",
                                    "reason": sizing.reason, "risk": sizing.__dict__})
                    continue
                outcome = submit_market_order(
                    mt5, config, account, symbol, side, sizing.volume,
                    candidate["stop_loss"], candidate["take_profit"], sizing,
                    config.get("max_deviation_points", 20))
                results.append({"symbol": symbol, "status": outcome["status"],
                                "signal": candidate, "ai": context,
                                "risk": sizing.__dict__, "execution": outcome})
                if outcome["status"] in ("PAPER_PREVIEW", "SUBMITTED"):
                    active_count += 1
            except ExecutionBlocked as exc:
                results.append({"symbol": symbol, "status": "EXECUTION_BLOCK",
                                "reason": str(exc)})
            except Exception as exc:
                results.append({"symbol": symbol, "status": "ERROR",
                                "reason": type(exc).__name__ + ": " + str(exc)})
        return {"account": {"login": int(account.login), "server": str(account.server),
                            "currency": str(account.currency), "equity": float(account.equity)},
                "daily_realized_loss": daily_loss, "execution_mode": config.get("execution_mode", "paper"),
                "results": results}
    finally:
        adapter.shutdown()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="mt5_openai/config.json")
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as fh:
        config = json.load(fh)
    print(json.dumps(run(config), indent=2, default=str))


if __name__ == "__main__":
    main()
