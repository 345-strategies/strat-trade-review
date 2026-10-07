# Using it in ChatGPT

Two ways, depending on your plan.

## A. Skills (if your ChatGPT shows a Skills option)

Upload `dist/strat-trade-review.zip` and `dist/trading-risk-and-mindset.zip`. They are the same `SKILL.md` folders Claude uses.

## B. Custom GPT (works on any plan that can create GPTs)

1. Explore GPTs > Create > Configure.
2. **Name:** TheStrat Trade Review.
3. **Instructions:** paste the contents of [`instructions.md`](instructions.md).
4. **Knowledge:** upload these files from `skills/strat-trade-review/`:
   - `scripts/strat_review.py`
   - `scripts/import_fills.py`
   - `scripts/share_post.py`
   - `references/strat-primer.md`
   - `references/connect-and-import.md`
   - `references/data-sources.md`

   And from `skills/trading-risk-and-mindset/`: `scripts/risk_calc.py`, `references/risk.md`, `references/mindset.md`, `references/strat-fit.md`.
5. **Capabilities:** turn on Code Interpreter & Data Analysis.
6. Save. Share by link if you want others to use it.

### The one limit to know

Code Interpreter has no internet access, so the free Yahoo download (`--fetch yfinance`) does not work inside ChatGPT. Users attach bars as files instead: a TradingView "Export chart data" CSV, or a download from their broker (Public, Tradier and Alpaca include option contract bars free with an account). Fills work the same as in Claude: the broker's export dropped in unedited, or a paste or screenshot.

To get live connection (no files), add a broker or data MCP server as a connector where your ChatGPT plan allows custom connectors, or give the GPT an Action against a market data API with your own key. Both are optional.
