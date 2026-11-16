"""Small, fail-closed MetaTrader 5 adapter. Requires Windows + MT5 terminal."""
class MT5Adapter:
    def __init__(self, terminal_path=None):
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError("Install MetaTrader5 on Windows and open the Exness terminal") from exc
        self.mt5 = mt5
        self.terminal_path = terminal_path

    def connect(self):
        ok = self.mt5.initialize(path=self.terminal_path) if self.terminal_path else self.mt5.initialize()
        if not ok:
            raise RuntimeError("MT5 initialize failed: " + str(self.mt5.last_error()))
        account = self.mt5.account_info()
        if account is None:
            self.mt5.shutdown()
            raise RuntimeError("MT5 account_info unavailable")
        return account

    def closed_bars(self, symbol, timeframe, count=250):
        mt5 = self.mt5
        frames = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
                  "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
                  "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
                  "D1": mt5.TIMEFRAME_D1}
        if timeframe not in frames:
            raise ValueError("Unsupported timeframe: " + str(timeframe))
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError("Cannot select " + symbol)
        # Position 0 is the still-forming candle; request one extra and drop it.
        rates = mt5.copy_rates_from_pos(symbol, frames[timeframe], 0, count + 1)
        if rates is None or len(rates) < count + 1:
            raise RuntimeError("Insufficient bars for " + symbol + " " + timeframe)
        return rates[:-1]

    def shutdown(self):
        self.mt5.shutdown()
