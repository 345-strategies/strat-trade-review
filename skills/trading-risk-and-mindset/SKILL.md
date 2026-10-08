---
name: trading-risk-and-mindset
description: Coach a trader on risk management, position sizing and trading psychology (discipline, loss limits, revenge trading, averaging down, process over outcome) in a way that fits TheStrat. Use for sizing a trade, setting loss limits, reviewing behavior across trades, or writing a trading plan.
---

# Trading risk and mindset

Use this when a trader asks how much to risk, how to size an option or futures position, what their loss limits should be, why they keep breaking their rules, how to stop revenge trading or averaging down, or wants a written trading plan. The `strat-trade-review` skill hands off to this one for the process and mindset part of a review.

It distills durable, widely taught principles (sources in `references/sources.md`) and fits them to TheStrat. TheStrat answers **where**: the trigger, the stop under C1, the target at the magnitude, and whether continuity agrees. This skill answers **how much** and **whether you will follow through**. It never adds indicators, opinions on direction, or entry rules of its own.

## Bundled files

- `references/risk.md`: R, expectancy, position sizing for shares, options and futures, loss limits, risk of ruin, correlated positions.
- `references/mindset.md`: thinking in probabilities, process over outcome, the common failure patterns (each with what it looks like in fills and a concrete fix), routines.
- `references/strat-fit.md`: how each principle maps onto TheStrat so the advice never conflicts with it.
- `references/sources.md`: the books and research behind each idea, so the trader can go deeper.
- `scripts/risk_calc.py`: position size, expectancy and drawdown stats from a list of R results, and a risk-of-ruin simulation. Stdlib only.
- `assets/trading-plan.md`: a one-page plan with a pre-trade checklist and daily rules the trader fills in.

## Conventions

- Green and red mean bull and bear, never good and bad. Don't color a loss red or a win green.
- Times in the trader's zone with ET in parentheses, e.g. `7:25 PT (10:25 ET)`.
- Talk in R (risk units) first, dollars second. R makes trades comparable across sizes and accounts.
- Cite the trader's own numbers. A principle without their data attached is a lecture.
- Not financial advice and not therapy. If a trader describes distress beyond trading (sleep, debt, relationships, gambling-like urges), say so plainly and point them to real help (in the US, the National Problem Gambling Helpline, 1-800-GAMBLER).

## How to help

### 1. Find out where they are

Ask, in one message, only what you don't already have:

- Account size, or the amount they treat as trading capital.
- What they risk per trade now, in dollars or percent, and whether that is decided before entry.
- Daily and weekly loss limits, if any, and what happens when they hit one.
- The last 20 or so trades as R multiples (or P/L plus the planned risk for each), or a journal or broker export. `strat-trade-review` output works directly.
- The one behavior they most want to change, in their words.

### 2. Sizing a specific trade

Run `scripts/risk_calc.py size` (examples in `references/risk.md`). Inputs: account, risk percent (or fixed dollars), entry, and the stop. For TheStrat the stop is the far side of C1 (the trigger bar's prior bar), so the stop is structural, not a dollar amount picked to feel comfortable. Options: size by the premium you will actually lose at the stop, or treat the whole premium as the risk when there is no stop. Futures: points to stop x point value x contracts. Report contracts or shares, the dollar risk, and what 1R is.

### 3. Reviewing behavior across trades

Run `scripts/risk_calc.py stats --r <file>` on their R list. Lead with expectancy (average R per trade), win rate, average win and average loss in R, largest loss in R, and the worst losing streak and peak-to-trough drawdown in R. Then:

- Losses bigger than -1R mean the stop is not being honored. That is the first fix, ahead of any entry improvement.
- Many small winners and a few large losers is the disposition effect (selling winners early, holding losers). Point at the specific trades.
- Results that collapse after the first loss of a day suggest tilt or revenge trading. Compare first-trade-of-day R with later trades if the dates are there.

Use `references/mindset.md` to name the pattern, show the evidence from their trades, and give one concrete rule. One rule at a time; a trader who gets ten rules follows none.

### 4. Writing the plan

Fill `assets/trading-plan.md` with them: risk per trade, daily and weekly stops, max trades per day, the setups they take (TheStrat combos and timeframes), the pre-trade checklist, and what they do after a loss. Keep it to one page. Plans that need re-reading during a trade don't get followed.

The rules they choose are theirs, and they differ from trader to trader; there is no single checklist. Keep their personal rules (loss limits, goals, habits like no averaging down) separate from what the chart says,. They are private: track them in the trader's own journal, never on a share card or post.

## Defaults when the trader has none

Offer these as starting points, and say they are conventions, not laws:

- Risk 0.5% to 1% of trading capital per trade while learning or rebuilding; up to 2% only with a positive expectancy over a meaningful sample (50+ trades).
- Daily loss limit of 2R to 3R; stop trading for the day when it is hit, no exceptions.
- Weekly loss limit of about 5R to 6R; at that point cut size in half until a green week (green meaning a net gain for the week).
- After two consecutive losses, a mandatory break (15 minutes away from the screen) before the next entry.
- No adding to a loser. Adds only on a new trigger in the trade's direction, with the stop moved so total risk stays at or under the original 1R.
- For 0DTE options, assume the premium can go to zero and size so that a full loss is at most the planned 1R.

## Writing the advice

- Lead with the one change that would have moved their results most, with the number behind it ("your 3 losses beyond -1R cost 7.2R, more than all 14 winners made").
- Separate decision quality from outcome. A trade taken on a trigger with the stop honored was a good trade even if it lost; an untriggered entry that made money was a bad trade that got paid.
- Use their words for what they think went wrong, then confirm or correct it with data.
- End with one rule, phrased as an if-then plan: "If I take a second loss today, then I stand up and walk away for 15 minutes before I look at a chart."
