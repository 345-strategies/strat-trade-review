---
name: strat-review
description: Slash command for the TheStrat trade review. Type /strat-review SYMBOL [DATE], for example /strat-review SPY today, then attach the broker export.
argument-hint: "SYMBOL [DATE] [rules: ...]   e.g. SPY today"
disable-model-invocation: true
---

Run a TheStrat trade review for: $ARGUMENTS

Load the `strat-trade-review` skill and follow its SKILL.md. Read the arguments above with its "Command form" rules (symbol required, date defaults to today, anything after `rules:` is the trader's own rules, anything else is context or a script option).

If no arguments were given, ask for the symbol and date in one line. Otherwise ask only for what is still missing, usually the fills, plus the skill's one optional question about their rules, and go.
