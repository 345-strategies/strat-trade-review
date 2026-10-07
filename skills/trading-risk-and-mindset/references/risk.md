# Risk and position sizing

## R: the unit everything is measured in

**1R is the amount you lose if the trade hits its stop.** You decide it before entry. Every result is then a multiple of R: a trade that makes twice what it risked is +2R, and one stopped out as planned is -1R. A loss bigger than -1R means the stop was moved, ignored or gapped through. (Van Tharp popularized R-multiples; see `sources.md`.)

Why R first:

- It makes a $50 trade and a $5,000 trade comparable.
- It shows whether the problem is the entries (too many -1R) or the discipline (losses past -1R).
- It is the honest way to share results: R travels between account sizes; dollars invite comparing accounts.

## Expectancy

```
expectancy (R per trade) = win rate x average win (R) - loss rate x average loss (R)
```

A 40% win rate with +2.5R average wins and -1R average losses is +0.4R per trade: profitable while losing most trades. A 70% win rate with +0.5R wins and -1.5R losses is -0.1R: losing while winning most trades. Win rate alone says almost nothing.

Sample size matters. Twenty trades can't tell skill from luck; treat expectancy as a working estimate until you have 50 to 100 trades of the same setup.

## Position size

```
units = (account x risk %) / (risk per unit)
```

Round **down**, never up.

| Asset | Risk per unit | Example |
|---|---|---|
| Shares | entry - stop (long) or stop - entry (short) | $25,000 account, 1% = $250. Long at 774.82, stop 773.61 (C1 low), risk 1.21/share: 206 shares. |
| Options, with a stop on the underlying | premium now - estimated premium at the stop, x 100 | Premium 0.94, estimated 0.45 at the stop (from delta or a pricing model): 0.49 x 100 = $49 per contract. $250 / 49 = 5 contracts. |
| Options, no stop (holding to zero or expiry) | full premium x 100 | Premium 0.94: $94 per contract. $250 / 94 = 2 contracts. |
| Futures | points to stop x point value | ES at $50/point, MES at $5/point. Stop 6 points: ES $300, MES $30 per contract. $250 budget: 0 ES, 8 MES. |

Notes:

- **Options stops are on the underlying** in TheStrat (the C1 level). Convert to a premium estimate with delta for a quick number, or use `risk_calc.py size --option` which uses Black-Scholes when you give it strike, expiry and IV. 0DTE premiums can move far more than delta suggests late in the day; size to the no-stop line if unsure.
- **Futures margin is not risk.** Margin is a deposit; the risk is the distance to your stop times the point value. Micros exist so small accounts can size properly.
- If the structural stop is too far for even one unit at your risk %, **skip the trade or use a smaller instrument** (MES instead of ES, a spread instead of a long option). Never shrink the stop to make size fit; that turns a structural stop into a wish.

`risk_calc.py size` does all of this:

```bash
python3 scripts/risk_calc.py size --account 25000 --risk-pct 1 --entry 774.82 --stop 773.61
python3 scripts/risk_calc.py size --account 25000 --risk-pct 1 --option --premium 0.94 --underlying 774.82 \
    --stop 773.61 --strike 775 --dte 0.2 --iv 0.18 --type call
python3 scripts/risk_calc.py size --account 25000 --risk-dollars 250 --entry 6500 --stop 6494 --point-value 5
```

## Loss limits

A loss limit is a pre-commitment, set when calm, that overrules the in-the-moment self.

- **Per trade:** 1R, enforced by an actual stop order or an alert you act on.
- **Per day:** 2R to 3R. When hit, trading ends for the day. Count realized plus open: the worst intraday point, not just the close, is what tests the rule (`strat-trade-review` reports it).
- **Per week / month:** about 5R to 6R a week, 10R to 12R a month. At the limit, cut size in half until a green week.
- **Per drawdown from equity peak:** at -10R or -10% of the account, stop and review the last 30 trades before trading again.

Write the limits down where you will see them, and set them in the broker if it supports a daily loss lock.

## Risk of ruin

The chance of losing so much that you cannot continue. It grows fast with risk per trade, even with a positive expectancy:

Simulated with `risk_calc.py ruin --win-rate 0.45 --avg-win 1.5` (a modestly profitable system, +0.13R per trade) over 200 trades:

| Risk per trade | Longest losing streak | Max drawdown, typical | Max drawdown, 1 run in 20 |
|---|---|---|---|
| 1% | 8 in a row typical, 12+ in 1 run in 20 | about 12% | about 21% |
| 3% | same | about 32% | about 52% |
| 5% | same | about 49% | about 68% |

The streak length is a property of the win rate, not of your risk; only the damage scales with size. Simulate your own numbers with `risk_calc.py ruin` (Monte Carlo over your R list or a win rate and payoff).

Full Kelly sizing (Kelly, Thorp; Ralph Vince's "optimal f") maximizes long-run growth on paper but produces drawdowns few people can sit through, and it needs an accurate edge estimate you won't have. If you use it at all, use a small fraction (a quarter Kelly or less) as a ceiling, not a target.

## Correlated positions

Three long calls on SPY, QQQ and NVDA are close to one trade at three times the size. Count correlated positions against a single risk budget (for example, total open risk across index and big-tech longs no more than 2R). Two TheStrat triggers on different timeframes of the same underlying are the same trade.

## Adds and averaging

- **Averaging down** (adding at a worse price with no new trigger) raises size exactly when the trade is proving the idea wrong. It turns -1R into -2R or -3R and makes the stop harder to honor. Don't.
- **Pyramiding** (adding at a better price on a new trigger in your direction) is fine when the stop on the whole position moves so total risk stays at or under the original 1R.
- Scaling out (half at the first target, stop to breakeven, trail the rest) trades some upside for a smoother equity curve and an easier hold. It is a choice, not a law; say which you use in the plan.
