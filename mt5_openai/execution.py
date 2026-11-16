"""Guarded MT5 execution. Never call this module from the AI analyst."""
import os


LIVE_ARM_VALUE = "I_UNDERSTAND_LIVE_TRADING_RISK"
ACCEPTED_RETCODES = {"TRADE_RETCODE_DONE", "TRADE_RETCODE_PLACED", "TRADE_RETCODE_DONE_PARTIAL"}


class ExecutionBlocked(RuntimeError):
    pass


def _filling_type(mt5, symbol_mode):
    """Translate SYMBOL_FILLING_* flags to ORDER_FILLING_* enum values."""
    if symbol_mode & getattr(mt5, "SYMBOL_FILLING_IOC", 2):
        return mt5.ORDER_FILLING_IOC
    if symbol_mode & getattr(mt5, "SYMBOL_FILLING_FOK", 1):
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def submit_market_order(mt5, config, account, symbol, side, volume, stop_loss,
                        take_profit, risk_decision, deviation=None):
    """Paper mode returns a preview. Live mode requires every independent gate."""
    if not risk_decision or not getattr(risk_decision, "approved", False):
        raise ExecutionBlocked("Risk engine did not approve this trade")
    if symbol not in config.get("symbols", []):
        raise ExecutionBlocked("Symbol is not allow-listed")
    if side not in ("buy", "sell") or volume <= 0 or stop_loss <= 0 or take_profit <= 0:
        raise ExecutionBlocked("Invalid order parameters")

    order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if tick is None or info is None or not info.trade_mode:
        raise ExecutionBlocked("Symbol unavailable or trading disabled")
    price = float(tick.ask if side == "buy" else tick.bid)
    if side == "buy" and not (stop_loss < price < take_profit):
        raise ExecutionBlocked("Buy order requires SL < price < TP")
    if side == "sell" and not (take_profit < price < stop_loss):
        raise ExecutionBlocked("Sell order requires TP < price < SL")

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": price,
        "sl": float(stop_loss),
        "tp": float(take_profit),
        "deviation": int(deviation if deviation is not None else config.get("max_deviation_points", 20)),
        "magic": int(config.get("magic_number", 611161)),
        "comment": "day-trader-skill-v2",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling_type(mt5, info.filling_mode)
    }

    checked = mt5.order_check(request)
    if checked is None or int(checked.retcode) != 0:
        raise ExecutionBlocked("MT5 order_check failed: " + str(checked))
    mode = config.get("execution_mode", "paper")
    if mode == "paper":
        return {"status": "PAPER_PREVIEW", "request": request,
                "estimated_loss": float(risk_decision.estimated_loss)}
    if mode != "automatic_live":
        raise ExecutionBlocked("Unknown execution mode; fail closed")
    if config.get("live_enabled") is not True:
        raise ExecutionBlocked("live_enabled must be explicitly true")
    if os.environ.get("MT5_LIVE_ARMED") != LIVE_ARM_VALUE:
        raise ExecutionBlocked("Live arming environment variable is missing")
    if int(account.login) not in [int(x) for x in config.get("account_allowlist", [])]:
        raise ExecutionBlocked("Current account login is not allow-listed")
    if str(account.server) not in config.get("server_allowlist", []):
        raise ExecutionBlocked("Current broker server is not allow-listed")
    if not bool(account.trade_allowed):
        raise ExecutionBlocked("MT5 account does not allow trading")
    if not bool(getattr(account, "trade_expert", True)):
        raise ExecutionBlocked("Expert trading is disabled on this account")

    result = mt5.order_send(request)
    if result is None:
        raise ExecutionBlocked("MT5 order_send returned no result")
    accepted = {getattr(mt5, name, -1) for name in
                ("TRADE_RETCODE_DONE", "TRADE_RETCODE_PLACED", "TRADE_RETCODE_DONE_PARTIAL")}
    if int(result.retcode) not in accepted:
        raise ExecutionBlocked("MT5 rejected order: " + str(result))
    return {"status": "SUBMITTED", "order": result._asdict(), "request": request}
