"""Deterministic MT5 risk sizing. No AI decisions and no order submission."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SizeDecision:
    approved: bool
    volume: float
    risk_cash: float
    estimated_loss: float
    reason: str


def size_position(mt5, symbol, order_type, entry, stop, equity,
                  risk_fraction=0.02, daily_loss=0.0,
                  max_daily_loss_fraction=0.04):
    """Size a position from broker-calculated P/L; always round volume down."""
    if equity <= 0 or not 0 < risk_fraction <= 0.02:
        return SizeDecision(False, 0.0, 0.0, 0.0, "Invalid equity or risk fraction")
    if daily_loss < 0 or daily_loss >= equity * max_daily_loss_fraction:
        return SizeDecision(False, 0.0, 0.0, 0.0, "Daily loss limit reached")
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if info is None or tick is None:
        return SizeDecision(False, 0.0, 0.0, 0.0, "Symbol data unavailable")
    if not info.visible and not mt5.symbol_select(symbol, True):
        return SizeDecision(False, 0.0, 0.0, 0.0, "Could not select symbol")
    if entry <= 0 or stop <= 0 or entry == stop:
        return SizeDecision(False, 0.0, 0.0, 0.0, "Invalid entry or stop")
    if order_type == mt5.ORDER_TYPE_BUY and stop >= entry:
        return SizeDecision(False, 0.0, 0.0, 0.0, "Buy stop must be below entry")
    if order_type == mt5.ORDER_TYPE_SELL and stop <= entry:
        return SizeDecision(False, 0.0, 0.0, 0.0, "Sell stop must be above entry")

    one_lot_loss = mt5.order_calc_profit(order_type, symbol, 1.0, entry, stop)
    if one_lot_loss is None or one_lot_loss >= 0:
        return SizeDecision(False, 0.0, 0.0, 0.0, "Broker could not calculate stop loss")
    risk_cash = min(equity * risk_fraction,
                    equity * max_daily_loss_fraction - daily_loss)
    raw_volume = risk_cash / abs(one_lot_loss)
    step = float(info.volume_step)
    minimum = float(info.volume_min)
    maximum = float(info.volume_max)
    if step <= 0 or minimum <= 0:
        return SizeDecision(False, 0.0, risk_cash, 0.0, "Invalid broker volume constraints")
    volume = math.floor((min(raw_volume, maximum) + 1e-12) / step) * step
    digits = max(0, min(8, int(round(-math.log10(step))) if step < 1 else 0))
    volume = round(volume, digits)
    if volume < minimum:
        return SizeDecision(False, 0.0, risk_cash, 0.0,
                            "Broker minimum volume exceeds the risk budget; no trade")
    estimated = abs(float(mt5.order_calc_profit(order_type, symbol, volume, entry, stop) or 0))
    if estimated <= 0 or estimated > risk_cash + 1e-8:
        return SizeDecision(False, 0.0, risk_cash, estimated,
                            "Calculated volume exceeds the permitted loss")
    return SizeDecision(True, volume, risk_cash, estimated, "Risk checks passed")
