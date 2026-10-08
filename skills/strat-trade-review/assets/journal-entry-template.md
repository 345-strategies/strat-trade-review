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

## Journal (in my words)

**Type of Trade:**
**Thesis:**
**Primary Timeframe & Combo:**
**When did this occur?:**
**What did that create, negate, or do?:**
**Management:**
**Notes:**

## Objective context at entry

<!-- From review.md: the TheStrat state table (5m / 15m / 30m / 60m, Day for context, continuity) at each fill. -->

## How it was filled

<!-- From review.md: every leg, local time (ET), side, qty, price, net, underlying. -->

## Strat checklist

<!-- From share_post.py or the review: each check GOOD or BAD with its evidence. -->

## Flags

## Review

<!-- Entry, management, exit, alternatives table with its "priced from" column, the clean Strat version. -->

## Lesson

<!-- One sentence you would tell yourself before the next one. -->

## Images

![timeframes](timeframes.png)
