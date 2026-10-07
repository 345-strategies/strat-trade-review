# Mindset and behavior

Principles first, then the failure patterns, each with how it shows up in fills and one concrete fix.

## Principles

1. **Think in probabilities.** Any single trade can lose, even a perfect setup; the edge only shows up across many trades. So a loss is not evidence you were wrong, and a win is not evidence you were right. (Mark Douglas, *Trading in the Zone*.)
2. **Judge the decision, not the result.** Grade every trade on two separate axes: was it a planned trade executed as planned (process), and did it make money (outcome)? A good process that lost is fine. A bad process that won is the dangerous one, because it teaches the bad habit. Annie Duke calls the mistake of judging decisions by outcomes "resulting" (*Thinking in Bets*).
3. **Decide before, execute during.** Entry trigger, stop, size, first target and runner rule are set before the order goes in. During the trade the job is execution, not analysis. Decisions made under live P/L are made by the part of you that feels losses about twice as strongly as gains (Kahneman and Tversky's loss aversion).
4. **Losses are a cost of doing business.** A -1R loss on a planned trade is the expense that buys access to the +2R and +3R trades. Treat it like rent, not like a verdict.
5. **Consistency beats brilliance.** The same setup, the same size, the same rules, logged every time, is what makes your results measurable and therefore improvable.
6. **Study what works, not only what fails.** Review your best trades as closely as your worst and do more of what they have in common. (Brett Steenbarger's solution-focused approach, *The Daily Trading Coach*.)
7. **Emotions are information, not instructions.** Notice and name them (bored, afraid, greedy, rushed); that awareness is the signal to slow down and check the plan, not to act on the feeling. (Denise Shull, *Market Mind Games*; Steenbarger.)

## Failure patterns

| Pattern | How it shows up in the fills | The fix (one rule) |
|---|---|---|
| **Averaging down** | Adds at worse prices with no new trigger; `AVERAGED_DOWN` flag; losses past -1R | "I only add on a new trigger in my direction, with the stop moved so total risk stays at 1R." |
| **Moving or ignoring the stop** | Losses bigger than -1R; holding through the C1 level | Put the stop order in with the entry. If it must be mental, set an alert at the level and act on the first touch. |
| **Cutting winners early** (the disposition effect: selling winners too soon and holding losers too long; Shefrin and Statman) | Many small wins, average win smaller than average loss; exits well before the target with no opposing trigger | Scale-out plan decided at entry: half at T1, stop to breakeven, trail the rest under each completed bar of your trail timeframe. |
| **Revenge trading / tilt** | Faster, larger trades right after a loss; R gets worse as the day goes on | Daily loss limit, plus a mandatory 15-minute break after two losses in a row. |
| **Overtrading** | Many trades, small or negative expectancy, commissions eating the edge; entries with no named trigger | Maximum trades per day (for example 3). Each entry must name its combo and timeframe before the order. |
| **FOMO and chasing** | Entries far past the trigger, after the move; `EARLY_SESSION` entries on the open's first bars | "If I missed the trigger by more than 0.5R, I wait for the next one." The open is the noisiest time; `--caution-until` exists for this. |
| **Fighting continuity** | `AGAINST_CONTINUITY` / `AGAINST_FTFC` flags | No entries against full timeframe continuity; against partial continuity only at half size. |
| **Size creep after wins** | Position size grows after a green streak, then one loss erases the streak | Size is set by the risk % on the current account, never by mood. Recompute only weekly. |
| **Freezing / hesitation** | Valid triggers skipped after a loss; late entries | Smaller size for the next three trades so the loss of each feels survivable; keep taking the triggers. |
| **Hope / no exit plan** | Options held to near zero; "it'll come back" | Every trade has a stop or a premium you accept losing at entry. Time stop for options: out if the move hasn't started within N bars. |

When you name a pattern, show the evidence from their trades ("3 of your 5 adds were below your first fill, and those trades averaged -2.1R"), then give the one rule.

## Routines

- **Before the session (5 minutes):** mark the levels (prior day high/low, prior close, the opening range once set), note continuity on the 60m and Day, write the day's loss limit and max trades on a sticky note.
- **Before each entry (the checklist in `assets/trading-plan.md`):** trigger named, stop at C1, size from the calculator, target, runner rule, continuity check, "how do I feel" in one word.
- **After each trade (2 minutes):** log the R, the setup, whether the plan was followed (yes or no), and one word for how it felt.
- **After the session:** one sentence: what I did well, what I'll do differently. Weekly: run `risk_calc.py stats` on the week's R list and look at plan-followed versus not.

## If-then plans

Rules stick better phrased as "if [situation], then [action]" (implementation intentions; Peter Gollwitzer's research). Help the trader write two or three:

- If I take my second loss of the day, then I stand up and leave the screen for 15 minutes.
- If price is past my trigger by more than half my risk, then I don't chase; I wait for the next trigger.
- If I hit my daily loss limit, then I close the platform and write my journal entry, nothing else.
- If I want to add to a losing position, then I ask whether there is a new trigger; if not, no add.
