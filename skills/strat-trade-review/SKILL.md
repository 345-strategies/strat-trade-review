---
name: strat-trade-review
description: Review a trade (options, shares or futures) against TheStrat multi-timeframe price action and price better entries, adds and exits. Also runs as the command /strat-review SYMBOL [DATE] [LOSS LIMIT].
---

# TheStrat trade review

Use this when someone wants a trade reviewed: "was my entry early", "should I have held", "I averaged down", "what should I have done", "review my SPY calls from today". It works for options, shares and futures, from any broker.

The output is a short, numbers-first review that answers three questions:

1. **Entry.** Where was the trade relative to TheStrat structure and continuity when it was opened, and where was the real trigger?
2. **Management.** Adds, average-downs, how close the worst point came to the trader's daily loss limit.
3. **Exit.** Where it was closed relative to the triggers and targets, and what the alternatives (hold, runner, scale out at target, roll, shares) would actually have paid.

It ends with a one-paragraph "what you should have done" plan the trader can reuse.

## Command form

The review also runs as a one-line command, the same in every app:

`/strat-review SYMBOL [DATE] [LOSS LIMIT] [anything else]`

Treat a message that starts with `/strat-review`, `@strat-trade-review` or `$strat-trade-review` as this command, and read the words after it:

- **Symbol** (required): an underlying or contract, e.g. `SPY`, `SPY 775C`, `ESZ6`, `MES`. If it is missing, ask for it and nothing else.
- **Date**: `today` (the default), `yesterday`, a weekday, `10/7` or `2026-10-07`. Resolve it to a trading date in the trader's zone and say which date you used.
- **Loss limit**: a dollar amount or a bare number after the date (`150`, `$150`) is the daily loss limit (`--max-daily-loss`).
- **Anything else**: their stop, plan or a script option in plain words (`entry 15m`, `futures`, `mark at close`). Map it to the matching flag.

Then go straight to Step 1 and ask only for what is still missing, usually the fills.

## Bundled files

This skill ships with `scripts/strat_review.py`, `scripts/import_fills.py`, `scripts/share_post.py`, `scripts/render_html.py`, `templates/` (the share card designs), `references/` (strat-primer, data-sources, connect-and-import), `assets/journal-entry-template.md` and a worked example in `examples/`. If they are not next to this file, get them from github.com/345-strategies/strat-trade-review (the `skills/strat-trade-review/` folder).

## Conventions (do not drift from these)

- **TheStrat grammar follows TheStrat Suite v3.1.x and its TheStratGrammar spec** (github.com/345-strategies/thestrat-suite). Summary in `references/strat-primer.md`. The rules that matter most: equal is not a break; `2u`/`2d` name the broken side, not the candle color; a `2u`/`2d` that closes back inside the prior range is a Failing 2 (`F2u` bearish, `F2d` bullish); a close exactly at the open counts as not above; Full Timeframe Continuity (FTFC) uses only close-vs-open of each forming bar.
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

## Step 1b: Ask for their journal entry (one message, all optional)

The numbers say what happened; only the trader can say what they were thinking, and the review is worth more when it holds the two side by side. While you fetch data, ask for a journal entry in this format (they can paste it, answer in their own words, or skip any line). Don't block on answers; review what you have.

```
Type of trade:                       (reversal, continuation, breakout, fade...)
Thesis:                              (why this, why here)
Primary timeframe & combo:           (e.g. 30m 2-1-2u)
When did this occur?:                (time of the trigger or the idea)
What did that create, negate, or do?: (the signal it put in force, or the one it broke)
Management:                          (stop, target, adds, exits, and why)
Notes:                               (anything else, including how it felt)
```

Also ask, in the same message, whether they want a Discord post (with dollars, or % and R only).

**Personal rules and goals stay private.** If the trader mentions their own rules or goals (a daily loss limit, no averaging down, a time they wait for), check them in the private review and journal entry only. They never go in the share post or card, and don't propose rules or defaults for them: there is no single checklist, and these are theirs, not TheStrat's.

Then grade every line against the bars, quoting their words and answering with a number:

| They wrote | Check it against |
|---|---|
| Type of trade | the family of the trigger they traded (Inside Reversal, 2-2 Reversal, 3-2 Expansion, continuation) and whether continuity supported that type |
| Thesis | the state on 5m/15m/30m/60m and the Day at the entry; reference levels (gap fill, prior day high/low, opening range) |
| Primary timeframe & combo | whether that combo actually triggered on that timeframe at that time (session triggers table), its C1 stop and target |
| When | the fill times versus the trigger time: early, on it, or chasing |
| Created / negated | which signals were in force at each fill and exit (a 2 in the trade's direction on 30m or 60m, a failed 2 the other way), and whether the trade's own trigger failed |
| Management | adds versus new triggers, the stop versus C1, the exit versus T1 and any higher-timeframe signal still in force |
| Notes | the feelings named, against the moments in the fills where they would have mattered |

How that reads, for an entry like: *"ES gapped down; shortly after the open we traded into a pocket of liquidity over a lack of liquidity, so I looked long for a reversal. First entry stopped at breakeven. Second went against me, I averaged down when I could have re-entered, and at a loss I took profit on all at the easy liquidity level instead of seeing the higher-timeframe signal in force, so I should have held."* The review checks the type (was there a reversal trigger, and what were the 30m and 60m doing at the first entry), finds the trigger that would have made a re-entry valid and where it was, prices the average-down against that re-entry, and checks the exit: if the 60m was in a 2u above its open when they sold, the chart facts read "Exit: with the 60m 2u still in force" and the alternatives show what holding to T1 or trailing would have paid.

If the trader asks about risk, sizing, discipline or mindset, or the flags show `AVERAGED_DOWN`, `AGAINST_FTFC` or a near-miss on the loss limit, use the `trading-risk-and-mindset` skill for that part if it is installed.

## Step 2: Get the bars

You need, for the trade's session:

| Data | Needed for | Minimum |
|---|---|---|
| Underlying intraday bars, **1m preferred** (needed to see the forming 5m bar), 5m acceptable | bar types, triggers, levels | the trade day **and the prior session** (the first 5m/15m/30m/60m bars of a day take C1/C2 from yesterday) |
| Underlying daily bars | Day C1/C2, prior close (gap fill), prior day H/L | 3 prior days (`--daily`) |
| The option contract's own intraday bars | real marks for alternatives and drawdown | optional; without it, option alternatives are Black-Scholes ESTIMATES |
| Next-expiry contract, leveraged ETF bars | roll / shares comparisons | only if the trader asks about those |

**Always get full context yourself; never ask the trader to.** The trade day alone is not enough: the first 5m, 15m, 30m and 60m bars of a day take their C1 and C2 from the previous session, and the Day needs prior daily bars. Pull the prior session and the daily bars from the same source as the trade day. The script also tries to fill in anything missing from Yahoo Finance on its own (`--no-auto-context` turns that off); if no source works, the review says so, the affected cells show `?`, and you tell the trader which states could not be resolved.

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
| `--caution-until` | off | entries before this ET time get `EARLY_SESSION`; set it only if waiting out the open is the trader's own rule |
| `--session futures` | auto for futures symbols | 18:00 to 17:00 ET sessions; equities use 09:30 to 16:00 |
| `--triggers-window` | `3` | hours either side of the entry to list triggers (0 = whole session) |
| `--fetch yfinance --yf-symbol ES=F --interval 1m` | off | download underlying bars instead of `--bars` |

It writes `review.md` (tables), `review.json` (same data for you to read), `timeframes_*.png` and `chart_*.png`. **`timeframes_*.png` is the main image to show the trader**: one panel each for 5m, 15m, 30m and 60m with every fill numbered (`#1`, `#2`...), the first trigger with the trade on each timeframe, the clean Strat entry and its C1 stop, and a table of the state on every timeframe at every fill. `chart_*.png` is the single-timeframe session view. Read `review.json` for exact values; do not re-derive them by hand.

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

If the trader keeps a journal, write the entry from `assets/journal-entry-template.md`: their journal answers verbatim at the top, then the fills, the state on each timeframe at each fill, the Strat scorecard, any personal rules they asked to track (private), the review and their reflection, with `timeframes_*.png` attached. Where they skipped a journal line, ask one question for each line the scorecard marks AGAINST rather than filling it in for them.

## Step 6: Share it (when asked)

```bash
python3 scripts/share_post.py --review review_out --lesson "<their reflection>" \
  [--setup "Reversal · 30m F2d-2u"] [--dollars] [--handle @name] [--number-color white] [--templates my-cards/]
```

The two images are drawn from the HTML templates in `templates/` (`card.html`, `timeframes.html`) with a headless Chrome, Chromium or Edge, at 2x for phones; with no browser (for example in a sandbox without one) it falls back to matplotlib versions of the same cards. If the trader wants their own look, point them to `templates/README.md`: copy the folder, change the colors and fonts at the top of each file or the layout itself, and pass `--templates` with their folder. `share/card.json` and `share/timeframes.json` hold the data, so `scripts/render_html.py` can re-render an edited template without re-running the review.

It writes to `review_out/share/`:

- `post.md`: the message, under Discord's 2,000-character limit, no tables (Discord does not render them; alternatives go in a code block).
- `timeframes.png`: the 5m/15m/30m/60m view, the main image: every fill numbered (blue buys, white sells), the bar type under each candle, the first trigger with the trade on each timeframe, the Strat entry and its C1 stop, and the state on each timeframe at each fill. No dollars and no position size.
- `card.png`: a 1200x675 card laid out like a broker's P/L share card (symbol and side, one big number, average in and out), with a Strat scorecard where a broker puts its referral code:
  - **The number:** % return on what was paid (options and shares; R for futures), green for a gain and red for a loss, with R and the average in and out under it. No dollars and no position size on the card, ever.
  - **Strat scorecard:** each decision marked WITH or AGAINST the chart, scored "n of m". Entered on a live trigger (not one already back inside); with continuity, or against it only on a reversal (valid only as an exhaustion reversal, which the trader judges); each add on a new trigger; the exit at T1, or AGAINST when a trigger in the trade's direction or a 30m/60m/Day signal was still in force. An exit before T1 with nothing in force is marked JUDGMENT and not scored. Context, not scored: a gap at the open, and Mondays (the week and the day are the same candle). Nothing personal: no loss limits, goals or rules.
  - **At entry** state on each timeframe, **If you had** alternatives in % and R, and the trader's **Reflection** in the band across the bottom.

  WITH and AGAINST use blue and amber with an icon and a label; green and red are only the bull/bear side, the timeframe states, and the headline gain or loss.
- `chart.png`: the single-timeframe view.

Read each scorecard line against your own review before posting. The reflection is the most prominent text on the card, so use the trader's own words (from the journal's Notes or Management line, or ask for one sentence); don't write it for them unless they ask. Pass their type of trade and primary timeframe/combo as `--setup`. Tell the trader to paste the text and attach `timeframes.png` and `card.png` to the same Discord message. The post shows % and R only; `--dollars` adds dollar amounts to the text (never to the card).

## Pitfalls

- **Missing prior session:** the first bars of the day show `?` for C1/C2. The script tries to fill it from Yahoo Finance; if that fails, fetch the previous session from the broker or TradingView and re-run.
- **Futures:** sessions run 18:00 to 17:00 ET, so a fill at 8 PM belongs to the next trade date. Micros (MES, MNQ) trade the same price as the minis; multipliers are in the script and can be overridden with `--multiplier`.
- **0DTE options** move far from Black-Scholes in the last hours. Use real contract bars whenever the alternatives are the point of the review.
- **Partial-day reviews:** when the session is still open, every hold row is a mark. Re-run with `--mark` at the close later and say the numbers changed.
- **Nothing here is a trade recommendation.** It reviews what happened against a stated method.
