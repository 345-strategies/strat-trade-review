---
name: strat-review
description: Slash command for the TheStrat trade review. Type /strat-review SYMBOL [DATE] [LOSS LIMIT], for example /strat-review SPY today 150, then attach the broker export.
argument-hint: "SYMBOL [DATE] [LOSS LIMIT]   e.g. SPY today 150"
disable-model-invocation: true
---

Run a TheStrat trade review for: $ARGUMENTS

Load the `strat-trade-review` skill and follow its SKILL.md. Read the arguments above with its "Command form" rules (symbol required, date defaults to today, a dollar amount or bare number is the daily loss limit, anything else is context or a script option).

If no arguments were given, ask for the symbol and date in one line. Otherwise ask only for what is still missing, usually the fills, and go.
