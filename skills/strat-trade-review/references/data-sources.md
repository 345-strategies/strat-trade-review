# Data sources

Written October 2026. Plans and limits change; check the provider before relying on a limit.

## Free default: Yahoo Finance via `yfinance`

```bash
python3 -m pip install yfinance
python3 scripts/strat_review.py --fills fills.csv --fetch yfinance --yf-symbol SPY --interval 1m --chart
```

- No key, no account. Unofficial, so it can break or rate-limit.
- Intraday depth: 1m for roughly the last 30 days (about a week per request), 2m to 30m for about 60 days, 60m for about two years.
- Futures: continuous front month, `ES=F`, `NQ=F`, `RTY=F`, `YM=F`, `CL=F`, `GC=F`, `SI=F`. Micros trade at the mini's price, so `ES=F` works for MES.
- Indexes: `^SPX`, `^NDX`, `^RUT`.
- **No historical intraday bars for option contracts.** Option alternatives fall back to the Black-Scholes estimate unless you add contract bars from another source.

Fetch the trade day and the prior session, plus daily bars (`interval="1d"`) for the Day timeframe.

## Free with something you already have

| Source | Underlying bars | Option contract bars | Futures | Notes |
|---|---|---|---|---|
| Your broker's MCP or API, if connected | usually | often for recent or live contracts | broker dependent | Best first choice. Save the response and pass it to `--bars` / `--contract-bars`. Public's `get_price_history` JSON is read directly. |
| TradingView chart export ("Export chart data") | yes | for listed option symbols on TradingView | yes | CSV with `time,open,high,low,close`. Export availability depends on your plan. A TradingView MCP `get-ohlcv` response (`{t,o,h,l,c}`) is read directly. |
| Schwab / thinkorswim API | minute bars, recent weeks | no historical bars via API | /ES etc. | Free with an account. thinkorswim OnDemand can replay options history by hand. |
| Tradier (brokerage account) | time and sales bars | yes, recent days | no | `/markets/timesales` accepts option symbols. |
| Interactive Brokers TWS API | yes | yes, live contracts | yes, including expired futures | Needs market data subscriptions for most feeds. |
| Alpaca (free plan) | IEX feed | indicative feed history | no | Check current plan terms for options history. |

## Paid, when the review needs real option marks after the fact

| Source | Strength | Pricing shape |
|---|---|---|
| Massive (formerly Polygon.io) | stocks, options (including expired contracts) and indices aggregates by the minute | monthly plans; limited free tier |
| Databento | OPRA options and CME futures, tick to 1m, very clean | pay per use; sign-up credits |
| Theta Data | options-focused, deep intraday history | free EOD tier, paid intraday |
| Interactive Brokers data subscriptions | whatever IBKR carries | small monthly fees per feed |
| FirstRate Data, Kibot | bulk historical intraday files | one-time purchase |
| CME DataMine | official futures history | per dataset |

## Getting the fills

Fills come from the broker, not a data vendor. See `connect-and-import.md`.

## Choosing

1. Connected broker or TradingView tool, if one is available.
2. `yfinance` for the underlying and daily bars.
3. For options reviews where the alternatives matter (0DTE especially), add the contract's own bars from the broker, Massive, Databento or Theta Data. Otherwise label option alternatives as ESTIMATES.
