# Connect or import: getting fills in with the least effort

Three routes, easiest first. Pick the first one that works for the trader's broker. Written October 2026; connector availability changes, so check what the trader actually has connected before suggesting setup.

## 1. Connected broker (zero files)

If the assistant already has a broker tool connected, pull the day's executions directly and save them as JSON or CSV for the script.

| Broker | How it connects | Notes |
|---|---|---|
| Public | Public's API, exposed as an MCP connector (`get_history` for fills, `get_price_history` for stock and option bars) | The script reads the `get_history` JSON as-is. Option bars work with `instrument_type=OPTION`. |
| Alpaca | Alpaca's official MCP server (account activities, bars) | Activities JSON (`activity_type=FILL`) is read as-is. |
| Interactive Brokers, Schwab, Tradier | Community MCP servers built on each broker's API | Needs the trader's own API app or gateway. Worth it only for frequent reviews. |
| Many brokers at once (Robinhood, Schwab, Fidelity, Webull, E*TRADE, IBKR, ...) | An aggregator such as SnapTrade (OAuth "connect your broker", read-only trade history) | Requires developer keys, so it suits a hosted version of this tool rather than a one-off review. |

In Claude these are connectors (MCP). In ChatGPT, the same MCP servers can be added as custom connectors where the plan allows developer mode. Never ask the trader to paste API keys into the chat.

## 2. Drop the broker's export file (one download)

`scripts/import_fills.py` recognizes these exports from their headers. The trader downloads the file and drops it in unedited; `strat_review.py --fills <that file>` detects and converts it automatically.

| Broker | Where to download | Watch for |
|---|---|---|
| Schwab / thinkorswim | thinkorswim: Monitor > Account Statement > export to file (uses the "Account Trade History" section) | Times are in the platform's zone: pass `--fills-tz PT` if it is set to Pacific |
| Interactive Brokers | Client Portal: Performance & Reports > Flex Queries > Trade Confirmation or Activity (Trades, Execution level, CSV) | Commissions come in as fees |
| Tradovate | Account > Reports > Orders (or Fills), Download CSV | Cancelled rows are skipped |
| NinjaTrader | Control Center > Executions tab > right-click > Export | `ES 12-26` style names are understood |
| Webull | Desktop: Orders > Order History > export | Only Filled rows are used; EDT/EST suffixes are read |
| Robinhood | Account > Reports and statements > Reports > generate account activity CSV | **No time of day.** The importer sets 09:30 ET and warns; get real times from each order's detail screen |
| Public | API / connector `get_history` JSON, or the history CSV | `netAmount` is used so P/L matches to the cent |
| Alpaca | Activities API JSON | |
| Anything else | Any CSV with time, symbol, side, qty and price columns | See the normalized format below |

To see what was detected without running a review: `python3 scripts/import_fills.py export.csv`.

## 3. Paste or screenshot

Paste the order history text or attach a screenshot of filled orders. Transcribe it into the normalized CSV, show the table back, and confirm the time zone before running. This is the universal fallback and works in any chat app.

## Normalized format

```
time,symbol,side,qty,price,fees,net
2026-10-07 10:25:21 ET,SPY261007C00775000,BUY,2,1.13,0,
```

| Column | Required | Notes |
|---|---|---|
| time | yes | Zone suffix (`ET`, `PT`, `CT`, `UTC`) or ISO offset. Without one, `--fills-tz` (default ET) applies. |
| symbol | yes | OCC option (`SPY261007C00775000`), `SPY 10/07/2026 775 C`, ticker, or futures (`ESZ6`, `MESZ26`, `ES 12-26`) |
| side | yes | BUY / SELL, or BTO / STC / STO / BTC / BOT / SLD |
| qty, price | yes | Contracts or shares; option price per share (1.13, not 113) |
| fees | no | Positive is a cost, negative a rebate |
| net | no | Signed cash for the leg; overrides price x qty x multiplier |

Positions are built per symbol: a position opens when the running quantity leaves zero and closes when it returns to zero.

## Bars

The same three routes apply to price bars: a connected broker or TradingView tool, a file export (TradingView "Export chart data", broker downloads), or the free `--fetch yfinance` download for the underlying. See `data-sources.md`.
