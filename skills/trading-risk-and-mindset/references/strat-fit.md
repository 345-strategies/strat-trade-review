# How this fits TheStrat

TheStrat is a complete method for **where**: price action and bar types, triggers, stops and targets, with continuity across timeframes. Nothing here replaces or adds to that. This file maps each risk or mindset principle onto the Strat's own pieces so the advice never conflicts with it.

| Principle | TheStrat piece it uses | How |
|---|---|---|
| Define risk before entry | **The trigger and C1** | 1R = distance from the trigger to the far side of C1 (the bar before the trigger bar). The stop is structural; size adjusts to it, never the reverse. |
| Size to the stop | **C1 range** | A wide C1 (a 3 bar, a big 2) means smaller size for the same 1R. If even one unit is more than 1R, skip it or use a smaller instrument. |
| Have a target and a reward-to-risk floor | **Magnitude** (the C2 extreme) and reference levels | First target = the nearest magnitude or level at least 1R away. If the nearest is less than 1R, the trade does not pay for its risk; pass. |
| Trade with the odds | **Full Timeframe Continuity** | FTFC in your direction is the probability filter. The one entry against continuity is an exhaustion reversal; anything else against it is a pass. |
| Don't chase | **Triggers are levels** | The entry is the break of the prior bar's high or low. Price far past the trigger means the risk to C1 is now larger than planned; wait for the next one. |
| No averaging down | **A new trigger** | Adding is fine only on a new trigger in your direction (a pyramid), never because price is cheaper. |
| Manage the winner | **Completed bars of a higher timeframe** | Trail a runner under each completed bar of the trail timeframe (60m by default in `strat-trade-review`). It is the Strat's own structure doing the trailing. |
| Know when timeframes couple | **The open, and Mondays** | "Let them open" is a judgment, not a rule: some setups are taken right off the bell. It matters most when timeframes are coupled, as on a Monday open when the week and the day are the same candle. Waiting is only a rule if the trader makes it theirs (`--caution-until`). |
| Accept losses | **Failed 2s and broken triggers** | A trigger that fails (an F2) is information the setup is wrong. Exiting at C1 is following the method, not losing to it. |
| Journal with structure | **Combo names** | Log every trade by its combo and timeframe (`30m F2d-2u`, `15m 2-1-2`), so `risk_calc.py stats` can be run per setup and you learn which ones pay you. |

What to avoid saying:

- Don't introduce indicators (RSI, moving averages, MACD) as filters or confirmations. TheStrat traders use price action and continuity.
- Don't offer opinions on direction. The bars and continuity decide that.
- Don't suggest wider stops "to give it room". The stop is where the setup is wrong, at C1.
- Don't use green and red to mean good and bad. In TheStrat (and the Suite colors) they mean bull and bear.
