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
flags: []          # SCALED_IN, AVERAGED_DOWN, SCALED_OUT, AGAINST_CONTINUITY, AGAINST_FTFC, EARLY_SESSION (only if set)
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

## What the chart said

<!-- Facts at each decision, not grades: the setup and its trigger at #1, continuity (and, if against, whether it was an exhaustion reversal), each add and its trigger, each exit and the signals in force. -->

## My rules

<!-- Only the rules in my-rules.json: each kept or broke, with the evidence. Leave out if none. -->

## Flags

## Review

<!-- Entry, management, exit, alternatives table with its "priced from" column, the clean Strat version. -->

## Reflection

<!-- In my words: what I'd tell myself before the next one. -->

## Images

![timeframes](timeframes.png)
