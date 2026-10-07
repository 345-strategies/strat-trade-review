---
id: YYYY-MM-DD-<symbol>-<hhmm>
underlying:
symbol:            # OCC option symbol, ticker, or futures contract
asset:             # option | stock | future
direction:         # BULL | BEAR
qty:               # total bought (or sold short) across all legs
entry_at:          # first fill, ISO with offset
entry_price:       # average across all entries
stop_level:        # underlying invalidation, if there was one
exit_at:
exit_price:        # average across all exits
pnl:
status:            # closed | open
flags: []          # SCALED_IN, AVERAGED_DOWN, SCALED_OUT, AGAINST_CONTINUITY, AGAINST_FTFC, EARLY_SESSION
---

# <Underlying> <contract> <local time> (<ET time>)

## What I saw

<!-- Your words. The setup as it looked at the time: levels, timeframes, the trigger. -->

## Why I took it

<!-- The reasoning in the moment. If there was none, write that. -->

## How I felt

<!-- Bored, chasing, revenge, confident, rushed, patient, certain. -->

## Objective context at entry

<!-- From review.md: the TheStrat state table (15m / 30m / 60m / Day, continuity) at each fill. -->

## How it was filled

<!-- From review.md: every leg, local time (ET), side, qty, price, net, underlying. -->

## Flags

## Review

<!-- Entry, management, exit, alternatives table with its "priced from" column, the clean Strat version. -->

## Lesson

<!-- One sentence you would tell yourself before the next one. -->

## Images

![chart](chart.png)
