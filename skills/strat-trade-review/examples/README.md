# Example: SPY 775C 0DTE, Oct 7 2026

A real 0DTE call trade: a 1-lot scratch, then 2 @ 1.13, an average-down 2 @ 0.71, and an exit of all 4 near 1.15 for +$91.14. Bars are 5-minute regular-hours bars from the broker.

```bash
python3 scripts/strat_review.py \
  --fills examples/spy_0dte_fills.csv \
  --bars examples/spy_5m.csv --daily examples/spy_daily.csv \
  --contract-bars examples/spy775c_5m.csv \
  --max-daily-loss 150 --chart --out /tmp/strat_review_example
```

What it should show: the 10:25 ET buy against a bearish 30m and 60m (and a red Day), the add under FTFC Down, the day's worst point about $2 from a -$150 limit, and the 30m F2d-2u trigger at 11:10 ET (the bar the position was sold on) as the clean entry. The prior session's intraday bars are not included, so the first bars of the day show `?` for C1/C2.
