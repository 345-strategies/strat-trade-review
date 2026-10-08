# Example: SPY 775C 0DTE, Oct 7 2026

A real 0DTE call trade: a 1-lot scratch, then 2 @ 1.13, an average-down 2 @ 0.71, and an exit of all 4 near 1.15 for +$91.14. Bars are 5-minute regular-hours bars from the broker for the trade day and the session before it.

```bash
python3 scripts/strat_review.py \
  --fills examples/spy_0dte_fills.csv \
  --bars examples/spy_5m.csv --daily examples/spy_daily.csv \
  --contract-bars examples/spy775c_5m.csv \
  --max-daily-loss 150 --chart --out /tmp/strat_review_example
```

What it should show: the 10:25 ET buy against a bearish 30m and 60m (and a Day below its open), the add under FTFC Down, the day's worst point about $2 from a -$150 limit, and the 30m F2d-2u trigger at 11:10 ET (the bar the position was sold on) as the clean entry. The prior session is included so the first bars of each timeframe have a C1 to compare with; without it they show `?`. It also writes `timeframes_*.png`, the 5m/15m/30m/60m view with each fill numbered.

To make the share post and card with the sample rules file:

```bash
python3 scripts/share_post.py --review /tmp/strat_review_example \
  --setup "Reversal · 30m F2d-2u" --lesson "The 30m F2d-2u was the trade. Wait for the trigger instead of averaging down, then hold to T1."
```

`example-card.png` and `example-timeframes.png` are the result, drawn from `templates/` (with Chrome, Chromium or Edge installed; otherwise matplotlib versions): +25% in the broker-card style, the Strat scorecard (1 of 4: entered as the 15m trigger was failing, the reversal against continuity, an add with no trigger, the exit on the 30m F2d-2u trigger bar), and the reflection.
