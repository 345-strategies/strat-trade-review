---
name: strat-trade-review
description: Review a trade (options, shares or futures) against TheStrat multi-timeframe price action and price better entries, adds and exits.
---

# TheStrat trade review

Use this when someone wants a trade reviewed: "was my entry early", "should I have held", "I averaged down", "what should I have done", "review my SPY calls from today". It works for options, shares and futures, from any broker.

The output is a short, numbers-first review that answers three questions:

1. **Entry.** Where was the trade relative to TheStrat structure and continuity when it was opened, and where was the real trigger?
2. **Management.** Adds, average-downs, how close the worst point came to the trader's daily loss limit.
3. **Exit.** Where it was closed relative to the triggers and targets, and what the alternatives (hold, runner, scale out at target, roll, shares) would actually have paid.

It ends with a one-paragraph "what you should have done" plan the trader can reuse.

## Bundled files

This skill ships with `scripts/strat_review.py`, `scripts/import_fills.py`, `scripts/share_post.py`, `references/` (strat-primer, data-sources, connect-and-import), `assets/journal-entry-template.md` and a worked example in `examples/`. If they are not next to this file, get them from github.com/natebking/strat-trade-review (the `skills/strat-trade-review/` folder).

## Conventions (do not drift from these)

- **TheStrat grammar follows TheStrat Suite v3.1.x and its TheStratGrammar spec** (github.com/natebking/thestrat-suite). Summary in `references/strat-primer.md`. The rules that matter most: equal is not a break; `2u`/`2d` name the broken side, not the candle color; a `2u`/`2d` that closes back inside the prior range is a Failing 2 (`F2u` bearish, `F2d` bullish); a close exactly at the open counts as not above; Full Timeframe Continuity (FTFC) uses only close-vs-open of each forming bar.
- **Green and red mean bull and bear, never good and bad.** Bar-type colors follow the Suite palette (2u `#4caf50`, 2d `#f23645`, 1u `#ffeb3b`, 1d `#ff9800`, 3u `#089981`, 3d `#e91e63`, F2d `#81c784`, F2u `#f77c80`). Charts draw plain candles by default (green close above open, red otherwise) with each bar's type labeled underneath; `--candles strat` colors them by bar type instead. Fill markers are neutral (blue buys, white sells). A P/L is never colored green or red for gain or loss.
- **Times:** show the trader's local zone with ET in parentheses, e.g. `7:25 PT (10:25 ET)`. Default local zone is Pacific; change with `--display-tz`.
- **Any Pine Script you produce is delivered as a `.txt` file.**
- **Label every estimate.** A number priced from real contract bars is a mark; a number priced by the Black-Scholes fallback says ESTIMATE. Before the close, "hold" rows are marks, not closing prices.

## Step 1: Get the fills

Make this as easy as possible for the trader. Ask only for the symbol and the date, then use the first route that works (details and download paths per broker in `references/connect-and-import.md`):

1. **Connected broker.** If a broker connector is available (Public, Alpaca, or another broker MCP), pull that day's executions yourself. No files.
2. **Their broker's export, unedited.** Tell them exactly where to click for their broker, then pass the file straight to `--fills`. The script auto-detects Schwab/thinkorswim, Interactive Brokers, Tradovate, NinjaTrader, Webull, Robinhood, Public and Alpaca exports. Robinhood exports have no time of day, so ask for the times from the order details.
3. **Paste or screenshot.** Transcribe into the normalized CSV, show the table back, and confirm the time zone.

If times carry no zone, pass `--fills-tz` (ET, PT, CT, UTC). Never ask for API keys or passwords in chat.

The normalized CSV, for anything the importer does not recognize:

```
time,symbol,side,qty,price,fees,net
2026-10-07 10:25:21 ET,SPY261007C00775000,BUY,2,1.13,0,
```

`symbol` can be an OCC option (`SPY261007C00775000`), `SPY 10/07/2026 775 C`, a ticker, or a futures contract (`ESZ6`, `MESZ26`, `ES 12-26`). `fees` is positive for a cost, negative for a rebate. A `net` column (signed cash) overrides price x qty x multiplier so broker P/L matches to the cent.

## Step 1b: Ask about the trade (one message, all optional)

The numbers say what happened; only the trader can say what they were thinking, and the review is worth more when it can hold the two side by side. Ask these together, in one short message, while you fetch data. Don't block on answers; review what you have.

1. **The plan at entry.** What did you see, on which timeframe, and what was the trigger? Where was your stop and your target?
2. **Adds and exits.** What made you add (if you did), and what made you get out when you did?
3. **Your read.** What do you think went right or wrong?
4. **How it felt.** One word each for entry and exit (calm, rushed, bored, chasing, scared, certain).
5. **Your rules.** Daily loss limit, and how much you risk per trade, if you use either.
6. **Sharing.** Want a post for Discord when we're done? With dollar amounts, or R only?

In the review, quote their answer and confirm or correct it with a number: "You said you bought the breakout; the 15m bar you bought was already closing back inside (F2u) while the 30m, 60m and Day were all below their opens." If the trader asks about risk, sizing, discipline or mindset, or the flags show `AVERAGED_DOWN`, `AGAINST_FTFC` or a near-miss on the loss limit, use the `trading-risk-and-mindset` skill for that part if it is installed.

## Step 2: Get the bars

You need, for the trade's session:

| Data | Needed for | Minimum |
|---|---|---|
| Underlying intraday bars, **1m preferred** (needed to see the forming 5m bar), 5m acceptable | bar types, triggers, levels | the trade day **and the prior session** (the first 5m/15m/30m/60m bars of a day take C1/C2 from yesterday) |
| Underlying daily bars | Day C1/C2, prior close (gap fill), prior day H/L | 3 prior days (`--daily`) |
| The option contract's own intraday bars | real marks for alternatives and drawdown | optional; without it, option alternatives are Black-Scholes ESTIMATES |
| Next-expiry contract, leveraged ETF bars | roll / shares comparisons | only if the trader asks about those |

Pick a source with `references/data-sources.md`, in this order:

1. **A connected broker or TradingView tool.** Pull the bars yourself and save them to CSV or JSON; the script reads plain CSV, Public's `get_price_history` JSON, and TradingView `{t,o,h,l,c}` rows or columns.
2. **Free broker data the trader already has an account for.** Public, Tradier and Alpaca (indicative feed) all return intraday bars for option contracts at no extra cost; Schwab and IBKR cover the underlying. Tell the trader this exists before reaching for a paid source.
3. **Yahoo Finance via `yfinance`**, free with no account (1m back about 30 days, 5m about 60; futures as `ES=F`, `NQ=F`, `CL=F`, `GC=F`). Enough for shares and futures, but it has no option contract history.
4. **Paid** (Massive, Databento, Theta Data) only when real option marks matter and no broker route works.

With 5m bars, a fill inside a 5m bar is judged on the bars closed before it. That is the honest no-lookahead view, but it can miss a break that happened in the same 5 minutes. Use 1m bars when the trader's question is about a few minutes either way.

## Step 3: Run the script

`scripts/strat_review.py` is stdlib Python 3.10+. `matplotlib` is needed only for `--chart`; `yfinance` only for `--fetch yfinance`.

```bash
python3 scripts/strat_review.py \
  --fills fills.csv --bars spy_1m.csv --daily spy_daily.csv \
  --contract-bars spy775c_1m.csv \
  --max-daily-loss 150 --chart --out review_out
```

Useful options:

| Option | Default | Use |
|---|---|---|
| `--tfs` | `5m,15m,30m,60m` | the four-timeframe view: state, continuity and flags at each fill |
| `--context-tfs` | `D` | shown for context, not counted in continuity (`''` for none) |
| `--entry-tf` | `30m` | timeframe whose trigger defines the "clean Strat" entry |
| `--clean-entry HH:MM ET` | first in-direction trigger near the trade | pin the clean entry when the auto pick is wrong |
| `--min-target-r` | `1.0` | first target = nearest magnitude or reference level at least this many R from the trigger |
| `--t1` | auto | override the first target |
| `--trail-tf` | `60m` | runners trail under each completed bar of this timeframe (a 30m trail tends to stop out a 0DTE runner on normal pullbacks) |
| `--mark` | last bar | mark time for hold and runner rows (use the close once the day is done) |
| `--caution-until` | `10:00` | entries before this ET time get `EARLY_SESSION` (`''` turns it off) |
| `--session futures` | auto for futures symbols | 18:00 to 17:00 ET sessions; equities use 09:30 to 16:00 |
| `--triggers-window` | `3` | hours either side of the entry to list triggers (0 = whole session) |
| `--fetch yfinance --yf-symbol ES=F --interval 1m` | off | download underlying bars instead of `--bars` |

It writes `review.md` (tables), `review.json` (same data for you to read), and `chart_*.png`. Read `review.json` for exact values; do not re-derive them by hand.

What it computes, so you can explain it:

- **State at each fill** per timeframe as `C1-CC` combo tokens plus the forming bar's sign, built only from bars closed by the fill time. `F2d-2u +` means the prior bar was a failed 2d and the forming bar has taken its high and is above its open.
- **Continuity** at each fill: FTFC Up, FTFC Down or Conflict across 5m, 15m, 30m and 60m. The Day is shown beside them for context but does not vote.
- With 5m base bars the 5m column reads `C1-(new)`: the forming 5m bar is invisible until it closes. Use 1m bars to see it.
- **Flags:** `SCALED_IN`, `AVERAGED_DOWN` (an add worse than the first fill), `SCALED_OUT`, `AGAINST_CONTINUITY` (most timeframes' forming bars against the trade), `AGAINST_FTFC` (all of them against, which the Suite's FTFC filter would veto), `EARLY_SESSION`.
- **Session triggers:** every first break of a prior bar's high or low per timeframe, with combo, family (Inside Reversal, 2-2 Reversal, 3-2 Expansion, continuations), trigger, C1 stop, target, which came first, and the best excursion in R.
- **Reference levels:** day open, opening range high/low, prior close (gap fill), prior day high/low, HOD/LOD.
- **Worst point of the day** across all positions (realized plus open), against `--max-daily-loss`.
- **Alternatives:** hold all, your exits plus a runner, half runners, all out at T1, half at T1 with a trailing runner, and the clean Strat version (same size, entered on the `--entry-tf` trigger, stop at C1, half at the first target at least 1R away, the rest trailing from breakeven under each completed `--trail-tf` bar). Each row also shows P/L in R, where 1R is the clean plan's dollar risk to its C1 stop at the same size, so the actual exit can be read as "+0.5R" instead of "+$91".
- **Delta at exit** for options, so a shares or leveraged-ETF comparison uses matched exposure.

## Step 4: Write the review

Lead with the net result and the single biggest lesson. Then entry, management, exit, alternatives, and the plan. Keep it to what changes the trader's next trade. Shape that has worked:

```
Net: +$91.14 on the 4-lot. The biggest lesson: your exit bar was the real entry.

- Entry, early. At 7:25 PT (10:25 ET) you bought a 15m break of 774.82 that was already
  closing back inside (F2u) while the 30m, 60m and Day were below their opens. It failed. The reversal that worked was the 15m and 30m
  F2d-2u off the 773.61 low at 8:10 PT (11:10 ET).
- Average-down. The add made the whole profit, but it was a double-down into a new low with no
  trigger. The day's worst point was -$147.89, $2 from the -$150 limit.
- Exit. You sold on the bar the 30m trigger fired: that was the entry, stop under 773.61,
  T1 at the 776.15 opening-range high.

| Plan | P/L | R | Priced from |
...

What you should have done:
1. Skip the entries that had no higher-timeframe confirmation.
2. Enter full size on the 30m trigger, stop under C1.
3. Sell half at T1, move the stop to breakeven.
4. Run the rest toward the next level, trailing under each completed 60m bar's low.
```

Rules for the write-up:

- Every claim cites a number from the script output (a price, a time, a combo, a P/L). If you inferred something, say so.
- Use the trader's words for what they think went wrong, then confirm or correct each point with the data.
- Separate the rule-break (entry, add) from its consequence (fear-driven exit). If the trader asks about mindset, help them see that a trade entered on a trigger is easier to hold, and suggest deciding the stop, T1 and runner rule at entry.
- The clean Strat row uses only information available at the trigger, but choosing which trigger to show is hindsight. Say so when it matters.
- **Score option targets on the option's bars, not just the underlying.** A wick through a level on the underlying (a gap-fill print, say) often does not show up as a matching high in the contract, because of spread and IV. The script prices target exits from the contract bar's close when contract bars are given; when you discuss "it hit the gap fill", check what the contract actually traded in that bar before claiming the runner would have been paid there.
- Shares and leveraged ETFs: compare at matched delta (see the delta line), mention notional and margin. They rarely substitute for a short-dated option runner.
- Rolls (next expiry, different strike): price them only from real bars of the new contract; it becomes a new trade with its own overnight risk and size.
- Anything over about fifteen lines goes in a file, with a short message pointing at it.

## Step 5: Save it

If the trader keeps a journal, write an entry from `assets/journal-entry-template.md` (frontmatter, fills table, Strat context table, flags, review, lesson) and attach the chart. Leave "What I saw / Why I took it / How I felt" for the trader's own words and ask them one question for each of the decisions you flagged.

## Step 6: Share it (when asked)

```bash
python3 scripts/share_post.py --review review_out --lesson "Wait for the 30m trigger." [--r-only] [--handle @name]
```

It writes `review_out/share/post.md` (under Discord's 2,000-character limit, no tables, since Discord does not render them; alternatives go in a code block), `card.png` (a 1200x675 summary card) and `chart.png`. Write the lesson yourself in one sentence, in the trader's words where you can. Show the post, attach both images, and tell them to paste the text and drop the two images into the same Discord message. Use `--r-only` when they would rather not show dollars; R travels better between account sizes anyway.

## Pitfalls

- **Missing prior session:** the first bars of the day show `?` for C1/C2. Fetch the previous session too.
- **Futures:** sessions run 18:00 to 17:00 ET, so a fill at 8 PM belongs to the next trade date. Micros (MES, MNQ) trade the same price as the minis; multipliers are in the script and can be overridden with `--multiplier`.
- **0DTE options** move far from Black-Scholes in the last hours. Use real contract bars whenever the alternatives are the point of the review.
- **Partial-day reviews:** when the session is still open, every hold row is a mark. Re-run with `--mark` at the close later and say the numbers changed.
- **Nothing here is a trade recommendation.** It reviews what happened against a stated method.
