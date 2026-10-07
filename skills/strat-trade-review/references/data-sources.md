# Data sources

Written October 2026. Plans and limits change; check the provider before relying on a limit.

## Free with a broker account (start here, especially for options)

Most traders already have one of these. They cost nothing beyond the account, and the first three return intraday bars for **option contracts**, which Yahoo cannot. The trader creates an API key in the broker's settings and connects it to their AI tool (an MCP connector) or runs a small download; never paste a key into chat.

| Broker | Underlying bars | Option contract bars | Futures | What to know |
|---|---|---|---|---|
| **Public** | 1m to 1h, intraday back about a month | yes, by OCC/OSI symbol | no | API key from the account settings. Public's MCP `get_price_history` JSON is read directly by `--bars` / `--contract-bars`. |
| **Tradier** | 1m, 5m, 15m time-and-sales bars (1m about 10 to 20 days back, 5m/15m about 18 to 40) | yes, pass the OCC symbol | no | Free with a Tradier brokerage account. Save `/markets/timesales` output as CSV. |
| **Alpaca** | yes (free IEX feed) | yes, from February 2024, on the free **indicative** feed (derived quotes, trades 15 minutes delayed; real OPRA needs a paid plan) | no | Fine for reviewing a past day; label option prices as indicative. |
| **Schwab / thinkorswim** | minute bars, recent weeks | no historical option bars via the API | /ES etc. | thinkorswim OnDemand can replay option history by hand. |
| **Interactive Brokers** | yes | yes, live contracts | yes, including expired futures | Most feeds need a small market data subscription. |
| **TradingView** chart export | yes | for listed option symbols on TradingView | yes | "Export chart data" CSV (plan dependent). A TradingView MCP `get-ohlcv` response is read directly. |

Limits and plans change; check the broker's current docs (written October 2026).

## Free without any account: Yahoo Finance via `yfinance`

```bash
python3 -m pip install yfinance
python3 scripts/strat_review.py --fills fills.csv --fetch yfinance --yf-symbol SPY --interval 1m --chart
```

- No key, no account. Unofficial, so it can break or rate-limit.
- Intraday depth: 1m for roughly the last 30 days (about a week per request), 2m to 30m for about 60 days, 60m for about two years.
- Futures: continuous front month, `ES=F`, `NQ=F`, `RTY=F`, `YM=F`, `CL=F`, `GC=F`, `SI=F`. Micros trade at the mini's price, so `ES=F` works for MES.
- Indexes: `^SPX`, `^NDX`, `^RUT`.
- **No historical intraday bars for option contracts.** Option alternatives fall back to the Black-Scholes estimate unless you add contract bars from a broker above or a paid source below.

Fetch the trade day and the prior session, plus daily bars (`interval="1d"`) for the Day timeframe.

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

1. A connected broker or TradingView tool, if one is available.
2. Shares or futures: `yfinance` is enough for the underlying and daily bars.
3. Options: get the contract's own bars free from Public, Tradier or Alpaca (indicative) if the trader has an account there; otherwise Massive, Databento or Theta Data. Without them, label option alternatives as ESTIMATES.
