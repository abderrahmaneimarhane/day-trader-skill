# OpenAI + MetaTrader 5 (Exness) integration

This is the V2 integration layer. It is additive: the original Claude/Alpaca
skills remain unchanged.

## Current status

- OpenAI is an analysis layer only. It cannot authorize or submit orders.
- MetaTrader 5 is the market-data and execution adapter.
- The deterministic risk engine is the final authority.
- The example configuration is paper-only.
- Live execution is fail-closed and requires both a config switch and an
  explicit environment arming value, plus account/server/symbol allow-lists.
- No credentials belong in source control, JSON config, or chat.

## Windows setup

1. Install Python 3.11+ and MetaTrader 5 terminal from Exness.
2. Log in to the Exness demo account first. Keep the terminal open.
3. From this repository root:

   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r mt5_openai/requirements.txt
   ```

4. Copy `mt5_openai/config.example.json` to `mt5_openai/config.json`.
5. Set `OPENAI_API_KEY` in your local environment. Never paste it into chat
   or commit it.
6. Run the connection diagnostic:

   ```powershell
   python -m mt5_openai.diagnostics --config mt5_openai/config.json
   ```

## Risk sizing

The risk engine calculates the loss of one lot at the proposed stop using
MetaTrader 5's `order_calc_profit`, then rounds volume DOWN to the broker's
volume step. If the resulting volume is below the broker's minimum, the
trade is rejected. It never rounds up to force a trade.

With a $10 account and a 2% risk limit, the maximum planned loss is $0.20
before commissions, slippage, gaps, and conversion effects. If Exness'
minimum volume risks more than $0.20, the correct result is NO TRADE.

## Execution gates

Live mode is deliberately unavailable unless all checks pass:

- `execution_mode` is `automatic_live`
- `live_enabled` is true in the local config
- `MT5_LIVE_ARMED=I_UNDERSTAND_LIVE_TRADING_RISK` is set locally
- the current MT5 account login and server match explicit allow-lists
- the symbol is allow-listed and trading is enabled
- the risk engine approves the exact order
- MT5 `order_check` succeeds before `order_send`

Start in paper mode, then Exness demo. A demo account is not the same as a
local paper simulator. Do not switch to a real account until the full
backtest, demo forward-test, and operational checks are complete.

## Important limitations

This integration is a foundation, not a validated profitable strategy.
Symbol names, contract sizes, leverage, minimum lot sizes, commissions,
swaps, and trading sessions vary by Exness account and instrument. Discover
them from the connected terminal; do not assume names such as US30 or BTCUSD
are universal. The first release does not claim to support every asset class
on every Exness account.
