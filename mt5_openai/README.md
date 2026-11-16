# OpenAI + MetaTrader 5 (Exness) integration

This is the V2 integration layer. It is additive: the original Claude/Alpaca
skills remain unchanged.

## Current status

- OpenAI is an analysis layer only. It cannot authorize or submit orders.
- MetaTrader 5 is the market-data and execution adapter.
- The deterministic risk engine is the final authority.
- The example configuration is paper-only. Run the one-pass scanner with `python -m mt5_openai.agent --config mt5_openai/config.json`. It reads closed M15 bars, filters candidate EMA/RSI/ATR setups with OpenAI context, checks spread and position limits, sizes through MT5, and emits paper previews. It records the maximum daily drawdown observed while the agent is running; it cannot reconstruct losses from periods when it was not running.
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
   python -m mt5_openai.agent --config mt5_openai/config.json
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


## Android + Termux research mode (semi-automatic)

This mode is separate from the Windows MT5 adapter. It is designed for an
Android phone and does **not** connect to the Exness MT5 mobile app or submit
broker orders.

### What it does

- Fetches indicative OHLC history through Yahoo Finance's chart endpoint.
- Uses the same deterministic EMA/RSI/ATR research baseline.
- Adds H1 and D1 trend context and optional OpenAI market-context analysis.
- Saves trade proposals and displays them in a local, loopback-only dashboard.
- Lets the user approve a proposal for **manual review** or reject it.
- Does not calculate broker lot size, because Yahoo prices are not Exness
  executable quotes and the Android app does not expose broker contract data
  to this Python process.

### Install on Android

1. Install Termux from the official F-Droid or Termux GitHub source. Do not mix
   APKs from different signing sources. The official project notes Android may
   stop background processes, so this is not a reliable always-on server.
2. Open Termux and run:

   ```sh
   pkg update && pkg upgrade
   pkg install python git
   git clone --branch v2/openai-exness-mt5 https://github.com/abderrahmaneimarhane/day-trader-skill.git
   cd day-trader-skill
   python -m venv .venv
   source .venv/bin/activate
   pip install -r mt5_openai/requirements.txt
   cp mt5_openai/android_config.example.json mt5_openai/android_config.json
   ```

3. Set the OpenAI key in the current Termux session (do not put it in the
   config file or commit it):

   ```sh
   export OPENAI_API_KEY="your-key"
   ```

4. Run one scan:

   ```sh
   python -m mt5_openai.android_agent --config mt5_openai/android_config.json
   ```

5. Start the dashboard in a second Termux session:

   ```sh
   cd day-trader-skill
   source .venv/bin/activate
   python -m mt5_openai.android_dashboard
   ```

6. Open `http://127.0.0.1:8765` in the Android browser.

### Manual approval workflow

A dashboard approval only changes a proposal to
`approved_for_manual_review`. It never submits an order. Before entering
anything manually in Exness MT5, independently verify the exact instrument,
current executable bid/ask, spread, contract size, margin, minimum volume,
stop distance, and expected loss. If the smallest allowed volume exceeds the
risk budget, do not trade.

### Data and operational limitations

Yahoo Finance symbols are research proxies, not a guarantee of matching
Exness instruments. Examples such as `GC=F`, `^DJI`, and `^IXIC` represent
gold futures, Dow Jones index data, and Nasdaq Composite data respectively;
they are not equivalent to every broker's XAUUSD, US30, or NAS100 CFD.
Availability, delay, history, and rate limits can change. Validate every
symbol and candle timestamp. Do not treat the dashboard as a live broker
terminal. Android may suspend Termux in the background; keep it foregrounded
for scans and do not depend on it for unattended monitoring.

This Android mode is research and manual trade preparation, not a validated
profitable strategy or financial advice.
