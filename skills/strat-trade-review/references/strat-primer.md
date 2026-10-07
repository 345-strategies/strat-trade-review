# TheStrat primer for trade reviews

Condensed from TheStrat Suite v3.1.x docs (`docs/concepts/*.md`) and `grammar/SPEC.md` in github.com/natebking/thestrat-suite. When this file and the Suite disagree, the Suite wins.

## Bar types

Every candle is classified by what it did to the previous candle's range.

| Type | Name | Definition vs prior candle |
|---|---|---|
| 1 | Inside | broke neither side (high <= prior high and low >= prior low) |
| 2u / 2d | Directional | broke exactly one side: 2u the prior high, 2d the prior low |
| 3 | Outside | broke both sides |

- **Equal is not a break.** A high exactly at the prior high has not crossed it.
- **Gaps get no type.** Classification is the range test, never the open.
- **A 2u can be red.** The u/d on a 2 names the broken side. On 1s and 3s the u/d is close vs open (`1u`, `3d`). A close exactly at the open counts as not above.

## Failing 2s

A 2 that broke one side and then closed back inside the prior range (Suite default "Reclaim" method).

- `F2u`: failed upside break, bearish.
- `F2d`: failed downside break, bullish.

In combos, `F2d-2u` means the prior bar was a failed 2d and the current bar is breaking up: a 2-2 reversal with the F2 filter satisfied, one of the stronger reversal shapes.

## Combos and families

Read oldest to newest. The last token is the forming bar. `*` means potential (trigger not yet crossed).

| Family | Shape | Read |
|---|---|---|
| Inside Reversal | `2d-1-2u` | coil resolves against the prior move |
| 2-2 Reversal | `2d-2u` | direct reversal |
| Inside Continuation | `2u-1-2u` | pause, then the move resumes |
| 2-2 Continuation | `2u-2u` | sustained push; noisy unfiltered |
| 3-2 Expansion | `3-2u` | outside bar's indecision resolves |
| Failing 2 | `F2u` / `F2d` | the breakout itself fails |

## Trigger, target, stop

- **Trigger:** C1's high (bull) or low (bear). A signal is in force while price holds beyond it.
- **Magnitude:** C2's extreme on the break side, when it lies beyond the trigger. Continuations have spent magnitude by definition.
- **Exhaustion:** nearest untested swing beyond magnitude (the Suite scans about 48 bars; the review script uses reference levels instead).
- **Stop:** C1 mode = C1's opposite side (wider, locked at trigger). CC mode = the breakout bar's own opposite extreme (tighter). Failing 2s always use CC.
- **Take Action Window:** between trigger and target. Entering after price has left it leaves little room.

## Full Timeframe Continuity (FTFC)

One question asked on every monitored timeframe: is the forming candle above its open?

- All above: **FTFC Up**. All at or below: **FTFC Down**. Anything else: **Conflict** (the normal state).
- Built from the sign channel only. Do not infer it from 2u/2d tokens.
- The Suite's FTFC filter is a veto: it hides a bullish setup only under full FTFC Down. A bullish entry under FTFC Down is the lowest-probability case.

## Colors (Suite v3.1.1 defaults)

| Token | Color |
|---|---|
| 2u | `#4caf50` green |
| 2d | `#f23645` red |
| 1u | `#ffeb3b` yellow |
| 1d | `#ff9800` orange |
| 3u | `#089981` teal |
| 3d | `#e91e63` pink |
| F2d | `#81c784` light green |
| F2u | `#f77c80` light red |

Green and red are bull and bear. They never mean good or bad.

## Timeframe alignment

Intraday bars are clock-aligned from the session open, as TradingView builds them: equities from 09:30 ET (60m bars at 9:30, 10:30, ...), CME futures from 18:00 ET. The day bar is the session.
